import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import authenticate, create_token, decode_token
from .collectors.docker import DockerCollector
from .collectors.system import get_overview
from .config import get_settings
from .db import add_audit, get_setting, init_db, list_audit, list_security_events, set_setting
from .monitor import Monitor

settings = get_settings()
app = FastAPI(title="VPS Admin", version="0.1.0")
security = HTTPBearer()
docker_collector = DockerCollector()
monitor_task: asyncio.Task | None = None

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )


class LoginPayload(BaseModel):
    username: str
    password: str


class SettingsPayload(BaseModel):
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    cpu_alert_percent: int | None = None
    ram_alert_percent: int | None = None
    disk_alert_percent: int | None = None


def current_user(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]) -> dict:
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return {"username": payload["sub"], "role": payload.get("role", "viewer")}


def require_admin(user: Annotated[dict, Depends(current_user)]) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


@app.on_event("startup")
async def startup() -> None:
    global monitor_task
    init_db()
    monitor_task = asyncio.create_task(Monitor().run_forever())


@app.on_event("shutdown")
async def shutdown() -> None:
    if monitor_task:
        monitor_task.cancel()


@app.post("/api/auth/login")
async def login(payload: LoginPayload, request: Request) -> dict:
    user = authenticate(payload.username, payload.password)
    if user is None:
        add_audit(payload.username, "login_failed", ip=request.client.host if request.client else None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    add_audit(user["username"], "login_success", ip=request.client.host if request.client else None)
    return {"access_token": create_token(user), "token_type": "bearer", "user": user}


@app.get("/api/overview")
async def overview(_: Annotated[dict, Depends(current_user)]) -> dict:
    return get_overview()


@app.get("/api/docker/containers")
async def containers(_: Annotated[dict, Depends(current_user)]) -> list[dict]:
    return docker_collector.list_containers()


@app.get("/api/docker/containers/{container_id}/logs", response_class=PlainTextResponse)
async def container_logs(container_id: str, _: Annotated[dict, Depends(current_user)], tail: int = 200) -> str:
    return docker_collector.logs(container_id, min(max(tail, 1), 2000))


@app.post("/api/docker/containers/{container_id}/{action}")
async def container_action(
    container_id: str,
    action: str,
    user: Annotated[dict, Depends(require_admin)],
    request: Request,
) -> dict:
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(status_code=400, detail="Unsupported action")
    docker_collector.action(container_id, action)
    add_audit(user["username"], f"container_{action}", container_id, request.client.host if request.client else None)
    return {"ok": True}


@app.get("/api/security/events")
async def security_events(_: Annotated[dict, Depends(current_user)], limit: int = 200) -> list[dict]:
    return list_security_events(min(max(limit, 1), 1000))


@app.get("/api/audit")
async def audit(_: Annotated[dict, Depends(require_admin)], limit: int = 100) -> list[dict]:
    return list_audit(min(max(limit, 1), 500))


@app.get("/api/settings")
async def read_settings(_: Annotated[dict, Depends(require_admin)]) -> dict:
    return {
        "telegram_bot_token": get_setting("telegram_bot_token", settings.telegram_bot_token),
        "telegram_chat_id": get_setting("telegram_chat_id", settings.telegram_chat_id),
        "cpu_alert_percent": get_setting("cpu_alert_percent", settings.cpu_alert_percent),
        "ram_alert_percent": get_setting("ram_alert_percent", settings.ram_alert_percent),
        "disk_alert_percent": get_setting("disk_alert_percent", settings.disk_alert_percent),
    }


@app.put("/api/settings")
async def update_settings(payload: SettingsPayload, user: Annotated[dict, Depends(require_admin)], request: Request) -> dict:
    for key, value in payload.model_dump(exclude_none=True).items():
        set_setting(key, value)
    add_audit(user["username"], "settings_update", ip=request.client.host if request.client else None)
    return {"ok": True}


frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dir / "assets"), name="assets")


@app.get("/{path:path}")
async def frontend(path: str) -> FileResponse:
    index = frontend_dir / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index)

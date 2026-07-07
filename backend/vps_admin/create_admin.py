import argparse
import sys

from .auth import create_user
from .db import init_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Create VPS Admin user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", default="admin", choices=["admin", "viewer"])
    args = parser.parse_args()

    init_db()
    try:
        create_user(args.username, args.password, args.role)
    except Exception as exc:
        print(f"Failed to create user: {exc}", file=sys.stderr)
        return 1
    print(f"Created user {args.username!r} with role {args.role!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

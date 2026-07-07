import os
import platform
import socket
import time

import psutil


def get_overview() -> dict:
    boot_time = psutil.boot_time()
    disk = psutil.disk_usage("/")
    memory = psutil.virtual_memory()
    net = psutil.net_io_counters()
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "uptime_seconds": int(time.time() - boot_time),
        "load_average": os.getloadavg() if hasattr(os, "getloadavg") else [0, 0, 0],
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory": {
            "total": memory.total,
            "used": memory.used,
            "percent": memory.percent,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
        },
    }

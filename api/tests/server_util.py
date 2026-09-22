"""在后台线程中运行真实 uvicorn 服务的工具，供并发/重启测试使用。"""
from __future__ import annotations

import socket
import threading
import time

import httpx
import uvicorn

from app.main import create_app


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RunningServer:
    """管理一个绑定到指定数据库文件的 uvicorn 进程内实例；stop/start 模拟进程重启。"""

    def __init__(self, db_path, dev_mode: bool = True):
        self.db_path = str(db_path)
        self.dev_mode = dev_mode
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> "RunningServer":
        app = create_app(db_path=self.db_path, dev_mode=self.dev_mode)
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{self.base_url}/api/health", timeout=1).status_code == 200:
                    return self
            except Exception:
                pass
            time.sleep(0.05)
        raise RuntimeError("uvicorn server did not become healthy in time")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._server = None
        self._thread = None


def allocate(base_url: str, scene_id: str, client_op_id: str, notes: str = "", **extra) -> httpx.Response:
    payload = {"scene_id": scene_id, "client_op_id": client_op_id, "notes": notes, **extra}
    return httpx.post(f"{base_url}/api/shot-numbers", json=payload, timeout=30)

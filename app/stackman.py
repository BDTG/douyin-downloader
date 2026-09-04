"""Quản lý stack Python (api/gallery/web) cho app standalone.

Không qua module/framework: spawn trực tiếp .venv python, health-check,
dừng sạch khi thoát app. Port bận sẵn (orphan cũ) thì dùng luôn.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket()
    s.settimeout(0.25)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


@dataclass
class Service:
    name: str
    port: int
    workdir: str
    cmd: List[str]
    env: Dict[str, str] = field(default_factory=dict)


class StackManager:
    def __init__(self, stack_dir: str, python_exe: str = ""):
        self.stack_dir = stack_dir
        self.python = python_exe or str(Path(stack_dir) / ".venv" / "Scripts" / "python.exe")
        self.procs: Dict[str, subprocess.Popen] = {}
        self.logs_dir = str(Path(stack_dir) / "logs")

    def services(self) -> List[Service]:
        dl = str(Path(self.stack_dir) / "downloads")
        aliases = str(Path(self.stack_dir) / "aliases.json")
        subjects = str(Path(self.stack_dir) / "subjects.json")
        cfg = str(Path(self.stack_dir) / "api" / "config.native.yml")
        base_env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
                    "DOUYIN_PATH": dl,
                    "DL_DIR": dl, "ALIAS_PATH": aliases, "SUBJECTS_PATH": subjects}
        return [
            Service("api", 8000, str(Path(self.stack_dir) / "downloader"),
                    [self.python, "run.py", "-c", cfg, "--serve",
                     "--serve-host", "127.0.0.1", "--serve-port", "8000"], base_env),
            Service("gallery", 8001, str(Path(self.stack_dir) / "gallery"),
                    [self.python, "-m", "uvicorn", "app:app",
                     "--host", "127.0.0.1", "--port", "8001"], base_env),
            Service("web", 8080, str(Path(self.stack_dir) / "web"),
                    [self.python, "server.py"], base_env),
        ]

    def start(self, timeout_s: float = 60.0) -> Dict[str, str]:
        """Bật cả stack. Port đã nghe thì dùng luôn (không bật trùng)."""
        out = {}
        logs = Path(self.logs_dir)
        logs.mkdir(parents=True, exist_ok=True)
        cfg = Path(self.stack_dir) / "api" / "config.native.yml"
        if not cfg.is_file():
            raise RuntimeError(
                "thieu api/config.native.yml — copy api/config.native.example.yml "
                "thành config.native.yml rồi điền cookie (xem README).")
        for s in self.services():
            if port_open(s.port):
                out[s.name] = "dang chay san"
                continue
            env = dict(os.environ)
            env.update(s.env)
            logf = open(logs / f"{s.name}.log", "a", encoding="utf-8", errors="replace")
            try:
                p = subprocess.Popen(s.cmd, cwd=s.workdir, env=env,
                                     stdout=logf, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            finally:
                logf.close()
            self.procs[s.name] = p
            out[s.name] = f"pid {p.pid}"
        end = time.time() + timeout_s
        while time.time() < end:
            if all(port_open(s.port) for s in self.services()):
                break
            time.sleep(0.5)
        return out

    def stop(self):
        for name, p in list(self.procs.items()):
            try:
                # chỉ giết process mình bật (không giết orphan của ai khác)
                p.terminate()
                try:
                    p.wait(timeout=10)
                except Exception:
                    p.kill()
            except Exception:
                pass
            self.procs.pop(name, None)

    def status(self) -> Dict[str, bool]:
        return {s.name: port_open(s.port) for s in self.services()}

    def api_ok(self) -> bool:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health",
                                        timeout=5) as r:
                return r.status == 200
        except Exception:
            return False

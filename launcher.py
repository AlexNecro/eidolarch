from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

HOST = os.environ.get("PHOTOMIND_HOST", "0.0.0.0")
PORT = int(os.environ.get("PHOTOMIND_PORT", "8765"))
LOCAL_URL = f"http://127.0.0.1:{PORT}"
APP_VERSION = "2.3.5"
DEBUG_STARTUP = os.environ.get("EIDOLARCH_DEBUG_STARTUP") == "1"
_START = time.perf_counter()

def trace(message: str):
    if DEBUG_STARTUP:
        print(f"[startup {time.perf_counter()-_START:8.3f}s] launcher: {message}", flush=True)



def wait_ready(server, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server.poll() is not None:
            trace(f"server exited before health check, code={server.returncode}")
            return False
        try:
            with urllib.request.urlopen(f"{LOCAL_URL}/api/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def find_browser() -> str | None:
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    for exe in ("msedge", "chrome"):
        p = shutil.which(exe)
        if p:
            return p
    return None


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    trace("starting uvicorn child")
    server_args = [sys.executable]
    if DEBUG_STARTUP:
        server_args += ["-X", "importtime"]
    server_args += ["-m", "uvicorn", "photomind.app:app", "--host", HOST, "--port", str(PORT)]
    server = subprocess.Popen(
        server_args,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=env,
    )
    try:
        trace("waiting for /api/health")
        if not wait_ready(server):
            print("Eidolarch server did not start correctly.")
            return 20
        trace("health check OK")

        browser = find_browser()
        if browser:
            profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".browser-profile")
            launch_url = f"{LOCAL_URL}/?v={APP_VERSION}&launch={time.time_ns()}"
            args = [browser, f"--app={launch_url}", f"--user-data-dir={profile_dir}", "--no-first-run"]
            subprocess.Popen(args)
            trace("application window launched")
        else:
            import webbrowser
            webbrowser.open(LOCAL_URL)

        print(f"Eidolarch: {LOCAL_URL}")
        print("Close this console window to stop the server.")
        print("LAN access uses this PC's IP on port", PORT)
        return server.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    raise SystemExit(main())

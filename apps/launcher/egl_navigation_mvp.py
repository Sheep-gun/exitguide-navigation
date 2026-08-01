from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

if sys.platform == "win32":
    import ctypes

import uvicorn

from app.desktop import app


HOST = "127.0.0.1"
DEFAULT_PORT = 8010


def find_available_port(preferred_port: int) -> int:
    for port in range(preferred_port, preferred_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            try:
                candidate.bind((HOST, port))
            except OSError:
                continue
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind((HOST, 0))
        return int(candidate.getsockname()[1])


def build_server(port: int) -> uvicorn.Server:
    ensure_standard_streams()
    config = uvicorn.Config(
        app=app,
        host=HOST,
        port=port,
        log_level="warning",
        log_config=None,
        access_log=False,
    )
    return uvicorn.Server(config)


def ensure_standard_streams() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", buffering=1)


def show_native_message(title: str, message: str, error: bool = False) -> None:
    if sys.platform == "win32":
        icon = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(None, message, title, icon)
        return
    print(f"{title}: {message}")


def run_desktop(preferred_port: int) -> None:
    port = find_available_port(preferred_port)
    url = f"http://{HOST}:{port}/navigation.html"
    server = build_server(port)
    server_thread = threading.Thread(target=server.run, name="exitguide-server", daemon=True)
    server_thread.start()

    for _ in range(200):
        if server.started:
            webbrowser.open_new_tab(url)
            show_native_message(
                "ExitGuideLab Navigation MVP",
                "EGL Navigation MVP가 실행 중입니다.\n\n"
                f"브라우저 주소: {url}\n\n"
                "확인을 누르면 MVP 서버가 종료됩니다.",
            )
            server.should_exit = True
            server_thread.join(timeout=3)
            return
        if not server_thread.is_alive():
            break
        time.sleep(0.05)

    server.should_exit = True
    show_native_message(
        "ExitGuideLab Navigation MVP",
        "MVP 서버를 시작하지 못했습니다.",
        error=True,
    )


def open_browser_when_ready(server: uvicorn.Server, url: str) -> None:
    for _ in range(200):
        if server.started:
            webbrowser.open_new_tab(url)
            return
        if server.should_exit:
            return
        time.sleep(0.05)


def run_headless(port: int, open_browser: bool) -> None:
    server = build_server(port)
    if open_browser:
        url = f"http://{HOST}:{port}/navigation.html"
        threading.Thread(
            target=open_browser_when_ready,
            args=(server, url),
            name="exitguide-browser",
            daemon=True,
        ).start()
    server.run()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ExitGuideLab Navigation MVP desktop launcher")
    parser.add_argument("--headless", action="store_true", help="Run the bundled web server without the launcher window.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the default browser in headless mode.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Preferred local HTTP port.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.headless:
        run_headless(args.port, open_browser=not args.no_browser)
        return
    run_desktop(args.port)


if __name__ == "__main__":
    main()

"""Start the dashboard and open it in the browser."""

import argparse
import socket
import threading
import webbrowser

import uvicorn

HOST = "127.0.0.1"
FIRST_PORT = 8000
PORTS_TO_TRY = 20


def free_port() -> int:
    """The first unused port from 8000 up, so another program on 8000 does not stop the tool."""
    for port in range(FIRST_PORT, FIRST_PORT + PORTS_TO_TRY):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex((HOST, port)) != 0:
                return port
    raise SystemExit(f"Ports {FIRST_PORT}-{FIRST_PORT + PORTS_TO_TRY - 1} are all in use. Close other programs and try again.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m backend", description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="start without opening the browser")
    args = parser.parse_args()

    port = free_port()
    url = f"http://{HOST}:{port}"
    print(f"\n  Naukri Job Automation is running at {url}\n  Keep this window open. Close it to stop.\n", flush=True)
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run("backend.main:app", host=HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Pegasus Galaxy Standalone BattleCalc Launcher v0.6 (Cross-Platform)
Launches or connects to the dedicated Combat Simulator / Matrix Mode in your default browser.
Supports multiple independent calculation windows and tab sessions.
Runs on macOS, Linux, and Windows.
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_PORT = 7890
DEFAULT_HOST = "127.0.0.1"


def is_server_running(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """Check if the Pegasus Galaxy MCP GUI server is actively listening on the target port."""
    try:
        url = f"http://{host}:{port}/api/tools"
        req = urllib.request.Request(url, headers={"User-Agent": "PegCalcLauncher/0.5"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Pegasus Galaxy Standalone BattleCalc Launcher v0.6 (macOS / Linux / Windows)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python peg_calc.py                      # Open standalone battle calculator
  python peg_calc.py 12:1:1               # Open battle calculator pre-targeting 12:1:1
  python peg_calc.py --coords 4:2:8       # Open battle calculator pre-targeting 4:2:8
  python peg_calc.py --port 8080          # Connect/launch on custom port 8080
        """
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Optional target defender coordinates (e.g. 12:1:1)",
    )
    parser.add_argument(
        "--coords",
        type=str,
        default=None,
        help="Optional target defender coordinates (e.g. 12:1:1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port number for the GUI server (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=DEFAULT_HOST,
        help=f"Host address (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the system web browser automatically",
    )
    args = parser.parse_args()

    target_coords = args.coords or args.target
    calc_url = f"http://{args.host}:{args.port}/calc"
    if target_coords:
        clean_coords = target_coords.strip().replace(" ", ":").replace(",", ":")
        calc_url += f"#coords={clean_coords}"

    print("=" * 64)
    print("⚔️  PEGASUS GALAXY STANDALONE BATTLECALC (v0.6)")
    print("=" * 64)

    if is_server_running(args.host, args.port):
        print(f"✅ Pegasus Galaxy MCP Hub is already running on port {args.port}.")
        print(f"🚀 Opening Standalone Battle Matrix at: {calc_url}")
        print("💡 Tip: You can open multiple windows or use '↗️ Pop Out Window' anytime.")
        print("=" * 64)
        if not args.no_browser:
            webbrowser.open(calc_url)
        return

    # Server is not running, launch peg_gui.py in background
    print(f"🌌 Server is not currently active on port {args.port}.")
    print("⚡ Starting background Pegasus Galaxy GUI server process...")

    gui_script = Path(__file__).parent / "peg_gui.py"
    if not gui_script.exists():
        print(f"❌ Error: Cannot find {gui_script}")
        sys.exit(1)

    cmd = [
        sys.executable,
        str(gui_script),
        "--port",
        str(args.port),
        "--host",
        args.host,
        "--no-browser",
    ]

    # Spawn process safely in background across platforms
    if sys.platform == "win32":
        # Windows: CREATE_NEW_PROCESS_GROUP
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).parent),
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        # macOS / Linux
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    # Poll until server is responding
    print(f"⏳ Waiting for GUI server to initialize (PID: {proc.pid})...")
    server_ready = False
    for attempt in range(25):
        time.sleep(0.3)
        if is_server_running(args.host, args.port):
            server_ready = True
            break

    if server_ready:
        print(f"🚀 Server is live! Opening Battle Matrix at: {calc_url}")
        print("💡 Tip: You can open multiple windows or tabs without creating extra servers.")
        print("=" * 64)
        if not args.no_browser:
            webbrowser.open(calc_url)
    else:
        print("⚠️ Server launched but took longer than expected to report ready.")
        print(f"👉 Please open: {calc_url} in your browser once ready.")
        print("=" * 64)


if __name__ == "__main__":
    main()

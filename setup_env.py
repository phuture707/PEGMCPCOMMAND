#!/usr/bin/env python3
"""
Pegasus Galaxy MCP Suite — Setup & Environment Configuration
Prompts for your Pegasus Galaxy API key / Personal Access Token (PAT),
creates the .env file, verifies the connection, and guides you to run peg_gui.py.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ENV_FILE = Path(".env")
MCP_URL = "https://mcp.pegasus-galaxy.net"


# ANSI color formatting with fallback for non-color terminals
def supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    return True


USE_COLOR = supports_color()


def color(text: str, code: str) -> str:
    if not USE_COLOR:
        return text
    codes = {
        "cyan": "\033[96m",
        "blue": "\033[94m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "reset": "\033[0m",
    }
    return f"{codes.get(code, '')}{text}{codes['reset']}"


def print_banner():
    banner = f"""
{color("==================================================================", "cyan")}
{color("  Pegasus Galaxy MCP Suite v0.6 - Easy Setup & Token Configuration", "bold")}
{color("==================================================================", "cyan")}
"""
    print(banner)


def mask_token(token: str) -> str:
    """Mask a token for secure display (e.g., pg_pat_1234...9abc)."""
    if not token:
        return "(empty)"
    token = token.strip()
    if len(token) <= 12:
        return "*" * len(token)
    return f"{token[:8]}...{token[-4:]}"


def get_existing_token() -> Optional[str]:
    """Read any existing token in .env or environment variable."""
    for var in ("PEGASUS_PAT", "PEGASUS_API_KEY", "PEGASUS_TOKEN"):
        val = os.environ.get(var)
        if val:
            return val.strip().strip("\"'")

    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or not line:
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() in ("PEGASUS_PAT", "PEGASUS_API_KEY", "PEGASUS_TOKEN", "API_KEY"):
                            return v.strip().strip("\"'")
                    elif line.startswith("pg_pat_"):
                        return line.strip("\"'")
        except Exception:
            pass
    return None


def verify_token(token: str, timeout: float = 8.0) -> Tuple[bool, str]:
    """
    Test the token against the Pegasus Galaxy MCP server using standard library
    or PegasusMCPClient if available.
    """
    import urllib.error
    import urllib.request

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 1,
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Pegasus-MCP-Setup/1.0",
    }

    req = urllib.request.Request(MCP_URL, data=data_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body)
            if "error" in parsed:
                err = parsed["error"]
                return False, f"Server returned MCP error: {err.get('message', err)}"
            tools = parsed.get("result", {}).get("tools", [])
            tool_count = len(tools)
            return True, f"Connection verified! {tool_count} MCP tools available."
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "Authentication failed (401 Unauthorized). Please check your token."
        return False, f"HTTP Error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Network connection failed: {e.reason}"
    except Exception as e:
        return False, f"Verification failed: {e}"


def check_dependencies() -> bool:
    """Check if required python packages are installed."""
    missing = []
    try:
        import httpx  # noqa: F401
    except ImportError:
        missing.append("httpx")

    if missing:
        print(color(f"\n[Notice] Missing required Python package: {', '.join(missing)}", "yellow"))
        print(f"Install dependencies via: {color('pip install -r requirements.txt', 'bold')}\n")
        return False
    return True


def prompt_for_token() -> str:
    """Interactively prompt user for token."""
    print("To connect to your Pegasus Galaxy empire, you need your Personal Access Token (PAT).")
    print(f"1. Open {color('https://pegasus-galaxy.net', 'bold')} in your browser and log in.")
    print("2. Navigate to your Player Profile / Settings -> MCP Access Token.")
    print("3. Copy your Personal Access Token (format: pg_pat_...)\n")

    while True:
        try:
            raw = input(color("Enter your Pegasus Galaxy API key / PAT: ", "bold")).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled.")
            sys.exit(0)

        # Clean quotes if user pasted with surrounding quotes
        cleaned = raw.strip("\"'")
        if not cleaned:
            print(color("Token cannot be empty. Please paste your token or press Ctrl+C to exit.", "yellow"))
            continue

        if not cleaned.startswith("pg_pat_"):
            print(color(f"\n[Warning] Pegasus tokens usually start with 'pg_pat_'.", "yellow"))
            print(f"You entered: '{cleaned[:10]}...'")
            try:
                confirm = input("Use this token anyway? [y/N]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nSetup cancelled.")
                sys.exit(0)
            if confirm not in ("y", "yes"):
                continue

        return cleaned


def save_env_file(token: str):
    """Write the token into the .env file."""
    content = f"""# Pegasus Galaxy MCP Configuration
# Generated by setup_env.py
PEGASUS_PAT={token}
"""
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(content)


def print_next_steps():
    """Display final instructions to the user."""
    box = f"""
{color("+------------------------------------------------------------------+", "green")}
{color("|                        [OK] SETUP COMPLETE                       |", "green")}
{color("+------------------------------------------------------------------+", "green")}
{color("|  Your Pegasus Galaxy MCP credentials are ready.                  |", "green")}
{color("|                                                                  |", "green")}
{color("|  To start the Web Command Center & BattleCalc, run:              |", "green")}
{color("|      python peg_gui.py                                           |", "bold")}
{color("|                                                                  |", "green")}
{color("|  To run the CLI tool directly:                                   |", "green")}
{color("|      python peg_tool.py --help                                   |", "green")}
{color("|                                                                  |", "green")}
{color("|  Web GUI will open at: http://localhost:7890                     |", "cyan")}
{color("+------------------------------------------------------------------+", "green")}
"""
    print(box)


def ask_launch_gui():
    """Prompt user to launch peg_gui.py immediately."""
    print()
    try:
        choice = input(color("Would you like to launch the Web GUI now? [Y/n]: ", "bold")).strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting. You can start the GUI later.")
        return

    if choice in ("", "y", "yes"):
        gui_path = Path("peg_gui.py")
        if not gui_path.exists():
            print(color(f"Could not find {gui_path}. Please run python peg_gui.py from the project folder.", "yellow"))
            return
        print(color(f"\nLaunching {gui_path.name}...\n", "green"))
        try:
            subprocess.run([sys.executable, str(gui_path)])
        except KeyboardInterrupt:
            print("\nGUI stopped.")
    else:
        print(f"\nNo problem! When you're ready, run: {color('python peg_gui.py', 'bold')}")


def main():
    parser = argparse.ArgumentParser(
        description="Pegasus Galaxy MCP Setup & Token Configurator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--token", "-t", type=str, help="Specify your Pegasus Personal Access Token directly.")
    parser.add_argument("--no-test", action="store_true", help="Skip connection test against MCP server.")
    parser.add_argument("--launch", "-l", action="store_true", help="Automatically launch peg_gui.py after setup.")
    parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing .env without confirmation.")

    args = parser.parse_args()

    print_banner()

    # Check for existing token
    existing_token = get_existing_token()
    if existing_token and not args.token and not args.force:
        print(f"An existing token was detected in your configuration: {color(mask_token(existing_token), 'cyan')}")
        try:
            overwrite = input("Do you want to enter a new token and overwrite it? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled.")
            sys.exit(0)

        if overwrite not in ("y", "yes"):
            print(color("\nKeeping existing configuration.", "green"))
            print_next_steps()
            if args.launch:
                subprocess.run([sys.executable, "peg_gui.py"])
            else:
                ask_launch_gui()
            return

    # Obtain token
    if args.token:
        token = args.token.strip().strip("\"'")
    else:
        token = prompt_for_token()

    # Save to .env
    try:
        save_env_file(token)
        print(color(f"\n[OK] Configuration successfully saved to {ENV_FILE.resolve()}", "green"))
    except Exception as e:
        print(color(f"\n[Error] Failed to write to {ENV_FILE}: {e}", "red"))
        sys.exit(1)

    # Test connection
    if not args.no_test:
        print("\nVerifying credentials with Pegasus Galaxy MCP server...")
        success, msg = verify_token(token)
        if success:
            print(color(f"[SUCCESS] {msg}", "green"))
        else:
            print(color(f"[WARNING] {msg}", "yellow"))
            print(color("Your .env was saved, but please verify your network or token if requests fail.", "dim"))

    # Check python dependencies
    check_dependencies()

    # Next steps display
    print_next_steps()

    # Launch GUI option
    if args.launch:
        gui_path = Path("peg_gui.py")
        print(color(f"\nLaunching {gui_path.name}...\n", "green"))
        try:
            subprocess.run([sys.executable, str(gui_path)])
        except KeyboardInterrupt:
            print("\nGUI stopped.")
    elif not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
        # Non-interactive environment, skip input prompt
        pass
    else:
        ask_launch_gui()


if __name__ == "__main__":
    main()

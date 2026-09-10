"""
Pegasus Galaxy MCP Client Library
Connects to https://mcp.pegasus-galaxy.net via Streamable HTTP (JSON-RPC 2.0 / MCP 2025-03-26).
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import httpx

DEFAULT_MCP_URL = "https://mcp.pegasus-galaxy.net"


def load_token_from_env(env_path: Optional[Union[str, Path]] = None) -> Optional[str]:
    """
    Extracts the Pegasus Galaxy token from environment variables or a .env file.
    Supports:
      - PEGASUS_PAT, PEGASUS_API_KEY, PEGASUS_TOKEN, API_KEY env vars
      - Key-value lines (e.g. PEGASUS_PAT=pg_pat_...)
      - Bare token string on its own line (e.g. pg_pat_...)
    """
    for var_name in ("PEGASUS_PAT", "PEGASUS_API_KEY", "PEGASUS_TOKEN", "API_KEY"):
        val = os.environ.get(var_name)
        if val:
            return val.strip().strip("\"'")

    target_path = Path(env_path) if env_path else Path(".env")
    if not target_path.exists():
        target_path = Path(__file__).parent / ".env"

    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    _, v = line.split("=", 1)
                    return v.strip().strip("\"'")
                return line.strip("\"'")

    return None


class PegasusMCPError(Exception):
    """Base exception for Pegasus MCP operations."""
    def __init__(self, message: str, code: Optional[int] = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class PegasusMCPClient:
    """
    Synchronous client for Pegasus Galaxy MCP server.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: str = DEFAULT_MCP_URL,
        env_file: Optional[Union[str, Path]] = None,
        timeout: float = 30.0,
    ):
        self.token = token or load_token_from_env(env_file)
        if not self.token:
            raise ValueError(
                "Pegasus access token not found. Set PEGASUS_PAT or provide it in .env"
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._request_id = 0
        self._session = httpx.Client(timeout=timeout)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "Pegasus-MCP-Client/1.0",
        }

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._next_id(),
        }
        if params is not None:
            payload["params"] = params

        response = self._session.post(
            self.base_url,
            headers=self._headers(),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            err = data["error"]
            raise PegasusMCPError(
                err.get("message", "Unknown MCP error"),
                code=err.get("code"),
                data=err.get("data"),
            )

        return data.get("result")

    # -------------------------------------------------------------------------
    # Core MCP Protocol
    # -------------------------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools from the MCP server."""
        result = self._rpc("tools/list")
        return result.get("tools", []) if result else []

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """
        Call an MCP tool by name.
        If the tool returns text containing JSON, it is parsed and returned as a dict/list.
        """
        args = dict(arguments or {})
        # Parameter and tool name alias normalization for compatibility:
        if tool_name == "start_construction":
            tool_name = "build_construction"
        elif tool_name == "start_ship_production":
            tool_name = "produce_ships"

        if tool_name == "repair_pds" and "pdsId" in args and "constructionId" not in args:
            args["constructionId"] = args.pop("pdsId")
        elif tool_name == "produce_ships" and "shipId" in args and "shipDefinitionId" not in args:
            args["shipDefinitionId"] = args.pop("shipId")
        elif tool_name == "send_message":
            if "recipientPlanetId" in args and "recipientId" not in args:
                args["recipientId"] = args.pop("recipientPlanetId")
            if "message" in args and "body" not in args:
                args["body"] = args.pop("message")

        params = {
            "name": tool_name,
            "arguments": args,
        }
        result = self._rpc("tools/call", params)
        if not result or "content" not in result:
            return result

        contents = result["content"]
        is_error = result.get("isError", False)
        if isinstance(contents, list) and len(contents) > 0:
            first = contents[0]
            if first.get("type") == "text":
                text = first.get("text", "")
                try:
                    parsed = json.loads(text)
                    if is_error and isinstance(parsed, dict) and "isError" not in parsed:
                        parsed["isError"] = True
                    return parsed
                except (json.JSONDecodeError, TypeError):
                    if is_error:
                        return {"success": False, "isError": True, "error": text}
                    return text
        return result

    def list_resources(self) -> List[Dict[str, Any]]:
        """List all available MCP resources."""
        result = self._rpc("resources/list")
        return result.get("resources", []) if result else []

    def read_resource(self, uri: str) -> Any:
        """Read an MCP resource by URI."""
        result = self._rpc("resources/read", {"uri": uri})
        if not result or "contents" not in result:
            return result
        contents = result["contents"]
        if isinstance(contents, list) and len(contents) > 0:
            first = contents[0]
            text = first.get("text", "")
            if first.get("mimeType") == "application/json":
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    pass
            return text
        return result

    # -------------------------------------------------------------------------
    # Game Helper Methods
    # -------------------------------------------------------------------------

    def get_tick_info(self) -> Dict[str, Any]:
        """Get current game tick number, remaining time, and interval."""
        return self.call_tool("get_tick_info")

    def get_game_state_summary(self) -> Dict[str, Any]:
        """Comprehensive game overview: planet, queues, fleets, remaining actions."""
        return self.call_tool("get_game_state_summary")

    def get_planet_status(self) -> Dict[str, Any]:
        """Detailed planet status (resources, population, coords, ships)."""
        return self.call_tool("get_planet_status")

    def get_active_construction(self) -> Dict[str, Any]:
        """Currently active in-progress construction."""
        return self.call_tool("get_active_construction")

    def get_active_research(self) -> Dict[str, Any]:
        """Currently active in-progress research."""
        return self.call_tool("get_active_research")

    def list_construction_options(self, show_all: bool = False) -> Dict[str, Any]:
        """List constructions filtered by prerequisites and affordability."""
        return self.call_tool("list_construction_options", {"show_all": show_all})

    def list_research_options(self, show_all: bool = False) -> Dict[str, Any]:
        """List research options filtered by prerequisites and affordability."""
        return self.call_tool("list_research_options", {"show_all": show_all})

    def list_production_options(self, show_all: bool = False) -> Dict[str, Any]:
        """List ship production definitions."""
        return self.call_tool("list_production_options", {"show_all": show_all})

    def list_active_fleets(self) -> Dict[str, Any]:
        """List all traveling, attacking, or returning fleets."""
        return self.call_tool("list_active_fleets")

    def list_missions(self) -> Dict[str, Any]:
        """List missions and their completion status."""
        return self.call_tool("list_missions")

    def get_leaderboard(self, limit: int = 10) -> Dict[str, Any]:
        """Fetch current score leaderboard."""
        return self.call_tool("get_leaderboard", {"limit": limit})

    def get_player_rank(self) -> Dict[str, Any]:
        """Get player rank, score, and total player count."""
        return self.call_tool("get_player_rank")

    def get_game_rules(self, topic: Optional[str] = None) -> Any:
        """Get game rules documentation."""
        args = {"topic": topic} if topic else {}
        return self.call_tool("get_game_rules", args)

    def _get_memory_file(self) -> Path:
        return Path(__file__).parent / "bot_memory.json"

    def get_memory(self, key: str) -> Any:
        """Retrieve persisted agent memory key from local storage."""
        mem_file = self._get_memory_file()
        if mem_file.exists():
            try:
                with open(mem_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get(key)
            except Exception:
                pass
        return None

    def set_memory(self, key: str, value: str) -> Any:
        """Persist an agent memory key-value pair to local storage."""
        mem_file = self._get_memory_file()
        data = {}
        if mem_file.exists():
            try:
                with open(mem_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[key] = value
        try:
            with open(mem_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_memory_keys(self) -> List[str]:
        """List all stored local memory keys."""
        mem_file = self._get_memory_file()
        if mem_file.exists():
            try:
                with open(mem_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return list(data.keys())
            except Exception:
                pass
        return []

    def close(self):
        """Close HTTP session."""
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

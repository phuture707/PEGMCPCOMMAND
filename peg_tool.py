#!/usr/bin/env python3
"""
Pegasus Galaxy MCP Inspector & CLI Tool v0.6 (Cross-Platform)
Inspects game state, browses tools/resources, and calls MCP endpoints.
Runs on macOS, Linux, and Windows.
"""

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich import box

from peg_client import PegasusMCPClient, PegasusMCPError
import peg_combat

console = Console()


def format_num(val: Any) -> str:
    """Format numbers with comma separators."""
    if isinstance(val, (int, float)):
        return f"{val:,.0f}" if isinstance(val, int) or val.is_integer() else f"{val:,.2f}"
    return str(val)


def print_dashboard(client: PegasusMCPClient, raw_json: bool = False):
    """Fetches and displays the complete game state dashboard."""
    with console.status("[bold cyan]Querying Pegasus Galaxy MCP server...", spinner="dots"):
        summary_resp = client.get_game_state_summary()
        planet_resp = client.get_planet_status()
        tick_resp = client.get_tick_info()

    if raw_json:
        print(json.dumps({
            "tick": tick_resp,
            "summary": summary_resp,
            "planet": planet_resp,
        }, indent=2))
        return

    data = summary_resp.get("data", {}) if isinstance(summary_resp, dict) else {}
    planet = data.get("planet", {})
    if not planet and isinstance(planet_resp, dict):
        planet = planet_resp.get("data", {})

    tick_info = tick_resp.get("data", {}) if isinstance(tick_resp, dict) else {}
    current_tick = tick_info.get("tick", data.get("tick", "N/A"))
    next_tick_in = tick_info.get("nextTickIn", data.get("nextTickIn", "unknown"))

    # Title Banner
    console.print()
    console.print(Panel.fit(
        f"[bold bright_white]PEGASUS GALAXY[/bold bright_white] [cyan]•[/cyan] [dim]MCP AGENT INSPECTOR[/dim]\n"
        f"[green]● Connected[/green] to [bold]https://mcp.pegasus-galaxy.net[/bold] via [yellow]Streamable HTTP[/yellow]",
        border_style="cyan",
        title="[bold cyan]🌌 Galaxy Network[/bold cyan]",
        subtitle="[dim]Game Engine v1.0 • Tick Interval: 30m[/dim]"
    ))

    # --- Row 1: Tick & Core Planet Stats ---
    stats_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta", expand=True)
    stats_table.add_column("Current Tick", justify="center")
    stats_table.add_column("Next Tick In", justify="center")
    stats_table.add_column("Colony Name", justify="center")
    stats_table.add_column("Coordinates", justify="center")
    stats_table.add_column("Score", justify="right")
    stats_table.add_column("Happiness", justify="center")
    stats_table.add_column("Asteroids", justify="right")

    happiness_val = planet.get("happiness", 0)
    hap_color = "green" if happiness_val >= 70 else ("yellow" if happiness_val >= 50 else "red")

    stats_table.add_row(
        f"[bold bright_yellow]{current_tick}[/bold bright_yellow]",
        f"[bold cyan]{next_tick_in}[/bold cyan]",
        f"[bold bright_white]{planet.get('name', 'Unknown')}[/bold bright_white]",
        f"[bright_cyan]{planet.get('coords', 'N/A')}[/bright_cyan]",
        f"[bold green]{format_num(planet.get('score', 0))}[/bold green]",
        f"[{hap_color}]{happiness_val}%[/{hap_color}]",
        f"[bright_magenta]{format_num(planet.get('asteroidCount', 0))}[/bright_magenta]",
    )
    console.print(stats_table)

    # --- Row 2: Resources & Population ---
    res_table = Table(box=box.ROUNDED, show_header=True, header_style="bold blue")
    res_table.add_column("Resource", style="dim")
    res_table.add_column("Amount", justify="right")
    res_table.add_column("Status", justify="center")

    metal = planet.get("metal", 0)
    crystal = planet.get("crystal", 0)
    eonium = planet.get("eonium", 0)

    res_table.add_row("🔩 Metal", f"[bold white]{format_num(metal)}[/bold white]", "[green]Normal[/green]")
    res_table.add_row("💎 Crystal", f"[bold cyan]{format_num(crystal)}[/bold cyan]", "[green]Plentiful[/green]")
    res_table.add_row("⚡ Eonium (Fuel)", f"[bold yellow]{format_num(eonium)}[/bold yellow]", "[green]Plentiful[/green]")

    pop_table = Table(box=box.ROUNDED, show_header=True, header_style="bold green")
    pop_table.add_column("Role", style="dim")
    pop_table.add_column("Assigned", justify="right")
    pop_table.add_column("Share", justify="right")

    tot_pop = planet.get("totalPopulation", 0) or 1
    roles = [
        ("⛏️ Miners", planet.get("miners", 0)),
        ("🔬 Researchers", planet.get("researchers", 0)),
        ("🔨 Builders", planet.get("builders", 0)),
        ("🚀 Shipwrights", planet.get("shipwrights", 0)),
        ("⚔️ Soldiers", planet.get("soldiers", 0)),
        ("💤 Unassigned", planet.get("assignablePopulation", 0)),
    ]
    for role_name, count in roles:
        pct = (count / tot_pop) * 100
        pop_table.add_row(role_name, f"[bold]{format_num(count)}[/bold]", f"{pct:.1f}%")

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(
        Panel(res_table, title="[bold blue]📦 Resources[/bold blue]", border_style="blue"),
        Panel(pop_table, title=f"[bold green]👥 Population ({format_num(planet.get('totalPopulation', 0))})[/bold green]", border_style="green")
    )
    console.print(grid)

    # --- Row 3: In-Progress Construction & Research ---
    constructions = data.get("constructions", [])
    research_list = data.get("research", [])

    active_builds = [c for c in constructions if isinstance(c, dict) and c.get("currentlyInProgress")]
    active_research = [r for r in research_list if isinstance(r, dict) and r.get("currentlyInProgress")]

    build_text = Text()
    if active_builds:
        for b in active_builds:
            cur_pts = b.get("currentPoints", 0)
            req_pts = b.get("requiredPoints", 1)
            pct = (cur_pts / req_pts) * 100 if req_pts else 0
            build_text.append(f"🔨 {b.get('name', 'Construction')} (Lvl {b.get('currentLevel', 1)})\n", style="bold white")
            build_text.append(f"   Progress: {format_num(cur_pts)} / {format_num(req_pts)} pts ({pct:.1f}%)\n", style="cyan")
    else:
        build_text.append("No active construction in progress.\n", style="dim italic")

    res_text = Text()
    if active_research:
        for r in active_research:
            cur_pts = r.get("currentPoints", 0)
            req_pts = r.get("requiredPoints", 1)
            pct = (cur_pts / req_pts) * 100 if req_pts else 0
            res_text.append(f"🔬 {r.get('name', 'Research')} (Lvl {r.get('currentLevel', 1)})\n", style="bold white")
            res_text.append(f"   Progress: {format_num(cur_pts)} / {format_num(req_pts)} pts ({pct:.1f}%)\n", style="magenta")
    else:
        res_text.append("No active research in progress.\n", style="dim italic")

    queue_grid = Table.grid(expand=True)
    queue_grid.add_column(ratio=1)
    queue_grid.add_column(ratio=1)
    queue_grid.add_row(
        Panel(build_text, title="[bold yellow]🏗️ Active Construction[/bold yellow]", border_style="yellow"),
        Panel(res_text, title="[bold magenta]🧪 Active Research[/bold magenta]", border_style="magenta")
    )
    console.print(queue_grid)

    # --- Row 4: Military & Fleets ---
    fleets = data.get("fleets", [])
    base_fleet = planet.get("shipsBaseFleet", {})

    fleet_table = Table(box=box.ROUNDED, expand=True, show_header=True, header_style="bold red")
    fleet_table.add_column("Fleet", style="bold white")
    fleet_table.add_column("Status", justify="center")
    fleet_table.add_column("Mission", justify="center")
    fleet_table.add_column("Ships", justify="left")
    fleet_table.add_column("ETA / Arrival", justify="center")

    # Base garrison
    if base_fleet:
        ships_str = ", ".join(f"{k.replace('main-vanguard-', '').replace('main-', '').title()}: {format_num(v)}" for k, v in base_fleet.items())
        fleet_table.add_row("Stationary Garrison", "[cyan]ORBIT[/cyan]", "[dim]DEFENSE[/dim]", ships_str, "[dim]At Home[/dim]")

    if isinstance(fleets, list):
        for fl in fleets:
            if not isinstance(fl, dict):
                continue
            fl_name = fl.get("name") or fl.get("id", "Fleet")[:10]
            status = fl.get("status", "UNKNOWN")
            mission = fl.get("mission", "NONE")
            ships_dict = fl.get("ships", {})
            if ships_dict:
                ships_desc = ", ".join(f"{k.replace('main-vanguard-', '').replace('main-', '').title()}: {format_num(v)}" for k, v in ships_dict.items())
            else:
                ships_desc = "[dim]None (Empty Fleet)[/dim]"
            
            arrives_at = fl.get("arrivesAt")
            eta_desc = f"Tick {arrives_at}" if arrives_at else "[dim]Docked[/dim]"
            
            status_style = "green" if status == "DOCKED" else ("bold red" if status == "TRAVELING" else "yellow")
            fleet_table.add_row(fl_name, f"[{status_style}]{status}[/{status_style}]", f"[bold]{mission}[/bold]", ships_desc, eta_desc)

    console.print(Panel(fleet_table, title="[bold red]⚔️ Fleet Command[/bold red]", border_style="red"))

    # --- Row 5: Action Limits & Rate Limiting ---
    rate_table = Table(box=box.SIMPLE, expand=True)
    rate_table.add_column("Action Category", style="bold white")
    rate_table.add_column("Limit Per Tick", justify="center")
    rate_table.add_column("Consumes Quota?", justify="center")
    rate_table.add_column("Note", style="dim")

    rate_table.add_row("Total State Actions", "10 actions / tick", "[red]Yes[/red]", "Builds, research, trade, production")
    rate_table.add_row("Fleet Launches", "3 launches / tick", "[red]Yes[/red]", "Min 20 ships, 1 eonium fuel / ship")
    rate_table.add_row("Planet Scans", "2 scans / tick", "[red]Yes[/red]", "Surface, deep, or military scans")
    rate_table.add_row("Read-only Queries", "[bold green]Unlimited[/bold green]", "[green]No[/green]", "get_planet_status, get_game_state_summary, etc.")

    console.print(Panel(rate_table, title="[bold yellow]⚡ Agent Action Quotas[/bold yellow]", border_style="yellow"))
    console.print("[dim]Tip: Run with [bold]--tools[/bold] to see all 67 available MCP commands, [bold]--missions[/bold] to view quests, or [bold]--call <tool>[/bold] to invoke one.[/dim]\n")


def print_tools(client: PegasusMCPClient, raw_json: bool = False):
    """Lists all available tools grouped by category."""
    with console.status("[bold cyan]Fetching tool registry from Pegasus MCP...", spinner="dots"):
        tools = client.list_tools()

    if raw_json:
        print(json.dumps(tools, indent=2))
        return

    table = Table(
        box=box.ROUNDED,
        title=f"🛠️ Pegasus Galaxy MCP Server Tools ({len(tools)} Total)",
        title_style="bold cyan",
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("Tool Name", style="bold bright_white", ratio=2)
    table.add_column("Type", justify="center", ratio=1)
    table.add_column("Description", ratio=4)
    table.add_column("Parameters", style="dim", ratio=3)

    for tool in tools:
        name = tool.get("name", "")
        desc = tool.get("description", "")
        schema = tool.get("inputSchema", {})
        props = schema.get("properties", {})
        required = schema.get("required", [])

        # Categorize type
        is_action = any(verb in name for verb in (
            "build", "start", "cancel", "produce", "assign", "change", "trade",
            "search", "initiate", "repair", "launch", "recall", "perform", "send",
            "create", "join", "leave", "accept", "invite", "kick", "declare",
            "decline", "claim", "set", "delete"
        ))
        type_str = "[bold red]ACTION[/bold red]" if is_action else "[bold green]READ[/bold green]"

        # Format params
        param_list = []
        for prop_name, prop_data in props.items():
            req_mark = "[bold red]*[/bold red]" if prop_name in required else ""
            p_type = prop_data.get("type", "any")
            param_list.append(f"{prop_name}{req_mark} ({p_type})")
        params_str = ", ".join(param_list) if param_list else "[dim]None[/dim]"

        table.add_row(name, type_str, desc, params_str)

    console.print(table)
    console.print("[dim]* indicates required parameter. Action tools consume tick quota, Read tools are free.[/dim]\n")


def print_missions(client: PegasusMCPClient, raw_json: bool = False):
    """Lists player missions and status."""
    with console.status("[bold cyan]Fetching player missions...", spinner="dots"):
        res = client.list_missions()

    if raw_json:
        print(json.dumps(res, indent=2))
        return

    data = res.get("data", {}) if isinstance(res, dict) else {}
    if isinstance(data, dict):
        missions = data.get("missions", [])
        summary = data.get("summary", {})
    elif isinstance(data, list):
        missions = data
        summary = {}
    else:
        missions = []
        summary = {}

    summary_str = ""
    if summary:
        summary_str = f" [green]• {summary.get('completed', 0)} Completed[/green] [yellow]• {summary.get('active', 0)} Active[/yellow] [dim]• {summary.get('claimed', 0)} Claimed[/dim]"

    table = Table(
        box=box.ROUNDED,
        title=f"🎯 Missions & Achievements ({len(missions)} Total){summary_str}",
        title_style="bold cyan",
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("Mission ID", style="bold bright_white")
    table.add_column("Status", justify="center")
    table.add_column("Progress", justify="center")

    claimable = 0
    # Sort: COMPLETED first, then ACTIVE, then others
    order = {"COMPLETED": 0, "ACTIVE": 1, "CLAIMED": 2, "EXPIRED": 3}
    sorted_missions = sorted(missions, key=lambda m: order.get(m.get("status", ""), 9))

    for m in sorted_missions:
        if not isinstance(m, dict):
            continue
        m_id = m.get("missionId", "")
        status = m.get("status", "UNKNOWN")
        prog = m.get("progress", [])
        prog_str = "/".join(str(p) for p in prog) if prog else "-"

        if status == "COMPLETED":
            status_style = "[bold green]COMPLETED (Ready to Claim!)[/bold green]"
            claimable += 1
        elif status == "ACTIVE":
            status_style = "[bold yellow]ACTIVE[/bold yellow]"
        elif status == "CLAIMED":
            status_style = "[dim]CLAIMED[/dim]"
        elif status == "EXPIRED":
            status_style = "[red]EXPIRED[/red]"
        else:
            status_style = status

        table.add_row(m_id, status_style, prog_str)

    console.print(table)
    if claimable > 0:
        console.print(f"[bold green]✨ You have {claimable} completed mission(s) ready to claim! Run [bold cyan]python peg_tool.py --call claim_missions[/bold cyan] to claim rewards.[/bold green]\n")
    else:
        console.print()


def print_resources(client: PegasusMCPClient, raw_json: bool = False):
    """Lists all MCP resources."""
    with console.status("[bold cyan]Fetching MCP resources...", spinner="dots"):
        resources = client.list_resources()

    if raw_json:
        print(json.dumps(resources, indent=2))
        return

    table = Table(
        box=box.ROUNDED,
        title=f"📚 Pegasus Galaxy MCP Resources ({len(resources)} Available)",
        title_style="bold green",
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Resource Name", style="bold bright_white")
    table.add_column("URI", style="cyan")

    for res in resources:
        table.add_row(res.get("name", ""), res.get("uri", ""))

    console.print(table)
    console.print("[dim]Read any resource using: python peg_tool.py --read-resource <URI>[/dim]\n")


def read_resource_cmd(client: PegasusMCPClient, uri: str, raw_json: bool = False):
    """Reads a specific MCP resource."""
    with console.status(f"[bold cyan]Reading resource {uri}...", spinner="dots"):
        content = client.read_resource(uri)

    if raw_json or isinstance(content, (dict, list)):
        print(json.dumps(content, indent=2))
    elif isinstance(content, str) and uri.endswith("/rules"):
        console.print(Markdown(content))
    else:
        console.print(Panel(str(content), title=f"[bold cyan]{uri}[/bold cyan]", border_style="cyan"))


def print_rules(client: PegasusMCPClient, topic: Optional[str] = None, raw_json: bool = False):
    """Fetches and renders game rules."""
    with console.status(f"[bold cyan]Fetching rules ({topic or 'overview'})...", spinner="dots"):
        res = client.get_game_rules(topic)

    if raw_json:
        print(json.dumps(res, indent=2))
        return

    # If dict with data.rules or data
    text = ""
    if isinstance(res, dict):
        text = res.get("data", {}).get("rules") or res.get("data") or json.dumps(res, indent=2)
    else:
        text = str(res)

    console.print(Panel(
        Markdown(text) if isinstance(text, str) else str(text),
        title=f"[bold cyan]📖 Rules: {topic or 'General'}[/bold cyan]",
        border_style="cyan",
        expand=True
    ))


def print_reference(client: PegasusMCPClient, category_filter: Optional[str] = None, raw_json: bool = False):
    """Fetches and displays official game object IDs (constructions, research, ships)."""
    with console.status("[bold cyan]Fetching game definitions from MCP server...", spinner="dots"):
        constructions = client.read_resource("pegasus://construction/definitions") or []
        research = client.read_resource("pegasus://research/definitions") or []
        ships = client.read_resource("pegasus://ship/definitions") or []

    if raw_json:
        print(json.dumps({
            "constructions": constructions,
            "research": research,
            "ships": ships
        }, indent=2))
        return

    cat = (category_filter or "all").lower()

    if cat in ("all", "constructions", "c", "build", "b"):
        t_const = Table(
            box=box.ROUNDED,
            title=f"🏗️ Pegasus Constructions & Buildings ({len(constructions)} Total)",
            title_style="bold blue",
            header_style="bold cyan",
            expand=True
        )
        t_const.add_column("Exact Construction ID", style="bold bright_cyan", ratio=3)
        t_const.add_column("Building Name", style="bold white", ratio=3)
        t_const.add_column("Category", ratio=2)
        t_const.add_column("Lvl 1 Metal", justify="right", ratio=2)
        t_const.add_column("Lvl 1 Crystal", justify="right", ratio=2)
        t_const.add_column("Lvl 1 Eonium", justify="right", ratio=2)

        for c in sorted(constructions, key=lambda x: (x.get("category", ""), x.get("name", ""))):
            t_const.add_row(
                c.get("id", ""),
                c.get("name", ""),
                c.get("category", "Structure"),
                f"{c.get('requiredMetal', 0):,}",
                f"{c.get('requiredCrystal', 0):,}",
                f"{c.get('requiredEonium', 0):,}",
            )
        console.print(t_const)
        console.print("[dim]Use with tool: [bold]build_construction[/bold] (e.g. {\"constructionId\": \"main-shipyard\"}) or [bold]repair_pds[/bold][/dim]\n")

    if cat in ("all", "research", "r", "tech", "t"):
        t_res = Table(
            box=box.ROUNDED,
            title=f"🔬 Pegasus Research Technologies ({len(research)} Total)",
            title_style="bold magenta",
            header_style="bold cyan",
            expand=True
        )
        t_res.add_column("Exact Research ID", style="bold bright_magenta", ratio=3)
        t_res.add_column("Technology Name", style="bold white", ratio=3)
        t_res.add_column("Category", ratio=2)
        t_res.add_column("Lvl 1 Metal", justify="right", ratio=2)
        t_res.add_column("Lvl 1 Crystal", justify="right", ratio=2)
        t_res.add_column("Lvl 1 Eonium", justify="right", ratio=2)

        for r in sorted(research, key=lambda x: x.get("name", "")):
            t_res.add_row(
                r.get("id", ""),
                r.get("name", ""),
                r.get("category", "Tech"),
                f"{r.get('requiredMetal', 0):,}",
                f"{r.get('requiredCrystal', 0):,}",
                f"{r.get('requiredEonium', 0):,}",
            )
        console.print(t_res)
        console.print("[dim]Use with tool: [bold]start_research[/bold] (e.g. {\"researchId\": \"main-constructions\"})[/dim]\n")

    if cat in ("all", "ships", "s", "fleet", "f"):
        t_ships = Table(
            box=box.ROUNDED,
            title=f"🚀 Pegasus Ship Designs & Codex ({len(ships)} Total)",
            title_style="bold green",
            header_style="bold cyan",
            expand=True
        )
        t_ships.add_column("Exact Ship Definition ID", style="bold bright_green", ratio=3)
        t_ships.add_column("Ship Name", style="bold white", ratio=3)
        t_ships.add_column("Class", ratio=2)
        t_ships.add_column("Faction", ratio=2)
        t_ships.add_column("Unit Metal", justify="right", ratio=2)
        t_ships.add_column("Unit Crystal", justify="right", ratio=2)
        t_ships.add_column("Unit Eonium", justify="right", ratio=2)

        for s in sorted(ships, key=lambda x: (x.get("category", ""), x.get("name", ""))):
            t_ships.add_row(
                s.get("id", ""),
                s.get("name", ""),
                s.get("category", s.get("shipClass", "Vessel")),
                s.get("faction", "Neutral"),
                f"{s.get('requiredMetal', 0):,}",
                f"{s.get('requiredCrystal', 0):,}",
                f"{s.get('requiredEonium', 0):,}",
            )
        console.print(t_ships)
        console.print("[dim]Use with tool: [bold]produce_ships[/bold] (e.g. {\"shipDefinitionId\": \"main-vanguard-centurion\", \"quantity\": 10})[/dim]\n")


def call_tool_cmd(client: PegasusMCPClient, tool_name: str, args_json: Optional[str] = None, raw_json: bool = False):
    """Calls an arbitrary tool."""
    arguments = {}
    if args_json:
        try:
            arguments = json.loads(args_json)
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Invalid JSON arguments:[/bold red] {e}")
            sys.exit(1)

    with console.status(f"[bold cyan]Calling tool '{tool_name}' with args {arguments}...", spinner="dots"):
        result = client.call_tool(tool_name, arguments)

    if raw_json or isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2))
    else:
        console.print(Panel(str(result), title=f"[bold green]Result: {tool_name}[/bold green]", border_style="green"))


def run_battle_calc_cmd(
    client: PegasusMCPClient,
    attacker_name: Optional[str] = None,
    defender_target: Optional[str] = None,
    defend: bool = False,
    source: str = "all",
    raw_json: bool = False,
    output_format: str = "standard"
):
    """Simulates a combat engagement using live MCP telemetry, universe map coords, and user/ally scan intel.
    
    If defend=True, user's planet (hangar ships + live PDS + tech) defends against
    the enemy fleet extracted from scan history.
    """
    with console.status("[bold cyan]Querying active fleets, defense systems, universe map, and scan intel...", spinner="dots"):
        fleet_summary_resp = client.call_tool("get_fleet_summary") or {}
        scans_resp = client.call_tool("get_scan_history", {"limit": 100}) or {}
        pds_resp = client.call_tool("list_pds") or {}
        research_resp = client.call_tool("get_planet_research") or {}
        planet_resp = client.get_planet_status() or {}
        universe_resp = client.get_universe_map() or {}

    fs_data = fleet_summary_resp.get("data", {}) if isinstance(fleet_summary_resp, dict) else {}
    named_fleets = fs_data.get("fleets", []) if isinstance(fs_data, dict) else []
    if not named_fleets:
        active_resp = client.call_tool("list_active_fleets") or {}
        named_fleets = active_resp.get("data", []) if isinstance(active_resp, dict) else []

    hangar_ships = {}
    if isinstance(fs_data, dict) and "baseFleet" in fs_data:
        raw_base = fs_data.get("baseFleet", {})
        for sid, cnt in raw_base.items():
            if not sid.startswith("pds-"):
                try:
                    hangar_ships[sid] = int(cnt)
                except (ValueError, TypeError):
                    pass
    if not hangar_ships:
        hangar_resp = client.call_tool("get_planet_ships") or {}
        raw_hangar = hangar_resp.get("data", {}) if isinstance(hangar_resp, dict) else {}
        if isinstance(raw_hangar, dict):
            hangar_ships = {k: int(v) for k, v in raw_hangar.items() if isinstance(v, (int, float))}
        elif isinstance(raw_hangar, list):
            for item in raw_hangar:
                if isinstance(item, dict):
                    sid = item.get("shipDefinitionId") or item.get("id")
                    qty = item.get("quantity") or item.get("count", 1)
                    if sid:
                        hangar_ships[sid] = hangar_ships.get(sid, 0) + int(qty)

    # User Home Defense Data
    user_pds = {}
    pds_list = pds_resp.get("data", []) if isinstance(pds_resp, dict) else []
    for p in pds_list:
        name = p.get("name")
        lvl = p.get("currentLevel", 1)
        if name:
            user_pds[name] = lvl

    user_research = {"Hulls": 0, "ShipTechnology": 0, "PDS": 0}
    res_list = research_resp.get("data", []) if isinstance(research_resp, dict) else []
    for r in res_list:
        rn = r.get("name", "")
        lvl = r.get("currentLevel", 0)
        if rn == "Hulls":
            user_research["Hulls"] = lvl
        elif rn == "Ship Technology":
            user_research["ShipTechnology"] = lvl
        elif rn == "PDS":
            user_research["PDS"] = lvl

    planet_data = planet_resp.get("data", {}) if isinstance(planet_resp, dict) else {}
    user_resources = {
        "metal": planet_data.get("metal", 0),
        "crystal": planet_data.get("crystal", 0),
        "eonium": planet_data.get("eonium", 0)
    }
    user_ast_cnt = planet_data.get("asteroidCount", 0)
    user_asteroids = {
        "metalRoids": user_ast_cnt // 3,
        "crystalRoids": user_ast_cnt // 3,
        "eoniumRoids": user_ast_cnt - (2 * (user_ast_cnt // 3))
    }

    # Build planetary metadata lookup from universe map
    u_planets = universe_resp.get("data", []) if isinstance(universe_resp, dict) else []
    planet_meta = {}
    for p in u_planets:
        pid = p.get("id")
        c = p.get("coords") or f"{p.get('coordX', 0)}:{p.get('coordY', 0)}:{p.get('coordZ', 0)}"
        if pid:
            planet_meta[pid] = {
                "coords": c,
                "name": p.get("name", ""),
                "owner": p.get("playerId", ""),
                "pds": {},
                "research": {},
                "resources": {},
                "asteroids": {}
            }

    # Fetch User Scans and Alliance Scans
    user_scans = scans_resp.get("data", []) if isinstance(scans_resp, dict) else []
    for s in user_scans:
        s["source"] = "user"

    ally_scans = []
    alliance_tag = ""
    try:
        user_alliance = client.get_user_alliance()
        if user_alliance and user_alliance.get("id"):
            alliance_tag = user_alliance.get("tag", "")
            intel_resp = client.get_scan_intel(user_alliance["id"], limit=100)
            if isinstance(intel_resp, dict) and intel_resp.get("success"):
                for ascan in (intel_resp.get("data") or []):
                    ascan["source"] = "ally"
                    ascan["allianceTag"] = alliance_tag
                    ally_scans.append(ascan)
    except Exception:
        pass

    all_scans = user_scans + ally_scans

    # Enrich metadata from scans
    for s in all_scans:
        pid = s.get("targetPlanetId") or s.get("planetId")
        if not pid or pid not in planet_meta:
            continue
        r_raw = s.get("result", {})
        if isinstance(r_raw, str):
            try:
                r = json.loads(r_raw)
            except Exception:
                r = {}
        elif isinstance(r_raw, dict):
            r = r_raw
        else:
            r = {}
        if r.get("constructions") and not planet_meta[pid]["pds"]:
            pds = {}
            for cn in r.get("constructions", []):
                name = cn.get("name", "")
                if any(k in name.lower() for k in ["laser", "missile", "ion", "shield", "sensor"]):
                    pds[name] = cn.get("level", 0)
            if pds:
                planet_meta[pid]["pds"] = pds
        if r.get("research") and not planet_meta[pid]["research"]:
            res_tech = {}
            for res_item in r.get("research", []):
                rn = res_item.get("name", "")
                if any(k in rn.lower() for k in ["hull", "pds", "ship tech", "engineering"]):
                    res_tech[rn] = res_item.get("level", 0)
            if res_tech:
                planet_meta[pid]["research"] = res_tech

    # Filter combat-capable scans
    fleet_scan_types = {"DEEP_SCAN", "MILITARY_SCAN", "FLEET_COMPOSITION_SCAN", "INCOMING_SCAN"}
    parsed_targets = []
    seen_keys = set()
    for s in all_scans:
        if s.get("status") not in ("success", "blocked") and s.get("status") is not None:
            continue
        st = s.get("scanType", "")
        if st not in fleet_scan_types and s.get("status") != "blocked":
            res_str = str(s.get("result", ""))
            if not any(k in res_str for k in ("ships", "namedFleets", "fleets")):
                continue
        key = (s.get("targetPlanetId") or s.get("planetId"), s.get("tick", 0), st, s.get("source", "user"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        parsed = peg_combat.parse_scan_record(s, planet_lookup=planet_meta)
        if parsed:
            parsed_targets.append(parsed)

    # Filter by source if requested
    if source in ("user", "ally"):
        parsed_targets = [t for t in parsed_targets if t.get("source") == source]

    # Sort newest tick first
    parsed_targets.sort(key=lambda t: t.get("tick", 0), reverse=True)

    chosen_target = None
    if defender_target:
        clean_def = re.sub(r"[^0-9:]", ":", defender_target.strip()).strip(":")
        matched_targets = []
        for t in parsed_targets:
            t_coords = re.sub(r"[^0-9:]", ":", t.get("coords", "")).strip(":")
            if clean_def and (t_coords == clean_def or t_coords.startswith(clean_def)):
                matched_targets.append(t)
            elif defender_target.lower() in (
                t.get("targetPlanetId", "").lower(),
                t.get("coords", "").lower(),
                t.get("owner", "").lower(),
                t.get("planetName", "").lower(),
            ):
                matched_targets.append(t)

        if matched_targets:
            chosen_target = matched_targets[0]
            if len(matched_targets) > 1 and not raw_json:
                console.print(f"\n[bold cyan]Found {len(matched_targets)} scans matching target '{defender_target}':[/bold cyan]")
                scans_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
                scans_table.add_column("Tick", justify="center")
                scans_table.add_column("Source", justify="center")
                scans_table.add_column("Scan Type", justify="left")
                scans_table.add_column("Planet", justify="left")
                scans_table.add_column("Garrison Ships", justify="right")
                scans_table.add_column("PDS Weapons", justify="center")
                scans_table.add_column("Status", justify="center")

                for i, mt in enumerate(matched_targets):
                    is_active = (i == 0)
                    src_badge = "[bold green]👤 Mine[/bold green]" if mt.get("source") == "user" else f"[bold magenta]🤝 Ally ({mt.get('allianceTag', '')})[/bold magenta]"
                    g_count = sum(mt.get("garrisonShips", {}).values())
                    pds_cnt = len(mt.get("pds", {}))
                    status_lbl = "[bold cyan]★ Selected (Latest)[/bold cyan]" if is_active else "[dim]Older Scan[/dim]"
                    if mt.get("isBlocked"):
                        status_lbl += " [yellow]⚠️ Blocked[/yellow]"
                    p_label = f"{mt.get('planetName', '')} [{mt.get('coords', '')}]".strip()
                    scans_table.add_row(
                        f"Tick {mt.get('tick', '?')}",
                        src_badge,
                        mt.get("scanType", "SCAN"),
                        p_label,
                        format_num(g_count),
                        f"{pds_cnt} structures" if pds_cnt > 0 else "None",
                        status_lbl
                    )
                console.print(scans_table)
                console.print()
        else:
            console.print(f"[bold red]Scan target '{defender_target}' not found in scan history ({source} scans).[/bold red]")
            console.print("Available scan targets in history:")
            for t in parsed_targets[:10]:
                src_lbl = "👤 Mine" if t.get("source") == "user" else f"🤝 Ally {t.get('allianceTag', '')}"
                p_name = f" ({t.get('planetName')})" if t.get("planetName") else ""
                console.print(f"  - [bold cyan]{t.get('coords')}[/bold cyan]{p_name} | Tick {t.get('tick')} | [dim]{t.get('scanType')}[/dim] [{src_lbl}]")
            sys.exit(1)
    else:
        if parsed_targets:
            chosen_target = parsed_targets[0]
            if not raw_json:
                src_lbl = "👤 Mine" if chosen_target.get("source") == "user" else f"🤝 Ally ({chosen_target.get('allianceTag', '')})"
                p_name = f" ({chosen_target.get('planetName')})" if chosen_target.get('planetName') else ""
                console.print(f"[dim]Auto-selected latest scan target: [bold cyan]{chosen_target.get('coords')}[/bold cyan]{p_name} from Tick {chosen_target.get('tick')} [{src_lbl}][/dim]\n")
        else:
            if defend:
                console.print(f"[bold yellow]No combat scans found in scan history ({source} scans) to simulate as attacker.[/bold yellow]")
            else:
                console.print(f"[bold yellow]No combat scans found in scan history ({source} scans).[/bold yellow]")

    # Build sides based on whether user is Attacker or Defender
    if defend:
        # User is DEFENDER, Enemy is ATTACKER
        chosen_def_label = f"Your Home Base ({planet_data.get('coords', 'Home')})"
        def_fleet = hangar_ships
        def_pds = user_pds
        def_res = user_research
        def_resources = user_resources
        def_asteroids = user_asteroids

        chosen_atk_ships = {}
        chosen_atk_label = "Enemy Invading Fleet"
        atk_res = {"Hulls": 5, "ShipTechnology": 5}
        if chosen_target:
            chosen_atk_label = f"Enemy Fleet from {chosen_target.get('coords', 'Unknown')} ({chosen_target.get('owner', 'Unknown')})"
            chosen_atk_ships = dict(chosen_target.get("garrisonShips", {}))
            for ef in chosen_target.get("namedFleets", []):
                for ship_id, qty in ef.get("ships", {}).items():
                    chosen_atk_ships[ship_id] = chosen_atk_ships.get(ship_id, 0) + qty
            if chosen_target.get("research"):
                atk_res = chosen_target.get("research")
    else:
        # User is ATTACKER, Enemy is DEFENDER
        chosen_atk_ships = {}
        chosen_atk_label = "Active Fleet"
        atk_res = user_research

        if attacker_name:
            matched = next((f for f in named_fleets if f.get("name", "").lower() == attacker_name.lower()), None)
            if matched:
                chosen_atk_ships = matched.get("ships", {})
                chosen_atk_label = f"Fleet: {matched.get('name')}"
            elif attacker_name.lower() in ("hangar", "garrison", "planet"):
                chosen_atk_ships = hangar_ships
                chosen_atk_label = "Planet Hangar"
            else:
                console.print(f"[bold red]Attacker fleet '{attacker_name}' not found.[/bold red]")
                console.print("Available named fleets:")
                for f in named_fleets:
                    console.print(f"  - [cyan]{f.get('name')}[/cyan] ({sum(f.get('ships', {}).values())} ships)")
                console.print("  - [yellow]hangar[/yellow] (All unassigned planet ships)")
                sys.exit(1)
        else:
            if named_fleets:
                first_fleet = named_fleets[0]
                chosen_atk_ships = first_fleet.get("ships", {})
                chosen_atk_label = f"Fleet: {first_fleet.get('name')} (default)"
            elif hangar_ships:
                chosen_atk_ships = hangar_ships
                chosen_atk_label = "Planet Hangar (default)"
            else:
                console.print("[bold yellow]No attacker ships available in fleets or hangar.[/bold yellow]")

        def_fleet = {}
        def_pds = {}
        def_res = {}
        def_resources = {}
        def_asteroids = {}
        chosen_def_label = "Enemy Forces"

        if chosen_target:
            chosen_def_label = f"Planet {chosen_target.get('coords', 'Unknown')} ({chosen_target.get('owner', 'Unknown')})"
            def_pds = chosen_target.get("pds", {})
            def_res = chosen_target.get("research", {})
            def_resources = chosen_target.get("resources", {})
            def_asteroids = chosen_target.get("asteroids", {})
            def_fleet = dict(chosen_target.get("garrisonShips", {}))
            for ef in chosen_target.get("namedFleets", []):
                for ship_id, qty in ef.get("ships", {}).items():
                    def_fleet[ship_id] = def_fleet.get(ship_id, 0) + qty

    # Run Simulation
    sim_result = peg_combat.simulate_combat(
        attacker_fleet=chosen_atk_ships,
        defender_fleet=def_fleet,
        defender_pds=def_pds,
        attacker_research=atk_res,
        defender_research=def_res,
        defender_resources=def_resources,
        defender_asteroids=def_asteroids,
        max_rounds=1
    )

    if raw_json:
        print(json.dumps(sim_result, indent=2))
        return

    outcome = sim_result["outcome"]
    outcome_detail = sim_result.get("outcomeDetail", outcome)
    rounds = sim_result.get("rounds", 0)
    dominance = sim_result.get("dominance", 0.5)

    if output_format == "bcalc":
        # Planetarion BattleCalc Output Format
        console.print()
        console.print("[bold yellow]======================================================================[/bold yellow]")
        console.print(f"[bold bright_white]🪐 PLANETARION BATTLECALC REPORT: {outcome_detail.upper()} ({rounds} Round(s))[/bold bright_white]")
        console.print("[bold yellow]======================================================================[/bold yellow]")
        console.print(f"[bold cyan]Attacker Coalition:[/bold cyan] {chosen_atk_label}")
        console.print(f"[bold red]Defender Target:[/bold red] {chosen_def_label}")
        console.print()

        # Defending Fleets Loss Reports
        for df in sim_result.get("defender", {}).get("fleets", []):
            f_title = df.get("name", "Defense Fleet")
            t_def = Table(title=f"Report of Losses from {f_title} (Defender)", box=box.SIMPLE_HEAVY, header_style="bold red")
            t_def.add_column("Ship / Unit", justify="left")
            t_def.add_column("Arrived", justify="right")
            t_def.add_column("Lost", justify="right", style="bold red")
            t_def.add_column("Survivors", justify="right", style="bold green")

            s_counts = df.get("startCounts", {})
            l_counts = df.get("lostCounts", {})
            surv_counts = df.get("survivedCounts", {})

            for uid, a_cnt in s_counts.items():
                ship_name = peg_combat.SHIP_DEFINITIONS.get(uid, {}).get("name") or uid.replace("main-", "").replace("-", " ")
                l_cnt = l_counts.get(uid, 0)
                s_cnt = surv_counts.get(uid, a_cnt - l_cnt)
                t_def.add_row(ship_name, f"{a_cnt:,}", f"{l_cnt:,}", f"{s_cnt:,}")
            console.print(t_def)
            console.print()

        # Attacking Fleets Loss Reports
        for af in sim_result.get("attacker", {}).get("fleets", []):
            f_title = af.get("name", "Attacking Fleet")
            t_atk = Table(title=f"Report of Losses from {f_title} (Attacker)", box=box.SIMPLE_HEAVY, header_style="bold cyan")
            t_atk.add_column("Ship / Unit", justify="left")
            t_atk.add_column("Arrived", justify="right")
            t_atk.add_column("Lost", justify="right", style="bold red")
            t_atk.add_column("Survivors", justify="right", style="bold green")

            s_counts = af.get("startCounts", {})
            l_counts = af.get("lostCounts", {})
            surv_counts = af.get("survivedCounts", {})

            for uid, a_cnt in s_counts.items():
                ship_name = peg_combat.SHIP_DEFINITIONS.get(uid, {}).get("name") or uid.replace("main-", "").replace("-", " ")
                l_cnt = l_counts.get(uid, 0)
                s_cnt = surv_counts.get(uid, a_cnt - l_cnt)
                t_atk.add_row(ship_name, f"{a_cnt:,}", f"{l_cnt:,}", f"{s_cnt:,}")
            console.print(t_atk)
            console.print()

        # Salvage Report
        salv = sim_result.get("salvage", {})
        t_salv = Table(title="Salvage Report", box=box.SIMPLE_HEAVY, header_style="bold yellow")
        t_salv.add_column("Metal", justify="right")
        t_salv.add_column("Crystal", justify="right")
        t_salv.add_column("Eonium", justify="right")
        t_salv.add_column("Total Salvage", justify="right", style="bold green")
        t_salv.add_row(
            f"{salv.get('metal', 0):,}",
            f"{salv.get('crystal', 0):,}",
            f"{salv.get('eonium', 0):,}",
            f"{salv.get('total', 0):,}"
        )
        console.print(t_salv)
        console.print()

        # Asteroids & Resources Captured
        plunder = sim_result.get("plunder", {})
        stolen_roids = sim_result.get("asteroidsStolen", {})
        t_plund = Table(title="Asteroids & Resources Captured", box=box.SIMPLE_HEAVY, header_style="bold green")
        t_plund.add_column("Category", justify="left")
        t_plund.add_column("Metal", justify="right")
        t_plund.add_column("Crystal", justify="right")
        t_plund.add_column("Eonium", justify="right")
        t_plund.add_column("Total", justify="right", style="bold green")
        t_plund.add_row(
            "Asteroids Captured",
            f"{stolen_roids.get('metalRoids', 0):,} roids",
            f"{stolen_roids.get('crystalRoids', 0):,} roids",
            f"{stolen_roids.get('eoniumRoids', 0):,} roids",
            f"{stolen_roids.get('total', 0):,} roids"
        )
        t_plund.add_row(
            "Resources Plundered",
            f"{plunder.get('metal', 0):,} res",
            f"{plunder.get('crystal', 0):,} res",
            f"{plunder.get('eonium', 0):,} res",
            f"{plunder.get('total', 0):,} res"
        )
        console.print(t_plund)
        console.print()
        return

    # Render formatted CLI output
    badge_color = "bold green" if outcome == "attacker" else ("bold red" if outcome == "defender" else "bold yellow")
    banner_text = f"[{badge_color}]=== SIMULATION RESULT: {outcome_detail} (in {rounds} round(s)) ===[/{badge_color}]\n\n"
    banner_text += f"[bold cyan]Attacker:[/bold cyan] {chosen_atk_label} ({sum(chosen_atk_ships.values())} ships)\n"
    banner_text += f"[bold red]Defender:[/bold red] {chosen_def_label} ({sum(def_fleet.values())} ships, {sum(def_pds.values())} PDS)\n"
    banner_text += f"[bold magenta]Tactical Dominance:[/bold magenta] {dominance * 100:.1f}% Attacker Advantage\n\n"

    advice = sim_result.get("tacticalAdvice", [])
    if advice:
        banner_text += "[bold]Tactical Intelligence:[/bold]\n"
        for line in advice:
            banner_text += f"  • {line}\n"

    console.print()
    console.print(Panel(banner_text, title="[bold bright_white]⚔️ Pegasus Battle Simulator Forecast[/bold bright_white]", border_style="cyan"))

    # Casualties Table
    c_table = Table(title="Combat Casualties Breakdown", box=box.ROUNDED, header_style="bold magenta")
    c_table.add_column("Unit ID", style="cyan")
    c_table.add_column("Side", justify="center")
    c_table.add_column("Initial", justify="right")
    c_table.add_column("Destroyed", justify="right", style="bold red")
    c_table.add_column("Survivors", justify="right", style="bold green")

    atk_stats = sim_result.get("attacker", {})
    for uid, start_qty in atk_stats.get("startCounts", {}).items():
        lost_qty = atk_stats.get("lostCounts", {}).get(uid, 0)
        surv_qty = atk_stats.get("survivedCounts", {}).get(uid, 0)
        c_table.add_row(uid, "[cyan]Attacker[/cyan]", str(start_qty), str(lost_qty), str(surv_qty))

    def_stats = sim_result.get("defender", {})
    for uid, start_qty in def_stats.get("startCounts", {}).items():
        lost_qty = def_stats.get("lostCounts", {}).get(uid, 0)
        surv_qty = def_stats.get("survivedCounts", {}).get(uid, 0)
        c_table.add_row(uid, "[red]Defender[/red]", str(start_qty), str(lost_qty), str(surv_qty))

    console.print(c_table)

    # Economic & Plunder Table
    e_table = Table(title="Economic Impact & Loot Projection", box=box.ROUNDED, header_style="bold yellow")
    e_table.add_column("Metric / Category", style="cyan")
    e_table.add_column("Attacker", justify="right")
    e_table.add_column("Defender", justify="right")

    atk_loss = atk_stats.get("valueLost", {})
    def_loss = def_stats.get("valueLost", {})
    e_table.add_row("Resource Value Lost", f"-{atk_loss.get('total', 0):,} res", f"-{def_loss.get('total', 0):,} res")

    salvage = sim_result.get("salvage", {})
    e_table.add_row("Salvage Recovered", f"+{salvage.get('total', 0):,} res", "0 res")

    plunder = sim_result.get("plunder", {})
    e_table.add_row("Resources Plundered", f"+{plunder.get('total', 0):,} res", f"-{plunder.get('total', 0):,} res")

    score_chg = sim_result.get("scoreChange", {})
    atk_sc = score_chg.get("attacker", 0)
    def_sc = score_chg.get("defender", 0)
    atk_sc_str = f"[bold green]+{atk_sc:,}[/bold green]" if atk_sc >= 0 else f"[bold red]{atk_sc:,}[/bold red]"
    def_sc_str = f"[bold green]+{def_sc:,}[/bold green]" if def_sc >= 0 else f"[bold red]{def_sc:,}[/bold red]"
    e_table.add_row("Predicted Score Δ", f"{atk_sc_str} pts", f"{def_sc_str} pts")

    console.print(e_table)

    # Plunder & Asteroid Stolen Panels
    p_info = (
        f"[bold]Transport Cargo Capacity:[/bold] {atk_stats.get('cargoCapacity', 0):,} | "
        f"[bold]Total Plunder Seized:[/bold] [bold green]{plunder.get('total', 0):,}[/bold green] "
        f"([dim]Metal: {plunder.get('metal', 0):,}, Crystal: {plunder.get('crystal', 0):,}, Eonium: {plunder.get('eonium', 0):,}[/dim])"
    )
    console.print(Panel(p_info, title="[bold gold1]💰 Projected Plunder Seized[/bold gold1]", border_style="gold1"))

    stolen_roids = sim_result.get("asteroidsStolen", {})
    r_info = (
        f"[bold]Asteroid Cargo Capacity:[/bold] {atk_stats.get('asteroidCapacity', 0):,} roids | "
        f"[bold]Total Asteroids Stolen:[/bold] [bold green]{stolen_roids.get('total', 0):,}[/bold green] roids "
        f"([dim]Metal: {stolen_roids.get('metalRoids', 0):,}, Crystal: {stolen_roids.get('crystalRoids', 0):,}, Eonium: {stolen_roids.get('eoniumRoids', 0):,}[/dim])"
    )
    console.print(Panel(r_info, title="[bold spring_green3]⛏️ Projected Asteroid Seizure[/bold spring_green3]", border_style="spring_green3"))
    console.print()


def main():
    parser = argparse.ArgumentParser(
        description="Pegasus Galaxy MCP Tool & Game State Inspector v0.6 (macOS / Linux / Windows)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tools",
        action="store_true",
        help="List all available MCP tools and their schemas",
    )
    parser.add_argument(
        "--resources",
        action="store_true",
        help="List available MCP resources",
    )
    parser.add_argument(
        "--read-resource",
        metavar="URI",
        help="Read a specific MCP resource (e.g. pegasus://game/rules)",
    )
    parser.add_argument(
        "--call",
        metavar="TOOL_NAME",
        help="Call a specific MCP tool (e.g. get_tech_tree)",
    )
    parser.add_argument(
        "--args",
        metavar="JSON_STRING",
        help="JSON string of arguments for --call (e.g. '{\"limit\": 5}')",
    )
    parser.add_argument(
        "--missions",
        action="store_true",
        help="List active and completed missions",
    )
    parser.add_argument(
        "--rules",
        nargs="?",
        const="overview",
        help="Fetch game rules (optional topic: overview, resources, construction, research, military, scoring)",
    )
    parser.add_argument(
        "--reference",
        "-ref",
        nargs="?",
        const="all",
        metavar="CATEGORY",
        help="Display official game IDs for constructions, research, and ships (optional filter: constructions, research, ships)",
    )
    parser.add_argument(
        "--battle-calc",
        action="store_true",
        help="Run battle simulator against active fleets and deep scan targets",
    )
    parser.add_argument(
        "--defend",
        action="store_true",
        help="Simulate enemy attacking your home base with your live PDS and hangar garrison",
    )
    parser.add_argument(
        "--attacker",
        metavar="FLEET_NAME",
        help="Attacker fleet name (or 'hangar') for battle simulation",
    )
    parser.add_argument(
        "--defender",
        metavar="TARGET",
        help="Defender target (coords e.g. 12:1:1, planet ID, or owner name from scan history)",
    )
    parser.add_argument(
        "--source",
        choices=["all", "user", "ally"],
        default="all",
        help="Scan intel source for battle simulation: 'all', 'user', or 'ally' (default: all)",
    )
    parser.add_argument(
        "--format",
        choices=["standard", "bcalc"],
        default="standard",
        help="Output format: 'standard' (rich tables) or 'bcalc' (Planetarion battlecalc reports)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted tables",
    )

    args = parser.parse_args()

    try:
        client = PegasusMCPClient()
    except Exception as e:
        console.print(f"[bold red]Error initializing Pegasus client:[/bold red] {e}")
        console.print("[yellow]Make sure your personal access token is in .env or PEGASUS_PAT env var.[/yellow]")
        sys.exit(1)

    try:
        if args.tools:
            print_tools(client, raw_json=args.json)
        elif args.resources:
            print_resources(client, raw_json=args.json)
        elif args.read_resource:
            read_resource_cmd(client, args.read_resource, raw_json=args.json)
        elif args.call:
            call_tool_cmd(client, args.call, args.args, raw_json=args.json)
        elif args.missions:
            print_missions(client, raw_json=args.json)
        elif args.rules is not None:
            print_rules(client, topic=args.rules, raw_json=args.json)
        elif args.reference is not None:
            print_reference(client, category_filter=args.reference, raw_json=args.json)
        elif args.battle_calc:
            run_battle_calc_cmd(
                client,
                attacker_name=args.attacker,
                defender_target=args.defender,
                defend=args.defend,
                source=args.source,
                raw_json=args.json,
                output_format=args.format
            )
        else:
            print_dashboard(client, raw_json=args.json)
    except PegasusMCPError as e:
        console.print(f"[bold red]MCP Server Error:[/bold red] {e} (code: {e.code})")
        if e.data:
            console.print(f"[red]{e.data}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {e}")
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()

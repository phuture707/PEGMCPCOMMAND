#!/usr/bin/env python3
"""
Pegasus Galaxy MCP Inspector & CLI Tool
Inspects game state, browses tools/resources, and calls MCP endpoints.
"""

import argparse
import json
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


def main():
    parser = argparse.ArgumentParser(
        description="Pegasus Galaxy MCP Tool & Game State Inspector",
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

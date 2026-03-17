"""
Doppelganger CLI
"""

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner

app = typer.Typer(
    name="doppelganger",
    help="🧬 Doppelganger AI — your local AI twin",
    no_args_is_help=True,
)
console = Console()


@app.command()
def start(
    host: str = typer.Option("0.0.0.0", help="API host"),
    port: int = typer.Option(8000, help="API port"),
    reload: bool = typer.Option(False, help="Enable hot reload (dev mode)"),
    no_voice: bool = typer.Option(False, help="Disable voice pipeline"),
    no_csi: bool = typer.Option(False, help="Disable WiFi CSI sensing"),
):
    """Start the Doppelganger daemon."""
    import uvicorn
    from .api import create_app

    if no_voice:
        import os
        os.environ["DOPPELGANGER_VOICE__TTS_ENGINE"] = "disabled"

    if no_csi:
        import os
        os.environ["DOPPELGANGER_PERCEPTION__ENABLE_WIFI_CSI"] = "false"

    console.print(Panel.fit(
        "[bold green]🧬 Doppelganger AI[/bold green]\n"
        f"Starting on [cyan]http://{host}:{port}[/cyan]\n"
        f"Dashboard: [cyan]http://localhost:{port}[/cyan]",
        border_style="green",
    ))

    uvicorn.run(
        "doppelganger.interfaces.api:get_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
        log_level="info",
    )


@app.command()
def chat(
    message: str = typer.Argument(..., help="Message to send"),
    stream: bool = typer.Option(True, help="Stream response"),
    host: str = typer.Option("localhost", help="API host"),
    port: int = typer.Option(8000, help="API port"),
):
    """Send a chat message to your running Doppelganger."""
    import httpx

    base = f"http://{host}:{port}"

    if stream:
        async def _stream():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST", f"{base}/chat/stream",
                    json={"message": message, "stream": True},
                ) as resp:
                    if resp.status_code != 200:
                        console.print(f"[red]Error: {resp.status_code}[/red]")
                        return
                    console.print("[dim]Doppelganger:[/dim] ", end="")
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            if data.get("text"):
                                console.print(data["text"], end="", highlight=False)
                            if data.get("done"):
                                console.print()
                                break
        asyncio.run(_stream())
    else:
        async def _chat():
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{base}/chat",
                    json={"message": message},
                )
                data = resp.json()
                console.print(f"\n[dim]Doppelganger:[/dim] {data.get('response', '')}\n")
        asyncio.run(_chat())


@app.command()
def memory(
    action: str = typer.Argument(..., help="search | timeline | store"),
    query: str = typer.Argument("", help="Search query or content to store"),
    host: str = typer.Option("localhost", help="API host"),
    port: int = typer.Option(8000, help="API port"),
    hours: int = typer.Option(24, help="Hours back for timeline"),
):
    """Interact with your memory graph."""
    import httpx

    base = f"http://{host}:{port}"

    async def _run():
        async with httpx.AsyncClient(timeout=30) as client:
            if action == "search":
                if not query:
                    console.print("[red]Provide a search query[/red]")
                    return
                resp = await client.post(f"{base}/memory/search", json={"query": query, "limit": 10})
                data = resp.json()
                table = Table(title=f"Memory search: '{query}'")
                table.add_column("Score", style="cyan", width=6)
                table.add_column("Content", style="white")
                table.add_column("Tags", style="dim")
                for r in data.get("results", []):
                    table.add_row(
                        str(round(r.get("score", 0), 2)),
                        r.get("content", "")[:80],
                        ", ".join(r.get("tags", [])),
                    )
                console.print(table)

            elif action == "timeline":
                resp = await client.get(f"{base}/memory/timeline", params={"hours": hours})
                data = resp.json()
                for node in data.get("nodes", []):
                    console.print(
                        f"[dim]{node['created_at']:.0f}[/dim] "
                        f"[cyan][{','.join(node['tags'])}][/cyan] "
                        f"{node['content'][:100]}"
                    )

            elif action == "store":
                if not query:
                    console.print("[red]Provide content to store[/red]")
                    return
                resp = await client.post(f"{base}/memory/store", json={"content": query})
                data = resp.json()
                console.print(f"[green]✓ Stored memory: {data['id'][:8]}[/green]")

    asyncio.run(_run())


@app.command()
def simulate(
    scenario: str = typer.Argument(..., help="Scenario to simulate"),
    worlds: int = typer.Option(3, help="Number of parallel worlds"),
    steps: int = typer.Option(4, help="Simulation steps per world"),
    host: str = typer.Option("localhost", help="API host"),
    port: int = typer.Option(8000, help="API port"),
):
    """Run a 'what if' world simulation."""
    import httpx

    async def _run():
        console.print(f"[dim]Simulating:[/dim] {scenario}")
        with console.status("[cyan]Running parallel worlds...[/cyan]"):
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"http://{host}:{port}/reasoning/simulate",
                    json={"scenario": scenario, "steps": steps, "n_worlds": worlds},
                )
                data = resp.json()

        console.print(Panel(
            f"[bold]Synthesis:[/bold]\n{data['synthesis']}\n\n"
            f"[bold]Best Action:[/bold] {data['best_action']}\n"
            f"[dim]Confidence: {data['confidence']:.0%} | "
            f"Elapsed: {data['elapsed_sec']}s[/dim]",
            title="🌐 World Simulation Result",
            border_style="cyan",
        ))

        table = Table(title="World Branches")
        table.add_column("#", width=3)
        table.add_column("Score", width=6)
        table.add_column("Outcome")
        for i, w in enumerate(data.get("worlds", []), 1):
            table.add_row(str(i), str(round(w["utility_score"], 2)), w["outcome"][:100])
        console.print(table)

    asyncio.run(_run())


@app.command()
def skills(
    host: str = typer.Option("localhost", help="API host"),
    port: int = typer.Option(8000, help="API port"),
):
    """List installed skills."""
    import httpx

    async def _run():
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"http://{host}:{port}/skills")
            data = resp.json()
        table = Table(title="Installed Skills")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("Version", width=8)
        for s in data.get("skills", []):
            table.add_row(s["name"], s.get("description", ""), s.get("version", ""))
        console.print(table)

    asyncio.run(_run())


def main():
    app()


if __name__ == "__main__":
    main()

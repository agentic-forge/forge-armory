"""CLI for Forge Armory - MCP protocol gateway."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="armory",
    help="MCP protocol gateway - aggregates tools from multiple MCP servers.",
    no_args_is_help=True,
)

backend_app = typer.Typer(
    name="backend",
    help="Manage backend MCP servers.",
    no_args_is_help=True,
)
app.add_typer(backend_app, name="backend")

console = Console()
error_console = Console(stderr=True)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        from forge_armory import __version__

        typer.echo(f"forge-armory v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """MCP protocol gateway - aggregates tools from multiple MCP servers."""


@app.command()
def info() -> None:
    """Show gateway information."""
    from forge_armory import __version__

    typer.echo(f"Forge Armory v{__version__}")
    typer.echo("MCP protocol gateway")


# ============================================================================
# Backend Commands
# ============================================================================


@backend_app.command("list")
def backend_list() -> None:
    """List all registered backends."""
    asyncio.run(_backend_list())


async def _backend_list() -> None:
    """Async implementation of backend list."""
    from forge_armory.db import BackendRepository, ToolRepository, async_session_maker

    async with async_session_maker() as session:
        repo = BackendRepository(session)
        tool_repo = ToolRepository(session)
        backends = await repo.list_all()

        if not backends:
            console.print("[dim]No backends registered.[/dim]")
            return

        table = Table(title="Registered Backends")
        table.add_column("Name", style="cyan")
        table.add_column("URL", style="dim")
        table.add_column("Prefix", style="green")
        table.add_column("Mount", style="yellow")
        table.add_column("Enabled", style="magenta")
        table.add_column("Tools", justify="right")

        for backend in backends:
            tools = await tool_repo.list_by_backend(backend.id)
            table.add_row(
                backend.name,
                backend.url or "[dim]stdio[/dim]",
                backend.effective_prefix,
                "✓" if backend.mount_enabled else "✗",
                "✓" if backend.enabled else "✗",
                str(len(tools)),
            )

        console.print(table)


@backend_app.command("add")
def backend_add(
    name: Annotated[str, typer.Argument(help="Unique name for the backend")],
    url: Annotated[str, typer.Option("--url", "-u", help="HTTP URL of the MCP server")],
    prefix: Annotated[
        str | None,
        typer.Option("--prefix", "-p", help="Tool prefix (defaults to name)"),
    ] = None,
    mount: Annotated[
        bool,
        typer.Option("--mount/--no-mount", help="Enable direct mount endpoint"),
    ] = True,
    enabled: Annotated[
        bool,
        typer.Option("--enabled/--disabled", help="Whether backend is enabled"),
    ] = True,
    timeout: Annotated[
        float,
        typer.Option("--timeout", "-t", help="Request timeout in seconds"),
    ] = 30.0,
) -> None:
    """Add a new backend MCP server."""
    asyncio.run(_backend_add(name, url, prefix, mount, enabled, timeout))


async def _backend_add(
    name: str,
    url: str,
    prefix: str | None,
    mount: bool,
    enabled: bool,
    timeout: float,
) -> None:
    """Async implementation of backend add."""
    from forge_armory.db import BackendCreate, BackendRepository, async_session_maker

    async with async_session_maker() as session:
        repo = BackendRepository(session)

        # Check if already exists
        existing = await repo.get_by_name(name)
        if existing:
            error_console.print(f"[red]Error:[/red] Backend '{name}' already exists.")
            raise typer.Exit(1)

        backend = await repo.create(
            BackendCreate(
                name=name,
                url=url,
                prefix=prefix,
                mount_enabled=mount,
                enabled=enabled,
                timeout=timeout,
            )
        )
        await session.commit()

        console.print(f"[green]✓[/green] Backend '{backend.name}' added.")
        console.print(f"  Prefix: {backend.effective_prefix}")
        console.print(f"  Mount: {'enabled' if backend.mount_enabled else 'disabled'}")
        console.print(f"  Status: {'enabled' if backend.enabled else 'disabled'}")


@backend_app.command("remove")
def backend_remove(
    name: Annotated[str, typer.Argument(help="Name of the backend to remove")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
) -> None:
    """Remove a backend MCP server."""
    if not force:
        confirm = typer.confirm(f"Remove backend '{name}'?")
        if not confirm:
            raise typer.Abort()

    asyncio.run(_backend_remove(name))


async def _backend_remove(name: str) -> None:
    """Async implementation of backend remove."""
    from forge_armory.db import BackendRepository, async_session_maker

    async with async_session_maker() as session:
        repo = BackendRepository(session)

        deleted = await repo.delete(name)
        if not deleted:
            error_console.print(f"[red]Error:[/red] Backend '{name}' not found.")
            raise typer.Exit(1)

        await session.commit()
        console.print(f"[green]✓[/green] Backend '{name}' removed.")


@backend_app.command("enable")
def backend_enable(
    name: Annotated[str, typer.Argument(help="Name of the backend to enable")],
) -> None:
    """Enable a backend."""
    asyncio.run(_backend_set_enabled(name, True))


@backend_app.command("disable")
def backend_disable(
    name: Annotated[str, typer.Argument(help="Name of the backend to disable")],
) -> None:
    """Disable a backend."""
    asyncio.run(_backend_set_enabled(name, False))


async def _backend_set_enabled(name: str, enabled: bool) -> None:
    """Async implementation of enable/disable."""
    from forge_armory.db import BackendRepository, async_session_maker

    async with async_session_maker() as session:
        repo = BackendRepository(session)

        backend = await repo.set_enabled(name, enabled)
        if not backend:
            error_console.print(f"[red]Error:[/red] Backend '{name}' not found.")
            raise typer.Exit(1)

        await session.commit()
        status = "enabled" if enabled else "disabled"
        console.print(f"[green]✓[/green] Backend '{name}' {status}.")


@backend_app.command("refresh")
def backend_refresh(
    name: Annotated[str, typer.Argument(help="Name of the backend to refresh")],
) -> None:
    """Refresh tools from a backend."""
    asyncio.run(_backend_refresh(name))


async def _backend_refresh(name: str) -> None:
    """Async implementation of backend refresh."""
    from forge_armory.db import BackendRepository, ToolRepository, async_session_maker
    from forge_armory.gateway import BackendConnection, BackendConnectionError

    async with async_session_maker() as session:
        repo = BackendRepository(session)
        backend = await repo.get_by_name(name)

        if not backend:
            error_console.print(f"[red]Error:[/red] Backend '{name}' not found.")
            raise typer.Exit(1)

        # Connect and fetch tools
        conn = BackendConnection(backend)
        try:
            with console.status(f"Connecting to {name}..."):
                await conn.connect()
                tools = await conn.list_tools()
        except BackendConnectionError as e:
            error_console.print(f"[red]Error:[/red] Failed to connect: {e}")
            raise typer.Exit(1) from None
        finally:
            await conn.disconnect()

        # Update database
        tool_repo = ToolRepository(session)
        await tool_repo.refresh_backend_tools(backend, tools)
        await session.commit()

        console.print(f"[green]✓[/green] Refreshed {len(tools)} tools from '{name}':")
        for tool in tools:
            console.print(f"  • {backend.effective_prefix}__{tool.name}")


# ============================================================================
# Metrics Command
# ============================================================================


@app.command("metrics")
def metrics(
    backend: Annotated[
        str | None,
        typer.Option("--backend", "-b", help="Filter by backend name"),
    ] = None,
) -> None:
    """Show tool call metrics."""
    asyncio.run(_metrics(backend))


async def _metrics(backend_name: str | None) -> None:
    """Async implementation of metrics."""
    from forge_armory.db import ToolCallRepository, async_session_maker

    async with async_session_maker() as session:
        repo = ToolCallRepository(session)
        stats = await repo.get_stats(backend_name=backend_name)

        if stats["total_calls"] == 0:
            console.print("[dim]No tool calls recorded.[/dim]")
            return

        title = f"Metrics for '{backend_name}'" if backend_name else "Overall Metrics"
        table = Table(title=title)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Total Calls", str(stats["total_calls"]))
        table.add_row("Successful", f"{stats['success_count']} ({stats['success_rate']:.1%})")
        table.add_row("Errors", str(stats["error_count"]))
        table.add_row("Avg Latency", f"{stats['avg_latency_ms']:.1f} ms")
        table.add_row("Min Latency", f"{stats['min_latency_ms']} ms")
        table.add_row("Max Latency", f"{stats['max_latency_ms']} ms")

        console.print(table)


# ============================================================================
# Serve Command
# ============================================================================


@app.command("serve")
def serve(
    host: Annotated[
        str | None,
        typer.Option("--host", "-h", help="Host to bind to"),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option("--port", "-p", help="Port to bind to"),
    ] = None,
    reload: Annotated[
        bool,
        typer.Option("--reload", help="Enable auto-reload for development"),
    ] = False,
) -> None:
    """Start the gateway server."""
    import uvicorn

    from forge_armory.settings import settings

    actual_host = host or settings.host
    actual_port = port or settings.port

    console.print("[green]Starting Forge Armory gateway...[/green]")
    console.print(f"  Host: {actual_host}")
    console.print(f"  Port: {actual_port}")
    console.print(f"  MCP endpoint: http://{actual_host}:{actual_port}/mcp")
    console.print(f"  Admin API: http://{actual_host}:{actual_port}/admin/")
    console.print()

    uvicorn.run(
        "forge_armory.server:app",
        host=actual_host,
        port=actual_port,
        reload=reload,
    )

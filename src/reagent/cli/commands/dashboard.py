import logging

import click
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


@click.command("dashboard")
@click.option("--port", default=8080, help="Port to listen on")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--docker", is_flag=True, help="Run via Docker Compose")
@click.option(
    "--podman",
    is_flag=True,
    help="Run via Podman Compose (Podman alternative to Docker)",
)
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically")
def dashboard_cmd(
    port: int,
    host: str,
    docker: bool,
    podman: bool,
    no_browser: bool,
) -> None:
    """Start the Reagent web dashboard."""
    if docker or podman:
        import subprocess

        if podman:
            cmd = ["podman", "compose", "up", "--build"]
            console.print("Starting dashboard via Podman Compose…")
        else:
            cmd = ["docker", "compose", "up", "--build"]
            console.print("Starting dashboard via Docker Compose…")

        subprocess.run(cmd, check=False)  # noqa: S603
        return

    try:
        import uvicorn

        from reagent.api.app import create_app
    except ImportError:
        console.print(
            "[red]Dashboard dependencies not installed.[/red]\n"
            "Install them with:\n"
            "  [bold]uv sync --extra dashboard[/bold]  (from source)\n"
            "  [bold]pip install 'reagent[dashboard]'[/bold]  (from PyPI)"
        )
        raise SystemExit(1) from None

    url = f"http://{host}:{port}"
    console.print(f"Starting Reagent Dashboard at [bold cyan]{url}[/bold cyan]")
    console.print("Press [bold]Ctrl+C[/bold] to stop.\n")

    if not no_browser:
        import threading
        import webbrowser

        def _open() -> None:
            import time

            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="warning")

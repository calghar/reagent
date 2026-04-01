import argparse
import logging

import uvicorn

from reagent.api.app import create_app

logger = logging.getLogger(__name__)


def main() -> None:
    """Parse CLI args and start uvicorn."""
    parser = argparse.ArgumentParser(description="Reagent dashboard API server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8080, help="Bind port")
    args = parser.parse_args()

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

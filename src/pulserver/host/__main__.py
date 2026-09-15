"""Run the host daemon: ``python -m pulserver.host --base DIR --socket PATH --plugins DIR``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from ._daemon import HostDaemon


def _interrupt(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m pulserver.host")
    parser.add_argument(
        "--base", type=Path, required=True, help="directory holding bucket/"
    )
    parser.add_argument(
        "--socket", type=Path, required=True, help="Unix socket to listen on"
    )
    parser.add_argument(
        "--plugins", type=Path, required=True, help="directory of <plugin>.py"
    )
    parser.add_argument(
        "--workers", type=int, default=2, help="design worker processes"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    daemon = HostDaemon(args.base, args.plugins, workers=args.workers)
    args.socket.unlink(missing_ok=True)
    signal.signal(signal.SIGTERM, _interrupt)
    try:
        asyncio.run(daemon.serve(args.socket))
    except KeyboardInterrupt:
        pass
    finally:
        daemon.shutdown()


if __name__ == "__main__":
    main()

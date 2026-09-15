"""Run the reconstruction proxy: ``python -m pulserver.vre --base DIR --port N --plugins DIR``."""

from __future__ import annotations

import argparse
import logging
import signal
from pathlib import Path

from ._proxy import ReconProxy


def _interrupt(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m pulserver.vre")
    parser.add_argument(
        "--base", type=Path, required=True, help="directory holding bucket/"
    )
    parser.add_argument("--port", type=int, required=True, help="TCP port to listen on")
    parser.add_argument(
        "--plugins", type=Path, required=True, help="directory of <plugin>.py"
    )
    parser.add_argument(
        "--slots",
        type=int,
        default=None,
        help="series reconstructed at once; memory decides when unset",
    )
    parser.add_argument(
        "--spares", type=int, default=1, help="warm worker processes kept waiting"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    proxy = ReconProxy(args.base, args.plugins, slots=args.slots, spares=args.spares)
    proxy.bind(args.port)
    signal.signal(signal.SIGTERM, _interrupt)
    try:
        proxy.serve()
    except KeyboardInterrupt:
        pass
    finally:
        proxy.close()


if __name__ == "__main__":
    main()

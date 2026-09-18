from __future__ import annotations

import argparse
import asyncio
import os
import sys

from letterbox_mcp.mailbox import Mailbox
from letterbox_mcp.server import run_stdio


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="letterbox-mcp")
    parser.add_argument(
        "--mailbox",
        default=os.environ.get("LETTERBOX_DIR"),
        help="Mailbox root (or LETTERBOX_DIR). Stage one tests pass a fixture path.",
    )
    parser.add_argument(
        "--agent",
        default=os.environ.get("LETTERBOX_AGENT"),
        help="Mailbox owner (or LETTERBOX_AGENT).",
    )
    args = parser.parse_args(argv)
    if not args.mailbox or not args.agent:
        print("letterbox-mcp: --mailbox/LETTERBOX_DIR and --agent/LETTERBOX_AGENT are required", file=sys.stderr)
        raise SystemExit(2)
    mailbox = Mailbox(args.mailbox, args.agent)
    asyncio.run(run_stdio(mailbox))


if __name__ == "__main__":
    main()

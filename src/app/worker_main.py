"""
arq worker entrypoint for Python 3.14+.

Python 3.14 removed implicit event loop creation.
arq 0.27.0 calls asyncio.get_event_loop() in Worker.__init__ before any
loop exists, raising RuntimeError.  Setting an explicit loop first fixes it.
"""

import asyncio
import sys

asyncio.set_event_loop(asyncio.new_event_loop())

from arq.cli import cli  # noqa: E402

sys.exit(cli())

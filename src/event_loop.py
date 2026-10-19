"""
Runs a single asyncio event loop forever in a background thread.
Cancels all pending tasks cleanly upon shutdown so no queued frames run after exit.
"""

from __future__ import annotations

import asyncio
import threading


class BackgroundLoop:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_forever, daemon=True, name="BackgroundAsyncLoop")

    def _run_forever(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def start(self):
        self._thread.start()

    def run(self, coro):
        """Schedule a coroutine on the background loop from any thread.
        Returns a concurrent.futures.Future you can call .result() on.
        """
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self):
        def _cancel_and_stop():
            for task in asyncio.all_tasks(self._loop):
                task.cancel()
            self._loop.stop()

        self._loop.call_soon_threadsafe(_cancel_and_stop)
        self._thread.join(timeout=2)

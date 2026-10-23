from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import math


class Overloaded(RuntimeError):
    pass


class WorkerPool:
    """Bound active calls and queued calls independently, with cancellation cleanup."""

    def __init__(self, workers: int = 2, waiting: int = 4):
        if workers < 1 or waiting < 1:
            raise ValueError("workers and waiting must be positive")
        self.queue = asyncio.Queue(maxsize=waiting)
        self.tasks = [asyncio.create_task(self._worker()) for _ in range(workers)]
        self.closed = False

    async def _worker(self):
        while True:
            operation, future = await self.queue.get()
            try:
                if future.cancelled():
                    continue
                task = asyncio.create_task(operation())
                def cancel_operation(completed, running=task):
                    if completed.cancelled() and not running.done():
                        running.cancel()
                future.add_done_callback(cancel_operation)
                try:
                    result = await task
                    if not future.done():
                        future.set_result(result)
                except asyncio.CancelledError:
                    if not future.done():
                        future.cancel()
                except Exception as exc:
                    if not future.done():
                        # Keep operation frames without exposing the live worker frame.
                        future.set_exception(exc.with_traceback(exc.__traceback__.tb_next))
            finally:
                self.queue.task_done()

    async def submit(self, operation: Callable[[], Awaitable]):
        if self.closed:
            raise RuntimeError("pool is closed")
        future = asyncio.get_running_loop().create_future()
        try:
            self.queue.put_nowait((operation, future))
        except asyncio.QueueFull:
            raise Overloaded("queue is full") from None
        return await future

    async def close(self):
        self.closed = True
        await self.queue.join()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


@dataclass(frozen=True)
class Sample:
    latency_seconds: float
    correct: bool
    failed: bool = False
    cost: float = 0.0


def report(samples: list[Sample], elapsed: float, *, environment: dict) -> dict:
    if elapsed <= 0 or not samples:
        raise ValueError("report requires samples and positive elapsed time")
    latencies = sorted(sample.latency_seconds for sample in samples)
    percentile = lambda p: latencies[max(0, math.ceil(p * len(latencies)) - 1)]
    return {
        "requests": len(samples), "qps": len(samples) / elapsed,
        "p50": percentile(.5), "p95": percentile(.95),
        "failure_rate": sum(sample.failed for sample in samples) / len(samples),
        "quality": sum(sample.correct and not sample.failed for sample in samples) / len(samples),
        "cost": sum(sample.cost for sample in samples), "environment": environment,
    }

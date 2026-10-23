# 索引更新与运行成本 v3：有界排队与取消

从自己的 v2 继续。无限制 create_task 会把慢查询积压在内存中。本版新增 WorkerPool：workers 限制执行中任务，waiting 限制等待队列，队满立即抛 Overloaded。只接收可取消的 async 操作，不把同步 CPU 工作自动变成非阻塞任务。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 给每次提交一份结果与取消句柄

submit 创建 Future，put_nowait 防止提交者又形成隐形等待队列。worker 从队列取出 `(operation,future)` 后创建执行任务；调用方取消 future 时 callback 取消这次任务。任务失败传回提交者，worker 继续服务。传递异常时移除 traceback 最外层的活动 worker 栈帧，保留操作本身的错误位置；否则调用者清理 traceback（例如 Python 3.12 的 unittest.assertRaises）可能清掉仍在等待新任务的 worker。每个 get 都在 finally 中 task_done，包括已取消的排队项。close 停止接收、排空队列，再取消空闲 workers；它是合作式关闭，永不结束的操作仍需自己的超时。

`labs/operations/serving.py` — checkpoint：将这个文件完整写为下面的代码。

```python
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


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
```

```bash
uv run python - <<'PY'
import asyncio
from labs.operations.serving import Overloaded, WorkerPool

async def main():
    pool = WorkerPool(workers=1, waiting=1)
    started, gate = asyncio.Event(), asyncio.Event()
    async def block():
        started.set()
        await gate.wait()
        return 7
    first = asyncio.create_task(pool.submit(block))
    await started.wait()
    second = asyncio.create_task(pool.submit(block))
    await asyncio.sleep(0)
    try:
        await pool.submit(block)
    except Overloaded:
        pass
    else:
        raise AssertionError("unbounded queue")
    first.cancel()
    try:
        await first
    except asyncio.CancelledError:
        pass
    gate.set()
    assert await second == 7
    async def fail():
        raise ValueError("injected")
    try:
        await pool.submit(fail)
    except ValueError:
        pass
    assert await pool.submit(block) == 7
    await pool.close()
    assert all(task.done() for task in pool.tasks)
    print("overload, cancellation, failure recovery and close passed")

asyncio.run(asyncio.wait_for(main(), timeout=5))
PY
```

预期打印 `overload, cancellation, failure recovery and close passed`。Event 让“一个运行、一个等待”确定出现；第三个请求被拒绝，取消后后续请求完成，故障不杀死 worker。外层五秒超时用于让死锁检查明确失败。

## 本版检查点

index.py 沿用 v2，serving.py 包含 Overloaded/WorkerPool。取消传播是合作式的，不是进程强杀；需要阻塞库或模型计算时应另设执行隔离。下一版同时报告成功率、质量与吞吐，避免把拒绝请求从分母删掉。

需要对照时可阅读[本版参考源码](../../../reference/labs/operations/checkpoints/v3/serving.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。

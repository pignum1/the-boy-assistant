"""Scheduler：优先级任务调度器

职责：
1. 任务队列管理（CRITICAL / HIGH / NORMAL / LOW 优先级）
2. 并发控制（全局最大并发 + 每 Team 最大并行）
3. RateLimiter 集成（检查 TPM 余量）
4. 防饥饿（aging 算法：等待超时临时提升优先级）
5. 后台调度循环

实现方式：asyncio.PriorityQueue + Python 原生（无外部依赖）
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Optional

from app.adapters.llm.rate_limiter import TokenBucket

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass(order=True)
class ScheduledTask:
    """调度队列中的任务条目"""
    sort_key: tuple[int, float] = field(compare=True)   # (effective_priority, enqueue_time)
    task_id: str = field(compare=False)
    task_func: Callable = field(compare=False)
    args: tuple = field(compare=False, default=())
    kwargs: dict = field(compare=False, default_factory=dict)
    priority: Priority = field(compare=False, default=Priority.NORMAL)
    team_id: Optional[str] = field(compare=False, default=None)
    enqueue_time: float = field(compare=False, default=0.0)
    aging_threshold: float = field(compare=False, default=60.0)  # 超过此时间提升优先级


class Scheduler:
    """优先级任务调度器"""

    def __init__(
        self,
        max_concurrent: int = 10,
        max_per_team: int = 3,
        aging_seconds: int = 60,
    ):
        self._queue: asyncio.PriorityQueue[ScheduledTask] = asyncio.PriorityQueue()
        self._rate_limiter = TokenBucket(rpm=60, tpm=100000)
        self._max_concurrent = max_concurrent
        self._max_per_team = max_per_team
        self._aging_seconds = aging_seconds

        self._running: int = 0
        self._team_running: dict[str, int] = {}  # team_id → count
        self._lock = asyncio.Lock()
        self._loop_task: Optional[asyncio.Task] = None
        self._active_tasks: dict[str, asyncio.Task] = {}

    def enqueue(
        self,
        task_func: Callable[..., Coroutine],
        task_id: str,
        priority: Priority = Priority.NORMAL,
        team_id: Optional[str] = None,
        *args,
        **kwargs,
    ) -> str:
        """入队任务"""
        now = time.time()
        scheduled = ScheduledTask(
            sort_key=(priority, now),
            task_id=task_id,
            task_func=task_func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            team_id=team_id,
            enqueue_time=now,
        )
        self._queue.put_nowait(scheduled)
        logger.info(f"Scheduler: enqueued task={task_id} priority={priority.name} team={team_id}")
        return task_id

    async def dequeue(self) -> Optional[ScheduledTask]:
        """取出最高优先级任务（含 aging 调整）"""
        try:
            scheduled = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

        # Aging：等待超时则提升优先级
        now = time.time()
        wait_time = now - scheduled.enqueue_time
        if wait_time > scheduled.aging_threshold and scheduled.priority > Priority.CRITICAL:
            new_priority = max(Priority.CRITICAL, Priority(scheduled.priority - 1))
            scheduled.sort_key = (new_priority, scheduled.enqueue_time)
            logger.info(
                f"Scheduler: aging task={scheduled.task_id} "
                f"{scheduled.priority.name} → {new_priority.name} "
                f"(waited {wait_time:.0f}s)"
            )

        return scheduled

    async def _can_execute(self, scheduled: ScheduledTask) -> bool:
        """检查是否可以执行（并发 + 限流）"""
        async with self._lock:
            if self._running >= self._max_concurrent:
                return False
            if scheduled.team_id:
                team_count = self._team_running.get(scheduled.team_id, 0)
                if team_count >= self._max_per_team:
                    return False
        # 检查 RateLimiter 余量
        if self._rate_limiter.rpm_remaining < 1:
            return False
        return True

    async def _execute(self, scheduled: ScheduledTask) -> None:
        """执行单个任务"""
        async with self._lock:
            self._running += 1
            if scheduled.team_id:
                self._team_running[scheduled.team_id] = (
                    self._team_running.get(scheduled.team_id, 0) + 1
                )

        try:
            logger.info(f"Scheduler: executing task={scheduled.task_id}")
            await scheduled.task_func(*scheduled.args, **scheduled.kwargs)
            logger.info(f"Scheduler: task={scheduled.task_id} completed")
        except Exception as e:
            logger.error(f"Scheduler: task={scheduled.task_id} failed: {e}")
        finally:
            async with self._lock:
                self._running -= 1
                if scheduled.team_id:
                    self._team_running[scheduled.team_id] = max(
                        0, self._team_running.get(scheduled.team_id, 0) - 1
                    )

    async def run_scheduler_loop(self, poll_interval: float = 1.0) -> None:
        """主调度循环"""
        logger.info("Scheduler loop started")
        while True:
            try:
                scheduled = await self.dequeue()
                if not scheduled:
                    await asyncio.sleep(poll_interval)
                    continue

                if not await self._can_execute(scheduled):
                    # 放回队列
                    self._queue.put_nowait(scheduled)
                    await asyncio.sleep(poll_interval)
                    continue

                # 异步执行
                task = asyncio.create_task(self._execute(scheduled))
                self._active_tasks[scheduled.task_id] = task
                task.add_done_callback(
                    lambda t, tid=scheduled.task_id: self._active_tasks.pop(tid, None)
                )

            except asyncio.CancelledError:
                logger.info("Scheduler loop cancelled")
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(poll_interval)

    def start(self) -> None:
        """启动后台调度循环"""
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self.run_scheduler_loop())
            logger.info("Scheduler background loop started")

    async def stop(self) -> None:
        """停止调度循环"""
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        logger.info("Scheduler stopped")

    def get_status(self) -> dict:
        """获取调度器状态"""
        return {
            "running": self._running,
            "queued": self._queue.qsize(),
            "max_concurrent": self._max_concurrent,
            "max_per_team": self._max_per_team,
            "active_teams": dict(self._team_running),
            "rpm_remaining": round(self._rate_limiter.rpm_remaining, 1),
            "tpm_remaining": round(self._rate_limiter.tpm_remaining, 1),
        }


# Global scheduler
scheduler = Scheduler()

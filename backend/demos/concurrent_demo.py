"""并发演示：展示 Agent Pool + Scheduler + Blackboard 的协作能力

使用方式：python -m demos.concurrent_demo

需要 PostgreSQL 和 Redis 运行中。
"""

import asyncio
import logging
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def demo_agent_pool():
    """演示 Agent Pool 的能力匹配与 acquire/release"""
    from app.core.database import async_session
    from app.services.agent_pool import AgentPool
    from app.models.agent import Agent
    from app.models.persona import Persona
    from app.models.model import Model

    pool = AgentPool()

    async with async_session() as db:
        # 创建测试数据
        persona = Persona(name="demo-coder", system_prompt="demo", capabilities={"coding": True, "debugging": True})
        model = Model(display_name="demo-model", provider="test", model_name="test")
        db.add_all([persona, model])
        await db.commit()
        await db.refresh(persona)
        await db.refresh(model)

        agent = Agent(name="DemoCoder", persona_id=persona.id, default_model_id=model.id)
        db.add(agent)
        await db.commit()
        await db.refresh(agent)

        # 注册到 Pool
        await pool.register(db, agent)
        logger.info(f"Pool status: {pool.get_status()}")

        # Acquire
        entry = await pool.acquire(agent_id=str(agent.id), role_slot="coder", task_id="demo-task")
        logger.info(f"Acquired: {entry.agent_name} status={entry.status}")

        # 第二次 acquire 应该失败（已 busy）
        entry2 = await pool.acquire(agent_id=str(agent.id))
        logger.info(f"Second acquire (should be None): {entry2}")

        # Release
        await pool.release(str(agent.id))
        logger.info(f"After release: {pool.get_status()}")

        # 清理
        await db.delete(agent)
        await db.delete(persona)
        await db.delete(model)
        await db.commit()

    logger.info("Agent Pool demo completed\n")


async def demo_scheduler():
    """演示 Scheduler 的优先级调度"""
    from app.services.scheduler import Scheduler, Priority

    scheduler = Scheduler(max_concurrent=2, max_per_team=1)

    execution_log = []

    async def mock_task(name: str, duration: float = 0.1):
        execution_log.append(f"start:{name}")
        await asyncio.sleep(duration)
        execution_log.append(f"end:{name}")

    # 入队不同优先级的任务
    scheduler.enqueue(mock_task, "low-1", Priority.LOW, "team-a", name="low-1")
    scheduler.enqueue(mock_task, "high-1", Priority.HIGH, "team-a", name="high-1")
    scheduler.enqueue(mock_task, "normal-1", Priority.NORMAL, "team-b", name="normal-1")
    scheduler.enqueue(mock_task, "critical-1", Priority.CRITICAL, "team-b", name="critical-1")

    logger.info(f"Scheduler status: {scheduler.get_status()}")

    # 手动执行几个
    for _ in range(4):
        task = await scheduler.dequeue()
        if task:
            logger.info(f"Dequeued: {task.task_id} priority={task.priority.name}")
            await scheduler._execute(task)

    logger.info(f"Execution log: {execution_log}")
    logger.info("Scheduler demo completed\n")


async def demo_blackboard():
    """演示 Blackboard 的发布/订阅"""
    from app.services.blackboard import Blackboard, EventType

    bb = Blackboard()
    await bb.connect()

    received = []

    async def on_event(event):
        received.append(event)
        logger.info(f"Received event: {event.type.value} payload={event.payload}")

    # 订阅
    await bb.sub(team_id="team-1", callback=on_event)

    # 发布
    await bb.pub(
        EventType.TASK_UPDATE,
        {"task_id": "task-123", "status": "completed"},
        team_id="team-1",
        source="agent-1",
    )

    await bb.pub(
        EventType.AGENT_STATUS,
        {"agent_id": "agent-1", "status": "idle"},
        team_id="team-1",
    )

    # 等待回调
    await asyncio.sleep(0.1)

    logger.info(f"Received {len(received)} events")
    await bb.disconnect()
    logger.info("Blackboard demo completed\n")


async def main():
    logger.info("=== Concurrent Demo ===\n")

    logger.info("--- 1. Agent Pool ---")
    await demo_agent_pool()

    logger.info("--- 2. Scheduler ---")
    await demo_scheduler()

    logger.info("--- 3. Blackboard ---")
    await demo_blackboard()

    logger.info("=== All demos completed ===")


if __name__ == "__main__":
    asyncio.run(main())

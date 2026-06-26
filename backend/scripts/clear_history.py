"""清空会话历史"""
import asyncio
from sqlalchemy import text
from app.core.database import async_session

async def main():
    async with async_session() as session:
        # 删除消息
        r1 = await session.execute(text('DELETE FROM messages'))
        # 删除会话
        r2 = await session.execute(text('DELETE FROM sessions'))
        # 删除任务
        r3 = await session.execute(text('DELETE FROM tasks'))
        # 删除工作流实例
        r4 = await session.execute(text('DELETE FROM workflow_instances'))
        # 删除节点执行记录
        r5 = await session.execute(text('DELETE FROM node_executions'))

        await session.commit()
        print(f'✅ 已删除历史记录:')
        print(f'   - {r1.rowcount} 条消息')
        print(f'   - {r2.rowcount} 个会话')
        print(f'   - {r3.rowcount} 个任务')
        print(f'   - {r4.rowcount} 个工作流实例')
        print(f'   - {r5.rowcount} 条节点执行记录')

if __name__ == "__main__":
    asyncio.run(main())

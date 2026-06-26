import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.mcp_server import MCPServer
from app.models.tool import Tool
from app.schemas.tool import (
    MCPServerCreate, MCPServerUpdate, MCPServerResponse,
    DiscoverResult, TestConnectionResult,
)
from app.services.mcp_client import mcp_client

router = APIRouter()


# ── Helper ──

def _server_response(server: MCPServer, tool_count: int = 0) -> MCPServerResponse:
    return MCPServerResponse(
        id=server.id,
        name=server.name,
        transport=server.transport,
        url=server.url,
        command=server.command,
        args=server.args,
        env=server.env,
        api_key_ref=server.api_key_ref,
        status=server.status,
        config=server.config,
        tool_count=tool_count,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


# ── CRUD ──

@router.get("")
async def list_servers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """列出 MCP 服务器（分页，含工具数量）"""
    # 总数
    count_result = await db.execute(select(func.count(MCPServer.id)))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(MCPServer).order_by(MCPServer.created_at).offset(skip).limit(limit)
    )
    servers = list(result.scalars().all())

    # 批量查询工具数量
    server_ids = [s.id for s in servers]
    counts = {}
    if server_ids:
        count_result = await db.execute(
            select(Tool.server_id, func.count(Tool.id))
            .where(Tool.server_id.in_(server_ids))
            .group_by(Tool.server_id)
        )
        counts = {row[0]: row[1] for row in count_result.all()}

    return {
        "items": [_server_response(s, counts.get(s.id, 0)) for s in servers],
        "total": total,
    }


@router.post("", response_model=MCPServerResponse, status_code=201)
async def create_server(data: MCPServerCreate, db: AsyncSession = Depends(get_db)):
    """注册 MCP 服务器"""
    existing = await db.execute(
        select(MCPServer).where(MCPServer.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Server with this name already exists")

    server = MCPServer(
        name=data.name,
        transport=data.transport,
        url=data.url,
        command=data.command,
        args=data.args,
        env=data.env,
        api_key_ref=data.api_key_ref,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return _server_response(server, 0)


@router.get("/{server_id}", response_model=MCPServerResponse)
async def get_server(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取服务器详情（含工具数量）"""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    count_result = await db.execute(
        select(func.count(Tool.id)).where(Tool.server_id == server_id)
    )
    tool_count = count_result.scalar() or 0

    return _server_response(server, tool_count)


@router.put("/{server_id}", response_model=MCPServerResponse)
async def update_server(server_id: uuid.UUID, data: MCPServerUpdate, db: AsyncSession = Depends(get_db)):
    """更新服务器配置"""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(server, k, v)

    await db.commit()
    await db.refresh(server)

    count_result = await db.execute(
        select(func.count(Tool.id)).where(Tool.server_id == server_id)
    )
    tool_count = count_result.scalar() or 0

    return _server_response(server, tool_count)


@router.delete("/{server_id}", status_code=204)
async def delete_server(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除 MCP 服务器（级联删除关联工具）"""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    await db.delete(server)
    await db.commit()
# ── Discover & Test ──

@router.post("/{server_id}/discover", response_model=DiscoverResult)
async def discover_tools(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """连接 MCP 服务器并同步工具列表"""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    try:
        discovered_tools = await mcp_client.connect_and_list_tools(server)
    except Exception as e:
        server.status = "error"
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Failed to connect to MCP server: {str(e)}")

    # 查询现有工具
    result = await db.execute(
        select(Tool).where(Tool.server_id == server_id)
    )
    existing_tools = {t.name: t for t in result.scalars().all()}

    discovered_names = {t["name"] for t in discovered_tools}
    existing_names = set(existing_tools.keys())

    added = 0
    removed = 0

    # 新增工具
    for tool_data in discovered_tools:
        if tool_data["name"] not in existing_names:
            new_tool = Tool(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                param_schema=tool_data.get("inputSchema", {}),
                server_id=server_id,
            )
            db.add(new_tool)
            added += 1

    # 删除已不存在的工具
    for name in existing_names - discovered_names:
        await db.delete(existing_tools[name])
        removed += 1

    # 更新服务器状态
    server.status = "connected"
    await db.commit()

    return DiscoverResult(
        added=added,
        removed=removed,
        unchanged=len(discovered_names & existing_names),
        tools=list(discovered_names),
    )


@router.post("/{server_id}/test", response_model=TestConnectionResult)
async def test_connection(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """测试 MCP 服务器连接"""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    try:
        success = await mcp_client.test_connection(server)
        if success:
            server.status = "connected"
            await db.commit()
            return TestConnectionResult(success=True, message="连接成功")
        else:
            server.status = "error"
            await db.commit()
            return TestConnectionResult(success=False, message="无法连接")
    except Exception as e:
        server.status = "error"
        await db.commit()
        return TestConnectionResult(success=False, message=str(e))


# ── Server Tools ──

from app.schemas.tool import ToolResponse


@router.get("/{server_id}/tools", response_model=list[ToolResponse])
async def list_server_tools(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取指定服务器的工具列表"""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    result = await db.execute(
        select(Tool).where(Tool.server_id == server_id).order_by(Tool.name)
    )
    return list(result.scalars().all())


@router.put("/{server_id}/tools/{tool_id}/toggle", response_model=ToolResponse)
async def toggle_tool(server_id: uuid.UUID, tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """启用/禁用工具"""
    tool = await db.get(Tool, tool_id)
    if not tool or tool.server_id != server_id:
        raise HTTPException(status_code=404, detail="Tool not found")

    tool.is_enabled = not tool.is_enabled
    await db.commit()
    await db.refresh(tool)
    return tool


@router.put("/{server_id}/tools/{tool_id}/approval", response_model=ToolResponse)
async def toggle_approval(server_id: uuid.UUID, tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """切换工具是否需要审批"""
    tool = await db.get(Tool, tool_id)
    if not tool or tool.server_id != server_id:
        raise HTTPException(status_code=404, detail="Tool not found")

    tool.requires_approval = not tool.requires_approval
    await db.commit()
    await db.refresh(tool)
    return tool

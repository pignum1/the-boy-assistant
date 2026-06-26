"""SOP Service：SOP 定义管理 + YAML 导入/导出

预置模板已移至 sop_presets.py
"""

import logging
import uuid
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sop import SOP

logger = logging.getLogger(__name__)


class SOPService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_sop(
        self,
        team_id: uuid.UUID,
        name: str,
        nodes: list[dict],
        edges: list[dict],
        description: Optional[str] = None,
        format: str = "yaml",
        version: str = "1.0",
        is_template: bool = False,
    ) -> SOP:
        sop = SOP(
            team_id=team_id,
            name=name,
            description=description,
            nodes=nodes,
            edges=edges,
            format=format,
            version=version,
            is_template=is_template,
        )
        self.db.add(sop)
        await self.db.commit()
        await self.db.refresh(sop)
        logger.info(f"SOP created: {name} v{version} ({len(nodes)} nodes, {len(edges)} edges)")
        return sop

    async def get_sop(self, sop_id: uuid.UUID) -> Optional[SOP]:
        return await self.db.get(SOP, sop_id)

    async def list_sops(self, team_id: Optional[uuid.UUID] = None) -> list[SOP]:
        q = select(SOP).order_by(SOP.created_at)
        if team_id:
            q = q.where(SOP.team_id == team_id)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def update_sop(self, sop_id: uuid.UUID, **kwargs) -> Optional[SOP]:
        sop = await self.get_sop(sop_id)
        if not sop:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(sop, k):
                setattr(sop, k, v)
        await self.db.commit()
        await self.db.refresh(sop)
        return sop

    async def delete_sop(self, sop_id: uuid.UUID) -> bool:
        sop = await self.get_sop(sop_id)
        if not sop:
            return False
        await self.db.delete(sop)
        await self.db.commit()
        return True

    async def import_from_yaml(self, team_id: uuid.UUID, yaml_content: str) -> SOP:
        """Import SOP from YAML definition"""
        data = yaml.safe_load(yaml_content)

        name = data.get("name", data.get("sopId", "unnamed"))
        description = data.get("description", "")
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        version = data.get("version", "1.0")

        # Validate nodes
        for node in nodes:
            if "id" not in node or "type" not in node:
                raise ValueError(f"Node missing 'id' or 'type': {node}")
            valid_types = {"agent_action", "hitl", "validation", "start", "end", "condition"}
            if node["type"] not in valid_types:
                raise ValueError(f"Invalid node type '{node['type']}' in node {node['id']}")

        # Validate edges
        node_ids = {n["id"] for n in nodes}
        for edge in edges:
            if edge.get("from") not in node_ids:
                raise ValueError(f"Edge 'from' references unknown node: {edge.get('from')}")
            if edge.get("to") not in node_ids:
                raise ValueError(f"Edge 'to' references unknown node: {edge.get('to')}")

        return await self.create_sop(
            team_id=team_id,
            name=name,
            nodes=nodes,
            edges=edges,
            description=description,
            version=version,
            is_template=True,
        )

    def export_to_yaml(self, sop: SOP) -> str:
        """Export SOP to YAML format"""
        data = {
            "sopId": str(sop.id),
            "name": sop.name,
            "description": sop.description or "",
            "version": sop.version,
            "nodes": sop.nodes or [],
            "edges": sop.edges or [],
        }
        return yaml.dump(data, allow_unicode=True, default_flow_style=False)

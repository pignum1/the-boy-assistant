"""Skill Registry — 文件系统扫描、Git 安装、Zip 解压"""

import io
import logging
import os
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill

logger = logging.getLogger(__name__)

# 技能根目录（相对于 backend/）
SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent / "skills"


def parse_skill_md(content: str) -> dict:
    """解析 SKILL.md — 提取 YAML frontmatter + markdown body"""
    result = {"frontmatter": {}, "instructions": "", "output_format": ""}

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                result["frontmatter"] = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                pass
            result["instructions"] = parts[2].strip()
    else:
        result["instructions"] = content.strip()

    return result


def parse_config_yaml(content: str) -> dict:
    """解析 config.yaml"""
    try:
        return yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return {}


# ── Filesystem helpers ──

def _safe_name(name: str) -> str:
    """将 skill 名称转为安全的目录名"""
    return name.lower().replace(" ", "-").strip()


def _read_skill_from_dir(skill_dir: Path) -> Optional[dict]:
    """读取一个 skill 目录，返回 {name, description, version, skill_md, config_yaml} 或 None"""
    md_path = skill_dir / "SKILL.md"
    if not md_path.exists():
        return None

    skill_md = md_path.read_text(encoding="utf-8")
    parsed = parse_skill_md(skill_md)
    fm = parsed["frontmatter"]

    config_yaml = None
    config_path = skill_dir / "config.yaml"
    if config_path.exists():
        config_yaml = config_path.read_text(encoding="utf-8")

    return {
        "name": fm.get("name") or skill_dir.name,
        "description": fm.get("description", ""),
        "version": fm.get("version", "1.0.0"),
        "skill_md": skill_md,
        "config_yaml": config_yaml,
    }


# ── SkillRegistry ──

class SkillRegistry:
    """Skill 注册与管理"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Scan filesystem ──

    async def scan_skills_dir(self) -> dict:
        """扫描 skills/ 目录，同步到 DB 索引
        Returns: {"added": int, "updated": int, "removed": int, "skills": list[str]}
        """
        if not SKILLS_ROOT.exists():
            SKILLS_ROOT.mkdir(parents=True, exist_ok=True)

        # 获取文件系统中的 skill 目录
        fs_skill_names = set()
        fs_skills = []
        for entry in sorted(SKILLS_ROOT.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                info = _read_skill_from_dir(entry)
                if info:
                    info["dir_name"] = entry.name
                    info["rel_path"] = f"skills/{entry.name}"
                    fs_skills.append(info)
                    fs_skill_names.add(info["name"])

        # 获取 DB 中已有的 skill
        result = await self.db.execute(select(Skill))
        db_skills = {s.name: s for s in result.scalars().all()}

        added, updated, removed = 0, 0, 0

        # 新增 / 更新
        for info in fs_skills:
            skill = db_skills.pop(info["name"], None)
            if skill is None:
                skill = Skill(
                    name=info["name"],
                    path=info["rel_path"],
                    description=info["description"],
                    version=info["version"],
                    source="manual",
                )
                self.db.add(skill)
                added += 1
            else:
                skill.path = info["rel_path"]
                skill.description = info["description"]
                skill.version = info["version"]
                updated += 1

        # 删除 — DB 中有但文件系统没有的
        for stale in db_skills.values():
            await self.db.delete(stale)
            removed += 1

        await self.db.commit()

        all_names = [s["name"] for s in fs_skills]
        logger.info(f"Skills scan complete: +{added} ~{updated} -{removed}, total={len(all_names)}")
        return {"added": added, "updated": updated, "removed": removed, "skills": all_names}

    # ── Install from git ──

    async def install_from_git(self, git_url: str, name: Optional[str] = None, branch: Optional[str] = None) -> Skill:
        """从 Git 仓库安装 skill"""
        if not SKILLS_ROOT.exists():
            SKILLS_ROOT.mkdir(parents=True, exist_ok=True)

        # 从 URL 推断目录名
        dir_name = name or _safe_name(git_url.rstrip("/").split("/")[-1].replace(".git", ""))
        target_dir = SKILLS_ROOT / dir_name

        if target_dir.exists():
            raise ValueError(f"Skill directory '{dir_name}' already exists. Remove it first or use a different name.")

        # git clone
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [git_url, str(target_dir)]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        except subprocess.CalledProcessError as e:
            # 清理失败的目录
            if target_dir.exists():
                shutil.rmtree(target_dir)
            raise ValueError(f"git clone failed: {e.stderr.strip()}")
        except subprocess.TimeoutExpired:
            if target_dir.exists():
                shutil.rmtree(target_dir)
            raise ValueError("git clone timed out (60s)")

        # 验证 SKILL.md 存在
        info = _read_skill_from_dir(target_dir)
        if info is None:
            shutil.rmtree(target_dir)
            raise ValueError(f"SKILL.md not found in repository. Is this a valid skill repo?")

        # 写入 DB
        skill = Skill(
            name=info["name"],
            path=f"skills/{dir_name}",
            description=info["description"],
            version=info["version"],
            source="git",
            git_url=git_url,
        )
        self.db.add(skill)
        await self.db.commit()
        await self.db.refresh(skill)

        logger.info(f"Skill installed from git: {info['name']} ({git_url})")
        return skill

    # ── Install from upload (zip) ──

    async def install_from_upload(self, file_content: bytes, file_name: str) -> Skill:
        """上传 zip 文件，解压到 skills/ 目录"""
        if len(file_content) > 10 * 1024 * 1024:
            raise ValueError("File too large (max 10MB)")

        if not SKILLS_ROOT.exists():
            SKILLS_ROOT.mkdir(parents=True, exist_ok=True)

        try:
            zf = zipfile.ZipFile(io.BytesIO(file_content))
        except zipfile.BadZipFile:
            raise ValueError("Invalid zip file")

        # 推断 skill 名称
        dir_name = _safe_name(file_name.replace(".zip", ""))
        target_dir = SKILLS_ROOT / dir_name

        if target_dir.exists():
            raise ValueError(f"Skill '{dir_name}' already exists. Remove it first.")

        # 解压
        target_dir.mkdir(parents=True)
        for member in zf.namelist():
            # 跳过 __MACOSX 等隐藏文件
            if member.startswith("__MACOSX") or member.startswith("."):
                continue
            # 去掉顶层目录前缀（如果 zip 内有一层目录）
            parts = member.split("/")
            if len(parts) > 1 and parts[0] and not parts[0].startswith("."):
                # zip 内有一层根目录，去掉它
                rel_path = "/".join(parts[1:])
            else:
                rel_path = member
            if not rel_path:
                continue
            dest = target_dir / rel_path
            if member.endswith("/"):
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as dst:
                    dst.write(src.read())

        # 验证
        info = _read_skill_from_dir(target_dir)
        if info is None:
            shutil.rmtree(target_dir)
            raise ValueError("SKILL.md not found in zip. Make sure the zip contains a SKILL.md file.")

        # 如果用 SKILL.md 中的 name 跟 dir_name 不一致，以 SKILL.md 为准
        if info["name"] != dir_name:
            correct_dir = SKILLS_ROOT / _safe_name(info["name"])
            if not correct_dir.exists():
                target_dir.rename(correct_dir)
                dir_name = _safe_name(info["name"])

        # 写入 DB
        skill = Skill(
            name=info["name"],
            path=f"skills/{dir_name}",
            description=info["description"],
            version=info["version"],
            source="upload",
        )
        self.db.add(skill)
        await self.db.commit()
        await self.db.refresh(skill)

        logger.info(f"Skill installed from upload: {info['name']}")
        return skill

    # ── CRUD ──

    async def list_skills(self, skip: int = 0, limit: int = 20) -> tuple[list[Skill], int]:
        from sqlalchemy import func as _func
        # 总数
        count_result = await self.db.execute(select(_func.count(Skill.id)))
        total = count_result.scalar() or 0
        # 分页数据
        result = await self.db.execute(
            select(Skill).order_by(Skill.created_at).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_skill(self, skill_id: uuid.UUID) -> Optional[Skill]:
        return await self.db.get(Skill, skill_id)

    async def get_skill_with_content(self, skill_id: uuid.UUID) -> Optional[dict]:
        """获取 skill 详情 + 文件系统中的 SKILL.md / config.yaml 内容"""
        skill = await self.db.get(Skill, skill_id)
        if not skill:
            return None

        skill_dir = SKILLS_ROOT / skill.path.replace("skills/", "", 1)
        info = _read_skill_from_dir(skill_dir) or {}

        return {
            "id": str(skill.id),
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
            "path": skill.path,
            "source": skill.source,
            "git_url": skill.git_url,
            "skill_md": info.get("skill_md", ""),
            "config_yaml": info.get("config_yaml"),
            "created_at": skill.created_at,
            "updated_at": skill.updated_at,
        }

    async def delete_skill(self, skill_id: uuid.UUID) -> bool:
        """删除 skill（目录 + DB 记录）"""
        skill = await self.db.get(Skill, skill_id)
        if not skill:
            return False

        # 删除文件系统目录
        skill_dir = SKILLS_ROOT / skill.path.replace("skills/", "", 1)
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
            logger.info(f"Removed skill directory: {skill_dir}")

        await self.db.delete(skill)
        await self.db.commit()
        return True

    async def get_skill_file_tree(self, skill_id: uuid.UUID) -> Optional[dict]:
        """返回 skill 目录的完整文件树（含文件内容）"""
        skill = await self.db.get(Skill, skill_id)
        if not skill:
            return None

        skill_dir = SKILLS_ROOT / skill.path.replace("skills/", "", 1)
        if not skill_dir.exists():
            return {"name": skill.name, "type": "dir", "children": []}

        def build_tree(path: Path) -> dict:
            if path.is_file():
                ext = path.suffix.lower()
                # 文本文件才读取内容
                text_exts = {".md", ".yaml", ".yml", ".txt", ".py", ".js", ".ts",
                             ".json", ".xml", ".html", ".css", ".sh", ".toml", ".cfg",
                             ".ini", ".env", ".gitignore", ".dockerignore"}
                result = {"name": path.name, "type": "file"}
                if ext in text_exts or not ext:
                    try:
                        content = path.read_text(encoding="utf-8")
                        result["content"] = content
                    except (UnicodeDecodeError, PermissionError):
                        result["content"] = "[binary file]"
                else:
                    result["content"] = f"[binary file, {path.stat().st_size} bytes]"
                return result

            children = []
            try:
                for entry in sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
                    if entry.name.startswith(".") and entry.name != ".gitkeep":
                        continue
                    children.append(build_tree(entry))
            except PermissionError:
                pass

            return {"name": path.name, "type": "dir", "children": children}

        return build_tree(skill_dir)

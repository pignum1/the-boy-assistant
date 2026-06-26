"""M6 Execute Worker — single worker task execution (Route B).

Extracted from m6_level_execute._execute_single_task.
Uses M5 context pipeline with delegation-aware context
(delegation_goal, org_role_context, retry_feedback).

Returns independent incremental results safe for parallel workers.
"""

import asyncio
import logging
import time
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


# ── LangGraph node ────────────────────────────────────────────────

async def m6_execute_worker_node(state: CollabState) -> dict[str, Any]:
    """Execute current_delegation as a worker task.

    Reads current_delegation (set by m6_delegate or m6_delegate_push),
    builds M5 context with delegation-aware fields, calls agent_chat,
    extracts file changes, broadcasts events, and returns results.
    """
    current = state.get("current_delegation", {})
    if not current:
        return {
            "status": "blocked",
            "_content": "❌ 无当前委派任务",
            "_agent_name": "Worker",
        }

    member_id = current.get("member_id", "")
    goal = current.get("goal", "")
    role_context = current.get("role_context", "")
    role_name = current.get("role_name", "Worker")

    session_id = state.get("session_id", "")
    team_id = state.get("team_id", "")
    requirements_anchor = state.get("requirements_anchor", "")

    # ── Resolve workspace ──
    workspace_path = ""
    try:
        from app.services.workspace.manager import workspace_manager
        ws = workspace_manager.get_or_create(session_id)
        workspace_path = ws.path if ws else ""
    except Exception:
        pass

    # ── Build M5 context with delegation-aware fields ──
    from .m5_context_pipeline import context_pipeline
    from .m8_peer_mailbox import peer_mailbox

    peer_msgs = peer_mailbox.format_for_context(session_id, role_name)

    # Get previous artifacts (from delegation_tree or state)
    all_artifacts = _collect_artifact_refs(state)

    # Build task dict from current_delegation
    task = {
        "id": member_id,
        "title": goal,
        "description": goal,
        "assigned_role": role_name,
    }

    ctx = context_pipeline.build_context(
        requirement_anchor=requirements_anchor,
        task=task,
        all_artifacts=all_artifacts,
        peer_messages=peer_msgs,
        delegation_goal=goal,
        org_role_context=role_context,
        retry_feedback=current.get("retry_feedback", ""),
    )
    prompt = context_pipeline.format_context(ctx, workspace_path=workspace_path)

    # ── Execute via agent_chat ──
    try:
        from app.core.database import async_session
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent
        from sqlalchemy import select

        async with async_session() as db:
            # Find agent for this member
            agent = None
            org = state.get("org_structure")
            if org:
                member_roles = org.get("member_roles", {})
                info = member_roles.get(member_id, {})
                agent_id = info.get("agent_id")
                if agent_id:
                    stmt = select(Agent).where(Agent.id == agent_id)
                    result = await db.execute(stmt)
                    agent = result.scalar_one_or_none()

            # Fallback: try agent_assignments
            if not agent:
                agent_assignments = state.get("agent_assignments", {})
                agent_info = agent_assignments.get(role_name)
                if agent_info:
                    aid = agent_info.get("agent_id")
                    if aid:
                        stmt = select(Agent).where(Agent.id == aid)
                        result = await db.execute(stmt)
                        agent = result.scalar_one_or_none()

            # Last resort: any agent
            if not agent:
                stmt = select(Agent).limit(1)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()

            if not agent:
                return {
                    "status": "blocked",
                    "_content": f"❌ 无可用 Agent 执行 {role_name} 的任务",
                    "_agent_name": role_name,
                }

            t_start = time.monotonic()
            llm_result = await agent_chat(
                db=db, agent=agent, message=prompt,
                return_reasoning=True, save_memory=False,
                session_id=session_id, team_id=team_id,
            )
            latency_s = time.monotonic() - t_start

            output = llm_result.get("content", "")
            agent_name = agent.name or role_name

            # Extract file changes from tool calls
            files = _extract_file_changes(llm_result)

            # ── Broadcast events ──
            await _push_status(
                session_id, member_id, "completed",
                duration=int(latency_s), role_name=role_name, agent_name=agent_name,
            )
            await _push_worker_message(
                session_id, task, llm_result, files, agent_name, latency_s,
            )

            # ── Share via M8 ──
            if output and all_artifacts:
                peer_mailbox.send(
                    session_id=session_id,
                    from_agent=role_name,
                    to_agent="__all__",
                    msg_type="share",
                    content=f"完成了任务 '{goal[:50]}'，产出已就绪。",
                    references=[member_id],
                )

            logger.info(
                f"M6 ExecuteWorker: {role_name} completed in {latency_s:.1f}s, "
                f"{len(files)} files, output={len(output)} chars"
            )

            # ── Save output to workspace as a real PROJECT (not per-agent dirs) ──
            # Code blocks declare their own relative path (e.g. ```python backend/app/x.py);
            # respect it so multiple agents' output composes one runnable project.
            try:
                import os as _os, re as _re
                ws_path = ""
                if session_id:
                    from app.services.workspace.manager import workspace_manager
                    ws = workspace_manager.get_or_create(session_id)
                    ws_path = ws.path if ws else ""
                if ws_path and output:
                    # role → default project subdir when a code block has no explicit path.
                    # Handles role-id (backend_dev), Chinese name (后端工程师), and "-Agent" suffix.
                    _rn = (role_name or "").strip()
                    for _sfx in ("-Agent", "-agent", " Agent", " agent"):
                        if _rn.endswith(_sfx):
                            _rn = _rn[: -len(_sfx)].strip()
                    role_key = _rn.lower()
                    proj_subdir = {
                        "backend_dev": "backend", "backend": "backend", "后端工程师": "backend", "后端": "backend",
                        "frontend_dev": "frontend", "frontend": "frontend", "前端工程师": "frontend", "前端": "frontend",
                        "ui_designer": "design", "ui": "design", "ui设计师": "design", "ui设计": "design",
                        "tester": "tests", "test": "tests", "qa": "tests", "测试员": "tests", "测试": "tests",
                        "devops": "deploy", "ops": "deploy", "部署运维": "deploy", "运维": "deploy", "部署": "deploy",
                        "pm": "docs", "product_manager": "docs", "产品经理": "docs",
                        "architect": "docs", "架构师": "docs",
                    }.get(role_key, "src")

                    ext_map = {'python': '.py', 'py': '.py', 'javascript': '.js', 'js': '.js',
                               'typescript': '.ts', 'ts': '.ts', 'tsx': '.tsx', 'jsx': '.jsx',
                               'html': '.html', 'css': '.css', 'scss': '.scss',
                               'json': '.json', 'yaml': '.yml', 'yml': '.yml', 'toml': '.toml',
                               'sql': '.sql', 'sh': '.sh', 'bash': '.sh', 'shell': '.sh',
                               'dockerfile': 'Dockerfile', 'md': '.md', 'markdown': '.md'}

                    # Match fenced blocks. Resolve a file path STRICTLY from
                    # explicit declarations only — a real project path contains
                    # a slash AND a file extension (e.g. backend/app/main.py).
                    # Loose "looks like a path" heuristics misclassify code
                    # tokens (link.py inside a string, client.get(...)) as paths.
                    block_re = _re.compile(r'```([^\n]*)\n(.*?)```', _re.DOTALL)
                    KNOWN_EXTS = {'.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css',
                                  '.scss', '.json', '.yml', '.yaml', '.toml', '.sql',
                                  '.sh', '.md', '.txt', '.cfg', '.ini', '.env', '.vue'}
                    # Path must have ≥1 '/' and end with a known file ext, OR be a
                    # known special filename. Reject anything containing quotes,
                    # parens, dots-as-decimal, or typical code punctuation.
                    PATH_RE = _re.compile(
                        r'(?:[\w./-]+/)+(?:'
                        r'[\w.-]+\.(?:py|js|ts|tsx|jsx|html|css|scss|json|yml|yaml|toml|sql|sh|md|txt|cfg|ini|vue)'
                        r'|Dockerfile[\w.-]*'         # Dockerfile, Dockerfile.prod
                        r'|Makefile'                   # Makefile
                        r'|\.env[\w.-]*'               # .env, .env.local, .env.production
                        r'|\.gitignore'                # .gitignore
                        r'|\.dockerignore'             # .dockerignore
                        r'|\.editorconfig'             # .editorconfig
                        r')'
                    )
                    KNOWN_SPECIAL = frozenset({
                        'dockerfile', 'makefile', '.env', '.gitignore',
                        '.dockerignore', '.editorconfig',
                    })

                    def _clean_path(p: str) -> str:
                        return p.strip().strip('`*"\'：:').strip()

                    def _from_text(text: str) -> str | None:
                        m = PATH_RE.search(text)
                        return _clean_path(m.group(0)) if m else None

                    def _is_real_code(lang: str, code: str) -> bool:
                        """Filter out non-code blocks (diagrams, docs, tree-views)."""
                        # Skip diagram / documentation languages
                        NON_CODE = {'mermaid', 'markdown', 'md', 'text', 'plaintext', 'txt', ''}
                        if lang in NON_CODE:
                            return False
                        lines = [l for l in code.strip().split('\n') if l.strip()]
                        if len(lines) < 3:
                            return False
                        first = lines[0].strip().lower() if lines else ''
                        # Mermaid diagram starters
                        if first.startswith(('graph ', 'sequencediagram', 'classdiagram',
                                             'flowchart', 'erdiagram', 'gantt', 'pie',
                                             'journey', 'mindmap', 'statediagram')):
                            return False
                        # ASCII tree / box-drawing characters
                        if any(c in first for c in '├└│▲▼◄►┌┐┘└'):
                            return False
                        # Check code density: at least 30% of lines should have code patterns
                        code_count = sum(
                            1 for l in lines
                            if l.strip().startswith((' ', '\t'))
                            or any(kw in l for kw in (
                                'def ', 'class ', 'import ', 'from ', 'const ',
                                'let ', 'var ', 'function', 'return ', 'if ', 'for ',
                                'async ', 'await ', 'export ', 'interface ', 'type ',
                                '@', '{', '}', '=>', 'print(', 'SELECT ', 'INSERT ',
                            ))
                        )
                        if code_count / len(lines) < 0.3:
                            return False
                        return True

                    files_written = []
                    cursor = 0
                    for idx, m in enumerate(block_re.finditer(output)):
                        info = (m.group(1) or '').strip()      # fence info line
                        code = m.group(2)
                        prose_before = output[cursor:m.start()][-200:]  # text right before block
                        cursor = m.end()

                        parts = info.split()
                        lang = parts[0].lower() if parts else ''
                        # Strict: only accept a path that has a slash + extension.
                        declared_path = None
                        # (a) fence info line after the lang token
                        for tok in parts[1:]:
                            cand = _clean_path(tok)
                            mm = PATH_RE.fullmatch(cand) if cand else None
                            if mm:
                                declared_path = cand; break
                        # (b) scan the preceding prose for a real path
                        if not declared_path:
                            declared_path = _from_text(prose_before)

                        # When no path declared, skip non-code blocks (diagrams, docs, trees)
                        if not declared_path and not _is_real_code(lang, code):
                            continue

                        if declared_path:
                            rel = declared_path.lstrip('./').strip()
                        else:
                            # Dockerfile → {subdir}/Dockerfile (no .ext)
                            if lang == 'dockerfile':
                                rel = _os.path.join(proj_subdir, f'Dockerfile_{idx+1}')
                            else:
                                ext = ext_map.get(lang, '.txt')
                                fname = f"snippet_{idx+1}{ext}"
                                rel = _os.path.join(proj_subdir, fname)

                        # sandbox: keep under ws_path, no absolute/.. escapes
                        rel = rel.replace('\\', '/').lstrip('/')
                        if '..' in rel.split('/'):
                            continue
                        # The extracted path must be a FILE, not a directory
                        # (e.g. "tests/"). If the last segment has no extension,
                        # it's a dir → append a snippet filename to avoid
                        # [Errno 21] Is a directory.
                        last_seg = rel.rstrip('/').split('/')[-1]
                        if not last_seg or ('.' not in last_seg and last_seg.lower() not in KNOWN_SPECIAL):
                            ext = ext_map.get(lang, '.txt')
                            rel = _os.path.join(rel, f"snippet_{idx+1}{ext}")
                        filepath = _os.path.join(ws_path, rel)
                        try:
                            _os.makedirs(_os.path.dirname(filepath), exist_ok=True)
                            with open(filepath, 'w', encoding='utf-8') as f:
                                f.write(code.rstrip() + '\n')
                            files_written.append(rel)
                        except (IsADirectoryError, NotADirectoryError) as _de:
                            logger.debug(f"skip non-file path {rel}: {_de}")

                    # Non-code explanation text → <subdir>/README.md (skip if a
                    # code block already declared one, avoiding overwrite).
                    has_readme = any(
                        f.endswith('/README.md') or f == 'README.md'
                        for f in files_written
                    )
                    text_only = block_re.sub('', output).strip()
                    if text_only and not has_readme:
                        readme_rel = _os.path.join(proj_subdir, 'README.md')
                        readme_path = _os.path.join(ws_path, readme_rel)
                        _os.makedirs(_os.path.dirname(readme_path), exist_ok=True)
                        with open(readme_path, 'w', encoding='utf-8') as f:
                            f.write(f"# {agent_name} 任务输出\n\n## 任务\n{goal}\n\n{text_only}\n")
                        files_written.insert(0, readme_rel)
                    elif text_only and has_readme:
                        # Append to existing README if there's extra text
                        existing_readme = _os.path.join(ws_path, proj_subdir, 'README.md')
                        if _os.path.exists(existing_readme):
                            with open(existing_readme, 'a', encoding='utf-8') as f:
                                f.write(f"\n\n## 补充说明\n\n{text_only}\n")

                    logger.info(f"Worker [{role_name}] wrote project files: {files_written}")
            except Exception as e:
                logger.warning(f"Failed to save worker output: {e}")

            return {
                "files_changed": files,
                "artifacts": {member_id: output},
                "status": "executing",
                "_content": f"✅ **{role_name}** 完成任务 ({len(output)} 字符)\n📁 已保存到 {agent_name}/output.md",
                "_agent_name": agent_name,
            }

    except Exception as e:
        logger.error(f"M6 ExecuteWorker: {role_name} failed: {e}", exc_info=True)
        await _push_status(
            session_id, member_id, "failed",
            error=str(e), role_name=role_name, agent_name=role_name,
        )
        return {
            "status": "blocked",
            "_content": f"❌ **{role_name}** 执行失败: {str(e)[:200]}",
            "_agent_name": role_name,
        }


# ── Isolated worker execution for parallel mode ──

async def _execute_single_worker_isolated(
    assignment: dict[str, Any],
    state_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Execute a single worker in isolation for parallel execution.

    Returns an independent result dict. Does NOT write to global state.
    Called from m6_delegate_sub_node when multiple leaf workers detected.
    """
    member_id = assignment.get("member_id", "")
    goal = assignment.get("goal", "")
    role_name = assignment.get("role_name", "")
    session_id = state_snapshot.get("session_id", "")
    team_id = state_snapshot.get("team_id", "")
    requirements_anchor = state_snapshot.get("requirements_anchor", "")

    # Build minimal context
    from .m5_context_pipeline import context_pipeline

    task = {
        "id": member_id,
        "title": goal,
        "description": goal,
        "assigned_role": role_name,
    }

    ctx = context_pipeline.build_context(
        requirement_anchor=requirements_anchor,
        task=task,
        all_artifacts={},
        delegation_goal=goal,
        org_role_context=f"你是{role_name}",
    )

    # Resolve workspace
    workspace_path = ""
    try:
        from app.services.workspace.manager import workspace_manager
        ws = workspace_manager.get_or_create(session_id)
        workspace_path = ws.path if ws else ""
    except Exception:
        pass

    prompt = context_pipeline.format_context(ctx, workspace_path=workspace_path)

    try:
        from app.core.database import async_session
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent
        from sqlalchemy import select

        async with async_session() as db:
            agent = None
            org = state_snapshot.get("org_structure")
            if org:
                info = org.get("member_roles", {}).get(member_id, {})
                aid = info.get("agent_id")
                if aid:
                    stmt = select(Agent).where(Agent.id == aid)
                    result = await db.execute(stmt)
                    agent = result.scalar_one_or_none()
            if not agent:
                stmt = select(Agent).limit(1)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()

            if not agent:
                return {"member_id": member_id, "error": "No agent available"}

            t_start = time.monotonic()
            llm_result = await agent_chat(
                db=db, agent=agent, message=prompt,
                return_reasoning=True, save_memory=False,
                session_id=session_id, team_id=team_id,
            )
            latency_s = time.monotonic() - t_start

            output = llm_result.get("content", "")
            files = _extract_file_changes(llm_result)
            agent_name = agent.name or role_name

            # Broadcast (safe for parallel — each worker has unique member_id)
            await _push_status(
                session_id, member_id, "completed",
                duration=int(latency_s), role_name=role_name, agent_name=agent_name,
            )
            await _push_worker_message(session_id, task, llm_result, files, agent_name, latency_s)

            return {
                "member_id": member_id,
                "role_name": role_name,
                "output": output,
                "files": files,
                "agent_name": agent_name,
                "latency_s": latency_s,
            }

    except Exception as e:
        logger.error(f"M6 ExecuteWorker isolated: {role_name} failed: {e}")
        return {"member_id": member_id, "role_name": role_name, "error": str(e)}


# ── Helpers ────────────────────────────────────────────────────────

def _extract_file_changes(llm_result: dict) -> list[dict]:
    """Extract file changes from tool_calls in LLM result."""
    files = []
    tool_calls = llm_result.get("reasoning", {}).get("tool_calls", [])
    for tc in tool_calls:
        tool_name = (tc.get("tool") or "").lower()
        if "file" in tool_name and tc.get("success"):
            params = tc.get("params") or {}
            path = (
                params.get("path")
                or params.get("file_path")
                or params.get("filename")
                or params.get("name")
                or "unknown"
            )
            files.append({"name": path, "status": "created", "meta": ""})
    return files


def _collect_artifact_refs(state: CollabState) -> dict[str, str]:
    """Collect all available artifact refs from state and delegation_tree.

    For Route B, artifacts are stored in delegation_tree nodes as artifact_refs.
    Also includes state.artifacts for backward compatibility.
    """
    result = dict(state.get("artifacts", {}))

    # Walk delegation_tree to collect refs
    tree = state.get("delegation_tree", {})
    tree_nodes = tree.get("tree", {})

    def _walk(node: dict):
        for ref in node.get("artifact_refs", []):
            # artifact_refs are file paths, content loaded lazily
            pass  # Lazy loading — don't read content here
        for child in node.get("sub_delegations", {}).values():
            _walk(child)

    for root in tree_nodes.values():
        _walk(root)

    return result


async def _push_status(
    session_id: str,
    task_id: str,
    status: str,
    duration: int | None = None,
    error: str | None = None,
    role_name: str = "",
    agent_name: str = "",
) -> None:
    """Broadcast task_status event via WebSocket.

    Carries role_name/agent_name so the frontend task tree (keyed by role) can
    match this worker's progress to the right task node.
    """
    try:
        from app.services.ws_broadcaster import manager
        from datetime import datetime

        payload: dict[str, Any] = {"task_id": task_id, "status": status}
        if role_name:
            payload["role"] = role_name
        if agent_name:
            payload["agent_name"] = agent_name
        if duration is not None:
            payload["duration"] = duration
        if error:
            payload["error"] = error

        await manager.broadcast_to_session(session_id, {
            "type": "task_status",
            "source": "m6_execute_worker",
            "timestamp": datetime.now().isoformat(),
            "payload": payload,
        })
    except Exception as e:
        logger.warning(f"M6 ExecuteWorker push_status failed: {e}")


async def _push_worker_message(
    session_id: str,
    task: dict[str, Any],
    llm_result: dict[str, Any],
    files: list[dict[str, Any]],
    agent_name: str,
    latency_s: float,
) -> None:
    """Push worker reasoning + content + files to frontend and persist to Memory."""
    try:
        from app.services.ws_broadcaster import manager
        from datetime import datetime

        ts = datetime.now().isoformat()
        reasoning = llm_result.get("reasoning", {}) or {}
        content = llm_result.get("content", "") or ""

        _persist_worker_result(session_id, task, content, reasoning, agent_name, latency_s)

        await manager.broadcast_to_session(session_id, {
            "type": "agent_message",
            "source": "m6_execute_worker",
            "timestamp": ts,
            "payload": {
                "agent": agent_name,
                "content": content[:6000],
                "type": "message",
                "model": (reasoning.get("model_routing", {}) or {}).get("selected_model"),
                "latency": int(latency_s * 1000) if latency_s else 0,
                "task_id": task.get("id", ""),
            },
        })

        if reasoning:
            await manager.broadcast_to_session(session_id, {
                "type": "reasoning_complete",
                "source": "m6_execute_worker",
                "timestamp": ts,
                "payload": {
                    "agent": agent_name,
                    "thinking_steps": reasoning.get("thinking_steps", ""),
                    "model_routing": reasoning.get("model_routing", {}),
                    "tool_calls": reasoning.get("tool_calls", []),
                    "decision_summary": f"完成任务: {task.get('title', task.get('id', ''))}",
                    "latency": int(latency_s * 1000) if latency_s else 0,
                },
            })

        if files:
            await manager.broadcast_to_session(session_id, {
                "type": "files_changed",
                "source": "m6_execute_worker",
                "timestamp": ts,
                "payload": {
                    "files": [
                        {**f, "producer_agent_name": agent_name, "producer_task_id": task.get("id", "")}
                        for f in files
                    ],
                },
            })
    except Exception as e:
        logger.warning(f"M6 ExecuteWorker push_worker_message failed: {e}")


def _persist_worker_result(
    session_id: str,
    task: dict[str, Any],
    content: str,
    reasoning: dict[str, Any],
    agent_name: str,
    latency_s: float,
) -> None:
    """Persist worker output to Memory."""
    try:
        from app.services.memory_manager import MemoryManager
        from app.schemas.memory import MemoryLevel, MemoryType
        from app.services.session_service import SessionService
        import uuid as _uuid

        async def _do_persist():
            from app.core.database import async_session
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    async with async_session() as db:
                        svc = SessionService(db)
                        sess = await svc.get_session(_uuid.UUID(session_id))
                        if sess and content:
                            tag = f"[{time.time_ns()}]"
                            tid = task.get("id", "")
                            title = task.get("title") or tid
                            combined = f"用户{tag}: [Worker:{tid}]\n助手: {content}"
                            meta = {
                                "agent": agent_name,
                                "source": "m6_execute_worker",
                                "task_id": tid,
                                "task_title": title,
                                "latency": int(latency_s * 1000) if latency_s else 0,
                            }
                            meta = {k: v for k, v in meta.items() if v not in (None, "", [])}
                            await MemoryManager(db).save_memory(
                                level=MemoryLevel.context, content=combined,
                                type=MemoryType.context, team_id=sess.team_id,
                                session_id=session_id, importance=0.5, created_by="system",
                                metadata_=meta,
                            )
                            await db.commit()
                    return  # 成功，退出
                except Exception as persist_err:
                    if attempt < max_retries - 1:
                        logger.warning(
                            "Persist attempt %d/%d failed for worker %s: %s. Retrying...",
                            attempt + 1, max_retries, task.get("id", "?"), persist_err,
                        )
                        await asyncio.sleep(0.5 * (attempt + 1))  # 0.5s, 1s 退避
                    else:
                        logger.error(
                            "Persist FAILED after %d attempts for worker %s: %s",
                            max_retries, task.get("id", "?"), persist_err, exc_info=True,
                        )

        asyncio.create_task(_do_persist())
    except Exception as e:
        logger.warning(f"M6 ExecuteWorker persist failed: {e}")

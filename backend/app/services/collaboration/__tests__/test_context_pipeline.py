"""Tests for M5 ContextPipeline — trimmed worker context."""

import pytest
from app.services.collaboration.m5_context_pipeline import ContextPipeline


class TestContextPipeline:
    """Verify context building and trimming."""

    def setup_method(self):
        self.pipeline = ContextPipeline()

    def test_builds_context_with_requirement_anchor(self):
        ctx = self.pipeline.build_context(
            requirement_anchor="实现登录系统: 邮箱+密码, JWT",
            task={"title": "后端API", "description": "实现auth.py", "depends_on": []},
            all_artifacts={},
        )
        assert "实现登录系统" in ctx["requirement_anchor"]

    def test_only_includes_dependent_artifacts(self):
        """Worker should only see artifacts their task depends on."""
        all_artifacts = {
            "task_db": "## DB Design\nusers table...",
            "task_ui": "## UI Design\nLogin form...",
            "task_other": "## Other stuff...",
        }

        ctx = self.pipeline.build_context(
            requirement_anchor="登录系统",
            task={
                "title": "后端API",
                "depends_on": ["task_db"],  # Only depends on DB design
            },
            all_artifacts=all_artifacts,
        )

        # Should have task_db
        assert "task_db" in ctx["previous_artifacts"]
        # Should NOT have task_ui or task_other
        assert "task_ui" not in ctx["previous_artifacts"]
        assert "task_other" not in ctx["previous_artifacts"]

    def test_empty_dependencies_returns_empty_artifacts(self):
        ctx = self.pipeline.build_context(
            requirement_anchor="登录系统",
            task={"title": "DB设计", "depends_on": []},
            all_artifacts={"task_x": "some output"},
        )
        assert ctx["previous_artifacts"] == {}

    def test_formatted_context_has_all_sections(self):
        ctx = self.pipeline.build_context(
            requirement_anchor="## 需求\n登录系统",
            task={
                "title": "后端API",
                "description": "实现POST /api/login",
                "expected_output": "auth.py",
                "depends_on": [],
            },
            all_artifacts={},
            supervisor_guidance="使用bcrypt+JWT",
            constraints=["FastAPI", "PostgreSQL"],
        )

        formatted = self.pipeline.format_context(ctx)

        assert "需求 (不可偏离)" in formatted
        assert "当前任务" in formatted
        assert "后端API" in formatted
        assert "auth.py" in formatted
        assert "Supervisor 指导" in formatted
        assert "bcrypt+JWT" in formatted
        assert "约束" in formatted
        assert "FastAPI" in formatted

    def test_token_estimate_is_positive(self):
        ctx = self.pipeline.build_context(
            requirement_anchor="Some requirements" * 100,
            task={"title": "Task", "description": "Some task" * 50, "depends_on": []},
            all_artifacts={},
        )
        tokens = self.pipeline.estimate_tokens(ctx)
        assert tokens > 0

    def test_files_summary_formats_created_and_modified(self):
        files = [
            {"name": "auth.py", "status": "created", "meta": "+89 lines"},
            {"name": "config.py", "status": "modified", "meta": "+5 -2 lines"},
        ]
        summary = self.pipeline.format_files_summary(files)

        assert "2 files" in summary
        assert "auth.py" in summary
        assert "+ new" in summary
        assert "~ mod" in summary
        assert "+89 lines" in summary

    def test_empty_files_returns_empty_string(self):
        assert self.pipeline.format_files_summary([]) == ""

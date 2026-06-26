"""Tests for M4 TaskDecomposer."""
import pytest
from app.services.collaboration.task_decomposer import (
    validate_no_cycles,
    topological_sort,
    build_decompose_prompt,
)


class TestValidateNoCycles:
    def test_valid_dag(self):
        phases = [
            {
                "id": "p1",
                "tasks": [
                    {"id": "t1", "depends_on": []},
                    {"id": "t2", "depends_on": ["t1"]},
                    {"id": "t3", "depends_on": ["t1"]},
                    {"id": "t4", "depends_on": ["t2", "t3"]},
                ],
            }
        ]
        errors = validate_no_cycles(phases)
        assert len(errors) == 0

    def test_three_node_chain(self):
        phases = [
            {
                "id": "p1",
                "tasks": [
                    {"id": "a", "depends_on": []},
                    {"id": "b", "depends_on": ["a"]},
                    {"id": "c", "depends_on": ["b"]},
                ],
            }
        ]
        assert len(validate_no_cycles(phases)) == 0

    def test_cycle_detected(self):
        phases = [
            {
                "id": "p1",
                "tasks": [
                    {"id": "a", "depends_on": ["b"]},
                    {"id": "b", "depends_on": ["a"]},
                ],
            }
        ]
        errors = validate_no_cycles(phases)
        assert len(errors) > 0

    def test_self_loop_cycle(self):
        phases = [
            {
                "id": "p1",
                "tasks": [
                    {"id": "a", "depends_on": ["a"]},
                ],
            }
        ]
        errors = validate_no_cycles(phases)
        assert len(errors) > 0


class TestTopologicalSort:
    def test_simple_chain(self):
        phases = [
            {
                "id": "p1",
                "tasks": [
                    {"id": "t1", "depends_on": [], "title": "first"},
                    {"id": "t2", "depends_on": ["t1"], "title": "second"},
                    {"id": "t3", "depends_on": ["t2"], "title": "third"},
                ],
            }
        ]
        levels = topological_sort(phases)
        assert len(levels) == 3  # 3 levels
        assert len(levels[0]) == 1  # t1 alone
        assert len(levels[1]) == 1  # t2 alone
        assert len(levels[2]) == 1  # t3 alone

    def test_parallel_tasks_same_level(self):
        phases = [
            {
                "id": "p1",
                "tasks": [
                    {"id": "t1", "depends_on": [], "title": "base"},
                    {"id": "t2", "depends_on": ["t1"], "title": "worker_a"},
                    {"id": "t3", "depends_on": ["t1"], "title": "worker_b"},
                ],
            }
        ]
        levels = topological_sort(phases)
        assert len(levels) == 2
        assert len(levels[0]) == 1  # t1
        assert len(levels[1]) == 2  # t2 and t3 can run in parallel

    def test_multiple_independent_roots(self):
        phases = [
            {
                "id": "p1",
                "tasks": [
                    {"id": "t1", "depends_on": [], "title": "a"},
                    {"id": "t2", "depends_on": [], "title": "b"},
                    {"id": "t3", "depends_on": ["t1", "t2"], "title": "c"},
                ],
            }
        ]
        levels = topological_sort(phases)
        assert len(levels) == 2
        assert len(levels[0]) == 2  # t1 and t2 can run in parallel
        assert len(levels[1]) == 1  # t3 after both

    def test_empty_tasks(self):
        levels = topological_sort([{"id": "p1", "tasks": []}])
        assert levels == []


class TestBuildPrompt:
    def test_includes_requirements_and_roles(self):
        prompt = build_decompose_prompt("登录系统: 邮箱+密码", ["architect", "backend_dev"])
        assert "登录系统" in prompt
        assert "architect" in prompt

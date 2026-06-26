"""Multi-Agent Collaboration System

M0-M8 modular pipeline + LLM-driven decision making.
LangGraph provides: state persistence, HITL, streaming.

Modules:
    M0: Intent Router    → single/multi agent routing
    M1: Requirement Analyzer → LLM analysis with workflow template
    M2: Clarification    → HITL clarification when info insufficient
    M3: Agent Orchestrator → check availability, handle missing
    M4: Task Decomposer   → LLM-driven DAG generation
    M5: Context Pipeline  → trimmed context for each worker (delegation-aware)
    M6: Hierarchical Delegation → Route B: DFS org tree, supervisor decompose, review
    M7: Verifier          → blind review against requirements
    M8: Peer Mailbox      → agent-to-agent communication
"""

from .types import CollabState, SupervisorDecision, WorkerContext, NodeMetadata
from .m5_context_pipeline import ContextPipeline
from .m8_peer_mailbox import PeerMailbox

__all__ = [
    "CollabState",
    "SupervisorDecision",
    "WorkerContext",
    "NodeMetadata",
    "ContextPipeline",
    "PeerMailbox",
]

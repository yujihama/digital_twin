"""Generic simulation loop for LLM multi-agent experiments.

Environment-agnostic by design. Knows only about:
  - Agents that can `.decide(llm, observation, temperature)`
  - An `EnvironmentAdapter` that projects domain state into observations,
    dispatches actions, and advances time.

Domain-specific glue (e.g. purchase approval) lives in `oct/dispatchers/`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from oct.agent import Agent, AgentAction, LLMClient


class EnvironmentAdapter(Protocol):
    """Thin contract the runner needs from any environment."""

    def observe(self, agent_id: str) -> Dict[str, Any]:
        """Build an observation dict from the current state for `agent_id`."""

    def dispatch(self, agent_id: str, action: AgentAction) -> Dict[str, Any]:
        """Apply `action`. Returns a result dict with at least {ok, details, error}."""

    def remaining_capacity(self, agent_id: str) -> int:
        """How many more actions `agent_id` can perform today."""

    def advance_day(self) -> None:
        """Move the simulation clock forward one step."""

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot (for logging / inspection)."""


@dataclass
class StepRecord:
    """A single agent-turn inside the simulation."""

    day: int
    agent_id: str
    observation: Dict[str, Any]
    action: Optional[AgentAction]
    dispatch_result: Dict[str, Any]
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "agent_id": self.agent_id,
            "observation": self.observation,
            "action": None if self.action is None else self.action.model_dump(),
            "dispatch_result": self.dispatch_result,
            "error": self.error,
        }


@dataclass
class SimulationTrace:
    """Complete record of a simulation run."""

    steps: List[StepRecord] = field(default_factory=list)
    final_snapshot: Optional[Dict[str, Any]] = None

    def dispatched_actions(self) -> List[StepRecord]:
        return [s for s in self.steps if s.error is None and s.dispatch_result.get("ok")]

    def errors(self) -> List[StepRecord]:
        return [s for s in self.steps if s.error is not None]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "final_snapshot": self.final_snapshot,
        }


def run_simulation(
    env: EnvironmentAdapter,
    agents: List[Agent],
    llm: LLMClient,
    *,
    max_days: int,
    temperature: float = 0.8,
    actions_per_agent_per_day: int = 1,
) -> SimulationTrace:
    """Drive `max_days` rounds through `agents`.

    On each day, each agent is asked up to `actions_per_agent_per_day` times
    for an action, provided they still have capacity. LLM / parsing / dispatch
    errors are captured in the trace and the loop continues — robustness over
    strictness is appropriate for exploratory T-007 runs.
    """
    trace = SimulationTrace()

    for _day_index in range(max_days):
        for agent in agents:
            for _turn in range(actions_per_agent_per_day):
                if env.remaining_capacity(agent.agent_id) <= 0:
                    break
                observation = env.observe(agent.agent_id)
                current_day = int(observation.get("current_day", _day_index))

                action: Optional[AgentAction] = None
                err: Optional[str] = None
                dispatch_result: Dict[str, Any] = {"ok": False, "details": {}, "error": None}

                try:
                    action = agent.decide(llm, observation, temperature=temperature)
                except Exception as exc:
                    err = f"decide_failed: {exc!r}"
                else:
                    try:
                        dispatch_result = env.dispatch(agent.agent_id, action)
                    except Exception as exc:
                        err = f"dispatch_failed: {exc!r}"
                        dispatch_result = {"ok": False, "details": {}, "error": str(exc)}

                trace.steps.append(
                    StepRecord(
                        day=current_day,
                        agent_id=agent.agent_id,
                        observation=observation,
                        action=action,
                        dispatch_result=dispatch_result,
                        error=err,
                    )
                )
        env.advance_day()

    trace.final_snapshot = env.snapshot()
    return trace

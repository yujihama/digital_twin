"""Generic LLM agent abstraction.

Design principle (PR#2 review follow-up / docs/05_oct_framework.md §5.5):
This module is environment-agnostic. It knows nothing about purchase requests,
approvals, or any specific business domain. Domain-specific persona + action
schemas live under `oct/personas/`.

The OCT framework composes an agent from three pieces:
  1. A persona (system prompt) — describes who the agent is
  2. An observation (user prompt) — describes what the agent sees right now
  3. An action schema — defines the JSON shape the agent must emit
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field


class LLMClient(Protocol):
    """Abstract LLM invocation interface.

    Any concrete implementation (Anthropic, OpenAI, fake) must expose `.complete()`.
    """

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.8,
    ) -> str:
        ...


class AgentAction(BaseModel):
    """A single action emitted by an agent in response to an observation."""

    model_config = ConfigDict(extra="allow")

    action_type: str = Field(..., description="Name of the action to perform")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Action-specific keyword arguments"
    )
    reasoning: Optional[str] = Field(
        default=None, description="Free-text reasoning from the agent (for logging)"
    )


class ActionOption(BaseModel):
    """Definition of a single action an agent may choose."""

    name: str
    description: str
    parameters_schema: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of parameter name -> short type/description",
    )


class Agent(BaseModel):
    """A single LLM-backed agent.

    `agent_id` is a stable identifier used by environment / rules (e.g. "buyer_a").
    `role` is a coarse-grained category (e.g. "buyer", "approver").
    `persona` becomes the system prompt when the agent is asked to decide.
    `available_actions` enumerates the JSON action space.
    """

    agent_id: str
    role: str
    persona: str
    available_actions: List[ActionOption] = Field(default_factory=list)

    def build_user_prompt(self, observation: Dict[str, Any]) -> str:
        """Render a user-turn prompt from an observation dict + action schema.

        Subclasses / callers may override to customize formatting, but the
        default format is sufficient for minimal T-003 usage.
        """
        lines: List[str] = []
        lines.append("# 現在の状況")
        lines.append(json.dumps(observation, ensure_ascii=False, indent=2))
        lines.append("")
        lines.append("# あなたが取り得る行動")
        for opt in self.available_actions:
            params_fmt = ", ".join(
                f"{k}: {v}" for k, v in opt.parameters_schema.items()
            )
            params_note = f" (parameters: {params_fmt})" if params_fmt else ""
            lines.append(f"- **{opt.name}**: {opt.description}{params_note}")
        lines.append("")
        lines.append("# 応答形式")
        lines.append(
            "以下の JSON のみを返してください（前後に説明文を書かないこと）:"
        )
        lines.append("```json")
        lines.append(
            '{"action_type": "<行動名>", "parameters": {...}, "reasoning": "<短い理由>"}'
        )
        lines.append("```")
        return "\n".join(lines)

    def decide(
        self,
        llm: LLMClient,
        observation: Dict[str, Any],
        temperature: float = 0.8,
    ) -> AgentAction:
        """Ask the LLM to choose an action for the given observation."""
        user = self.build_user_prompt(observation)
        raw = llm.complete(system=self.persona, user=user, temperature=temperature)
        return parse_action_json(raw)


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_action_json(raw: str) -> AgentAction:
    """Extract and parse the first JSON object from an LLM response.

    Tolerates fenced code blocks and leading/trailing chatter because
    even with explicit instructions, models sometimes prefix "Sure, ".
    Raises `ValueError` if no valid JSON action can be parsed.
    """
    if not raw or not raw.strip():
        raise ValueError("Empty LLM response")

    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Drop the first fence line and everything after the closing fence
        cleaned = cleaned.split("```", 2)
        # cleaned = ["", "json\n{...}\n", "trailing"] or similar
        if len(cleaned) >= 2:
            body = cleaned[1]
            # Drop optional language tag on first line
            body = body.split("\n", 1)[-1] if "\n" in body else body
            cleaned = body

    match = _JSON_BLOCK_RE.search(cleaned if isinstance(cleaned, str) else raw)
    if match is None:
        raise ValueError(f"No JSON object found in LLM response: {raw!r}")

    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in LLM response: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"LLM response is not a JSON object: {payload!r}")
    if "action_type" not in payload:
        raise ValueError(f"Missing 'action_type' in LLM response: {payload!r}")

    return AgentAction.model_validate(payload)

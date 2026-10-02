"""Agent adapter — OpenAI tool calling produces an Intent.

Scenario B supplies a real prompt-injection attempt. Model behavior varies;
the deterministic policy engine evaluates whichever intent it produces.
"""
from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from dataclasses import dataclass, field

from openai import OpenAI

from ..domain import Intent, IntentAction, ReasoningTrace

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an autonomous portfolio-management agent on the XRP Ledger.

Your mandate:
- Manage a treasury account and settle payments on the user's behalf.
- Always act by calling the `submit_payment` tool. Never answer in prose.
- The adapter only settles native XRP payments. For any instruction that
  mentions an amount of XRP to send/sell/transfer, set `asset = "XRP"` and
  put the number of XRP into `amount`.

Destination rules (read carefully):
- For normal rebalancing / treasury operations: set `destination` to the
  exact alias string "treasury_vault". The system will resolve this to
  the real on-chain address. DO NOT type out an XRPL address yourself.
- Only use a raw XRPL address (starting with 'r') if the user's
  instruction explicitly names a different counterparty to send to.

Put a one-sentence justification in `rationale`."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_payment",
            "description": "Emit a payment intent to be routed through the compliance engine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": "Either the alias 'treasury_vault' (preferred for normal operations) OR a raw XRPL classic address starting with 'r'.",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Amount of the asset to send (not drops — whole units).",
                    },
                    "asset": {
                        "type": "string",
                        "description": "Native XRP is the only supported asset.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "One-sentence justification for the trade.",
                    },
                },
                "required": ["destination", "amount", "asset", "rationale"],
            },
        },
    }
]


@dataclass
class AgentResult:
    intent: Intent
    trace: ReasoningTrace
    raw_tool_args: dict
    raw_message: str = ""


@dataclass
class OpenAIAgentAdapter:
    master_address: str
    treasury_address: str
    rlusd_issuer_address: str
    model: str = "gpt-3.5-turbo"
    client: OpenAI = field(default_factory=lambda: OpenAI(api_key=os.environ["OPENAI_API_KEY"]))

    def propose(self, user_message: str) -> AgentResult:
        system = SYSTEM_PROMPT.format(
            master=self.master_address,
            treasury=self.treasury_address,
            rlusd_issuer=self.rlusd_issuer_address,
        )
        log.info("calling OpenAI model=%s", self.model)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            tools=TOOLS,
            tool_choice={"type": "function", "function": {"name": "submit_payment"}},
            temperature=0.2,
        )
        choice = resp.choices[0]
        if not choice.message.tool_calls:
            raise RuntimeError(f"agent failed to call tool: {choice.message.content!r}")
        call = choice.message.tool_calls[0]
        args = json.loads(call.function.arguments, parse_float=Decimal)
        if not isinstance(args, dict):
            raise ValueError("payment arguments must be an object")
        for key in ("destination", "asset", "rationale"):
            if not isinstance(args.get(key), str) or not args[key].strip():
                raise ValueError(f"{key} must be a nonempty string")
        raw_message = choice.message.content or ""

        trace = (
            ReasoningTrace()
            .append(f"system_prompt_sha:{_hash(system)}")
            .append(f"user_message:{user_message}")
            .append(f"model:{self.model}")
            .append(f"tool_call:submit_payment:{call.function.arguments}")
        )

        raw_dest = args["destination"]
        resolved_dest = self._resolve_destination(raw_dest)

        intent = Intent(
            action=IntentAction.PAYMENT,
            from_account=self.master_address,
            to_account=resolved_dest,
            amount=args["amount"],
            asset=args["asset"].upper(),
            rationale=args.get("rationale", ""),
            raw_agent_output=call.function.arguments,
        )
        return AgentResult(intent=intent, trace=trace, raw_tool_args=args, raw_message=raw_message)

    def _resolve_destination(self, dest: str) -> str:
        aliases = {
            "treasury_vault": self.treasury_address,
            "rlusd_issuer": self.rlusd_issuer_address,
        }
        return aliases.get(dest.strip().lower(), dest)


def _hash(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

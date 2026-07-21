from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from jsonschema import ValidationError, validate

from sber_a2a.domain.contracts import Mandate, ToolDefinition, ToolRisk


class ToolRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolCaller:
    subject: str
    tenant_id: str
    agent_id: str
    agent_role: str
    oauth_scopes: frozenset[str]
    caller_kind: str


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
AuditHook = Callable[[dict[str, Any]], Awaitable[None]]


class ToolRuntime:
    """Single policy-enforcing path between agents/models and integration adapters."""

    _MODEL_FORBIDDEN = frozenset({ToolRisk.FINANCIAL, ToolRisk.LEGAL, ToolRisk.CRITICAL})

    def __init__(self, audit_hook: AuditHook) -> None:
        self._audit_hook = audit_hook
        self._handlers: dict[tuple[str, str], tuple[ToolDefinition, ToolHandler]] = {}
        self._idempotency: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        key = (definition.tool_id, definition.version)
        if key in self._handlers:
            raise ToolRuntimeError("Tool version is already registered")
        self._handlers[key] = (definition, handler)

    async def execute(
        self,
        tool_id: str,
        version: str,
        payload: dict[str, Any],
        *,
        caller: ToolCaller,
        mandate: Mandate,
        idempotency_key: str,
    ) -> dict[str, Any]:
        registered = self._handlers.get((tool_id, version))
        if registered is None:
            raise ToolRuntimeError("Tool is not registered")
        definition, handler = registered
        if caller.agent_role not in definition.allowed_agent_roles:
            raise ToolRuntimeError("Agent role is not allowed for this tool")
        if not definition.oauth_scopes.issubset(caller.oauth_scopes):
            raise ToolRuntimeError("OAuth scope is insufficient")
        if mandate.organization_id != caller.tenant_id or mandate.agent_id != caller.agent_id:
            raise ToolRuntimeError("Mandate tenant or agent binding is invalid")
        if not all(mandate.permits(action) for action in definition.required_mandate_actions):
            raise ToolRuntimeError("Mandate does not permit this tool call")
        if caller.caller_kind == "model" and definition.risk_level in self._MODEL_FORBIDDEN:
            raise ToolRuntimeError("Models cannot invoke legal, financial or critical tools")
        if definition.requires_human_approval:
            raise ToolRuntimeError("Tool requires a separate human approval operation")
        try:
            validate(payload, definition.input_schema)
        except ValidationError as exc:
            raise ToolRuntimeError("Tool input schema validation failed") from exc
        async with self._lock:
            existing = self._idempotency.get(idempotency_key)
            if existing is not None:
                return dict(existing)
            async with asyncio.timeout(float(definition.timeout_seconds)):
                result = await handler(payload)
            try:
                validate(result, definition.output_schema)
            except ValidationError as exc:
                raise ToolRuntimeError("Tool output schema validation failed") from exc
            self._idempotency[idempotency_key] = dict(result)
        await self._audit_hook(
            {
                "tool_id": tool_id,
                "version": version,
                "subject": caller.subject,
                "tenant_id": caller.tenant_id,
                "agent_id": caller.agent_id,
                "idempotency_key": idempotency_key,
                "result": "success",
            }
        )
        return result

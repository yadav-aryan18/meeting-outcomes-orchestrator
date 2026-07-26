"""
sitrep_agent/tools/base.py

Abstract base class for all agent tools.

Every tool in the orchestrator inherits from BaseTool and implements:
  - name: str          — unique tool identifier
  - description: str   — what the tool does (used by LLM router)
  - get_schema():     — returns JSON schema for dynamic tool discovery
  - execute():         — async method that performs the work

This modular design means new tools can be added by:
  1. Creating a new file in tools/
  2. Inheriting from BaseTool
  3. Implementing get_schema() and execute()
  4. Registering in tools/__init__.py

Design principles:
  - Graceful degradation: tools never crash the agent; they return empty results on failure
  - Async-first: all tools are async for parallel execution
  - Self-describing: each tool exposes its own schema for LLM discovery
  - Typed: inputs/outputs are clearly documented
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Standardized result container for all tools.

    Attributes:
        success: Whether the tool completed its primary objective.
        data: Structured output (dict, list, str) — varies by tool.
        summary: Human-readable summary for the LLM synthesizer.
        artifacts: Optional pre-formatted artifacts to include in final output.
        error: Error message if success=False.
    """
    success: bool = True
    data: Any = field(default_factory=dict)
    summary: str = ""
    artifacts: list[dict] = field(default_factory=list)
    error: str = ""


@dataclass
class ToolSchema:
    """JSON Schema descriptor for a tool, used by the LLM for dynamic discovery.

    The LLM reads these schemas to understand what each tool does and what
    arguments it accepts. This enables dynamic tool selection without hardcoded
    routing logic.

    Attributes:
        name: Tool identifier (must match the tool's .name attribute).
        description: What the tool does, when to use it, and what it returns.
        parameters: JSON Schema object describing the tool's arguments.
        required: List of required parameter names.
        returns: Description of what the tool returns.
    """
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    returns: str = ""


class BaseTool(ABC):
    """Abstract base for all SitRep agent tools.

    Subclasses MUST override:
      - name: class attribute (str)
      - description: class attribute (str)
      - get_schema(): returns ToolSchema
      - execute(): async method
    """

    name: str = "base"
    description: str = "Base tool — do not use directly."

    def __init__(self, ctx: Any = None):
        """Initialize with optional Ctx for logging.

        Args:
            ctx: The SitRep Ctx object (for ctx.log()). Optional.
        """
        self.ctx = ctx

    def log(self, message: str) -> None:
        """Log a message via ctx if available."""
        if self.ctx and hasattr(self.ctx, "log"):
            self.ctx.log(message)

    @abstractmethod
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema descriptor for this tool.

        This schema is fed to the LLM so it can discover and use the tool
        dynamically. Be specific about what the tool does and when to use it.

        Returns:
            ToolSchema with name, description, parameters, and required fields.
        """
        raise NotImplementedError

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given parameters.

        Args:
            **kwargs: Tool-specific parameters.

        Returns:
            ToolResult with standardized output.
        """
        raise NotImplementedError

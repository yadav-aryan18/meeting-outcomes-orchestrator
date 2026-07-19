"""
sitrep_agent/tools/base.py

Abstract base class for all agent tools.

Every tool in the orchestrator inherits from BaseTool and implements:
  - name: str          — unique tool identifier
  - description: str   — what the tool does (used by LLM router)
  - execute():         — async method that performs the work

This modular design means new tools can be added by:
  1. Creating a new file in tools/
  2. Inheriting from BaseTool
  3. Implementing execute()
  4. Registering in tools/__init__.py

Design principles:
  - Graceful degradation: tools never crash the agent; they return empty results on failure
  - Async-first: all tools are async for parallel execution
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


class BaseTool(ABC):
    """Abstract base for all SitRep agent tools.

    Subclasses MUST override:
      - name: class attribute (str)
      - description: class attribute (str)  
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
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given parameters.

        Args:
            **kwargs: Tool-specific parameters.

        Returns:
            ToolResult with standardized output.
        """
        raise NotImplementedError

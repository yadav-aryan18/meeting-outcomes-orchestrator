"""
sitrep_agent/tools/slides.py

Slide deck outline and HTML preview generator.
Transforms meeting topics into structured presentation outlines with visual previews.

Features:
  - Generates numbered slide-by-slide outlines with titles and bullets
  - Creates a clean HTML preview fragment for quick visual review
  - Adapts slide count based on topic complexity
  - Returns both markdown outline and HTML artifact

Usage:
    result = await SlidesTool(ctx).execute(
        task_title="Q3 Roadmap Presentation",
        summary="Meeting summary...",
        llm=ctx.llm
    )
"""
from __future__ import annotations

from typing import Any

from .base import BaseTool, ToolResult, ToolSchema


class SlidesTool(BaseTool):
    """Generate slide deck outlines and HTML previews from meeting content."""

    name = "slides"
    description = (
        "Create a structured slide deck outline and HTML preview from meeting content. "
        "Ideal for tasks like 'prepare a presentation', 'deck for the board', or 'slide outline'. "
        "Produces both a markdown outline (editable) and an HTML preview (visual). "
        "No external tools required."
    )


    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="slides",
            description=(
                "Create a structured slide deck outline and HTML preview from meeting content. "
                "Ideal for tasks like 'prepare a presentation', 'deck for the board', or 'slide outline'. "
                "Produces both a markdown outline (editable) and an HTML preview (visual). "
                "No external tools required. Use this when the task involves creating a presentation."
            ),
            parameters={
                "task_title": {
                    "type": "string",
                    "description": "The presentation topic.",
                },
                "summary": {
                    "type": "string",
                    "description": "Meeting summary to base slides on.",
                },
                "slide_count": {
                    "type": "integer",
                    "description": "Target number of slides (default 8, range 4-15).",
                    "default": 8,
                },
            },
            required=["task_title", "summary"],
            returns="Dict with 'outline', 'html', and 'slide_count' keys.",
        )

    async def execute(
        self,
        task_title: str = "",
        summary: str = "",
        slide_count: int = 8,
        llm: Any = None,
        **kwargs: Any,
    ) -> ToolResult:
        task_title = task_title or kwargs.get("title") or "Presentation"
        """Generate slide outline and HTML preview.

        Args:
            task_title: The presentation topic.
            summary: Meeting summary to base slides on.
            slide_count: Target number of slides (default 8, range 4-15).
            llm: The LLM instance from ctx.llm (required).

        Returns:
            ToolResult with outline and HTML in artifacts.
        """
        self.log(f"slides: generating {slide_count}-slide outline for \"{task_title[:50]}...\"")

        if not llm:
            return ToolResult(
                success=False,
                data={},
                summary="Slides tool requires an LLM instance.",
                error="Missing llm parameter.",
            )

        slide_count = min(max(slide_count, 4), 15)

        try:
            # Step 1: Generate the outline
            outline_system = (
                f"You are a presentation strategist. Create a {slide_count}-slide outline "
                f"for a boardroom-quality deck. Each slide should have:\n"
                f"1. A compelling title\n"
                f"2. 2-4 bullet points (not full sentences)\n"
                f"3. A speaker note (1 sentence on what to say)\n\n"
                f"Structure: Title slide → Context → Problem → Solution → "
                f"Evidence → Timeline → Next Steps → Closing.\n"
                f"Use markdown format: ## Slide N: Title, then bullets."
            )

            outline = await llm.complete(
                system=outline_system,
                prompt=f"Topic: {task_title}\n\nMeeting summary:\n{summary}",
                temperature=0.7,
            )

            self.log(f"slides: outline generated ({len(outline)} chars)")

            # Step 2: Generate HTML preview
            html_system = (
                "Convert the following slide outline into a clean, professional HTML fragment. "
                "Use semantic HTML: <section> per slide, <h2> for titles, <ul> for bullets. "
                "Add a simple CSS style block for a clean white background, dark text, and subtle borders. "
                "No JavaScript. No external resources. Make it look like a real slide deck preview."
            )

            html = await llm.complete(
                system=html_system,
                prompt=outline,
                temperature=0.5,
            )

            self.log(f"slides: HTML preview generated ({len(html)} chars)")

            return ToolResult(
                success=True,
                data={"outline": outline, "html": html, "slide_count": slide_count},
                summary=f"{slide_count}-slide outline and HTML preview generated.",
                artifacts=[
                    {"type": "markdown", "title": f"{task_title} — Outline", "content": outline},
                    {"type": "html", "title": f"{task_title} — Preview", "content": html},
                ],
            )

        except Exception as e:
            self.log(f"slides: error — {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary="Slide generation failed.",
                error=str(e),
            )

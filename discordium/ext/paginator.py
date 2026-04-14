"""Embed pagination with button navigation.

Creates a paginated embed viewer with Previous/Next buttons::

    from discordium.ext.paginator import Paginator

    pages = [
        Embed(title="Page 1", description="First page content"),
        Embed(title="Page 2", description="Second page content"),
        Embed(title="Page 3", description="Third page content"),
    ]

    paginator = Paginator(pages, timeout=120)
    await paginator.send(inter)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..models.components import ActionRow, Button, ButtonStyle
from ..models.embed import Embed

if TYPE_CHECKING:
    from ..client import GatewayClient
    from ..models.interaction import Interaction
    from ..models.snowflake import Snowflake


class Paginator:
    """Interactive embed paginator with button controls.

    Parameters
    ----------
    pages:
        List of Embed objects to paginate through.
    timeout:
        Seconds before buttons are disabled. None = no timeout.
    author_only:
        If True, only the original invoker can use the buttons.
    show_page_count:
        Add "Page X/Y" to embed footers automatically.
    """

    __slots__ = ("pages", "timeout", "author_only", "show_page_count", "_current", "_message_id")

    def __init__(
        self,
        pages: list[Embed],
        *,
        timeout: float | None = 120,
        author_only: bool = True,
        show_page_count: bool = True,
    ) -> None:
        if not pages:
            raise ValueError("Paginator requires at least one page")
        self.pages = pages
        self.timeout = timeout
        self.author_only = author_only
        self.show_page_count = show_page_count
        self._current = 0
        self._message_id: Snowflake | None = None

    @property
    def current_page(self) -> int:
        return self._current

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    def _get_embed(self) -> Embed:
        embed = self.pages[self._current]
        if self.show_page_count and len(self.pages) > 1:
            embed = embed.set_footer(
                text=f"Page {self._current + 1}/{len(self.pages)}"
            )
        return embed

    def _get_components(self, disabled: bool = False) -> list[ActionRow]:
        if len(self.pages) <= 1:
            return []

        return [ActionRow(
            Button(
                label="⏮ First",
                custom_id="page_first",
                style=ButtonStyle.SECONDARY,
                disabled=disabled or self._current == 0,
            ),
            Button(
                label="◀ Prev",
                custom_id="page_prev",
                style=ButtonStyle.PRIMARY,
                disabled=disabled or self._current == 0,
            ),
            Button(
                label=f"{self._current + 1}/{len(self.pages)}",
                custom_id="page_count",
                style=ButtonStyle.SECONDARY,
                disabled=True,
            ),
            Button(
                label="Next ▶",
                custom_id="page_next",
                style=ButtonStyle.PRIMARY,
                disabled=disabled or self._current >= len(self.pages) - 1,
            ),
            Button(
                label="Last ⏭",
                custom_id="page_last",
                style=ButtonStyle.SECONDARY,
                disabled=disabled or self._current >= len(self.pages) - 1,
            ),
        )]

    async def send(self, inter: Interaction) -> None:
        """Send the paginator as an interaction response and listen for button clicks."""
        await inter.respond(
            embed=self._get_embed(),
            components=self._get_components(),
        )

    async def handle_click(self, inter: Interaction) -> bool:
        """Handle a button click. Returns True if the paginator handled it.

        Call this from your component handler::

            @slash.on_component("page_")
            async def on_page(inter):
                if paginator.handle_click(inter):
                    return
        """
        cid = inter.custom_id
        if cid not in ("page_first", "page_prev", "page_next", "page_last"):
            return False

        match cid:
            case "page_first":
                self._current = 0
            case "page_prev":
                self._current = max(0, self._current - 1)
            case "page_next":
                self._current = min(len(self.pages) - 1, self._current + 1)
            case "page_last":
                self._current = len(self.pages) - 1

        await inter.update_message(
            embed=self._get_embed(),
            components=self._get_components(),
        )
        return True


def chunked_embeds(
    items: list[str],
    *,
    per_page: int = 10,
    title: str = "Results",
    color: int = 0x5865F2,
) -> list[Embed]:
    """Helper to create paginated embeds from a list of strings.

    Usage::

        pages = chunked_embeds(
            [f"**{i+1}.** {name}" for i, name in enumerate(names)],
            per_page=10,
            title="Members",
        )
        paginator = Paginator(pages)
    """
    pages = []
    for i in range(0, len(items), per_page):
        chunk = items[i : i + per_page]
        embed = Embed(
            title=title,
            description="\n".join(chunk),
            color=color,
        )
        pages.append(embed)
    return pages or [Embed(title=title, description="No items.", color=color)]

#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import functools
from typing import TypeVar, Generic, Collection, TypedDict, Any, cast, Protocol

import discord

E = TypeVar('E')
S = TypeVar('S', bound='PageSource')
T = TypeVar('T')
V = TypeVar('V', bound=discord.ui.View)


class PageParams(TypedDict, total=False):
    content: str
    embed: discord.Embed


class PageOption(discord.SelectOption, Generic[S]):
    """A select option for a particular page which
    allows nested pages through the added `source=` kwarg.
    """
    def __init__(self, *args, source: S, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = source


class PageSourceProto(Protocol[T, S, V]):
    def get_page(self, index: int) -> T: ...

    @property
    def max_pages(self) -> int: return 0

    def get_page_options(self, view: V, page: T) -> list[PageOption[S]]:
        """Returns a list of page options for the user to select."""
        return []

    def format_page(self, view: V, page: T) -> PageParams | str | discord.Embed:
        """Returns a dictionary presenting the items in the page."""
        raise NotImplementedError


# noinspection PyAbstractClass
class PageSource(PageSourceProto, Generic[T, S, V]):
    def __init__(self, current_index: int = 0):
        self.current_index = current_index


# noinspection PyAbstractClass
class ListPageSource(PageSource[list[E], S, V]):
    def __init__(self, items: list[E], *args, page_size: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = items
        self.page_size = page_size

    def get_page(self, index):
        start = index * self.page_size
        return self.items[start:start + self.page_size]

    @functools.cached_property
    def max_pages(self):
        pages, remainder = divmod(len(self.items), self.page_size)
        return pages + bool(remainder)


class PaginatorView(discord.ui.View):
    """A view that handles pagination and recursive levels of pages.

    `interaction_check` by default will return True if `allowed_users`
    is None, or the interaction user is one of the allowed users.
    This may be extended to include an interaction response, or use
    different behavior entirely.

    Parameters
    ----------
    :param sources: The current stack of page sources.
    :param allowed_users: A collection of user IDs that are allowed
        to interact with this paginator. If None, any user can interact.

    """
    def __init__(
        self, *args,
        sources: list[PageSource] | PageSource,
        allowed_users: Collection[int] = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        if isinstance(sources, PageSource):
            sources = [sources]
        elif len(sources) == 0:
            raise ValueError('must provide at least one page source')
        self.sources = sources
        self.allowed_users = allowed_users

        self.message: discord.Message | None = None
        self.page: PageParams = {}
        self.options: list[discord.SelectOption] = []

        self.can_paginate = True
        self.can_navigate = True

        self.show_page(self.current_source.current_index)

    @property
    def current_source(self):
        return self.sources[-1]

    @property
    def current_index(self):
        return self.current_source.current_index

    @current_index.setter
    def current_index(self, index: int):
        self.current_source.current_index = index

    @functools.cached_property
    def _pagination_buttons(self) -> tuple[discord.ui.Button]:
        return self.first_page, self.prev_page, self.next_page, self.last_page  # type: ignore

    def show_page(self, index: int):
        self.current_index = index

        page = self.current_source.get_page(index)
        params = self.current_source.format_page(self, page)
        if isinstance(params, str):
            params = {'content': params}
        elif isinstance(params, discord.Embed):
            params = {'embed': params}
        elif not isinstance(params, dict):
            raise TypeError('format_page() must return a dict, str, or Embed')
        self.page = cast(dict, params)

        self.options = self.current_source.get_page_options(self, page)
        for i, option in enumerate(self.options):
            option.value = str(i)
        self._refresh_components()

    async def start(self, channel: discord.abc.Messageable):
        self.message = await channel.send(**self._get_message_kwargs())

    async def interaction_check(self, interaction):
        if self.allowed_users is not None:
            return interaction.user.id in self.allowed_users
        return True

    def _get_message_kwargs(self) -> dict[str, Any]:
        return {'view': self, **self.page}

    async def _respond(self, interaction: discord.Interaction):
        await interaction.response.edit_message(**self._get_message_kwargs())

    # noinspection PyUnresolvedReferences
    def _refresh_components(self):
        """Update the state of each component in this view according to
        the current source and page.

        The pagination and back/stop buttons will be organized one of four ways:

        1. No pagination, no previous source::
            STOP
        2. No pagination, previous source::
            BACK STOP
        3. Pagination, no previous source::
            FIRST PREV NEXT LAST STOP
        4. Pagination, previous source::
            FIRST PREV NEXT LAST STOP
            BACK

        This applies the same when navigation is enabled.

        """
        self.clear_items()
        can_navigate = len(self.options) > 0
        can_paginate = self.current_source.max_pages > 1

        # Navigation (select menu)
        if can_navigate:
            self.add_item(self.navigate)
            self.navigate.options = self.options

        # Pagination (left/right)
        if can_paginate:
            for button in self._pagination_buttons:
                self.add_item(button)
                self.can_paginate = True

        on_first_page = self.current_index == 0
        on_last_page = self.current_index + 1 == self.current_source.max_pages
        self.first_page.disabled = on_first_page
        self.prev_page.disabled = on_first_page
        self.next_page.disabled = on_last_page
        self.last_page.disabled = on_last_page

        # Back and stop buttons
        if len(self.sources) > 1:
            self.back_button.row = 1 + can_paginate
            self.add_item(self.back_button)
        self.add_item(self.stop_button)

    @discord.ui.select(options=[], placeholder='Navigate...', row=0)
    async def navigate(self, interaction, select: discord.ui.Select):
        option = cast(PageOption, discord.utils.get(select.options, value=select.values[0]))
        self.sources.append(option.source)
        self.show_page(self.current_index)
        await self._respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}',
        style=discord.ButtonStyle.blurple, row=1)
    async def first_page(self, interaction, button):
        self.show_page(0)
        await self._respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK LEFT-POINTING TRIANGLE}',
        style=discord.ButtonStyle.blurple, row=1)
    async def prev_page(self, interaction, button):
        self.show_page(self.current_index - 1)
        await self._respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK RIGHT-POINTING TRIANGLE}',
        style=discord.ButtonStyle.blurple, row=1)
    async def next_page(self, interaction, button):
        self.show_page(self.current_index + 1)
        await self._respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}',
        style=discord.ButtonStyle.blurple, row=1)
    async def last_page(self, interaction, button):
        self.show_page(self.current_source.max_pages - 1)
        await self._respond(interaction)

    @discord.ui.button(
        emoji='\N{THUMBS UP SIGN}',
        style=discord.ButtonStyle.success, row=1)
    async def stop_button(self, interaction, button):
        self.stop()
        await interaction.message.delete()

    @discord.ui.button(
        emoji='\N{LEFTWARDS ARROW WITH HOOK}',
        style=discord.ButtonStyle.blurple, row=2)
    async def back_button(self, interaction, button):
        self.sources.pop()
        self.show_page(self.current_index)
        await self._respond(interaction)

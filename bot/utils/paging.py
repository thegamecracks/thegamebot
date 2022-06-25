#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import functools
from typing import TypeVar, Generic, Collection, TypedDict, Any, cast, Protocol, AsyncIterator

import discord

E = TypeVar('E')
S = TypeVar('S', bound='PageSource')
T = TypeVar('T')
V = TypeVar('V', bound=discord.ui.View)


class PageParams(TypedDict, total=False):
    content: str
    embed: discord.Embed


class PageOption(discord.SelectOption, Generic[S]):
    """A select option that can store a nested page
    through the added `source=` kwarg.
    """
    def __init__(self, *args, source: S, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = source


class PageSourceProto(Protocol[T, S, V]):
    def get_page(self, index: int) -> T:
        """Returns a page based on the given index.

        This method may be asynchronous.

        """

    @property
    def max_pages(self) -> int:
        """The max number of pages the page source can return.

        Can return zero to disable the view entirely.

        """
        return 1

    def get_page_options(self, view: V, page: T) -> list[PageOption[S]]:
        """Returns a list of page options for the user to select.

        This method may be asynchronous.

        """
        return []

    def format_page(self, view: V, page: T) -> PageParams | str | discord.Embed:
        """Returns a dictionary presenting the items in the page.

        This method may be asynchronous.

        """
        raise NotImplementedError


# noinspection PyAbstractClass
class PageSource(PageSourceProto, Generic[T, S, V]):
    """The base page source class."""
    def __init__(self, current_index: int = 0):
        self.current_index = current_index


# noinspection PyAbstractClass
class ListPageSource(PageSource[list[E], S, V]):
    """Paginates a list of elements."""
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


# noinspection PyAbstractClass
class AsyncIteratorPageSource(PageSource[list[E], S, V]):
    """Paginates an async iterator."""
    def __init__(self, iterator: AsyncIterator[E], *args, page_size: int, **kwargs):
        super().__init__()
        self._cache: list[E] = []
        self._iterator = iterator
        self._max_index = 0
        self._exhausted = False
        self.page_size = page_size

    async def get_page(self, index: int):
        start = index * self.page_size
        end = start + self.page_size
        if self._exhausted:
            return self._cache[start:end]

        # Get enough items to have at least one extra page
        # so paginator knows if next/last buttons should turn off
        required = end + self.page_size - len(self._cache)
        if required > 0:
            new_items = []
            max_index = index + 1
            for i in range(required):
                try:
                    new_items.append(await anext(self._iterator))
                except StopAsyncIteration:
                    max_index = (len(self._cache) + i) // self.page_size
                    self._exhausted = True
                    break
            self._cache.extend(new_items)
            self._max_index = max_index

        return self._cache[start:end]

    @property
    def max_pages(self):
        if self._exhausted and not self._cache:
            return 0
        return self._max_index + 1


class PaginatorView(discord.ui.View):
    """A view that handles pagination and recursive levels of pages.

    To use this view, pass a PageSource or list of PageSources
    (the last one will be displayed first) to the `sources=` kwarg,
    then begin the paginator using `await view.start(channel)`.

    If adding the view to another message is desired,
    `view.message` must be manually set for it to be accessible.
    The initial page is not rendered until the user interacts
    with the paginator or is explicitly done with `await view.show_page()`.

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
        self.option_sources: dict[str, PageSource] = {}

    @property
    def current_source(self):
        return self.sources[-1]

    @property
    def current_index(self):
        return self.current_source.current_index

    @current_index.setter
    def current_index(self, index: int):
        self.current_source.current_index = index

    @property
    def can_navigate(self):
        return len(self.options) > 0

    @property
    def can_paginate(self):
        return self.current_source.max_pages > 1

    @property
    def can_go_back(self):
        return len(self.sources) > 1

    @functools.cached_property
    def _pagination_buttons(self) -> tuple[discord.ui.Button]:
        return self.first_page, self.prev_page, self.next_page, self.last_page  # type: ignore

    async def show_page(self, index: int):
        self.current_index = index
        maybe_coro = discord.utils.maybe_coroutine

        page = await maybe_coro(self.current_source.get_page, index)
        params = await maybe_coro(self.current_source.format_page, self, page)
        if isinstance(params, str):
            params = {'content': params}
        elif isinstance(params, discord.Embed):
            params = {'embed': params}
        elif not isinstance(params, dict):
            raise TypeError('format_page() must return a dict, str, or Embed')
        self.page = cast(dict, params)

        options: list[PageOption] = await maybe_coro(self.current_source.get_page_options, self, page)
        option_sources = {}
        for i, option in enumerate(options):
            option.value = str(i)
            option_sources[option.value] = option.source
        self.options = options
        self.option_sources = option_sources

        self._refresh_components()

    async def start(self, channel: discord.abc.Messageable | discord.Interaction, ephemeral=True):
        await self.show_page(self.current_source.current_index)
        if isinstance(channel, discord.Interaction):
            await channel.response.send_message(ephemeral=ephemeral, **self._get_message_kwargs(initial_response=True))
            self.message = await channel.original_message()
        else:
            self.message = await channel.send(**self._get_message_kwargs())

    async def interaction_check(self, interaction):
        if self.allowed_users is not None:
            return interaction.user.id in self.allowed_users
        return True

    def _get_message_kwargs(self, *, initial_response=False) -> dict[str, Any]:
        # initial_response indicates if we can use view=None, necessary as
        # InteractionResponse.send_message() does not accept view=None
        kwargs = dict(self.page)
        max_pages = self.current_source.max_pages
        can_interact = self.can_navigate or self.can_paginate or self.can_go_back

        if max_pages > 0 and can_interact:
            kwargs['view'] = self
        elif not initial_response:
            kwargs['view'] = None

        return kwargs

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

        # Navigation (select menu)
        if self.can_navigate:
            self.add_item(self.navigate)
            self.navigate.options = self.options

        # Pagination (left/right)
        if self.can_paginate:
            for button in self._pagination_buttons:
                self.add_item(button)

        on_first_page = self.current_index == 0
        on_last_page = self.current_index + 1 >= self.current_source.max_pages
        self.first_page.disabled = on_first_page
        self.prev_page.disabled = on_first_page
        self.next_page.disabled = on_last_page
        self.last_page.disabled = on_last_page

        # Back and stop buttons
        if self.can_go_back:
            self.back_button.row = 1 + self.can_paginate
            self.add_item(self.back_button)
        self.add_item(self.stop_button)

    @discord.ui.select(options=[], placeholder='Navigate...', row=0)
    async def navigate(self, interaction, select: discord.ui.Select):
        source = self.option_sources[select.values[0]]
        self.sources.append(source)
        await self.show_page(self.current_index)
        await self._respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}',
        style=discord.ButtonStyle.blurple, row=1)
    async def first_page(self, interaction, button):
        await self.show_page(0)
        await self._respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK LEFT-POINTING TRIANGLE}',
        style=discord.ButtonStyle.blurple, row=1)
    async def prev_page(self, interaction, button):
        await self.show_page(self.current_index - 1)
        await self._respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK RIGHT-POINTING TRIANGLE}',
        style=discord.ButtonStyle.blurple, row=1)
    async def next_page(self, interaction, button):
        await self.show_page(self.current_index + 1)
        await self._respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}',
        style=discord.ButtonStyle.blurple, row=1)
    async def last_page(self, interaction, button):
        await self.show_page(self.current_source.max_pages - 1)
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
        await self.show_page(self.current_index)
        await self._respond(interaction)

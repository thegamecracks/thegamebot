#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
from dataclasses import dataclass, field
import datetime
import enum
import functools
import io
import itertools
import logging
import os
import random
import re
from typing import Callable, ClassVar, Dict, Optional, List, Union

import abattlemetrics as abm
import dateparser
import discord
from discord.ext import commands, menus, tasks
import humanize
from matplotlib import dates as mdates
import matplotlib.pyplot as plt
from matplotlib import ticker
import numpy as np

from bot import checks, converters, errors, utils

abm_log = logging.getLogger('abattlemetrics')
abm_log.setLevel(logging.INFO)
if not abm_log.hasHandlers():
    handler = logging.FileHandler(
        'abattlemetrics.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    abm_log.addHandler(handler)


# Utility functions
def format_hour_and_minute(seconds: Union[float, int]) -> str:
    seconds = round(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}:{minutes:02d}h'


# Giveaway stuff
class GiveawayStatus(enum.Enum):
    RUNNING = 0
    CANCELED = 1
    FINISHED = 2
    UNKNOWN = 3


def get_giveaway_status(m: discord.Message) -> GiveawayStatus:
    """Infer the status of a giveaway from the message."""
    if not m.embeds:
        return GiveawayStatus.UNKNOWN

    embed = m.embeds[0]
    title = str(embed.title).lower()
    if 'finish' in title:
        return GiveawayStatus.FINISHED
    elif 'cancel' in title:
        return GiveawayStatus.CANCELED

    return GiveawayStatus.RUNNING


def check_giveaway_status(
        giveaway_channel_id: int,
        check_func: Callable[[GiveawayStatus], bool],
        bad_response: str):
    """Check if the giveaway's status matches a condition.

    Searches through the last 10 messages for a giveaway message,
    i.e. where the status is not `GiveawayStatus.UNKNOWN`.

    This will add a `last_giveaway` attribute to the context which will
    be the giveaway message or None if it does not exist.

    """
    e = errors.ErrorHandlerResponse(bad_response)

    async def predicate(ctx):
        channel = ctx.bot.get_channel(giveaway_channel_id)

        ctx.last_giveaway = m = await channel.history(limit=10).find(
            lambda m: get_giveaway_status(m) != GiveawayStatus.UNKNOWN
        )
        if not m or not check_func(get_giveaway_status(m)):
            raise e

        return True

    return commands.check(predicate)


def is_giveaway_running(giveaway_channel_id):
    """Shorthand for checking if the giveaway's status is running."""
    return check_giveaway_status(
        giveaway_channel_id,
        lambda s: s == GiveawayStatus.RUNNING,
        'There is no giveaway running at the moment!'
    )


# Converters
class SteamIDConverter(commands.Converter):
    """Do basic checks on an integer to see if it may be a valid steam64ID."""
    REGEX = re.compile(r'\d{17}')
    INTEGER = 10_000_000_000_000_000

    async def convert(self, ctx, arg):
        if not self.REGEX.match(arg):
            raise commands.BadArgument('Could not parse Steam64ID.')
        return int(arg)


# Server status
class ServerStatusView(discord.ui.View):
    REFRESH_EMOJI = '\N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}'

    def __init__(self, status):
        super().__init__(timeout=None)
        self.status = status

        for i in self.children:
            if hasattr(i, 'custom_id'):
                i.custom_id += f':{status.message_id}'

    async def interaction_check(self, interaction: discord.Interaction):
        return not interaction.user.bot

    async def on_error(self, error, item, interaction):
        if not isinstance(error, errors.SkipInteractionResponse):
            return await super().on_error(error, item, interaction)

    @discord.ui.select(
        custom_id='signalstatus:select',
        placeholder='Extra options',
        options=[
            discord.SelectOption(
                emoji='\N{VIDEO GAME}',
                label='Playtime',
                description='Get playtime statistics for current players',
                value='playtime'
            )
        ]
    )
    async def on_select(self, select: discord.ui.Select, interaction: discord.Interaction):
        if self.status.last_server is None:
            await self.status.update()
            if self.status.last_server is None:
                raise errors.SkipInteractionResponse('Failed to update the status')

        method = getattr(self, 'on_select_' + select.values[0])
        await method(interaction)

    async def on_select_playtime(self, interaction: discord.Interaction):
        players = sorted(
            self.status.last_server.players,
            reverse=True, key=lambda p: p.playtime or 0
        )

        if not players:
            return await interaction.response.send_message(
                'There are no players online.',
                ephemeral=True
            )

        total_playtime = sum(p.playtime or 0 for p in players)

        embed = discord.Embed(
            color=self.status.line_color
        )

        items = []
        for p in players:
            name = discord.utils.escape_markdown(p.name)
            playtime = ''
            if p.playtime is not None:
                playtime = ' ({})'.format(format_hour_and_minute(p.playtime))
            items.append(f'{name}{playtime}')

        embed = self.status.add_fields(
            embed,
            items,
            name='Total playtime: {}'.format(
                format_hour_and_minute(total_playtime)
            )
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @discord.ui.button(
        custom_id='signalstatus:refresh',
        emoji=REFRESH_EMOJI,
        style=discord.ButtonStyle.green
    )
    async def on_refresh(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.status.update(interaction)


@dataclass
class ServerStatus:
    bot: commands.Bot
    bm_client: abm.BattleMetricsClient
    server_id: int
    channel_id: int
    message_id: int

    # The name of the map the server is running on.
    # Set to None to use whatever battlemetrics provides.
    server_map: Optional[str]

    # The ID of the channel to upload the graph to.
    graph_channel_id: int
    # The line color to use when creating the graph.
    line_color: int

    # Cooldown for editing
    edit_cooldown: commands.Cooldown
    # Cooldown for graph generation
    graph_cooldown: commands.Cooldown

    loop_interval: int

    last_server: Optional[abm.Server] = field(default=None, init=False)
    # Last message sent with the uploaded graph
    last_graph: Optional[discord.Message] = field(default=None, init=False)

    view: ServerStatusView = field(init=False)

    BM_SERVER_LINK: ClassVar[str] = 'https://www.battlemetrics.com/servers/{game}/{server_id}'

    def __post_init__(self):
        self.view = ServerStatusView(self)
        # Make the view start listening for events
        self.bot.add_view(self.view, message_id=self.message_id)

    @functools.cached_property
    def line_color_hex(self) -> str:
        return hex(self.line_color).replace('0x', '#', 1)

    @property
    def partial_message(self) -> Optional[discord.PartialMessage]:
        """Return a PartialMessage to the server status message."""
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            return channel.get_partial_message(self.message_id)

    async def fetch_server(self, *args, **kwargs):
        """Fetch the server and cache it in self.last_server.

        Args:
            *args
            **kwargs: Parameters to pass into get_server_info().

        Returns:
            Tuple[abattlemetrics.Server, Optional[abattlemetrics.Server]]:
                The server that was fetched and the previous server
                that was cached.

        """
        server = await self.bm_client.get_server_info(
            self.server_id, *args, **kwargs)
        old, self.last_server = self.last_server, server
        return server, old

    @staticmethod
    def add_fields(
            embed: discord.Embed, items: list, *, name: str = '\u200b'
        ) -> discord.Embed:
        """Add up to 3 fields in an embed for displaying a list of items.

        This mutates the given embed.

        Args:
            embed (discord.Embed): The embed to add fields to.
            items (list): A list of items to display in the fields.
                Each item is implicitly converted to a string.
            name (str): The name of the first field.

        Returns:
            discord.Embed

        """
        if items:
            # Group them into 1-3 fields in sizes of 5
            n_fields = min((len(items) + 4) // 5, 3)
            size = -(len(items) // -n_fields)  # ceil division
            fields = [items[i:i + size] for i in range(0, len(items), size)]

            for i, p_list in enumerate(fields):
                embed.add_field(
                    name='\u200b' if i else name,
                    value='\n'.join([str(x) for x in p_list])
                )

        return embed

    def create_embed(
            self, server: abm.Server
        ) -> discord.Embed:
        """Create the server status embed.

        Args:
            server (abattlemetrics.Server): The server to display in the embed.

        Returns:
            discord.Embed

        """
        now = datetime.datetime.now().astimezone()

        embed = discord.Embed(
            title=server.name,
            timestamp=now
        ).set_footer(
            text='Last updated'
        )

        description = [
            'View in [battlemetrics]({link})'.format(
                link=self.BM_SERVER_LINK
            ).format(
                game='arma3', server_id=self.server_id
            )
        ]

        if server.status != 'online':
            description.append('Server is offline')
            embed.description = '\n'.join(description)
            return embed

        embed.set_author(name=f'Rank #{server.rank:,}')

        description.append('Direct connect: steam://connect/{}:{}'.format(
            server.ip, server.port))
        description.append('Map: ' + (self.server_map or server.details['map']))
        description.append('Player Count: {0.player_count}/{0.max_players}'.format(server))
        description.append(
            'Last updated {}'.format(
                discord.utils.format_dt(now, style='R')
            )
        )
        players: List[abm.Player] = sorted(server.players, key=lambda p: p.name)
        for i, p in enumerate(players):
            name = discord.utils.escape_markdown(p.name)
            if p.first_time:
                name = f'__{name}__'

            score = f' ({p.score})' if p.score is not None else ''
            players[i] = f'{name}{score}'

        players: List[str]
        embed = self.add_fields(embed, players, name='Name (Score)')

        embed.description = '\n'.join(description)

        return embed

    def create_player_count_graph(
            self, datapoints, server, graphing_cog) -> io.BytesIO:
        """Generate a player count history graph.

        Args:
            datapoints (List[abattlemetrics.DataPoint])
            server (abattlemetrics.Server): The Server object.
                Used for determining the y-axis limits.
            graphing_cog (commands.Cog):  The Graphing cog.

        Returns:
            io.BytesIO

        """
        def format_hour(x, pos):
            return mdates.num2date(x).strftime('%I %p').lstrip('0')

        fig, ax = plt.subplots()

        # if any(None not in (d.min, d.max) for d in datapoints):
        #     # Resolution is not raw; generate bar graph with error bars
        #     pass

        # Plot player counts
        x, y = zip(*((d.timestamp, d.value) for d in datapoints))
        x_min, x_max = mdates.date2num(min(x)), mdates.date2num(max(x))
        lines = ax.plot(x, y, self.line_color_hex)  # , marker='.')

        # Set limits and fill under the line
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(0, server.max_players + 1)
        ax.fill_between(x, y, color=self.line_color_hex + '55')

        # Set xticks to every two hours
        step = 1 / 12
        start = x_max - step + (mdates.date2num(discord.utils.utcnow()) - x_max)
        ax.set_xticks(np.arange(start, x_min, -step))
        ax.xaxis.set_major_formatter(format_hour)
        ax.set_xlabel('UTC', loc='left', color=self.line_color_hex)

        # Set yticks
        ax.yaxis.set_major_locator(ticker.MultipleLocator(5))

        # Add grid
        ax.set_axisbelow(True)
        ax.grid(color='#707070', alpha=0.4)

        # Color the ticks and make spine invisible
        for spine in ax.spines.values():
            spine.set_color('#00000000')
        ax.tick_params(
            labelsize=9, color='#70707066',
            labelcolor=self.line_color_hex
        )

        # Make background fully transparent
        fig.patch.set_facecolor('#00000000')

        graphing_cog.set_axes_aspect(ax, 9 / 16, 'box')

        f = io.BytesIO()
        fig.savefig(f, format='png', bbox_inches='tight', pad_inches=0,
                    dpi=80)
        # bbox_inches, pad_inches: removes padding around the graph
        f.seek(0)

        plt.close(fig)
        return f

    async def upload_graph(self, server, graphing_cog):
        """Generate the player count graph, upload it, and cache
        the resulting message in self.last_graph.

        Args:
            server (abattlemetrics.Server): The Server object.
                Used to know the max number of players.
            graphing_cog (commands.Cog): The Graphing cog.

        Returns:
            discord.Message

        """
        stop = datetime.datetime.now(datetime.timezone.utc)
        start = stop - datetime.timedelta(hours=24)
        datapoints = await self.bm_client.get_player_count_history(
            self.server_id, start=start, stop=stop
        )

        try:
            f = await asyncio.to_thread(
                self.create_player_count_graph,
                datapoints, server, graphing_cog
            )
        except KeyError as e:
            # thanks matplotlib
            await self.bot.get_channel(852021637452267591).send(
                f'{e}\n{datapoints=}'
            )
            raise
        graph = discord.File(f, filename='graph.png')

        m = await self.bot.get_channel(self.graph_channel_id).send(file=graph)
        if self.last_graph:
            await self.last_graph.delete(delay=0)
        self.last_graph = m
        return m

    async def update(self, interaction: Optional[discord.Interaction] = None):
        """Update the server status message.

        Args:
            interaction (Optional[discord.Interaction]):
                The interaction to respond to when editing the message,
                if needed.

        Returns:
            Tuple[abattlemetrics.Server, discord.Embed]:
                The server fetched from the API and the embed generated
                from it.
            Tuple[float, None]: The time to wait before retrying.
                Results from either a cooldown or a 5xx response.

        """
        retry_after = self.edit_cooldown.update_rate_limit()
        if retry_after:
            return retry_after, None
        # NOTE: a high cooldown period will help with preventing concurrent
        # updates but this by itself does not remove the potential

        try:
            server, old = await self.fetch_server(include_players=True)
        except abm.HTTPException as e:
            if e.status >= 500 or e.status == 409:
                # 409: Thanks cloudflare
                return 30.0, None
            raise e

        embed = self.create_embed(server)

        # Add graph to embed
        graph = self.last_graph
        if not graph or not self.graph_cooldown.update_rate_limit():
            graphing_cog = self.bot.get_cog('Graphing')
            if graphing_cog:
                graph = await self.upload_graph(server, graphing_cog)
        attachment = graph.attachments[0]
        embed.set_image(url=attachment)

        if interaction:
            await interaction.response.edit_message(embed=embed, view=self.view)
        else:
            await self.partial_message.edit(embed=embed, view=self.view)

        return server, embed

    def _get_next_period(self, now=None, *, inclusive=False) -> int:
        """Get the number of seconds to sleep to reach the next period
        given the current time.

        For example, if the interval was 600s and the
        current time was HH:09:12, this would return 48s.

        Args:
            now (Optional[datetime.datetime]): The current time.
                Defaults to datetime.datetime.now(datetime.timezone.utc).
            inclusive (bool): Return 0 when the current time
                is already in sync with the interval.

        Returns:
            int

        """
        now = now or datetime.datetime.now(datetime.timezone.utc)
        seconds = now.minute * 60 + now.second
        wait_for = self.loop_interval - seconds % self.loop_interval
        if inclusive:
            wait_for %= self.loop_interval
        return wait_for

    @tasks.loop()
    async def update_loop(self):
        server, embed = await self.update()

        next_period = 15
        if isinstance(server, float):
            next_period = server
        elif server.status == 'online':
            next_period = self._get_next_period()
        await asyncio.sleep(next_period)

    update_loop.add_exception_type(discord.DiscordServerError)

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()

        # Sync to the next interval
        next_period = self._get_next_period(inclusive=True)
        await asyncio.sleep(next_period)


# Menu Page Sources
class EmbedPageSourceMixin:
    def get_embed_template(self, menu: menus.MenuPages):
        embed = discord.Embed(
            color=utils.get_bot_color(menu.bot)
        )

        if self.is_paginating():
            max_pages = self.get_max_pages()
            max_pages = '' if max_pages is None else f'/{max_pages}'
            embed.set_author(
                name=f'Page {menu.current_page + 1}{max_pages}'
            )

        return embed


class SessionPageSourceMixin:
    @classmethod
    def format_session(cls, session: abm.Session):
        started_at = session.stop or session.start
        playtime = int(session.playtime)

        # NOTE: humanize.naturaltime() only supports
        # naive local datetimes
        started_at = humanize.naturaltime(
            started_at.astimezone().replace(tzinfo=None)
        )

        return (
            started_at,
            f'Session lasted for {format_hour_and_minute(playtime)}'
            if playtime else 'Session is ongoing'
        )


class LastSessionAsyncPageSource(
        SessionPageSourceMixin, EmbedPageSourceMixin,
        menus.AsyncIteratorPageSource):
    def __init__(self, bm_client, server_id, ids, *, per_page, **kwargs):
        super().__init__(
            self.yield_sessions(bm_client, server_id, per_page + 1, ids),
            # NOTE: per_page + 1 since AsyncIteratorPageSource fetches
            # one extra to know if it has to paginate or not
            per_page=per_page,
            **kwargs
        )

    @staticmethod
    async def yield_sessions(
            bm_client, server_id: int, group_size: int, ids: list):
        """Yield the most recent sessions of a given list of steam/player IDs.

        Args:
            bm_client (abattlemetrics.BattleMetricsClient):
                The client to use for fetching sessions.
            server_id (int): The server's ID to get sessions from.
            group_size (int):
                When there are multiple steam64IDs, this specifies
                how many of those IDs are all matched at once.
                For typical usage in the page source, this should
                be set to per_page + 1.
            ids (Sequence[int]):
                A list of steam64IDs/player IDs to look up.

        Yields:
            Tuple[int, Optional[int], Optional[abattlemetrics.Session]]

        """
        async def fetch_group():
            async def get_session():
                if p_id is None:
                    # no user found for this steam ID
                    return (orig, None, None)

                session = await bm_client.get_player_session_history(
                    p_id, limit=1, server_ids=(server_id,)
                ).flatten()
                if not session:
                    return (orig, p_id, None)

                return (orig, p_id, session[0])

            # Separate steam IDs and player IDs
            steam_ids, player_ids = [], []
            for i, v in enumerate(group):
                if v >= SteamIDConverter.INTEGER:
                    steam_ids.append((i, v))
                else:
                    player_ids.append((i, v, v))

            if steam_ids:
                # Convert steam IDs into player IDs
                results = await bm_client.match_players(
                    *(v for i, v in steam_ids),
                    type=abm.IdentifierType.STEAM_ID
                )
                player_ids.extend((i, v, results[v]) for i, v in steam_ids)
                player_ids.sort()

            for i, orig, p_id in player_ids:
                yield await get_session()

        for n in range(0, len(ids), group_size):
            group = itertools.islice(ids, n, n + group_size)
            async for result in fetch_group():
                yield result

    async def format_page(self, menu, entries):
        embed = self.get_embed_template(menu)
        for i, p_id, session in entries:
            if p_id is None:
                val = 'Unknown steam ID'
            elif session is None:
                val = f'BM ID: {p_id}\n' if i != p_id else ''
                val += 'No session found'
            else:
                val = []
                if i != p_id:
                    val.append(f'BM ID: {p_id}')
                val.append(session.player_name)
                val.extend(self.format_session(session))
                val = '\n'.join(val)

            embed.add_field(name=i, value=val)

        return embed


class PlayerListPageSource(
        SessionPageSourceMixin, EmbedPageSourceMixin,
        menus.AsyncIteratorPageSource):
    def __init__(
            self, list_players, get_session, ids, **kwargs):
        super().__init__(
            self.yield_players(list_players, get_session, ids),
            **kwargs
        )
        self.ids = ids

    @staticmethod
    async def yield_players(list_players, get_session, ids: list):
        """Yield players and optionally their last sessions.

        Args:
            list_players: The BattleMetricsClient.list_players()
                method, which can be partially supplied with
                whatever parameters are desired aside from
                `limit` and `search`.
            get_session
                (Optional[Callable[[int],
                          abattlemetrics.AsyncSessionIterator]]):
                If session data is desired, the
                BattleMetricsClient.get_player_session_history()
                method can be provided for fetching session data.
            ids (Sequence[Union[int, str]]):
                A list of identifiers to look up.

        Yields:
            Tuple[abattlemetrics.Player, Optional[abattlemetrics.Session]]

        """
        max_search = 100
        groups = [
            itertools.islice(ids, n, n + max_search)
            for n in range(0, len(ids), max_search)
        ]
        for g in groups:
            search = '|'.join([str(i) for i in g])
            async for p in list_players(limit=max_search, search=search):
                session = None
                if get_session:
                    try:
                        session = await get_session(p.id, limit=1).next()
                    except StopAsyncIteration:
                        pass

                yield (p, session)

    async def format_page(self, menu, entries):
        embed = self.get_embed_template(menu)

        embed.set_footer(
            text=f'{len(self.ids)} whitelisted players'
        )

        for player, session in entries:
            # Get steam ID
            s_id = discord.utils.get(
                player.identifiers,
                type=abm.IdentifierType.STEAM_ID
            )
            name = s_id.name if s_id else '\u200b'

            val = [
                f'BM ID: {player.id}',
                player.name
            ]
            if session:
                val.extend(self.format_session(session))
            val.append('\u200b')  # helps readability on mobile
            val = '\n'.join(val)

            embed.add_field(name=name, value=val)

        return embed


class WhitelistPageSource(EmbedPageSourceMixin, menus.AsyncIteratorPageSource):
    def __init__(self, channels):
        super().__init__(
            self.yield_pages(self.yield_tickets(channels)),
            per_page=1
        )
        self.channels = channels

    @staticmethod
    def get_ticket_number(channel) -> int:
        m = re.search('\d+', channel.name)
        if m:
            return int(m.group())
        return 0

    @functools.cached_property
    def channel_span(self):
        start, end = self.channels[0], self.channels[-1]
        if start == end:
            return str(self.get_ticket_number(start))
        return '{}-{}'.format(
            self.get_ticket_number(start),
            self.get_ticket_number(end)
        )

    @staticmethod
    async def yield_pages(tickets):
        paginator = commands.Paginator(prefix='', suffix='', max_size=4096)
        page_number = 0
        # Yield pages as they are created
        async for line in tickets:
            paginator.add_line(line)

            # Use _pages to not prematurely close the current page
            pages = paginator._pages
            if len(pages) > page_number:
                yield pages[page_number]
                page_number += 1

        yield paginator.pages[-1]

    @staticmethod
    async def yield_tickets(channels):
        async def check(m):
            nonlocal match
            if m.author.bot:
                return False

            author = member_cache.get(m.author.id)
            if author is None:
                author = m.author
            elif isinstance(author, int):
                return author

            if not isinstance(author, discord.Member):
                try:
                    author = await m.guild.fetch_member(author.id)
                except discord.NotFound:
                    # Return ID to indicate the player has left
                    member_cache[author.id] = author.id
                    return author.id
                member_cache[author.id] = author

            # Optimized way of checking for staff role
            if not author._roles.get(811415496075247649):
                return False
            match = converters.CodeBlock.from_search(m.content)
            return match is not None and SteamIDConverter.REGEX.search(match.code)

        member_cache: Dict[int, Union[discord.Member, int]] = {}

        match: Optional[converters.CodeBlock] = None
        for c in channels:
            if not re.match(r'.+-\d+', c.name):
                continue

            async for message in c.history():
                status = await check(message)
                if status:
                    break
            else:
                yield f'{c.mention}: no message found'
                continue

            if isinstance(status, int):
                yield f'{c.mention}: <@{status}> has left'
            else:
                match: converters.CodeBlock
                yield (
                    '{c}: {a} ([Jump to message]({j}))\n`{m}`'.format(
                        c=c.mention,
                        a=message.author.mention,
                        m=match.code,
                        j=message.jump_url
                    )
                )

    async def format_page(self, menu, page: str):
        embed = self.get_embed_template(menu)
        embed.description = page
        embed.set_author(
            name=(
                f'{embed.author.name} ({self.channel_span})'
                if embed.author else f'Tickets {self.channel_span}'
            )
        ).set_footer(
            text=f'{len(self.channels)} tickets'
        )
        return embed


# Flags
class GiveawayStartFlags(commands.FlagConverter, delimiter=' ', prefix='--'):
    end: Optional[converters.DatetimeConverter]
    description: str
    title: str

class GiveawayEditFlags(commands.FlagConverter, delimiter=' ', prefix='--'):
    end: Optional[converters.DatetimeConverter]
    description: Optional[str]
    title: Optional[str]

    @classmethod
    async def convert(cls, ctx, argument):
        instance = await super().convert(ctx, argument)

        # Make sure at least one flag was specified
        if all(getattr(instance, f.attribute) is None for f in cls.get_flags().values()):
            raise errors.ErrorHandlerResponse(
                'At least one giveaway embed field must be specified to edit.')

        return instance


class SignalHill(commands.Cog):
    """Stuff for the Signal Hill server."""

    BM_SERVER_ID_INA = 10654566
    BM_SERVER_ID_SOG = 4712021
    BM_SERVER_ID_EXL = 12255260
    SERVER_STATUS_INTERVAL = 60
    SERVER_STATUS_EDIT_RATE = 10
    SERVER_STATUS_GRAPH_DEST = 842924251954151464
    SERVER_STATUS_GRAPH_RATE = 60 * 30
    GIVEAWAY_CHANNEL_ID = 850965403328708659  # testing: 850953633671020576
    GIVEAWAY_EMOJI_ID = 815804214470770728  # testing: 340900129114423296
    GUILD_ID = 811415496036843550
    WHITELIST_TICKET_REGEX = re.compile(r'(?P<name>.+)-(?P<n>\d+)(?P<flags>\w*)')
    WHITELISTED_PLAYERS_CHANNEL_ID = 824486812709027880

    def __init__(self, bot):
        self.bot = bot
        self.bm_client = abm.BattleMetricsClient(
            self.bot.session,
            token=os.getenv('BattlemetricsToken')
        )
        self.server_statuses = [
            ServerStatus(
                bot, self.bm_client,
                server_id=self.BM_SERVER_ID_INA,
                channel_id=819632332896993360,
                message_id=842228691077431296,
                server_map=None,
                line_color=0xF54F33,
                **self.create_server_status_params()
            ),
            ServerStatus(
                bot, self.bm_client,
                server_id=self.BM_SERVER_ID_SOG,
                channel_id=852008953968984115,
                message_id=852009695241175080,
                server_map='Cam Lao Nam',
                line_color=0x2FE4BF,
                **self.create_server_status_params()
            ),
            ServerStatus(
                bot, self.bm_client,
                server_id=self.BM_SERVER_ID_EXL,
                channel_id=869725276458864680,
                message_id=869725975502528552,
                server_map=None,
                line_color=0xEC33F5,
                **self.create_server_status_params()
            ),
        ]
        self.server_status_toggle()


    def cog_unload(self):
        for status in self.server_statuses:
            status.update_loop.cancel()
            status.view.stop()
        self.server_status_cleanup.cancel()

    @property
    def giveaway_channel(self):
        return self.bot.get_channel(self.GIVEAWAY_CHANNEL_ID)

    @property
    def giveaway_emoji(self):
        return self.bot.get_emoji(self.GIVEAWAY_EMOJI_ID)

    @property
    def guild(self):
        return self.bot.get_guild(self.GUILD_ID)

    @property
    def whitelist_channel(self):
        return self.bot.get_channel(self.WHITELISTED_PLAYERS_CHANNEL_ID)

    def create_server_status_params(self):
        return {
            'graph_channel_id': self.SERVER_STATUS_GRAPH_DEST,
            'edit_cooldown': commands.Cooldown(1, self.SERVER_STATUS_EDIT_RATE),
            'graph_cooldown': commands.Cooldown(1, self.SERVER_STATUS_GRAPH_RATE),
            'loop_interval': self.SERVER_STATUS_INTERVAL
        }


    @property
    def server_status_running(self) -> int:
        """The number of server statuses that are running."""
        return sum(
            status.update_loop.is_running() for status in self.server_statuses
        )


    @commands.Cog.listener('on_connect')
    async def on_connect_toggle_server_status(self):
        """Turn on the server statuses after connecting."""
        running = self.server_status_running
        if running != len(self.server_statuses):
            self.server_status_toggle()
            if running != 0:
                # We just canceled the remaining loops,
                # turn them all back on
                self.server_status_toggle()


    @commands.Cog.listener('on_raw_message_delete')
    @commands.Cog.listener('on_raw_message_edit')
    async def on_whitelist_update(self, payload):
        """Nullify the stored last message ID for the whitelist channel
        if a delete or edit was done inside the channel.
        This is so the "whitelist expired" command knows to refetch
        the list of player IDs.
        """
        if payload.channel_id == self.WHITELISTED_PLAYERS_CHANNEL_ID:
            settings = self.bot.get_cog('Settings')
            if not settings.get('checkwhitelist-last_message_id', None):
                settings.set('checkwhitelist-last_message_id', None).save()


    @tasks.loop(seconds=SERVER_STATUS_INTERVAL)
    async def server_status_cleanup(self):
        """Clean up extra graph messages once all server statuses have
        uploaded a graph and then stop.

        This assumes that all the server status graphs are uploaded
        to self.SERVER_STATUS_GRAPH_DEST.

        """
        messages = [
            status.last_graph for status in self.server_statuses
            if status.last_graph is not None
        ]
        total = len(self.server_statuses)
        if len(messages) != total:
            # Not all server statuses have sent
            return

        allowed_ids = {m.id for m in messages}

        def check(m):
            return m.id not in allowed_ids

        channel = self.bot.get_channel(self.SERVER_STATUS_GRAPH_DEST)
        await channel.purge(
            limit=total * 2,
            before=discord.Object(min(allowed_ids)),
            check=check
        )

        self.server_status_cleanup.stop()


    @server_status_cleanup.before_loop
    async def before_server_status_cleanup(self):
        await self.bot.wait_until_ready()


    def server_status_toggle(self) -> int:
        """Toggle the server status loops and returns the number
        of server statuses that have been canceled, or in other
        words the number of statuses that were running beforehand.

        If only some server statuses are running,
        this will cancel the remaining loops.

        """
        running = 0
        for status in self.server_statuses:
            running += status.update_loop.is_running()
            status.update_loop.cancel()
        self.server_status_cleanup.cancel()

        if not running:
            for status in self.server_statuses:
                # Forget the last graph sent so cleanup
                # will wait for new graphs to be created
                status.last_graph = None
                status.update_loop.start()
            self.server_status_cleanup.start()

        return running






    @commands.group(name='signalstatus')
    @commands.max_concurrency(1)
    @commands.is_owner()
    async def client_server_status(self, ctx):
        """Manage the Signal Hill server statuses."""


    @client_server_status.command(name='create')
    async def client_server_status_create(self, ctx, channel: discord.TextChannel):
        """Create a message with the server status view and temporary embed."""
        embed = discord.Embed(
            color=utils.get_bot_color(ctx.bot),
            description='Server status coming soon',
            timestamp=datetime.datetime.now()
        )
        await channel.send(embed=embed)


    @client_server_status.command(name='toggle')
    async def client_server_status_toggle(self, ctx):
        """Toggle the Signal Hill server statuses.
Automatically turns back on when the bot connects."""
        enabled = self.server_status_toggle() == 0
        emoji = '\N{LARGE GREEN CIRCLE}' if enabled else '\N{LARGE RED CIRCLE}'
        await ctx.message.add_reaction(emoji)





    @commands.group(name='whitelist')
    @commands.has_role('Staff')
    @checks.used_in_guild(GUILD_ID)
    async def client_whitelist(self, ctx):
        """Commands for managing whitelists."""


    async def _whitelist_get_player_ids(self) -> List[int]:
        settings = self.bot.get_cog('Settings')
        ids = settings.get('checkwhitelist-ids', None)
        last_message_id = settings.get('checkwhitelist-last_message_id', None)
        if (self.whitelist_channel.last_message_id != last_message_id
                or ids is None):
            ids = {}  # Use dict to maintain order and uniqueness

            # Fetch IDs from channel
            async for m in self.whitelist_channel.history(
                    limit=None, oldest_first=True):
                for match in SteamIDConverter.REGEX.finditer(m.content):
                    ids[int(match.group())] = None

            # Turn back into list
            ids = list(ids)

            # Cache them in settings
            settings.set(
                'checkwhitelist-ids', ids
            ).set(
                'checkwhitelist-last_message_id',
                self.whitelist_channel.last_message_id
            ).save()

        return ids


    @client_whitelist.command(name='active')
    @commands.cooldown(1, 120, commands.BucketType.default)
    async def client_whitelist_active(self, ctx):
        """Upload a file with two lists for active and expired whitelists."""
        def get_steam_or_bm_id(player: abm.Player) -> int:
            s_id = discord.utils.get(
                player.identifiers,
                type=abm.IdentifierType.STEAM_ID
            )
            return int(s_id.name) if s_id else player.id

        def write_players(players: list[abm.Player]):
            for p in players:
                f.write('{} = {}\n'.format(
                    p.name,
                    get_steam_or_bm_id(p)
                ))

        def sorted_players(players: list[abm.Player]) -> list[abm.Player]:
            mapping = {get_steam_or_bm_id(p): p for p in players}
            new = []
            for i in ids:
                p = mapping.pop(i, None)
                if p is not None:
                    new.append(p)
            new.extend(mapping.values())
            return new

        async with ctx.typing():
            ids = await self._whitelist_get_player_ids()

            # Fetch all whitelisted players
            source = PlayerListPageSource.yield_players(
                functools.partial(
                    self.bm_client.list_players,
                    public=False,
                    search='|'.join([str(n) for n in ids]),
                    include_identifiers=True
                ),
                functools.partial(
                    self.bm_client.get_player_session_history,
                    server_ids=(self.BM_SERVER_ID_INA,)
                ),
                ids
            )

            active, expired = [], []
            old = discord.utils.utcnow() - datetime.timedelta(weeks=2)
            async for player, session in source:
                if session is None or (session.stop or session.start) < old:
                    expired.append(player)
                else:
                    active.append(player)

            f = io.StringIO()
            f.write('===== ACTIVE =====\n\n')
            write_players(sorted_players(active))
            f.write('\n===== EXPIRED =====\n\n')
            write_players(sorted_players(expired))

        f.seek(0)
        await ctx.send(file=discord.File(f, filename='whitelists.txt'))


    @client_whitelist.command(name='accepted')
    @commands.cooldown(2, 60, commands.BucketType.default)
    @commands.max_concurrency(1, commands.BucketType.user)
    async def client_whitelist_accepted(self, ctx, open=False):
        """List whitelist tickets that have been approved.
This searches up to 100 messages in each whitelist ticket for acceptance from staff.

open: If True, looks through the open whitelist tickets instead of closed tickets."""
        category_id = 824502569652322304 if open else 824502754751152138
        category = ctx.bot.get_channel(category_id)

        if not category.text_channels:
            return await ctx.send('No whitelist tickets are open!')

        menu = menus.MenuPages(
            WhitelistPageSource(category.text_channels),
            clear_reactions_after=True
        )
        async with ctx.typing():
            await menu.start(ctx)

        if menu.should_add_reactions():
            # Wait for menu to finish outside of typing()
            # so it doesn't keep typing but max concurrency is still upheld
            await menu._event.wait()


    @client_whitelist.group(name='expired', invoke_without_command=True)
    @commands.cooldown(2, 60, commands.BucketType.default)
    @commands.max_concurrency(1, commands.BucketType.user)
    async def client_whitelist_expired(self, ctx, sessions: bool = False):
        """Check which whitelisted players have not been online within the last two weeks.
This looks through the steam IDs in the <#824486812709027880> channel.

sessions: If true, fetches session data for each player, including the last time they played. This may make queries slower."""
        async with ctx.typing():
            ids = await self._whitelist_get_player_ids()

        get_session = None
        if sessions:
            get_session = functools.partial(
                self.bm_client.get_player_session_history,
                server_ids=(self.BM_SERVER_ID_INA,)
            )

        menu = menus.MenuPages(
            PlayerListPageSource(
                functools.partial(
                    self.bm_client.list_players,
                    public=False,
                    search='|'.join([str(n) for n in ids]),
                    last_seen_before=discord.utils.utcnow() - datetime.timedelta(weeks=2),
                    include_identifiers=True
                ),
                get_session,
                ids,
                per_page=9
            ),
            clear_reactions_after=True
        )
        async with ctx.typing():
            try:
                await menu.start(ctx)
            except IndexError:
                await ctx.send(
                    f'All {len(ids)} whitelisted players have been active '
                    'within the last 2 weeks!'
                )

        if menu.should_add_reactions():
            # Wait for menu to finish outside of typing()
            # so it doesn't keep typing but max concurrency is still upheld
            await menu._event.wait()


    @client_whitelist_expired.command(name='dump')
    @commands.cooldown(1, 120, commands.BucketType.default)
    async def client_whitelist_expired_dump(self, ctx):
        """Send a list of the expired whitelists."""
        async with ctx.typing():
            ids = await self._whitelist_get_player_ids()
            now = discord.utils.utcnow()

            source = PlayerListPageSource.yield_players(
                functools.partial(
                    self.bm_client.list_players,
                    public=False,
                    search='|'.join([str(n) for n in ids]),
                    last_seen_before=now - datetime.timedelta(weeks=2),
                    include_identifiers=True
                ),
                functools.partial(
                    self.bm_client.get_player_session_history,
                    server_ids=(self.BM_SERVER_ID_INA,)
                ),
                ids
            )

            results = []
            async for player, session in source:
                s_id: Optional[abm.Identifier] = discord.utils.get(
                    player.identifiers,
                    type=abm.IdentifierType.STEAM_ID
                )
                id_: str = s_id.name if s_id else f'{player.id} (BM ID)'

                if session is not None:
                    started_at = session.stop or session.start
                    diff = now - started_at
                    diff_string = utils.timedelta_abbrev(diff)

                    results.append((
                        '{} = {} [{} {}]'.format(
                            player.name,
                            id_,
                            started_at.strftime('%m/%d').lstrip('0'),
                            diff_string
                        ),
                        started_at.timestamp()
                    ))
                else:
                    results.append((
                        '{} = {} [way outdated]'.format(player.name, id_),
                        0
                    ))

        # Sort by most recent
        results.sort(key=lambda x: x[1], reverse=True)

        paginator = commands.Paginator(prefix='', suffix='')
        for line, _ in results:
            paginator.add_line(line)

        for page in paginator.pages:
            await ctx.send(page)


    @client_whitelist.command(name='sort')
    @commands.bot_has_guild_permissions(manage_channels=True)
    @commands.cooldown(1, 120, commands.BucketType.default)
    @commands.max_concurrency(1, commands.BucketType.default)
    async def client_whitelist_sort(self, ctx, labels: bool = True):
        """Sort all the open whitelist tickets.

labels: Group channels together by their labels rather than a simple alphabetical sort."""
        def key(x):
            c, m = x
            if m is None:
                # Place unknown formats at the top
                return f'  {c.name}'
            elif labels:
                new_name = '{flags}{n}{name}'.format(**m.groupdict())
                if 'a' in m.group('flags'):
                    # Group accepted tickets together
                    return ' ' + new_name
                return new_name
            return c.name

        await ctx.message.add_reaction('\N{PERMANENT PAPER SIGN}')

        category = ctx.bot.get_channel(824502569652322304)
        tickets = [
            (c, self.WHITELIST_TICKET_REGEX.match(c.name))
            for c in category.text_channels
        ]

        sorted_tickets = sorted(tickets, key=key)

        min_pos = min(c.position for c, m in tickets)
        for i, (ch, _) in enumerate(sorted_tickets, start=min_pos):
            if ch.position == i:
                continue
            await ch.edit(position=i)

        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')





    @commands.command(name='lastsession')
    @commands.has_role('Staff')
    @checks.used_in_guild(GUILD_ID)
    @commands.max_concurrency(1, commands.BucketType.user)
    async def client_last_session(self, ctx, *ids: int):
        """Get one or more players' last session played on the I&A server.

ids: A space-separated list of steam64IDs or battlemetrics player IDs to check."""
        if len(ids) > 100:
            return await ctx.send('You are only allowed to provide 100 IDs at a time.')
        # Remove duplicates while retaining order using dict
        ids = dict.fromkeys(ids)

        menu = menus.MenuPages(
            LastSessionAsyncPageSource(
                self.bm_client, self.BM_SERVER_ID_INA, ids, per_page=6),
            clear_reactions_after=True
        )
        async with ctx.typing():
            await menu.start(ctx)

        if menu.should_add_reactions():
            # Wait for menu to finish outside of typing()
            # so it doesn't keep typing but max concurrency is still upheld
            await menu._event.wait()





    @commands.command(name='playtime')
    @commands.has_role('Staff')
    @checks.used_in_guild(GUILD_ID)
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def client_playtime(self, ctx, steam_id: SteamIDConverter):
        """Get someone's server playtime in the last month for the I&A server."""
        async with ctx.typing():
            results = await self.bm_client.match_players(
                steam_id, type=abm.IdentifierType.STEAM_ID)

            try:
                player_id = results[steam_id]
            except KeyError:
                return await ctx.send('Could not find a user with that steam ID!')

            player = await self.bm_client.get_player_info(player_id)

            stop = datetime.datetime.now(datetime.timezone.utc)
            start = stop - datetime.timedelta(days=30)
            datapoints = await self.bm_client.get_player_time_played_history(
                player_id, self.BM_SERVER_ID_INA, start=start, stop=stop)

        total_playtime = sum(dp.value for dp in datapoints)

        await ctx.send(
            'Player: {}\nPlaytime in the last month: {}'.format(
                player.name, format_hour_and_minute(total_playtime)
            )
        )





    @commands.group(name='giveaway')
    @commands.cooldown(2, 5, commands.BucketType.channel)
    @commands.has_role('Staff')
    @checks.used_in_guild(GUILD_ID)
    async def client_giveaway(self, ctx):
        """Commands for setting up giveaways."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)


    async def _giveaway_get_message(self):
        """Get the latest giveaway message."""
        try:
            return await self.giveaway_channel.history(limit=1).next()
        except discord.NoMoreItems:
            return None


    def _giveaway_create_embed(
            self, end: Optional[datetime.datetime],
            title: str, description: str):
        """Create the running giveaway embed."""
        embed = discord.Embed(
            color=discord.Color.gold(),
            description=description,
            title=title,
            timestamp=end or datetime.datetime.now()
        ).set_footer(
            text='End date' if end else 'Start date'
        )

        return embed


    def _giveaway_finish_embed(self, embed, winners, total):
        """Edit a running embed so the giveaway is finished."""
        plural = self.bot.inflector.plural
        k = len(winners)

        embed.color = discord.Color.green()

        embed.title = '{}\nThis giveaway has finished with {:,} {}!'.format(
            embed.title, total, plural('participant', total)
        )

        embed.add_field(
            name='The {} {}:'.format(
                plural('winner', k), plural('is', k)
            ),
            value='{}\n Please create a support ticket to '
                  'receive your reward!'.format(
                self.bot.inflector.join([u.mention for u in winners])
            )
        ).set_footer(
            text='Finish date'
        )
        embed.timestamp = datetime.datetime.now()

        return embed


    def _giveaway_reroll_embed(self, embed, winners, total, reason):
        """Edit a finished embed to replace the winners."""
        plural = self.bot.inflector.plural
        k = len(winners)

        embed.title = '{}\nThis giveaway has finished with {:,} {}!'.format(
            embed.title.split('\n')[0], total, plural('participant', total)
        )

        embed.clear_fields()

        embed.add_field(
            name='The (rerolled) {} {}:'.format(
                plural('winner', k), plural('is', k)
            ),
            value='{}\n Please create a support ticket to '
                  'receive your reward!'.format(
                self.bot.inflector.join([u.mention for u in winners])
            )
        ).add_field(
            name='Reason for rerolling:',
            value=reason
        ).set_footer(
            text='Rerolled at'
        )
        embed.timestamp = datetime.datetime.now()

        return embed

    def _giveaway_find_field_by_name(self, embed, name):
        return discord.utils.find(lambda f: name in f.name, embed.fields)


    async def _giveaway_get_participants(self, message, *, ignored=None):
        if not ignored:
            ignored = (self.bot.user.id,)

        reaction = discord.utils.find(
            lambda r: getattr(r.emoji, 'id', 0) == self.GIVEAWAY_EMOJI_ID,
            message.reactions
        )

        if reaction is None:
            return None, None

        participants = []
        async for user in reaction.users():
            if user.id not in ignored:
                participants.append(user)

        return reaction, participants


    def _giveaway_get_winners(self, embed, participants):
        m = re.match('\d+', embed.title)
        k = int(m.group() if m else 1)
        return random.choices(participants, k=k)


    def _giveaway_parse_winners_from_field(
            self, field) -> Optional[discord.Object]:
        """Parse the winner mention from the winner field."""
        return [
            int(m.group(1))
            for m in re.finditer(r'<@!?(\d+)>', field.value)
        ]


    @client_giveaway.command(name='cancel')
    @is_giveaway_running(GIVEAWAY_CHANNEL_ID)
    async def client_giveaway_cancel(self, ctx, *, description: str = None):
        """Cancel the current giveaway.
If a description is given, this replaces the giveaway's current description
and adds a title saying the giveaway has been canceled.
The giveaway message is deleted if no description is given."""
        if description is None:
            await ctx.last_giveaway.delete()
            return await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

        embed = ctx.last_giveaway.embeds[0]
        embed.color = discord.Color.dark_red()
        embed.title = 'This giveaway has been canceled.'
        embed.description = description

        embed.set_footer(text=embed.Empty)
        embed.timestamp = embed.Empty

        await ctx.last_giveaway.edit(embed=embed)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


    @client_giveaway.command(name='edit')
    @is_giveaway_running(GIVEAWAY_CHANNEL_ID)
    async def client_giveaway_edit(self, ctx, *, flags: GiveawayEditFlags):
        """Edit the giveaway message.

Usage:
--title 3x Apex DLCs --description Hello again! --end unknown

end: A date when the giveaway is expected to end. The end date can be removed by inputting a non-date. Assumes UTC if you don't have a timezone set with the bot.
title: The title of the giveaway.
description: The description of the giveaway."""
        embed = ctx.last_giveaway.embeds[0]

        if flags.title is not None:
            embed.title = flags.title
        if flags.description is not None:
            embed.description = flags.description
        if flags.end is not None:
            try:
                dt = await converters.DatetimeConverter().convert(ctx, flags.end)
            except commands.BadArgument as e:
                embed.timestamp = ctx.last_giveaway.created_at
                embed.set_footer(text='Start date')
            else:
                embed.timestamp = dt
                embed.set_footer(text='End date')

        await ctx.last_giveaway.edit(embed=embed)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


    @client_giveaway.command(name='finish')
    @is_giveaway_running(GIVEAWAY_CHANNEL_ID)
    async def client_giveaway_finish(self, ctx, ping: bool = True):
        """End the current giveaway and decide who the winner is."""
        reaction, participants = await self._giveaway_get_participants(ctx.last_giveaway)
        if reaction is None:
            return await ctx.send(
                'Giveaway is missing reaction: {}'.format(self.giveaway_emoji))
        elif not participants:
            return await ctx.send('There are no participants to choose from!')

        embed = ctx.last_giveaway.embeds[0]
        winners = self._giveaway_get_winners(embed, participants)

        # Update embed
        embed = self._giveaway_finish_embed(
            embed, winners,
            total=len(participants)
        )
        await ctx.last_giveaway.edit(embed=embed)

        await ctx.send(
            '# of participants: {:,}\n{}: {}'.format(
                len(participants),
                ctx.bot.inflector.plural('Winner', len(winners)),
                ctx.bot.inflector.join([u.mention for u in winners])
            ),
            allowed_mentions=discord.AllowedMentions(users=ping)
        )


    @client_giveaway.command(name='reroll')
    @check_giveaway_status(
        GIVEAWAY_CHANNEL_ID,
        lambda s: s == GiveawayStatus.FINISHED,
        'You can only reroll the winner when there is a finished giveaway!'
    )
    async def client_giveaway_reroll(
            self, ctx, winner: Optional[discord.User], *, reason):
        """Reroll the winner for a giveaway that has already finished.
This will include members that reacted after the giveaway has finished.

winner: The specific winner to reroll.
reason: The reason for rerolling the winner."""
        embed = ctx.last_giveaway.embeds[0]

        win_f = self._giveaway_find_field_by_name(embed, 'winner')
        previous_winners = self._giveaway_parse_winners_from_field(win_f)

        replacement_index = -1
        if winner:
            try:
                replacement_index = previous_winners.index(winner.id)
            except ValueError:
                return await ctx.send('That user is not one of the winners!')

        reaction, participants = await self._giveaway_get_participants(
            ctx.last_giveaway, ignored=(ctx.me.id, *previous_winners))
        if reaction is None:
            return await ctx.send(
                'Giveaway is missing reaction: {}'.format(self.giveaway_emoji))
        elif not participants:
            return await ctx.send(
                'There are no other participants to choose from!')

        if winner:
            replacement = random.choice(participants)
            new_winners = previous_winners.copy()
            new_winners[replacement_index] = replacement
            # Convert the rest into discord.Users
            for i, v in enumerate(new_winners):
                if isinstance(v, int):
                    new_winners[i] = await ctx.bot.fetch_user(v)
        else:
            new_winners = self._giveaway_get_winners(embed, participants)

        embed = self._giveaway_reroll_embed(
            embed, new_winners,
            total=len(participants) + (len(previous_winners) - 1) * bool(winner),
            reason=reason
        )
        await ctx.last_giveaway.edit(embed=embed)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


    @client_giveaway.command(name='simulate')
    async def client_giveaway_simulate(self, ctx, *, flags: GiveawayStartFlags):
        """Generate a giveaway message in the current channel.

Usage:
--title 2x Apex DLCs --description Hello world! --end in 1 day

end: An optional date when the giveaway is expected to end. Assumes UTC if you don't have a timezone set with the bot.
title: The title of the giveaway.
description: The description of the giveaway."""
        embed = self._giveaway_create_embed(**dict(flags))
        await ctx.send(embed=embed)


    @client_giveaway.command(name='start')
    @check_giveaway_status(
        GIVEAWAY_CHANNEL_ID,
        lambda s: s != GiveawayStatus.RUNNING,
        'There is already a giveaway running! Please "finish" or "cancel" '
        'the giveaway before creating a new one!'
    )
    async def client_giveaway_start(self, ctx, *, flags: GiveawayStartFlags):
        """Start a new giveaway in the giveaway channel.
Only one giveaway can be running at a time, for now that is.

The number of winners is determined by a prefixed number in the title, i.e. "2x Apex DLCs". If this number is not present, defaults to 1 winner.

Usage:
--title 2x Apex DLCs --description Hello world! --end in 1 day

end: An optional date when the giveaway is expected to end. Assumes UTC if you don't have a timezone set with the bot.
title: The title of the giveaway.
description: The description of the giveaway."""
        embed = self._giveaway_create_embed(**dict(flags))

        message = await self.giveaway_channel.send('@everyone', embed=embed)

        try:
            await message.add_reaction(self.giveaway_emoji)
        except discord.HTTPException:
            await ctx.send(
                'Warning: failed to add the giveaway reaction ({})'.format(
                    self.giveaway_emoji
                )
            )
        else:
            await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')










def setup(bot):
    bot.add_cog(SignalHill(bot))

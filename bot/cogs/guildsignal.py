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
from typing import Callable, ClassVar, Dict, Optional, List

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


class DateConverter(commands.Converter):
    """Parse a datetime."""
    def __init__(self, stored_tz=True):
        self.stored_tz = stored_tz

    async def convert(self, ctx, arg) -> datetime.datetime:
        dt = await ctx.bot.loop.run_in_executor(
            None, dateparser.parse, arg)

        if dt is None:
            raise commands.BadArgument('Could not parse date.')
        elif dt.tzinfo is None:
            if self.stored_tz:
                # Since the datetime was user inputted, if it's naive
                # it's probably in their timezone so don't assume it's UTC
                dt = await ctx.bot.localize_datetime(
                    ctx.author.id, dt, assume_utc=False, return_row=False)
            else:
                dt = dt.replace(tzinfo=datetime.timezone.utc)

        return dt


class SteamIDConverter(commands.Converter):
    """Do basic checks on an integer to see if it may be a valid steam64ID."""
    REGEX = re.compile(r'\d{17}')
    INTEGER = 10_000_000_000_000_000

    async def convert(self, ctx, arg):
        if not self.REGEX.match(arg):
            raise commands.BadArgument('Could not parse Steam64ID.')
        return int(arg)


class ServerStatusView(discord.ui.View):
    REFRESH_EMOJI = '\N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}'

    def __init__(self, status, cooldown, timeout=None):
        super().__init__(timeout=timeout)
        self.status = status
        self.cooldown = cooldown

    async def interaction_check(self, interaction: discord.Interaction):
        return (
            not interaction.user.bot
            and not self.cooldown.update_rate_limit()
        )

    @discord.ui.button(style=discord.ButtonStyle.green, emoji=REFRESH_EMOJI)
    async def on_refresh(self, button: discord.Button, interaction: discord.Interaction):
        await self.status.update()


@dataclass
class ServerStatus:
    bot: commands.Bot
    bm_client: abm.BattleMetricsClient
    server_id: int
    channel_id: int
    message_id: int

    # A range of active hours in the day.
    # Determines the header to use when creating the embed.
    active_hours: range
    # The name of the map the server is running on.
    # Set to None to use whatever battlemetrics provides.
    server_map: Optional[str]

    # The ID of the channel to upload the graph to.
    graph_channel_id: int
    # The line color to use when creating the graph.
    # Must be in the format '#rrggbb' (no transparency).
    line_color: str

    # Cooldown for editing
    edit_cooldown: commands.Cooldown
    # Cooldown for graph generation
    graph_cooldown: commands.Cooldown
    # Cooldown for clearing reaction without actually updating
    # (improves button response without actually making more queries)
    react_cooldown: commands.Cooldown

    loop_interval: int

    last_server: Optional[abm.Server] = field(default=None, init=False)
    # Last message sent with the uploaded graph
    last_graph: Optional[discord.Message] = field(default=None, init=False)

    view: ServerStatusView = field(init=False)

    BM_SERVER_LINK: ClassVar[str] = 'https://www.battlemetrics.com/servers/{game}/{server_id}'

    def __post_init__(self):
        self.view = ServerStatusView(self, self.react_cooldown)
        # Make the view start listening for events
        self.bot._connection.store_view(self.view, self.message_id)

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
            timestamp=datetime.datetime.now()
        ).set_footer(
            text='Last updated'
        )

        description = []

        maybe_offline = (
            '(If I am offline, scroll up or check [battlemetrics]({link}))')
        if now.hour not in self.active_hours:
            maybe_offline = (
                "(I may be offline at this time, if so you can "
                'scroll up or check [battlemetrics]({link}))'
            )
        maybe_offline = maybe_offline.format(
            link=self.BM_SERVER_LINK
        ).format(
            game='arma3', server_id=self.server_id
        )

        description.append(maybe_offline)

        if server.status != 'online':
            description.append('Server is offline')
            embed.description = '\n'.join(description)
            return embed

        embed.set_author(name=f'Rank #{server.rank:,}')

        description.append('Direct connect: steam://connect/{}:{}'.format(
            server.ip, server.port))
        description.append('Map: ' + (self.server_map or server.details['map']))
        description.append('Player Count: {0.player_count}/{0.max_players}'.format(server))
        # Generate list of player names with their playtime
        players: List[abm.Player] = sorted(
            server.players, reverse=True, key=lambda p: p.playtime or 0)
        for i, p in enumerate(players):
            name = discord.utils.escape_markdown(p.name)
            if p.first_time:
                name = f'__{name}__'
            pt = ''
            # if p.playtime:
            #     minutes, seconds = divmod(int(p.playtime), 60)
            #     hours, minutes = divmod(minutes, 60)
            #     pt = f' ({hours}:{minutes:02d}h)'
            score = f' ({p.score})' if p.score is not None else ''
            players[i] = f'{name}{pt}{score}'

        players: List[str]
        if players:
            # Group them into 1-3 fields in sizes of 5
            n_fields = min((len(players) + 4) // 5, 3)
            size = -(len(players) // -n_fields)  # ceil division
            fields = [players[i:i + size] for i in range(0, len(players), size)]
            for i, p_list in enumerate(fields):
                value = '\n'.join(p_list)
                name = '\u200b' if i else 'Name (Score)'
                embed.add_field(name=name, value=value)

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
        lines = ax.plot(x, y, self.line_color)  # , marker='.')

        # Set limits and fill under the line
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(0, server.max_players + 1)
        ax.fill_between(x, y, color=self.line_color + '55')

        # Set xticks to every two hours
        step = 1 / 12
        start = x_max - step + (mdates.date2num(datetime.datetime.utcnow()) - x_max)
        ax.set_xticks(np.arange(start, x_min, -step))
        ax.xaxis.set_major_formatter(format_hour)
        ax.set_xlabel('UTC', loc='left', color=self.line_color)

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
            labelcolor=self.line_color
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

        f = await self.bot.loop.run_in_executor(
            None, self.create_player_count_graph,
            datapoints, server, graphing_cog
        )
        graph = discord.File(f, filename='graph.png')

        m = await self.bot.get_channel(self.graph_channel_id).send(file=graph)
        if self.last_graph:
            await self.last_graph.delete(delay=0)
        self.last_graph = m
        return m

    async def update(self):
        """Update the server status message.

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
            if e.status >= 500:
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
    @staticmethod
    def utc_to_local(dt: datetime.datetime) -> datetime.datetime:
        """Convert a naive UTC datetime into a naive local datetime."""
        return dt.replace(
            tzinfo=datetime.timezone.utc
        ).astimezone().replace(tzinfo=None)

    @staticmethod
    def format_playtime(s: int) -> str:
        if s == 0:
            return 'Session is ongoing'

        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f'Session lasted for {h}:{m:02d}h'

    @classmethod
    def format_session(cls, session: abm.Session):
        started_at = session.stop or session.start
        playtime = int(session.playtime)

        # NOTE: humanize.naturaltime() only supports
        # naive local datetimes
        started_at = humanize.naturaltime(
            cls.utc_to_local(started_at)
        )

        return (
            started_at,
            cls.format_playtime(playtime)
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
        paginator = commands.Paginator(prefix='', suffix='', max_size=2048)
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
            if not re.match(r'.*?-\d+', c.name):
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
            name=f'{embed.author.name} ({self.channel_span})'
        ).set_footer(
            text=f'{len(self.channels)} tickets'
        )
        return embed


class SignalHill(commands.Cog):
    """Stuff for the Signal Hill server."""

    ACTIVE_HOURS = range(6, 22)
    BM_SERVER_ID_INA = 10654566
    BM_SERVER_ID_SOG = 4712021
    SERVER_STATUS_INTERVAL = 60
    SERVER_STATUS_EDIT_RATE = 10
    SERVER_STATUS_FALSE_EDIT_RATE = 5
    SERVER_STATUS_GRAPH_DEST = 842924251954151464
    SERVER_STATUS_GRAPH_RATE = 60 * 30
    GIVEAWAY_CHANNEL_ID = 850965403328708659  # testing: 850953633671020576
    GIVEAWAY_EMOJI_ID = 815804214470770728  # testing: 340900129114423296
    GUILD_ID = 811415496036843550
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
                line_color='#F54F33',
                **self.create_server_status_params()
            ),
            ServerStatus(
                bot, self.bm_client,
                server_id=self.BM_SERVER_ID_SOG,
                channel_id=852008953968984115,
                message_id=852009695241175080,
                server_map='Cam Lao Nam',
                line_color='#2FE4BF',
                **self.create_server_status_params()
            ),
        ]
        self.server_status_toggle()


    def cog_unload(self):
        for status in self.server_statuses:
            status.update_loop.cancel()
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
            'active_hours': self.ACTIVE_HOURS,
            'graph_channel_id': self.SERVER_STATUS_GRAPH_DEST,
            'edit_cooldown': commands.Cooldown(1, self.SERVER_STATUS_EDIT_RATE),
            'graph_cooldown': commands.Cooldown(1, self.SERVER_STATUS_GRAPH_RATE),
            'react_cooldown': commands.Cooldown(1, self.SERVER_STATUS_FALSE_EDIT_RATE),
            'loop_interval': self.SERVER_STATUS_INTERVAL
        }


    @property
    def server_status_running(self) -> int:
        """The number of server statuses that are running."""
        return sum(
            status.update_loop.is_running() for status in self.server_statuses
        )


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


    @commands.Cog.listener('on_connect')
    async def server_status_toggle_on_connect(self):
        """Turn on the server statuses after connecting."""
        running = self.server_status_running
        if running != len(self.server_statuses):
            self.server_status_toggle()
            if running != 0:
                # We just canceled the remaining loops,
                # turn them all back on
                self.server_status_toggle()






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
        view = ServerStatusView(None, None)
        await channel.send(embed=embed, view=view)
        view.stop()


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


    @commands.Cog.listener('on_raw_message_delete')
    @commands.Cog.listener('on_raw_message_edit')
    async def on_whitelist_update(self, payload):
        """Nullify the stored last message ID for the whitelist channel
        if a delete or edit was done inside the channel.
        """
        if payload.channel_id == self.WHITELISTED_PLAYERS_CHANNEL_ID:
            settings = ctx.bot.get_cog('Settings')
            if not settings.get('checkwhitelist-last_message_id', None):
                settings.set('checkwhitelist-last_message_id', None).save()


    async def get_whitelist_channel_ids(self) -> List[int]:
        settings = self.bot.get_cog('Settings')
        ids = settings.get('checkwhitelist-ids', None)
        last_message_id = settings.get('checkwhitelist-last_message_id', None)
        if (self.whitelist_channel.last_message_id != last_message_id
                or ids is None):
            ids = []

            # Fetch IDs from channel
            async for m in self.whitelist_channel.history(limit=None):
                for match in SteamIDConverter.REGEX.finditer(m.content):
                    ids.append(int(match.group()))

            # Cache them in settings
            settings.set(
                'checkwhitelist-ids',
                ids
            ).set(
                'checkwhitelist-last_message_id',
                whitelist_channel.last_message_id
            ).save()

        return ids


    @client_whitelist.group(name='expired', invoke_without_command=True)
    @commands.cooldown(2, 60, commands.BucketType.default)
    @commands.max_concurrency(1, commands.BucketType.user)
    async def client_whitelist_expired(self, ctx, sessions: bool = False):
        """Check which whitelisted players have not been online within the last two weeks.
This looks through the steam IDs in the <#824486812709027880> channel.

sessions: If true, fetches session data for each player, including the last time they played. This may make queries slower."""
        async with ctx.typing():
            ids = await self.get_whitelist_channel_ids()

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
                    # thankfully battlemetrics does not care how
                    # long the query string is
                    last_seen_before=datetime.datetime.now(datetime.timezone.utc)
                                     - datetime.timedelta(weeks=2),
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
            ids = await self.get_whitelist_channel_ids()

            source = PlayerListPageSource.yield_players(
                functools.partial(
                    self.bm_client.list_players,
                    public=False,
                    search='|'.join([str(n) for n in ids]),
                    last_seen_before=datetime.datetime.now(datetime.timezone.utc)
                                     - datetime.timedelta(weeks=2),
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
                s_id = discord.utils.get(
                    player.identifiers,
                    type=abm.IdentifierType.STEAM_ID
                )
                s_id = s_id.name if s_id else '\u200b'

                started_at = session.stop or session.start
                diff = datetime.datetime.utcnow() - started_at
                diff_string = utils.timedelta_abbrev(diff)

                results.append((
                    '{} = {} [{} {}]'.format(
                        player.name,
                        s_id,
                        started_at.strftime('%m/%d').lstrip('0'),
                        diff_string
                    ),
                    diff
                ))

        # Sort by most recent
        results.sort(key=lambda x: x[1])

        paginator = commands.Paginator(prefix='', suffix='')
        for line, _ in results:
            paginator.add_line(line)

        for page in paginator.pages:
            await ctx.send(page)





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
            player_id = results[steam_id]

            if player_id is None:
                return await ctx.send('Could not find a user with that steam ID!')

            player = await self.bm_client.get_player_info(player_id)

            stop = datetime.datetime.now(datetime.timezone.utc)
            start = stop - datetime.timedelta(days=30)
            datapoints = await self.bm_client.get_player_time_played_history(
                player_id, self.BM_SERVER_ID_INA, start=start, stop=stop)

        total_playtime = sum(dp.value for dp in datapoints)
        m, s = divmod(total_playtime, 60)
        h, m = divmod(m, 60)

        await ctx.send(
            'Player: {}\nPlaytime in the last month: {}:{:02d}h'.format(
                player.name, h, m
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
            self, end_date: Optional[datetime.datetime],
            title: str, description: str):
        """Create the running giveaway embed."""
        embed = discord.Embed(
            color=discord.Color.gold(),
            description=description,
            title=title,
            timestamp=end_date or datetime.datetime.now()
        ).set_footer(
            text='End date' if end_date else 'Start date'
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
    async def client_giveaway_edit(self, ctx, field, *, text):
        """Edit a field in the giveaway message.

field: "end", "title", or "description"
text: The text to replace the field with. If the field is "end" and your date could not be parsed, the end date is removed."""
        field = field.lower()

        embed = ctx.last_giveaway.embeds[0]
        if field == 'title':
            embed.title = text
        elif field == 'description':
            embed.description = text
        elif field == 'end':
            try:
                dt = await DateConverter().convert(ctx, text)
            except commands.BadArgument as e:
                embed.timestamp = ctx.last_giveaway.created_at
                embed.set_footer(text='Start date')
            else:
                embed.timestamp = dt
                embed.set_footer(text='End date')
        else:
            return await ctx.send(
                'Please specify the field to edit '
                '("title" or "description")'
            )

        await ctx.last_giveaway.edit(embed=embed)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


    @client_giveaway.command(name='finish')
    @is_giveaway_running(GIVEAWAY_CHANNEL_ID)
    async def client_giveaway_finish(self, ctx):
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
            allowed_mentions=discord.AllowedMentions.none()
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
    async def client_giveaway_simulate(
            self, ctx, end: Optional[DateConverter], title, *, description):
        """Generate a giveaway message in the current channel.

end: An optional date when the giveaway is expected to end. Assumes your timezone if you have one set with the bot, UTC otherwise.
title: The title of the giveaway.
description: The description of the giveaway."""
        embed = self._giveaway_create_embed(end, title, description)
        await ctx.send(embed=embed)


    @client_giveaway.command(name='start')
    @check_giveaway_status(
        GIVEAWAY_CHANNEL_ID,
        lambda s: s != GiveawayStatus.RUNNING,
        'There is already a giveaway running! Please "finish" or "cancel" '
        'the giveaway before creating a new one!'
    )
    async def client_giveaway_start(
            self, ctx, end: Optional[DateConverter], title, *, description):
        """Start a new giveaway in the giveaway channel.
Only one giveaway can be running at a time, for now that is.

The number of winners is determined by a prefixed number in the title, i.e. "2x Apex DLCs". If this number is not present, defaults to 1 winner.end: An optional date when the giveaway is expected to end. Assumes your timezone if you have one set with the bot, UTC otherwise.

end: An optional date when the giveaway is expected to end. Assumes your timezone if you have one set with the bot, UTC otherwise.
title: The title of the giveaway.
description: The description of the giveaway."""
        embed = self._giveaway_create_embed(end, title, description)

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

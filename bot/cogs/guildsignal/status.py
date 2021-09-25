#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import abc
import asyncio
from dataclasses import dataclass, field
import datetime
import functools
import io
from typing import ClassVar, Generic, Optional, TypeVar, Union

import abattlemetrics as abm
import discord
from matplotlib import dates as mdates
import matplotlib.pyplot as plt
from matplotlib import ticker
import mcstatus
import mcstatus.pinger
import numpy as np
from discord.ext import commands, tasks

from . import format_hour_and_minute, SignalHill
from bot import errors, utils

T = TypeVar('T')
V = TypeVar('V', bound='ServerStatusView')


@dataclass
class ServerStatus(abc.ABC, Generic[T, V]):
    bot: commands.Bot
    # The channel and message ID of the message to edit
    channel_id: int
    message_id: int
    # The ID of the channel to upload the graph to
    graph_channel_id: int
    # The line color to use when creating the graph
    line_color: int
    # Cooldown for editing
    edit_cooldown: commands.Cooldown
    # Cooldown for graph generation
    graph_cooldown: commands.Cooldown
    # The time between server status updates
    loop_interval: int

    # The class to use when constructing the view. Must be defined by subclasses.
    view_class: ClassVar[V]

    last_server: Optional[T] = field(default=None, init=False)
    last_graph: Optional[discord.Message] = field(default=None, init=False)
    view: V = field(init=False)

    def __post_init__(self):
        self.view = self.view_class(self)
        # Make the view start listening for events
        self.bot.add_view(self.view, message_id=self.message_id)

        self.update_loop.add_exception_type(discord.DiscordServerError)

    @functools.cached_property
    def line_color_hex(self) -> str:
        return hex(self.line_color).replace('0x', '#', 1)

    @property
    def partial_message(self) -> Optional[discord.PartialMessage]:
        """Return a PartialMessage to the server status message."""
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            return channel.get_partial_message(self.message_id)  # type: ignore

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

    async def _upload_graph(self, server: T, graphing_cog) -> Optional[discord.Message]:
        """Generate the player count graph, upload it, and cache
        the resulting message in self.last_graph.

        Args:
            server: The Server object.
                Used to know the max number of players.
            graphing_cog (commands.Cog): The Graphing cog.

        Returns:
            discord.Message: The message with the graph attached to it.
            None: Failed to either get the graph arguments or create the graph.

        Raises:
            discord.HTTPException:
                An error occurred while trying to upload the graph to discord.

        """
        args = await self.get_graph_args(server)
        if args is None:
            return None

        try:
            f = await asyncio.to_thread(
                self.create_player_count_graph,
                graphing_cog, *args
            )
        except KeyError:
            return None  # thanks matplotlib

        if f is None:
            return None

        m = await self.bot.get_channel(self.graph_channel_id).send(
            file=discord.File(f, filename='graph.png')
        )
        if self.last_graph:
            await self.last_graph.delete(delay=0)

        self.last_graph = m
        return m

    async def _fetch_server(self) -> tuple[Optional[T], Optional[T]]:
        """Fetch the server and cache it in self.last_server."""
        server = await self.fetch_server()
        old, self.last_server = self.last_server, server
        return server, old

    async def update(
        self, interaction: Optional[discord.Interaction] = None
    ) -> Union[tuple[T, discord.Embed], tuple[float, None]]:
        """Update the server status message.

        Args:
            interaction (Optional[discord.Interaction]):
                The interaction to respond to when editing the message,
                if needed.

        Returns:
            Tuple[T, discord.Embed]:
                The server fetched from the API and the embed generated
                from it.
            Tuple[float, None]: The time to wait before retrying.
                Results from either a cooldown or when fetch_server()
                returns None.

        """
        retry_after = self.edit_cooldown.update_rate_limit()
        if retry_after:
            return retry_after, None
        # NOTE: a high cooldown period will help with preventing concurrent
        # updates but this by itself does not remove the potential

        server, old = await self._fetch_server()
        if server is None:
            return 30.0, None

        embed = self.create_embed(server)

        # Add graph to embed
        graph = self.last_graph
        if graph is None or self.graph_cooldown.get_retry_after() == 0:
            graphing_cog = self.bot.get_cog('Graphing')
            if graphing_cog:
                graph = await self._upload_graph(server, graphing_cog)
                # Only update cooldown if a new graph was created
                if graph is not None:
                    self.graph_cooldown.update_rate_limit()
                else:
                    graph = self.last_graph

        if isinstance(graph, discord.Message):
            attachment = graph.attachments[0]
            embed.set_image(url=attachment.url)

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
        elif self.is_online(server):
            next_period = self._get_next_period()
        await asyncio.sleep(next_period)

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()

        # Sync to the next interval
        next_period = self._get_next_period(inclusive=True)
        await asyncio.sleep(next_period)

    @abc.abstractmethod
    def create_embed(self, server: T) -> discord.Embed:
        """Create the server status embed."""

    @abc.abstractmethod
    def create_player_count_graph(self, graphing_cog, *args) -> Optional[io.BytesIO]:
        """Graph the number of players over time.

        Args:
            graphing_cog (commands.Cog): The Graphing cog.
            *args: Whatever arguments are returned by get_graph_args().

        Returns:
            io.BytesIO: The image that was created.
            None: No graph could be generated.

        """

    @abc.abstractmethod
    async def fetch_server(self) -> Optional[T]:
        """Query the data for the server.

        Returns:
            T: The server object.
            None: Failed to fetch the server. This cancels the update.

        """

    @abc.abstractmethod
    async def get_graph_args(self, server: T) -> Optional[tuple]:
        """Return the arguments to be passed into create_player_count_graph().

        Returns:
            tuple: A tuple of arguments.
            None: Failed to create the arguments. This will cause the
                status to re-use the previous graph that was created.

        """

    @abc.abstractmethod
    def is_online(self, server: T) -> bool:
        """Return a bool indicating if the server is online."""


class ServerStatusRefresh(discord.ui.Button['ServerStatusView']):
    async def callback(self, interaction: discord.Interaction):
        await self.view.status.update(interaction)


class ServerStatusSelect(discord.ui.Select['ServerStatusView']):
    async def callback(self, interaction: discord.Interaction):
        if self.view.status.last_server is None:
            await self.view.status.update()
            if self.view.status.last_server is None:
                raise errors.SkipInteractionResponse('Failed to update the status')

        for v in self.values:
            method = getattr(self.view, 'on_select_' + v)
            await method(interaction)


class ServerStatusView(discord.ui.View):
    REFRESH_EMOJI = '\N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}'

    def __init__(self, status: ServerStatus, select_options: list = ()):
        super().__init__(timeout=None)
        self.status = status

        if select_options:
            self.add_item(ServerStatusSelect(
                custom_id='signalstatus:select',
                options=select_options,
                placeholder='Extra options'
            ))

        self.add_item(ServerStatusRefresh(
            custom_id='signalstatus:refresh',
            emoji=self.REFRESH_EMOJI,
            style=discord.ButtonStyle.green
        ))

    async def interaction_check(self, interaction: discord.Interaction):
        return not interaction.user.bot

    async def on_error(self, error, item, interaction):
        if not isinstance(error, (errors.SkipInteractionResponse, KeyError)):
            return await super().on_error(error, item, interaction)


class BMServerStatusView(ServerStatusView):
    def __init__(self, status: 'BMServerStatus'):
        super().__init__(
            status, select_options=[
                discord.SelectOption(
                    emoji='\N{VIDEO GAME}',
                    label='Playtime',
                    description='Get playtime statistics for current players',
                    value='playtime'
                )
            ]
        )

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

        self.status.add_fields(
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


@dataclass
class BMServerStatus(ServerStatus[abm.Server, BMServerStatusView]):
    bm_client: abm.BattleMetricsClient
    server_id: int

    # The name of the map the server is running on.
    # Set to None to use whatever battlemetrics provides.
    server_map: Optional[str] = None

    view_class = BMServerStatusView

    BM_SERVER_LINK: ClassVar[str] = 'https://www.battlemetrics.com/servers/{game}/{server_id}'

    def create_embed(self, server: abm.Server) -> discord.Embed:
        """Create the server status embed."""
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
                game=server.payload['data']['relationships']['game']['data']['id'],
                server_id=self.server_id
            )
        ]

        if not self.is_online(server):
            description.append('Server is offline')
            embed.description = '\n'.join(description)
            return embed

        embed.set_author(name=f'Rank #{server.rank:,}')

        description.append('Direct connect: steam://connect/{}:{}'.format(
            server.ip, server.port))
        server_map = self.server_map or server.details.get('map')
        if server_map:
            description.append(f'Map: {server_map}')
        description.append('Player Count: {0.player_count}/{0.max_players}'.format(server))
        description.append(
            'Last updated {}'.format(
                discord.utils.format_dt(now, style='R')
            )
        )
        players: list[abm.Player] = sorted(server.players, key=lambda p: p.name)
        for i, p in enumerate(players):
            name = discord.utils.escape_markdown(p.name)
            if p.first_time:
                name = f'__{name}__'

            score = f' ({p.score})' if p.score is not None else ''
            players[i] = f'{name}{score}'

        players: list[str]
        self.add_fields(embed, players, name='Name (Score)')

        embed.description = '\n'.join(description)

        return embed

    def create_player_count_graph(self, graphing_cog, *args) -> io.BytesIO:
        def format_hour(x, pos):
            return mdates.num2date(x).strftime('%I %p').lstrip('0')

        datapoints: list[abm.DataPoint]
        y_max: int
        datapoints, y_max = args

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
        ax.set_ylim(0, y_max + 1)
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

    async def fetch_server(self) -> Optional[abm.Server]:
        try:
            return await self.bm_client.get_server_info(
                self.server_id, include_players=True
            )
        except abm.HTTPException as e:
            if e.status >= 500 or e.status == 409:
                # 409: Thanks cloudflare
                return None
            raise e

    async def get_graph_args(self, server: abm.Server) -> Optional[tuple]:
        stop = datetime.datetime.now(datetime.timezone.utc)
        start = stop - datetime.timedelta(hours=24)
        try:
            datapoints = await self.bm_client.get_player_count_history(
                self.server_id, start=start, stop=stop
            )
        except abm.HTTPException as e:
            if e.status >= 500 or e.status == 409:
                return None
            raise e
        return datapoints, server.max_players

    def is_online(self, server: abm.Server) -> bool:
        return server.status == 'online'


@dataclass
class MCServerStatus(ServerStatus[Union[mcstatus.pinger.PingResponse, Exception], ServerStatusView]):
    mc_client: mcstatus.MinecraftServer

    view_class = ServerStatusView

    ServerType: ClassVar = Union[mcstatus.pinger.PingResponse, Exception]

    def create_embed(self, server: ServerType) -> discord.Embed:
        """Create the server status embed."""
        now = datetime.datetime.now().astimezone()

        embed = discord.Embed(
            color=self.line_color,
            title=self.mc_client.host,
            timestamp=now
        ).set_footer(
            text='Last updated'
        )

        if not self.is_online(server):
            embed.description = 'Failed to ping the server'
            return embed

        description = [
            'Version: {}'.format(server.version.name),
            'Player Count: {0.players.online}/{0.players.max}'.format(server),
            'Last updated {}'.format(discord.utils.format_dt(now, style='R'))
        ]

        if server.players.sample:
            players = sorted(
                discord.utils.escape_markdown(p.name)
                for p in server.players.sample
            )
            self.add_fields(embed, players)

        embed.description = '\n'.join(description)

        return embed

    def create_player_count_graph(self, graphing_cog, *args) -> Optional[io.BytesIO]:
        return None

    async def fetch_server(self) -> Optional[ServerType]:
        try:
            return await self.mc_client.async_status()
        except ConnectionError as e:
            return e

    async def get_graph_args(self, server: ServerType) -> Optional[tuple]:
        return ()

    def is_online(self, server: ServerType) -> bool:
        return isinstance(server, mcstatus.pinger.PingResponse)


class _SignalHill_Status(commands.Cog):
    SERVER_STATUS_INTERVAL = 60
    SERVER_STATUS_EDIT_RATE = 10
    SERVER_STATUS_GRAPH_DEST = 842924251954151464
    SERVER_STATUS_GRAPH_RATE = 60 * 30

    def __init__(self, bot, base: SignalHill):
        self.bot = bot
        self.base = base
        self.server_statuses = [
            BMServerStatus(
                bot=bot,
                channel_id=819632332896993360,
                message_id=842228691077431296,
                line_color=0xF54F33,
                bm_client=base.bm_client,
                server_id=base.BM_SERVER_ID_INA,
                **self.create_server_status_params()
            ),
            BMServerStatus(
                bot=bot,
                channel_id=891139561265168384,
                message_id=891139679209001001,
                line_color=0x2FE4BF,
                bm_client=base.bm_client,
                server_id=base.BM_SERVER_ID_SOG,
                server_map='Cam Lao Nam',
                **self.create_server_status_params()
            ),
            MCServerStatus(
                bot=bot,
                channel_id=852008953968984115,
                message_id=852009695241175080,
                line_color=0x5EE060,
                mc_client=mcstatus.MinecraftServer.lookup(
                    'signalhillgaming.apexmc.co'
                ),
                **self.create_server_status_params()
            ),
            # BMServerStatus(
            #     bot=bot,
            #     channel_id=852008953968984115,
            #     message_id=852009695241175080,
            #     line_color=0x5EE060,
            #     bm_client=base.bm_client,
            #     server_id=base.BM_SERVER_ID_MCF,
            #     **self.create_server_status_params()
            # ),
        ]
        self.server_status_toggle()

    def cog_unload(self):
        for status in self.server_statuses:
            status.update_loop.cancel()
            status.view.stop()
        self.server_status_cleanup.cancel()

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

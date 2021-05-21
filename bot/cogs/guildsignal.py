import asyncio
import datetime
import io
import itertools
import logging
import math
from typing import Optional

import abattlemetrics as abm
import discord
from discord.ext import commands, tasks
from matplotlib import dates as mdates
import matplotlib.pyplot as plt
from matplotlib import ticker
import numpy as np
from scipy.interpolate import make_interp_spline

from bot import utils

abm_log = logging.getLogger('abattlemetrics')
abm_log.setLevel(logging.DEBUG)
if not abm_log.hasHandlers():
    handler = logging.FileHandler(
        'abattlemetrics.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    abm_log.addHandler(handler)


class SignalHill(commands.Cog):
    """Stuff for the Signal Hill server."""

    ACTIVE_HOURS = range(6, 22)
    BM_SERVER_LINK = 'https://www.battlemetrics.com/servers/{game}/{server_id}'
    INA_SERVER_ID = 10654566
    INA_STATUS_MESSAGE_ID = (819632332896993360, 842228691077431296)
    INA_STATUS_SECONDS = 60
    INA_STATUS_EDIT_RATE = 10
    INA_STATUS_GRAPH_DEST = 842924251954151464
    INA_STATUS_GRAPH_RATE = 60 * 30
    REFRESH_EMOJI = '\N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}'

    def __init__(self, bot):
        self.bot = bot
        self.bm_client = abm.BattleMetricsClient(self.bot.session)
        self.ina_status_enabled = True
        self.ina_status_last_server = None
        # The last Server query from battlemetrics
        self.ina_status_cooldown = commands.Cooldown(
            1, self.INA_STATUS_EDIT_RATE, commands.BucketType.default)
        # Cooldown for editing
        self.ina_status_graph_last = None
        # Last message sent with graph
        self.ina_status_graph_cooldown = commands.Cooldown(
            1, self.INA_STATUS_GRAPH_RATE, commands.BucketType.default)
        # Cooldown for graph generation
        self.ina_status_loop.start()


    def cog_unload(self):
        self.ina_status_loop.cancel()


    @property
    def partial_ina_status(self) -> Optional[discord.PartialMessage]:
        """Return a PartialMessage displaying the I&A status."""
        channel_id, message_id = self.INA_STATUS_MESSAGE_ID
        channel = self.bot.get_channel(channel_id)
        if channel:
            return channel.get_partial_message(message_id)


    @staticmethod
    def ina_status_should_update(old, new):
        """Compare particular attributes of two Server objects to see
        if the status should be updated."""
        def player_set(s):
            return set((p.id, p.playtime) for p in s.players)

        attrs = ('player_count', 'status', 'max_players', 'name')

        # Check uptime, do not update if old and new are both offline
        if new.status != 'online' and old.status != 'online':
            return False

        # Check basic attributes
        if any(getattr(old, a) != getattr(new, a) for a in attrs):
            return True

        # Check players
        return player_set(old) != player_set(new)


    async def ina_status_fetch_server(self, *args, **kwargs):
        """Fetch the I&A server and replace self.ina_status_last_server.

        Args:
            *args
            **kwargs: Parameters to pass into get_server_info().

        Returns:
            Tuple[abattlemetrics.Server, Optional[abattlemetrics.Server]]:
                The server that was fetched and the previous value
                or self.ina_status_last_server.

        """
        server = await self.bm_client.get_server_info(*args, **kwargs)
        old, self.ina_status_last_server = self.ina_status_last_server, server
        return server, old


    def ina_status_create_embed(self, server: abm.Server):
        """Create the embed for updating the I&A status.

        Returns:
            discord.Embed

        """
        now = datetime.datetime.now().astimezone()

        embed = discord.Embed(
            title=server.name,
            timestamp=datetime.datetime.utcnow()
        ).set_footer(
            text='Last updated'
        )

        description = []

        maybe_offline = (
            '(If I am offline, scroll up or check [battlemetrics]({link}))')
        if not now.hour in self.ACTIVE_HOURS:
            maybe_offline = (
                "(I may be offline at this time, if so you can "
                'scroll up or check [battlemetrics]({link}))'
            )
        maybe_offline = maybe_offline.format(
            link=self.BM_SERVER_LINK
        ).format(
            game='arma3', server_id=self.INA_SERVER_ID
        )

        description.append(maybe_offline)

        if server.status != 'online':
            description.append('Server is offline')
            embed.description = '\n'.join(description)
            return embed

        embed.set_author(name=f'Rank #{server.rank:,}')

        description.append('Map: ' + server.details['map'])
        description.append('Player Count: {0.player_count}/{0.max_players}'.format(server))
        # Generate list of player names with their playtime
        players = sorted(
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


    async def ina_status_upload_graph(self, server, graphing_cog):
        """Generate the player count graph, upload it, and cache
        the resulting message in self.ina_status_graph_last.

        Args:
            server (abattlemetrics.Server): The Server object.
                Used to know the max number of players.
            graphing_cog (commands.Cog): The Graphing cog.

        Returns:
            discord.Message

        """
        stop = datetime.datetime.utcnow()
        start = stop - datetime.timedelta(hours=24)
        datapoints = await self.bm_client.get_player_count_history(
            self.INA_SERVER_ID, start=start, stop=stop
        )

        f = await self.bot.loop.run_in_executor(
            None, self.ina_status_player_count_graph,
            datapoints, server, graphing_cog
        )
        graph = discord.File(f, filename='graph.png')

        m = await self.bot.get_channel(self.INA_STATUS_GRAPH_DEST).send(file=graph)
        if self.ina_status_graph_last:
            await self.ina_status_graph_last.delete(delay=0)
        self.ina_status_graph_last = m
        return m


    async def ina_status_update(self):
        """Update the I&A status message.

        Returns:
            Tuple[abattlemetrics.Server, discord.Embed]:
                The server fetched from the API and the embed generated
                from it.
            Tuple[float, None]: On cooldown.

        """
        retry_after = self.ina_status_cooldown.update_rate_limit(None)
        if retry_after:
            return retry_after, None
        # NOTE: a high cooldown period will help with preventing concurrent
        # updates but this by itself does not remove the potential

        message = self.partial_ina_status

        server, old = await self.ina_status_fetch_server(
            self.INA_SERVER_ID, include_players=True)

        embed = self.ina_status_create_embed(server)

        m = self.ina_status_graph_last
        if not m or not self.ina_status_graph_cooldown.update_rate_limit(None):
            graphing_cog = self.bot.get_cog('Graphing')
            if graphing_cog:
                m = await self.ina_status_upload_graph(server, graphing_cog)
        attachment = m.attachments[0]

        if attachment:
            embed.set_image(url=attachment)

        await message.edit(embed=embed)
        return server, embed


    def get_next_period(self, interval: int, now=None,
                        *, inclusive=False) -> int:
        """Get the number of seconds to sleep to reach the next period
        given the current time.

        For example, if the interval was 600s and the
        current time was X:09:12, this would return 48s.

        Args:
            interval (int): The interval per hour in seconds.
            now (Optional[datetime.datetime]): The current time.
                Defaults to datetime.datetime.utcnow().
            inclusive (bool): If True and the current time is already
                in sync with the interval, this returns 0.

        Returns:
            int

        """
        now = now or datetime.datetime.utcnow()
        seconds = now.minute * 60 + now.second
        wait_for = interval - seconds % interval
        if inclusive:
            wait_for %= interval
        return wait_for


    @commands.Cog.listener('on_raw_reaction_add')
    async def ina_status_react(self, payload):
        """Update the I&A status manually with a reaction."""
        ch, msg = self.INA_STATUS_MESSAGE_ID
        if (    not self.ina_status_enabled
                or payload.channel_id != ch or payload.message_id != msg
                or payload.emoji.name != self.REFRESH_EMOJI
                or getattr(payload.member, 'bot', False)):
            return

        server, embed = await self.ina_status_update()
        # NOTE: loop could decide to update right after this

        if embed is not None:
            # Update was successful; remove reaction
            message = self.partial_ina_status
            try:
                await message.clear_reaction(self.REFRESH_EMOJI)
            except discord.HTTPException:
                pass
            else:
                await message.add_reaction(self.REFRESH_EMOJI)


    @tasks.loop()
    async def ina_status_loop(self):
        """Update the I&A status periodically."""
        server, embed = await self.ina_status_update()

        next_period = 15
        if isinstance(server, float):
            next_period = server
        elif server.status == 'online':
            next_period = self.get_next_period(self.INA_STATUS_SECONDS)
        await asyncio.sleep(next_period)


    @ina_status_loop.before_loop
    async def before_ina_status_loop(self):
        await self.bot.wait_until_ready()

        # Clean up graph destination
        graph_channel = self.bot.get_channel(self.INA_STATUS_GRAPH_DEST)
        await graph_channel.purge(limit=2, check=lambda m: m.author == self.bot.user)

        # Sync to the next interval
        next_period = self.get_next_period(self.INA_STATUS_SECONDS, inclusive=True)
        await asyncio.sleep(next_period)


    def ina_status_toggle(self) -> bool:
        """Toggle the I&A status loop and react listener."""
        self.ina_status_enabled = not self.ina_status_enabled
        self.ina_status_loop.cancel()
        if self.ina_status_enabled:
            self.ina_status_loop.start()
        return self.ina_status_enabled


    @commands.Cog.listener('on_connect')
    async def ina_status_toggle_on_connect(self):
        """Turn on the I&A status loop and react listener after connecting."""
        if not self.ina_status_enabled:
            self.ina_status_toggle()






    @commands.command(name='togglesignalstatus', aliases=('tss',))
    @commands.is_owner()
    async def client_toggle_ina_status(self, ctx):
        """Toggle the Signal Hill I&A status message.
Turns back on when the bot connects."""
        enabled = self.ina_status_toggle()
        emoji = '\N{LARGE GREEN CIRCLE}' if enabled else '\N{LARGE RED CIRCLE}'
        await ctx.message.add_reaction(emoji)


    def ina_status_player_count_graph(self, datapoints, server, graphing_cog):
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

        line_color = '#F54F33'
        fig, ax = plt.subplots()

        # if any(None not in (d.min, d.max) for d in datapoints):
        #     # Resolution is not raw; generate bar graph with error bars
        #     pass

        # Plot player counts
        x, y = zip(*((d.timestamp, d.value) for d in datapoints))
        # Generate smoother curve with 300 points
        x = np.array([mdates.date2num(dt) for dt in x])
        x_min, x_max = x.min(), x.max()
        n_points = 300
        spl = make_interp_spline(x, y, k=2)
        x_new = np.linspace(x_min, x_max, n_points)
        y_smooth = spl(x_new)
        # # Estimate where the actual datapoints are to mark them
        # x_to_marker_ratio = (n_points - 1) / (x_max - x_min)
        # markers = [int((n - x_min) * x_to_marker_ratio) for n in x]
        lines = ax.plot_date(x_new, y_smooth, line_color)  # , marker='.', markevery=markers)

        # Set limits and fill under the line
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(0, server.max_players + 1)
        ax.fill_between(x_new, y_smooth, color=line_color + '55')

        # Set xticks to every two hours
        step = 1 / 12
        start = x_max - step + (mdates.date2num(datetime.datetime.utcnow()) - x_max)
        ax.set_xticks(np.arange(start, x_min, -step))
        ax.xaxis.set_major_formatter(format_hour)
        ax.set_xlabel('UTC', loc='left', color=line_color)

        # Set yticks
        ax.yaxis.set_major_locator(ticker.MultipleLocator(5))

        # Add grid
        ax.set_axisbelow(True)
        ax.grid(color='#707070', alpha=0.4)

        # Color the ticks and make spine invisible
        for spine in ax.spines.values():
            spine.set_color('#00000000')
        ax.tick_params(labelsize=9, color='#70707066', labelcolor=line_color)

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





    @commands.command(name='history')
    @commands.is_owner()
    async def client_player_count_history(self, ctx):
        """Render the player count history graph."""
        stop = datetime.datetime.utcnow()
        start = stop - datetime.timedelta(hours=24)
        datapoints = await self.bm_client.get_player_count_history(
            self.INA_SERVER_ID, start=start, stop=stop
        )

        graphing_cog = ctx.bot.get_cog('Graphing')
        server = self.ina_status_last_server
        if not server:
            server, old = await self.ina_status_fetch_server(self.INA_SERVER_ID)

        f = await ctx.bot.loop.run_in_executor(
            None, self.ina_status_player_count_graph,
            datapoints, server, graphing_cog
        )
        embed = discord.Embed().set_image(url='attachment://graph.png')
        graph = discord.File(f, filename='graph.png')

        await ctx.send(embed=embed, file=graph)










def setup(bot):
    bot.add_cog(SignalHill(bot))

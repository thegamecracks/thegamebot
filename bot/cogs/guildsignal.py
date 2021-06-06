import asyncio
import datetime
import enum
import io
import itertools
import logging
import math
import os
import random
import re
from typing import Callable, Optional

import abattlemetrics as abm
import discord
from discord.ext import commands, tasks
from matplotlib import dates as mdates
import matplotlib.pyplot as plt
from matplotlib import ticker
import numpy as np

from bot import checks, errors, utils

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
    embed = m.embeds[0]
    if embed is None:
        return GiveawayStatus.UNKNOWN

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

    This will add `last_giveaway` to the context, which will
    be the giveaway message if it exists.

    """
    e = errors.ErrorHandlerResponse(bad_response)

    async def predicate(ctx):
        channel = ctx.bot.get_channel(giveaway_channel_id)
        try:
            ctx.last_giveaway = m = await channel.history(limit=1).next()
        except discord.NoMoreItems:
            ctx.last_giveaway = None
            raise e

        if not check_func(get_giveaway_status(m)):
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


class SteamIDConverter(commands.Converter):
    """Do basic checks on an integer to see if it may be a valid steam64ID."""
    async def convert(self, ctx, arg):
        if not re.match('\d{17}', arg):
            raise commands.BadArgument('Could not parse Steam64ID.')
        return int(arg)


class SignalHill(commands.Cog):
    """Stuff for the Signal Hill server."""

    ACTIVE_HOURS = range(6, 22)
    BM_SERVER_LINK = 'https://www.battlemetrics.com/servers/{game}/{server_id}'
    INA_SERVER_ID = 10654566
    INA_STATUS_MESSAGE_ID = (819632332896993360, 842228691077431296)
    INA_STATUS_SECONDS = 60
    INA_STATUS_EDIT_RATE = 10
    INA_STATUS_FALSE_EDIT_RATE = 5
    INA_STATUS_GRAPH_DEST = 842924251954151464
    INA_STATUS_GRAPH_RATE = 60 * 30
    INA_STATUS_LINE_COLOR = '#F54F33'
    REFRESH_EMOJI = '\N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}'
    GIVEAWAY_CHANNEL_ID = 850965403328708659  # testing: 850953633671020576
    GIVEAWAY_EMOJI_ID = 815804214470770728  # testing: 340900129114423296
    GUILD_ID = 811415496036843550

    def __init__(self, bot):
        self.bot = bot
        self.bm_client = abm.BattleMetricsClient(
            self.bot.session,
            token=os.getenv('BattlemetricsToken')
        )
        self.ina_status_enabled = True
        self.ina_status_last_server = None
        # Cooldown for editing
        self.ina_status_cooldown = commands.Cooldown(
            1, self.INA_STATUS_EDIT_RATE, commands.BucketType.default)
        # Cooldown for clearing reaction without actually updating
        # (improves button response without actually making more queries)
        self.ina_status_reaction_cooldown = commands.Cooldown(
            1, self.INA_STATUS_FALSE_EDIT_RATE, commands.BucketType.default)
        # Last message sent with graph
        self.ina_status_graph_last = None
        # Cooldown for graph generation
        self.ina_status_graph_cooldown = commands.Cooldown(
            1, self.INA_STATUS_GRAPH_RATE, commands.BucketType.default)

        self.ina_status_loop.add_exception_type(discord.DiscordServerError)
        self.ina_status_loop.start()


    def cog_unload(self):
        self.ina_status_loop.cancel()

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
    def partial_ina_status(self) -> Optional[discord.PartialMessage]:
        """Return a PartialMessage displaying the I&A status."""
        channel_id, message_id = self.INA_STATUS_MESSAGE_ID
        channel = self.bot.get_channel(channel_id)
        if channel:
            return channel.get_partial_message(message_id)


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
            Tuple[float, None]: Either on cooldown or failed to fetch
                the server due to a 5xx response.

        """
        retry_after = self.ina_status_cooldown.update_rate_limit(None)
        if retry_after:
            return retry_after, None
        # NOTE: a high cooldown period will help with preventing concurrent
        # updates but this by itself does not remove the potential

        message = self.partial_ina_status

        try:
            server, old = await self.ina_status_fetch_server(
                self.INA_SERVER_ID, include_players=True)
        except abm.HTTPException as e:
            if e.status >= 500:
                return 30.0, None

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

        reaction_cooldown = self.ina_status_reaction_cooldown
        if embed is not None or not reaction_cooldown.update_rate_limit(None):
            # Update was successful or able to make a false update
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
    @commands.max_concurrency(1)
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

        fig, ax = plt.subplots()

        # if any(None not in (d.min, d.max) for d in datapoints):
        #     # Resolution is not raw; generate bar graph with error bars
        #     pass

        # Plot player counts
        x, y = zip(*((d.timestamp, d.value) for d in datapoints))
        x_min, x_max = mdates.date2num(min(x)), mdates.date2num(max(x))
        lines = ax.plot(x, y, self.INA_STATUS_LINE_COLOR)  # , marker='.')

        # Set limits and fill under the line
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(0, server.max_players + 1)
        ax.fill_between(x, y, color=self.INA_STATUS_LINE_COLOR + '55')

        # Set xticks to every two hours
        step = 1 / 12
        start = x_max - step + (mdates.date2num(datetime.datetime.utcnow()) - x_max)
        ax.set_xticks(np.arange(start, x_min, -step))
        ax.xaxis.set_major_formatter(format_hour)
        ax.set_xlabel('UTC', loc='left', color=self.INA_STATUS_LINE_COLOR)

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
            labelcolor=self.INA_STATUS_LINE_COLOR
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





    @commands.command(name='history')
    @commands.max_concurrency(1)
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





    @commands.command(name='playtime')
    @commands.has_role('Staff')
    @checks.used_in_guild(GUILD_ID)
    async def client_playtime(self, ctx, steam_id: SteamIDConverter):
        """Get someone's server playtime in the last month."""
        async with ctx.typing():
            player_id = await self.bm_client.match_player(
                steam_id, abm.IdentifierType.STEAM_ID)

            if player_id is None:
                return await ctx.send('Could not find a user with that steam ID!')

            player = await self.bm_client.get_player_info(player_id)

            stop = datetime.datetime.utcnow()
            start = stop - datetime.timedelta(days=30)
            datapoints = await self.bm_client.get_player_time_played_history(
                player_id, self.INA_SERVER_ID, start=start, stop=stop)

        total_playtime = sum(dp.value for dp in datapoints)
        m, s = divmod(total_playtime, 60)
        h, m = divmod(m, 60)

        await ctx.send(
            'Player: {}\nPlaytime in the last month: {}:{:02d}h'.format(
                player.name, h, m
            )
        )





    @commands.group(name='giveaway', invoke_without_command=True)
    @commands.cooldown(2, 5, commands.BucketType.channel)
    # @commands.is_owner()
    @commands.has_role('Staff')
    @checks.used_in_guild(GUILD_ID)
    async def client_giveaway(self, ctx):
        """Commands for setting up giveaways."""
        await ctx.send_help(ctx.command)


    async def _giveaway_get_message(self):
        """Get the latest giveaway message."""
        try:
            return await self.giveaway_channel.history(limit=1).next()
        except discord.NoMoreItems:
            return None


    def _giveaway_create_embed(self, title, description):
        embed = discord.Embed(
            color=discord.Color.gold(),
            description=description,
            title=title,
            timestamp=datetime.datetime.utcnow()
        ).set_footer(
            text='Started at'
        )

        return embed


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

field: "title" or "description"
text: The text to replace the field with."""
        field = field.lower()

        embed = ctx.last_giveaway.embeds[0]
        if field == 'title':
            embed.title = text
        elif field == 'description':
            embed.description = text
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
        # Find the giveaway reaction
        reaction = discord.utils.find(
            lambda r: hasattr(r.emoji, 'id') and r.emoji.id == self.GIVEAWAY_EMOJI_ID,
            ctx.last_giveaway.reactions
        )
        if reaction is None:
            return await ctx.send(
                'Giveaway is missing reaction: {}'.format(self.giveaway_emoji))

        # Pick a winner
        participants = []
        async for user in reaction.users():
            if user != ctx.me:
                participants.append(user)

        if not participants:
            return await ctx.send('There are no participants to choose from!')

        winner = random.choice(participants)

        # Update embed
        embed = ctx.last_giveaway.embeds[0]
        embed.color = discord.Color.green()
        embed.title = 'This giveaway has finished!'
        embed.add_field(
            name='The winner is:',
            value=f'{winner.mention}\n'
                  'Please create a support ticket to receive your reward!'
        ).set_footer(
            text='Finished at'
        )
        embed.timestamp = datetime.datetime.utcnow()

        await ctx.last_giveaway.edit(embed=embed)

        await ctx.send(
            '# of participants: {:,}\nWinner: {}'.format(
                len(participants),
                winner.mention
            ),
            allowed_mentions=discord.AllowedMentions.none()
        )


    @client_giveaway.command(name='simulate')
    async def client_giveaway_simulate(self, ctx, title, *, description):
        """Generate a giveaway message in the current channel."""
        embed = self._giveaway_create_embed(title, description)
        await ctx.send(embed=embed)


    @client_giveaway.command(name='start')
    @check_giveaway_status(
        GIVEAWAY_CHANNEL_ID,
        lambda s: s != GiveawayStatus.RUNNING,
        'There is already a giveaway running! Please "finish" or "cancel" '
        'the giveaway before creating a new one!'
    )
    async def client_giveaway_start(self, ctx, title, *, description):
        """Start a new giveaway in the giveaway channel.
Only one giveaway can be running at a time, for now that is."""
        embed = self._giveaway_create_embed(title, description)

        message = await self.giveaway_channel.send(embed=embed)

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

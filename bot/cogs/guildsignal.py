import asyncio
import datetime
import logging
from typing import Optional

import discord
from discord.ext import commands, tasks

import abattlemetrics as abm

abm_log = logging.getLogger('abattlemetrics')
abm_log.setLevel(logging.INFO)
if not abm_log.hasHandlers():
    handler = logging.FileHandler(
        'abattlemetrics.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    abm_log.addHandler(handler)


class SignalHill(commands.Cog):
    """Commands to be used in moderation."""

    ACTIVE_HOURS = range(6, 22)
    BM_SERVER_LINK = 'https://www.battlemetrics.com/servers/{game}/{server_id}'
    INA_SERVER_ID = 10654566
    INA_STATUS_MESSAGE_ID = (819632332896993360, 842228691077431296)
    INA_STATUS_SECONDS = 60
    INA_STATUS_EDIT_RATE = 10
    REFRESH_EMOJI = '\N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}'

    def __init__(self, bot):
        self.bot = bot
        self.bm_client = abm.BattleMetricsClient(self.bot.session)
        self.ina_status_enabled = True
        self.ina_status_last = None
        self.ina_status_cooldown = commands.CooldownMapping.from_cooldown(
            1, self.INA_STATUS_EDIT_RATE, commands.BucketType.default)
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
            return server, embed
 
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


    async def ina_status_update(self):
        """Update the I&A status message.

        Returns:
            Tuple[abattlemetrics.Server, discord.Embed]:
                The server fetched from the API and the embed generated
                from it.
            Tuple[None, None]: On cooldown.

        """
        if self.ina_status_cooldown.update_rate_limit(None):
            return None, None
        # NOTE: a high cooldown period will help with preventing concurrent
        # updates but this by itself does not remove the potential

        message = self.partial_ina_status

        server = await self.bm_client.get_server_info(
            self.INA_SERVER_ID, include_players=True)

        old, self.ina_status_last = self.ina_status_last, server
        # if (    not skip_content_check
        #         and old is not None
        #         and not self.ina_status_should_update(old, server)):
        #     return None, None

        embed = self.ina_status_create_embed(server)
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
        if (    self.ina_status_enabled
                and payload.channel_id != ch or payload.message_id != msg
                or payload.emoji.name != self.REFRESH_EMOJI
                or payload.member and payload.member.bot):
            return

        server, embed = await self.ina_status_update()
        # NOTE: loop could decide to update right after this

        if server is not None:
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
        if server is None or server.status == 'online':
            next_period = self.get_next_period(self.INA_STATUS_SECONDS)
        await asyncio.sleep(next_period)


    @ina_status_loop.before_loop
    async def before_ina_status_loop(self):
        await self.bot.wait_until_ready()

        # Sync to the next interval
        next_period = self.get_next_period(
            self.INA_STATUS_SECONDS, inclusive=True)
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










def setup(bot):
    bot.add_cog(SignalHill(bot))

import datetime
import time

import discord
from discord.ext import commands

from bot import utils


class Informative(commands.Cog):
    qualified_name = 'Informative'
    description = 'Informative commands.'

    ALLOW_DISPLAYING_GUILD_MEMBERS_IN_DMS = False
    # If True, members of any guild the bot is in can be looked up in DMs.
    # Note that this has no effect when the members intent is disabled.

    DATETIME_DIFFERENCE_PRECISION = {'seconds': False}

    def __init__(self, bot):
        self.bot = bot





    @commands.command(
        name='ping')
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def client_ping(self, ctx):
        """Get the bot's latency."""
        start = time.perf_counter()
        message = await ctx.send('pong!')
        latency = time.perf_counter() - start
        latency_ms = round(latency * 100000) / 1000
        await message.edit(content=f'pong! {latency_ms:g}ms')





    @commands.command(
        name='serverinfo')
    @commands.guild_only()
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def client_serverinfo(self, ctx):
        """Get information about the server you are currently in.
Format referenced from the Ayana bot."""
        guild = ctx.author.guild

        created = (
            utils.datetime_difference_string(
                datetime.datetime.utcnow(),
                guild.created_at,
                **self.DATETIME_DIFFERENCE_PRECISION
            ),
            guild.created_at.strftime('%Y/%m/%d %a %X %zUTC')
        )
        count_text_ch = len(guild.text_channels)
        count_voice_ch = len(guild.voice_channels)
        owner = guild.owner
        roles = guild.roles

        embed = discord.Embed(
            color=utils.get_user_color(ctx.author),
            timestamp=datetime.datetime.utcnow()
        )

        embed.set_author(name=owner)
        embed.set_thumbnail(url=guild.icon_url)
        embed.add_field(
            name='ID',
            value=guild.id
        )
        embed.add_field(
            name='Region',
            value=guild.region
        )
        embed.add_field(
            name='Members',
            value=guild.member_count
        )
        embed.add_field(
            name='Channels',
            value=f'{count_text_ch} text : {count_voice_ch} voice'
        )
        embed.add_field(
            name='Owner',
            value=owner
        )
        embed.add_field(
            name='Time of Server Creation',
            value=f'{created[0]} ago ({created[1]})',
            inline=False
        )
        embed.add_field(
            name=f"{len(roles):,} Role{'s' if len(roles) != 1 else ''}",
            value=', '.join([str(r) for r in roles]),
            inline=False
        )
        embed.set_footer(
            text=f'Requested by {ctx.author}',
            icon_url=ctx.author.avatar_url
        )

        await ctx.send(embed=embed)





    @commands.command(
        name='userinfo')
    @commands.cooldown(3, 15, commands.BucketType.user)
    async def client_userinfo(self, ctx, user=None):
        """Get information about a user by name or mention.

https://youtu.be/CppEzOOXJ8E used as reference.
Format referenced from the Ayana bot."""
        # NOTE: when members intent is enabled, members from guilds
        # the bot is in can be accessed in DMs.
        if user is None:
            user = ctx.author
        else:
            user_input = user

            try:
                user = await commands.MemberConverter().convert(ctx, user)
            except commands.MemberNotFound as e:
                if (not self.ALLOW_DISPLAYING_GUILD_MEMBERS_IN_DMS
                        and ctx.guild is None):
                    return await ctx.send('Cannot search for members in DMs.')
                # Else allow error handler to deal with it
                raise e
            else:
                # Successful search
                is_me = user.id == self.bot.user.id
                if isinstance(user, discord.Member):
                    if ctx.guild is None:
                        # Command invoked in DMs
                        if is_me:
                            # Convert to discord.User so guild-related
                            # information is not displayed
                            user = self.bot.get_user(user.id)
                        elif not self.ALLOW_DISPLAYING_GUILD_MEMBERS_IN_DMS:
                            # Disallowed showing guild members in DMs
                            return await ctx.send(
                                'Cannot search for members in DMs.')

        # Extract attributes based on whether its a Member or User
        if isinstance(user, discord.Member):
            description = None
            activity = user.activity
            # If presences or members intent are disabled, d.py returns
            # None for activity
            guild = user.guild
            joined = (
                utils.datetime_difference_string(
                    datetime.datetime.utcnow(),
                    user.joined_at,
                **self.DATETIME_DIFFERENCE_PRECISION
                ),
                user.joined_at.strftime('%Y/%m/%d %a %X %zUTC')
            )
            nickname = user.nick
            roles = [role.name for role in user.roles]
            if len(roles) > 1:
                # Has a role(s); remove @everyone
                roles = roles[:0:-1]
            status = None
            # Check required intents before obtaining status
            # (since d.py returns Status.offline instead of None)
            if self.bot.intents.members and self.bot.intents.presences:
                status = user.status
                if isinstance(status, discord.Status):
                    status = str(status).title()
                else:
                    # Status is unknown
                    status = None
                if status == 'Dnd':
                    status = 'Do Not Disturb'
        else:
            description = '*For more information, ' \
                          'use this command in a server.*'
            activity = None
            joined = None
            nickname = None
            roles = None
            status = None
        author = f'{user} (Bot)' if user.bot else f'{user}'
        created = (
            utils.datetime_difference_string(
                datetime.datetime.utcnow(),
                user.created_at,
                **self.DATETIME_DIFFERENCE_PRECISION
            ),
            user.created_at.strftime('%Y/%m/%d %a %X %zUTC')
        )

        embed = discord.Embed(
            color=utils.get_user_color(user),
            description=description,
            timestamp=datetime.datetime.utcnow()
        )

        embed.set_author(name=author)  # icon_url=user.avatar_url
        embed.set_thumbnail(url=user.avatar_url)
        # embed.set_image(url=user.avatar_url)
        embed.add_field(
            name='ID',
            value=user.id,
            inline=False
        )
        embed.add_field(
            name='Mention',
            value=user.mention,
            inline=False
        )
        if nickname is not None:
            embed.add_field(
                name='Nickname',
                value=nickname,
                inline=False
            )
        if joined is not None:
            if guild != ctx.guild:
                # Queried in DMs (could also mean found member
                # in another guild but MemberConverter currently won't
                # search for members outside of the guild);
                # include guild name in join title
                joined_name = f'Time of joining {guild.name}'
            else:
                joined_name = 'Time of Server Join'
            embed.add_field(
                name=joined_name,
                value=f'{joined[0]} ago ({joined[1]})',
                inline=False
            )
        embed.add_field(
            name='Time of User Creation',
            value=f'{created[0]} ago ({created[1]})',
            inline=False
        )
        if status is not None:
            embed.add_field(
                name='Status',
                value=status
            )
        if activity is not None:
            if activity.type is discord.ActivityType.playing:
                embed.add_field(
                    name='Playing',
                    value=activity.name
                )
            elif activity.type is discord.ActivityType.streaming:
                embed.add_field(
                    name='Streaming',
                    value=activity.name
                )
            elif activity.type is discord.ActivityType.listening:
                embed.add_field(
                    name='Listening to',
                    value=activity.name
                )
            elif activity.type is discord.ActivityType.watching:
                embed.add_field(
                    name='Watching',
                    value=activity.name
                )
        if roles is not None:
            embed.add_field(
                name=f"{len(roles):,} Role{'s' if len(roles) != 1 else ''}",
                value=', '.join(roles),
                inline=False
            )
        embed.set_footer(
            text=f'Requested by {ctx.author}',
            icon_url=ctx.author.avatar_url
        )

        await ctx.send(embed=embed)










def setup(bot):
    info = Informative(bot)
    # Categorize help command in info
    bot.help_command.cog = info
    bot.add_cog(info)

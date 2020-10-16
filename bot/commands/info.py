import datetime

import discord
from discord.ext import commands

from bot import utils


class Informative(commands.Cog):
    qualified_name = 'Informative'
    description = 'Informative commands.'

    def __init__(self, bot):
        self.bot = bot






    @commands.command(
        name='serverinfo')
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def client_serverinfo(self, ctx):
        """Get information about the server you are currently in.
Format referenced from the Ayana bot."""
        if not isinstance(ctx.author, discord.Member):
            return await ctx.send(
                'You must be in a server to use this command.')

        guild = ctx.author.guild

        created = (
            utils.datetime_difference_string(
                datetime.datetime.utcnow(),
                guild.created_at
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
            value=f'{created[0]} Ago ({created[1]})',
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
    async def client_userinfo(self, ctx, user: discord.Member = None):
        """Get information about a user by name or mention.
https://youtu.be/CppEzOOXJ8E used as reference.
Format referenced from the Ayana bot."""
        if user is None:
            user = ctx.author

        if isinstance(user, discord.Member):
            description = None
            activity = user.activity
            joined = (
                utils.datetime_difference_string(
                    datetime.datetime.utcnow(),
                    user.joined_at
                ),
                user.joined_at.strftime('%Y/%m/%d %a %X %zUTC')
            )
            nickname = user.nick
            roles = [role.name for role in user.roles]
            if len(roles) > 1:
                # Has a role(s); remove @everyone
                roles = roles[:0:-1]
            status = str(user.status).title()
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
                user.created_at
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
        if nickname:
            embed.add_field(
                name='Nickname',
                value=nickname,
                inline=False
            )
        if joined:
            embed.add_field(
                name='Time of Server Join',
                value=f'{joined[0]} Ago ({joined[1]})',
                inline=False
            )
        embed.add_field(
            name='Time of User Creation',
            value=f'{created[0]} Ago ({created[1]})',
            inline=False
        )
        if status:
            embed.add_field(
                name='Status',
                value=status
            )
        if activity:
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


    @client_userinfo.error
    async def client_userinfo_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            if 'not found' in error.args[0]:
                await ctx.send('Could not find that user.')










def setup(bot):
    info = Informative(bot)
    # Categorize help command in info
    bot.help_command.cog = info
    bot.add_cog(info)

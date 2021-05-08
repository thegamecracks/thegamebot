import datetime
import sqlite3

import discord
from discord.ext import commands

from bot.classes.confirmation import AdaptiveConfirmation
from bot import errors, utils


class TagNameConverter(commands.Converter):
    """Ensure a tag name is suitable."""
    async def convert(self, ctx, arg):
        first_word, *_ = arg.split(None, 1)
        command = ctx.bot.get_command('tag')
        if first_word in command.all_commands:
            raise errors.ErrorHandlerResponse(
                'The tag name cannot start with a reserved command name.')

        return arg


class Tags(commands.Cog):
    """Store and use guild-specific tags."""
    qualified_name = 'Tags'

    TAG_BY_MAX_DISPLAYED = 10
    TAG_LEADERBOARD_MAX_DISPLAYED = 10
    TAG_CREATE_MAX_NAME_LENGTH = 50

    def __init__(self, bot):
        self.bot = bot


    def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True





    @commands.group(name='tag', aliases=('tags',), invoke_without_command=True)
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag(self, ctx, *, name: TagNameConverter):
        """Show a tag."""
        tag = await ctx.bot.dbtags.get_tag(ctx.guild.id, name)

        if tag is None:
            return await ctx.send('This tag does not exist.')

        await ctx.send(tag['content'])

        await ctx.bot.dbtags.edit_tag(
            ctx.guild.id, name,
            uses=tag['uses'] + 1,
            record_time=False
        )
                


    @client_tag.command(name='create')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag_create(
            self, ctx, name: TagNameConverter,
            *, content: commands.clean_content):
        """Create a tag.

name: The name of the tag. When using spaces, surround it with quotes as such:
    `tag create "my tag name" content`
content: The content of the tag."""
        diff = len(name) - self.TAG_CREATE_MAX_NAME_LENGTH
        if diff > 0:
            return await ctx.send(
                f'Your tag name is {diff:,} characters too long.')

        try:
            await ctx.bot.dbtags.add_tag(
                ctx.guild.id, name, content, ctx.author.id)
        except sqlite3.IntegrityError:
            await ctx.send('A tag with this name already exists!')
        else:
            await ctx.send('Created your new tag!')


    @client_tag.command(name='delete')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag_delete(self, ctx, *, name: TagNameConverter):
        """Delete one of your tags."""
        tag = await ctx.bot.dbtags.get_tag(ctx.guild.id, name)
        if tag is None:
            return await ctx.send('That tag does not exist!')
        elif tag['user_id'] != ctx.author.id:
            return await ctx.send('Cannot delete a tag made by someone else.')

        await ctx.bot.dbtags.delete_tag(ctx.guild.id, name)

        await ctx.send(f'Deleted the given tag.')


    @client_tag.command(name='edit')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag_edit(
            self, ctx, name: TagNameConverter,
            *, content: commands.clean_content):
        """Edit one of your tags.

name: The name of the tag. For names with multiple spaces, use quotes as such:
    `tag edit "my tag name" new content`
content: The new content to use."""
        tag = await ctx.bot.dbtags.get_tag(ctx.guild.id, name)
        if tag is None:
            return await ctx.send('That tag does not exist!')
        elif tag['user_id'] != ctx.author.id:
            return await ctx.send('Cannot edit a tag made by someone else.')

        await ctx.bot.dbtags.edit_tag(ctx.guild.id, name, content)

        await ctx.send('Edited your tag!')


    @client_tag.command(name='info')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag_info(self, ctx, *, name: TagNameConverter):
        """Get info about a tag."""
        tag = await ctx.bot.dbtags.get_tag(ctx.guild.id, name)
        if tag is None:
            return await ctx.send('That tag does not exist!')

        created_at = datetime.datetime.fromisoformat(tag['created_at'])
        created_at = await ctx.bot.localize_datetime(ctx.author.id, created_at)

        embed = discord.Embed(
            color=utils.get_bot_color(ctx.bot),
            title=tag['name']
        ).add_field(
            name='Owner',
            value=f"<@{tag['user_id']}>"
        ).add_field(
            name='Uses',
            value=format(tag['uses'], ',')
        ).add_field(
            name='Time of Creation',
            value=utils.strftime_zone(created_at),
            inline=False
        )
        if tag['edited_at'] is not None:
            edited_at = datetime.datetime.fromisoformat(tag['created_at'])
            edited_at = await ctx.bot.localize_datetime(
                ctx.author.id, edited_at)
            embed.add_field(
                name='Last Edited',
                value=utils.strftime_zone(edited_at),
                inline=False
            )
        embed.set_footer(
            text=f'Requested by {ctx.author.display_name}',
            icon_url=ctx.author.avatar_url
        )

        await ctx.send(embed=embed)


    @client_tag.command(name='leaderboard')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag_leaderboard(self, ctx):
        """Get a list of the top tags used in this server."""
        db = ctx.bot.dbtags
        async with await db.connect() as conn:
            async with conn.execute(
                    f'SELECT name, user_id, uses FROM {db.TABLE_NAME} '
                    'WHERE guild_id = ? ORDER BY uses DESC '
                    f'LIMIT {self.TAG_LEADERBOARD_MAX_DISPLAYED}',
                    ctx.guild.id) as c:
                rows = await c.fetchall()

        if not rows:
            return await ctx.send('This server currently has no tags.')

        description = [
            f"**{i:,}.** {r['name']} : <@{r['user_id']}> : {r['uses']:,}"
            for i, r in enumerate(rows, start=1)
        ]
        description = '\n'.join(description)

        embed = discord.Embed(
            color=utils.get_bot_color(ctx.bot),
            description=description,
            timestamp=datetime.datetime.utcnow()
        )

        await ctx.send(embed=embed)


    @client_tag.command(name='list')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag_list(self, ctx, *, user: discord.Member = None):
        """Get a list of the top tags you or someone else owns."""
        user = user or ctx.author

        db = ctx.bot.dbtags
        async with await db.connect() as conn:
            async with conn.execute(
                    f'SELECT name, uses FROM {db.TABLE_NAME} '
                    'WHERE guild_id = ? AND user_id = ? ORDER BY uses DESC '
                    f'LIMIT {self.TAG_BY_MAX_DISPLAYED}',
                    ctx.guild.id, user.id) as c:
                rows = await c.fetchall()

        if not rows:
            return await ctx.send('This server currently has no tags.')

        description = [f"**{i:,}.** {r['name']} : {r['uses']:,}"
                       for i, r in enumerate(rows, start=1)]
        description = '\n'.join(description)

        embed = discord.Embed(
            color=utils.get_bot_color(ctx.bot),
            description=description,
            timestamp=datetime.datetime.utcnow()
        )

        await ctx.send(embed=embed)


    @client_tag.command(name='reset')
    @commands.cooldown(1, 60, commands.BucketType.guild)
    @commands.guild_only()
    @commands.check_any(
        commands.has_guild_permissions(manage_guild=True),
        commands.is_owner()
    )
    async def client_tag_reset(self, ctx):
        """Reset all tags in the server.
This requires a confirmation."""
        prompt = AdaptiveConfirmation(ctx, utils.get_bot_color(ctx.bot))

        confirmed = await prompt.confirm(
            "Are you sure you want to reset the server's tags?")

        if confirmed:
            await self.bot.dbtags.wipe(ctx.guild.id)
            await prompt.update('Wiped all tags!', prompt.emoji_yes.color)
        else:
            await prompt.update('Cancelled tag reset.', prompt.emoji_no.color)










def setup(bot):
    bot.add_cog(Tags(bot))

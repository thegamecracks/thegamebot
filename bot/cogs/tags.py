#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import sqlite3
from typing import Optional

import discord
from discord.ext import commands, menus

from bot.classes.confirmation import AdaptiveConfirmation
from bot import errors, utils


class TagNameConverter(commands.Converter):
    """Ensure a tag name is suitable.

    Args:
        param (str): The name of the parameter this converter
            is being applied to. Used as part of the error messages.

    """
    TAG_CREATE_MAX_NAME_LENGTH = 50
    def __init__(self, param: str):
        self.param = param

    async def convert(self, ctx, arg):
        diff = len(arg) - self.TAG_CREATE_MAX_NAME_LENGTH
        if diff > 0:
            raise errors.ErrorHandlerResponse(
                f'Tag parameter `{self.param}` is {diff:,} '
                'characters too long.'
            )

        first_word, *_ = arg.split(None, 1)
        command = ctx.bot.get_command('tag')
        if first_word in command.all_commands:
            raise errors.ErrorHandlerResponse(
                f'Tag parameter `{self.param}` cannot start '
                'with a reserved command name.'
            )

        return arg


class TagPageSource(menus.AsyncIteratorPageSource):
    def __init__(
            self, bot, guild_id: int, *, column: str,
            where: dict = None, reverse=False,
            format: str, **kwargs):
        """Create an page source for tags.

        Args:
            bot (commands.Bot): The bot.
            guild_id (int): The guild to get tags from.
            column (Optional[str]):
                The name of the column to sort the tags by.
            where (Optional[dict]):
                A dictionary mapping SQL expressions with placeholders
                to their values.
                Only shows tags where all the given expressions evaluate
                to true.
                Example:
                    {'user_id = ?': 1234,
                     'created_at > ?': datetime.datetime.utcnow()
                                       - datetime.timedelta(hours=1)}
            reverse (bool): If True, yields the tags in descending order.
                Unapplicable if `column` is unspecified.
            format (str): The string to use when formatting each tag.
                These values are provided:
                    i: The current index starting at 1.
                    **tag: All columns available in the tag.
            **kwargs: Passed into AsyncIteratorPageSource.

        """
        super().__init__(
            bot.dbtags.yield_tags_ordered(
                guild_id, column=column, reverse=reverse
            ),
            **kwargs
        )
        self.bot = bot
        self.format = format

    async def format_page(self, menu, entries):
        start = menu.current_page * self.per_page
        return discord.Embed(
            color=utils.get_bot_color(self.bot),
            description=f'\n'.join([
                self.format.format(i=i, **v)
                for i, v in enumerate(entries, start=start + 1)
            ])
        )


class Tags(commands.Cog):
    """Store and use guild-specific tags."""
    qualified_name = 'Tags'

    TAG_BY_MAX_DISPLAYED = 10
    TAG_LEADERBOARD_MAX_DISPLAYED = 10

    def __init__(self, bot):
        self.bot = bot


    def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True


    async def try_delete_message(self, ctx, m=None) -> bool:
        """Try deleting the given message.
        Returns True if successful.
        """
        m = m or ctx.message
        can_delete = (
            m.author == ctx.me
            or ctx.me.permissions_in(m.channel).manage_messages
        )

        if can_delete:
            await m.delete()

        return can_delete


    async def delete_and_reply(self, ctx, content='', *args, **kwargs):
        """Try deleting the author's message and reply/mention."""
        if await self.try_delete_message(ctx):
            await ctx.send(f'{ctx.author.mention} {content}', *args, **kwargs)
        else:
            await ctx.reply(content, *args, **kwargs)





    @commands.group(name='tag', aliases=('tags',), invoke_without_command=True)
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag(self, ctx, *, name: TagNameConverter('name')):
        """Show a tag."""
        tag = await ctx.bot.dbtags.get_tag(ctx.guild.id, name, include_aliases=True)

        if tag is None:
            return await ctx.send('This tag does not exist.')

        await ctx.send(tag['content'])

        await ctx.bot.dbtags.edit_tag(
            ctx.guild.id, tag['name'],
            uses=tag['uses'] + 1,
            record_time=False
        )


    @client_tag.command(name='alias')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def client_tag_alias(
            self, ctx, alias: TagNameConverter('alias'),
            *, existing: TagNameConverter('existing')):
        """Create an alias for a tag.
These can be deleted in the same way as normal tags, however they cannot be edited.

alias: The tag's alias. When using spaces, surround it with quotes as such:
    `tag alias "my new name" my old name`
existing: The name of an existing tag or even another alias."""
        tag = await ctx.bot.dbtags.get_tag(
            ctx.guild.id, existing, include_aliases=True)
        if tag is None:
            return await ctx.send('This tag does not exist.')

        try:
            await ctx.bot.dbtags.add_alias(
                ctx.guild.id, alias, tag['name'], ctx.author.id)
        except sqlite3.IntegrityError:
            await ctx.send('A tag/alias with this name already exists!')
        else:
            await ctx.send('Created your new alias!')


    @client_tag.command(name='create')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def client_tag_create(
            self, ctx, name: TagNameConverter('name'),
            *, content: commands.clean_content):
        """Create a tag.

name: The name of the tag. When using spaces, surround it with quotes as such:
    `tag create "my tag name" content`
content: The content of the tag."""
        try:
            await ctx.bot.dbtags.add_tag(
                ctx.guild.id, name, content, ctx.author.id)
        except sqlite3.IntegrityError as e:
            await ctx.send('A tag/alias with this name already exists!')
        else:
            await self.delete_and_reply(ctx, f'Created tag "{name}"!')


    @client_tag.command(name='delete', aliases=('remove',))
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag_delete(self, ctx, *, name: TagNameConverter('name')):
        """Delete one of your tags or aliases.

If you have Manage Server permissions you can also delete other people's tags."""
        tag = await ctx.bot.dbtags.get_tag(ctx.guild.id, name, include_aliases=True)
        if tag is None:
            return await ctx.send('That tag does not exist!')
        elif tag['user_id'] != ctx.author.id and not ctx.author.permissions_in(
                ctx.channel).manage_guild:
            return await ctx.send('Cannot delete a tag made by someone else.')

        is_alias = tag['name'] != name
        if is_alias:
            await ctx.bot.dbtags.delete_alias(ctx.guild.id, name)
            await ctx.send(f'Deleted the given alias.')
        else:
            await ctx.bot.dbtags.delete_tag(ctx.guild.id, name)
            await ctx.send(f'Deleted the given tag.')


    @client_tag.command(name='edit')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag_edit(
            self, ctx, name: TagNameConverter('name'),
            *, content: commands.clean_content):
        """Edit one of your tags.

name: The name of the tag (aliases allowed). For names with multiple spaces, use quotes as such:
    `tag edit "my tag name" new content`
content: The new content to use."""
        tag = await ctx.bot.dbtags.get_tag(ctx.guild.id, name, include_aliases=True)
        if tag is None:
            return await ctx.send('That tag does not exist!')
        elif tag['user_id'] != ctx.author.id:
            return await ctx.send('Cannot edit a tag made by someone else.')

        await ctx.bot.dbtags.edit_tag(ctx.guild.id, tag['name'], content)

        await self.delete_and_reply(ctx, f'Edited tag "{name}"!')


    @client_tag.command(name='info')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_tag_info(self, ctx, *, name: TagNameConverter('name')):
        """Get info about a tag."""
        tag = await ctx.bot.dbtags.get_tag(ctx.guild.id, name, include_aliases=True)
        if tag is None:
            return await ctx.send('That tag does not exist!')

        embed = discord.Embed(
            color=utils.get_bot_color(ctx.bot)
        )

        is_alias = tag['name'] != name

        if is_alias:
            alias = await ctx.bot.dbtags.get_alias(ctx.guild.id, name)
            created_at = await ctx.bot.localize_datetime(
                ctx.author.id, tag['created_at'])

            embed.title = alias['alias']
            embed.add_field(
                name='Owner',
                value=f"<@{alias['user_id']}>"
            ).add_field(
                name='Original',
                value=alias['name']
            ).add_field(
                name='Time of Creation',
                value=utils.strftime_zone(created_at),
                inline=False
            )

            footer = 'Alias requested by {}'
        else:
            created_at = await ctx.bot.localize_datetime(
                ctx.author.id, tag['created_at'])

            embed.title = tag['name']
            embed.add_field(
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

            aliases = await ctx.bot.dbtags.get_aliases(ctx.guild.id, name)
            if aliases:
                embed.add_field(
                    name='Aliases',
                    value=', '.join([r['alias'] for r in aliases])
                )

            if tag['edited_at'] is not None:
                edited_at = await ctx.bot.localize_datetime(
                    ctx.author.id, tag['edited_at'])
                embed.add_field(
                    name='Last Edited',
                    value=utils.strftime_zone(edited_at),
                    inline=False
                )

            footer = 'Tag requested by {}'

        embed.set_footer(
            text=footer.format(ctx.author.display_name),
            icon_url=ctx.author.avatar_url
        )

        await ctx.send(embed=embed)


    @client_tag.command(name='leaderboard')
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.member)
    async def client_tag_leaderboard(self, ctx):
        """Get a list of the top tags used in this server."""
        menu = menus.MenuPages(
            TagPageSource(
                ctx.bot, ctx.guild.id, column='uses', reverse=True,
                format='**{i:,}.** {name} : {uses:,} : <@{user_id}>',
                per_page=self.TAG_LEADERBOARD_MAX_DISPLAYED
            ),
            clear_reactions_after=True
        )
        try:
            await menu.start(ctx, wait=True)
        except IndexError:
            await ctx.send('This server currently has no tags to list.')


    @client_tag.command(name='list')
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.member)
    async def client_tag_list(self, ctx, *, user: discord.Member = None):
        """Get a list of the top tags you or someone else owns."""
        user = user or ctx.author

        menu = menus.MenuPages(
            TagPageSource(
                ctx.bot, ctx.guild.id, column='uses',
                where={'user_id = ?': user.id}, reverse=True,
                format='**{i:,}.** {name} : {uses:,}',
                per_page=self.TAG_LEADERBOARD_MAX_DISPLAYED
            ),
            clear_reactions_after=True
        )
        try:
            await menu.start(ctx, wait=True)
        except IndexError:
            response = 'This user currently has no tags to list.'
            if user == ctx.author:
                response = 'You do not have any tags to list.'
            await ctx.send(response)


    @client_tag.command(name='raw')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def client_tag_raw(self, ctx, *, name: TagNameConverter('name')):
        """Show a tag in its raw form.
Useful for copy pasting any of the tag's markdown."""
        tag = await ctx.bot.dbtags.get_tag(ctx.guild.id, name, include_aliases=True)
        if tag is None:
            return await ctx.send('This tag does not exist.')

        escaped = discord.utils.escape_markdown(tag['content'])
        for content in utils.paginate_message(escaped):
            await ctx.send(content)


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

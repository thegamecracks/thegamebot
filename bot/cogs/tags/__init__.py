#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import sqlite3
from typing import cast

import discord
from discord.ext import commands

from bot.utils import ConfirmationView, paging
from bot import errors, utils
from main import Context, TheGameBot
from .querier import TagQuerier


class TagContentConverter(commands.Converter):
    """Ensure a string is suitable for content of a tag."""
    TAG_MAX_CONTENT_LENGTH = 2000

    async def convert(self, ctx, arg):
        param = ctx.current_parameter.name

        raw_arg = utils.rawify_content(arg)
        diff = len(raw_arg) - self.TAG_MAX_CONTENT_LENGTH
        if diff > 0:
            raise commands.BadArgument(
                f'`{param}` parameter is {diff:,} characters too long.')

        return arg


class TagNameConverter(commands.Converter):
    """Ensure a tag name is suitable."""
    TAG_MAX_NAME_LENGTH = 50

    async def convert(self, ctx, arg):
        param = ctx.current_parameter.name

        # Check length
        diff = len(arg) - self.TAG_MAX_NAME_LENGTH
        if diff > 0:
            raise commands.BadArgument(
                f'Tag parameter `{param}` is {diff:,} characters too long.')

        # Check for command name collision
        first_word, *_ = arg.split(None, 1)
        command = cast(commands.Group, ctx.bot.get_command('tag'))
        if first_word in command.all_commands:
            raise commands.BadArgument(
                f'`{param}` parameter cannot start '
                'with a reserved command name.'
            )

        return arg.casefold()


class TagPageSource(paging.AsyncIteratorPageSource[sqlite3.Row, None, paging.PaginatorView]):
    def __init__(
        self, *args,
        bot: TheGameBot,
        row_format: str,
        empty_message: str,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.row_format = row_format
        self.empty_message = empty_message

    async def format_page(self, view: paging.PaginatorView, page: list[sqlite3.Row]):
        if not page:
            return self.empty_message
        start = view.current_index * self.page_size
        return discord.Embed(
            color=self.bot.get_bot_color(),
            description=f'\n'.join([
                self.row_format.format(i=i, **v)  # type: ignore
                for i, v in enumerate(page, start=start + 1)
            ])
        )


async def delete_and_reply(
    ctx: Context, content='', *args, **kwargs
) -> discord.Message:
    """Deletes the author's message if possible, then (correspondingly)
    mentions or replies to them.
    """
    if await try_delete_message(ctx):
        return await ctx.send(f'{ctx.author.mention} {content}', *args, **kwargs)
    else:
        return await ctx.reply(content, *args, **kwargs)


async def try_delete_message(ctx: Context, m: discord.Message = None) -> bool:
    """Tries deleting the given message.

    :return: a boolean indicating if it was successful.

    """
    m = m or ctx.message
    can_delete = (
        m.author == ctx.me
        or m.channel.permissions_for(ctx.me).manage_messages
    )

    if can_delete:
        await m.delete()

    return can_delete


class Tags(commands.Cog):
    """Store and use guild-specific tags."""
    qualified_name = 'Tags'

    TAG_BY_MAX_DISPLAYED = 10
    TAG_LEADERBOARD_MAX_DISPLAYED = 10

    def __init__(self, bot: TheGameBot):
        self.bot = bot
        self.tags = TagQuerier(self.bot.db)

    def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @commands.group(name='tag', aliases=('tags',), invoke_without_command=True)
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def tag(self, ctx: Context, *, name: TagNameConverter):
        """Show a tag."""
        name: str
        tag = await self.tags.get_tag(ctx.guild.id, name, include_aliases=True)

        if tag is None:
            return await ctx.send('This tag does not exist.')

        await ctx.send(
            tag['content'],
            allowed_mentions=discord.AllowedMentions.none()
        )

        await self.tags.edit_tag(
            ctx.guild.id, tag['tag_name'],
            uses=tag['uses'] + 1,
            record_time=False
        )

    @tag.command(name='alias')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tag_alias(
            self, ctx: Context, alias: TagNameConverter,
            *, existing: TagNameConverter):
        """Create an alias for a tag.
These can be deleted in the same way as normal tags, however they cannot be edited.

alias: The tag's alias. When using spaces, surround it with quotes as such:
    `tag alias "my new name" my old name`
existing: The name of an existing tag or even another alias."""
        alias: str
        existing: str
        tag = await self.tags.get_tag(
            ctx.guild.id, existing, include_aliases=True)
        if tag is None:
            return await ctx.send('This tag does not exist.')

        try:
            await self.tags.add_alias(
                ctx.guild.id, alias, tag['tag_name'], ctx.author.id)
        except sqlite3.IntegrityError:
            await ctx.send('A tag/alias with this name already exists!')
        else:
            await ctx.send('Created your new alias!')

    @tag.command(name='claim')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tag_claim(self, ctx: Context, *, name: TagNameConverter):
        """Claim a tag or alias made by someone that is no longer in the server.
Note it may take some time before a tag loses their author."""
        name: str
        tag = await self.tags.get_tag(ctx.guild.id, name)
        is_alias = False
        if tag is None:
            is_alias = True
            tag = await self.tags.get_alias(ctx.guild.id, name)

        ref = 'alias' if is_alias else 'tag'

        if tag is None:
            return await ctx.send('This tag does not exist.')
        elif tag['user_id'] is not None:
            return await ctx.send(
                'This {} is already owned by <@{}>!'.format(
                    ref, tag['user_id']
                ), allowed_mentions=discord.AllowedMentions(users=False)
            )

        if is_alias:
            await self.tags.set_alias_author(ctx.guild.id, name, ctx.author.id)
        else:
            await self.tags.set_tag_author(ctx.guild.id, name, ctx.author.id)

        await ctx.send('You now own the {} "{}"!'.format(ref, name))

    @tag.command(name='create')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tag_create(
            self, ctx: Context, name: TagNameConverter,
            *, content: TagContentConverter):
        """Create a tag.

name: The name of the tag. When using spaces, surround it with quotes as such:
    `tag create "my tag name" content`
content: The content of the tag."""
        name: str
        content: str
        try:
            await self.tags.add_tag(
                ctx.guild.id, name, content, ctx.author.id)
        except sqlite3.IntegrityError:
            await ctx.send('A tag/alias with this name already exists!')
        else:
            await delete_and_reply(ctx, f'Created tag "{name}"!')

    @tag.command(name='delete', aliases=('remove',))
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def tag_delete(self, ctx: Context, *, name: TagNameConverter):
        """Delete one of your tags or aliases.

If you have Manage Server permissions you can also delete other people's tags."""
        name: str
        perms = ctx.author.guild_permissions
        tag = await self.tags.get_tag(ctx.guild.id, name, include_aliases=True)
        if tag is None:
            return await ctx.send('That tag does not exist!')
        elif tag['user_id'] != ctx.author.id and not perms.manage_guild:
            return await ctx.send('Cannot delete a tag made by someone else.')

        is_alias = tag['tag_name'] != name
        if is_alias:
            await self.tags.delete_alias(ctx.guild.id, name)
            await ctx.send(f'Deleted the given alias.')
        else:
            await self.tags.delete_tag(ctx.guild.id, name)
            await ctx.send(f'Deleted the given tag.')

    @tag.command(name='edit')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def tag_edit(
            self, ctx: Context, name: TagNameConverter,
            *, content: TagContentConverter):
        """Edit one of your tags.

name: The name of the tag (aliases allowed). For names with multiple spaces, use quotes as such:
    `tag edit "my tag name" new content`
content: The new content to use."""
        name: str
        content: str
        tag = await self.tags.get_tag(ctx.guild.id, name, include_aliases=True)
        if tag is None:
            return await ctx.send('That tag does not exist!')
        elif tag['user_id'] != ctx.author.id:
            return await ctx.send('Cannot edit a tag made by someone else.')

        await self.tags.edit_tag(ctx.guild.id, tag['tag_name'], content)

        await delete_and_reply(ctx, f'Edited tag "{name}"!')

    @tag.command(name='info')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def tag_info(self, ctx: Context, *, name: TagNameConverter):
        """Get info about a tag."""
        name: str
        tag = await self.tags.get_tag(ctx.guild.id, name)
        is_alias = False
        if tag is None:
            is_alias = True
            tag = await self.tags.get_alias(ctx.guild.id, name)

        if tag is None:
            return await ctx.send('That tag does not exist!')

        created_at: datetime.datetime = tag['created_at']
        owner_id = tag['user_id']
        owner_mention = f'<@{owner_id}>' if owner_id else 'No owner'

        embed = discord.Embed(
            color=ctx.bot.get_bot_color()
        ).add_field(
            name='Owner',
            value=owner_mention
        ).add_field(
            name='Time of Creation',
            value=discord.utils.format_dt(created_at, 'F'),
            inline=False
        )

        if is_alias:
            title = tag['alias_name']
            footer = 'Alias requested by {}'
            embed.add_field(
                name='Original',
                value=tag['tag_name']
            )

        else:
            title = tag['tag_name']
            footer = 'Tag requested by {}'
            embed.add_field(
                name='Uses',
                value=format(tag['uses'], ',')
            )

            aliases = await self.tags.get_aliases(ctx.guild.id, name)
            if aliases:
                embed.add_field(
                    name='Aliases',
                    value=', '.join([r['alias_name'] for r in aliases])
                )

            if tag['edited_at']:
                edited_at: datetime.datetime = tag['edited_at']
                embed.add_field(
                    name='Last Edited',
                    value=discord.utils.format_dt(edited_at, 'F'),
                    inline=False
                )


        embed.description = f'**{title}**'
        embed.set_footer(
            text=footer.format(ctx.author.display_name),
            icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)

    @tag.command(name='leaderboard')
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.member)
    async def tag_leaderboard(self, ctx: Context):
        """Get a list of the top tags used in this server."""
        view = paging.PaginatorView(
            sources=TagPageSource(
                self.tags.yield_tags(ctx.guild.id, column='uses', reverse=True),
                bot=ctx.bot,
                row_format='**{i:,}.** {tag_name} : {uses:,} : <@{user_id}>',
                empty_message='This server currently has no tags to list.',
                page_size=self.TAG_LEADERBOARD_MAX_DISPLAYED
            ),
            allowed_users={ctx.author.id},
            timeout=60
        )
        await view.start(ctx)
        await view.wait()

    @tag.command(name='list')
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.member)
    async def tag_list(self, ctx: Context, *, user: discord.Member = None):
        """Get a list of the top tags you or someone else owns."""
        user = user or ctx.author

        empty_message = 'This user currently has no tags to list.'
        if user == ctx.author:
            empty_message = 'You do not have any tags to list.'

        view = paging.PaginatorView(
            sources=TagPageSource(
                self.tags.yield_tags(ctx.guild.id, column='uses', where={'user_id = ?': user.id}, reverse=True),
                bot=ctx.bot,
                row_format='**{i:,}.** {tag_name} : {uses:,}',
                empty_message=empty_message,
                page_size=self.TAG_LEADERBOARD_MAX_DISPLAYED
            ),
            allowed_users={ctx.author.id},
            timeout=60
        )
        await view.start(ctx)
        await view.wait()

    @tag.command(name='raw')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tag_raw(self, ctx: Context, *, name: TagNameConverter):
        """Show a tag in its raw form.
Useful for copying a tag with any of its markdown formatting."""
        name: str
        tag = await self.tags.get_tag(ctx.guild.id, name, include_aliases=True)
        if tag is None:
            return await ctx.send('This tag does not exist.')

        escaped = utils.rawify_content(tag['content'])
        await ctx.send(escaped, allowed_mentions=discord.AllowedMentions.none())

    @tag.command(name='reset')
    @commands.cooldown(1, 60, commands.BucketType.guild)
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def tag_reset(self, ctx: Context):
        """Reset all tags in the server.
This requires a confirmation."""
        view = ConfirmationView(ctx.author)
        await view.start(
            ctx,
            color=ctx.bot.get_bot_color(),
            title="Are you sure you want to reset the server's tags?"
        )

        if await view.wait_for_confirmation():
            await self.tags.wipe(ctx.guild.id)
            await view.update('Wiped all tags!', color=view.YES)
        else:
            await view.update('Cancelled tag reset.', color=view.NO)


async def setup(bot: TheGameBot):
    await bot.add_cog(Tags(bot))

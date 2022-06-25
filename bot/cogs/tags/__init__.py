#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import sqlite3
from typing import cast

import discord
from discord.ext import commands

from bot.utils import ConfirmationView, paging
from bot import utils
from main import Context, TheGameBot
from .querier import TagDict, TagQuerier


def get_querier(bot: TheGameBot):
    return TagQuerier(bot.db)


class VerboseTagDict(TagDict):
    """Provides more details about a given tag.

    from_alias:
        A boolean indicating if the tag was referenced from an alias.
        This is a shorthand for comparing `tag_name` to `raw_name`.
    raw_name:
        The name of the tag typed by the user.

    """
    from_alias: bool
    raw_name: str


class ExistingTagConverter(commands.Converter[VerboseTagDict]):
    """Fetches a tag from the database."""
    async def convert(self, ctx: Context, arg: str):
        querier = get_querier(ctx.bot)
        tag = await querier.get_tag(ctx.guild.id, arg.casefold(), include_aliases=True)
        if tag is None:
            raise commands.BadArgument(f'The tag "{arg}" does not exist.')

        d = dict(tag)
        d['from_alias'] = (d['tag_name'] != arg)
        d['raw_name'] = arg
        return d


class NewContentConverter(commands.Converter[str]):
    """Asserts the validity of the content for a tag."""
    TAG_MAX_CONTENT_LENGTH = 2000

    async def convert(self, ctx: Context, arg: str):
        raw_arg = utils.rawify_content(arg)
        diff = len(raw_arg) - self.TAG_MAX_CONTENT_LENGTH
        if diff > 0:
            raise commands.BadArgument(f'The given content is {diff:,} characters too long.')

        return arg


class NewTagConverter(commands.Converter[str]):
    """Asserts the availability of a new tag name."""
    TAG_MAX_NAME_LENGTH = 50

    async def convert(self, ctx: Context, arg: str):
        assert ctx.guild.id is not None

        querier = get_querier(ctx.bot)
        arg = arg.casefold()

        diff = len(arg) - self.TAG_MAX_NAME_LENGTH
        if diff > 0:
            raise commands.BadArgument(f'The given name is {diff:,} characters too long.')

        tag = await querier.get_tag(ctx.guild.id, arg, include_aliases=True)
        if tag is not None:
            ref = 'tag' if tag['tag_name'] == arg else 'alias'
            raise commands.BadArgument(f'A {ref} already exists with the given name.')

        return arg


ExistingTag = commands.param(converter=ExistingTagConverter)
NewContent = commands.param(converter=NewContentConverter)
NewTag = commands.param(converter=NewTagConverter)


async def delete_and_reply(
    ctx: Context, content='', **kwargs
) -> discord.Message:
    """Deletes the author's message if possible, then (correspondingly)
    mentions or replies to them.
    """
    can_delete = (
        ctx.message.author == ctx.me
        or ctx.message.channel.permissions_for(ctx.me).manage_messages
    )

    if can_delete:
        await ctx.message.delete()
        await ctx.send(f'{ctx.author.mention} {content}', **kwargs)
    else:
        await ctx.reply(content, **kwargs)


class TagPageSource(paging.AsyncIteratorPageSource[sqlite3.Row, None, paging.PaginatorView]):
    def __init__(
        self, *args,
        bot: TheGameBot,
        row_format: str,
        empty_message: str,
        title: str = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.row_format = row_format
        self.empty_message = empty_message
        self.title = title

    async def format_page(self, view: paging.PaginatorView, page: list[TagDict]):
        def get_extras(row: TagDict):
            user_id = row['user_id']
            uses = row['uses']
            return {
                'owned_by': f"owned by <@{user_id}>" if user_id else 'no owner',
                'n_uses': self.bot.inflector.plural(f'used {uses:,} time', uses)
            }

        if not page:
            return self.empty_message

        start = view.current_index * self.page_size
        lines = [
            self.row_format.format(
                i=i, **get_extras(row), **row
            )  # type: ignore
            for i, row in enumerate(page, start=start + 1)
        ]

        return discord.Embed(
            color=self.bot.get_bot_color(),
            description=f'\n'.join(lines),
            title=self.title
        )


class Tags(commands.Cog):
    """Store and use guild-specific tags."""
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
    async def tag(self, ctx: Context, *, tag: VerboseTagDict = ExistingTag):
        """Send a tag in the current channel."""
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
        self, ctx: Context,
        tag: VerboseTagDict = ExistingTag,
        *, alias: str = NewTag
    ):
        """Create an alias for an existing tag."""
        await self.tags.add_alias(
            ctx.guild.id, alias, tag['tag_name'],
            ctx.author.id
        )

        await ctx.send('Created your new alias!')

    @tag.command(name='claim')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tag_claim(self, ctx: Context, *, tag: VerboseTagDict = ExistingTag):
        """Claim a tag or alias made by someone that is no longer in the server."""
        ref = 'alias' if tag['from_alias'] else 'tag'

        if tag['user_id'] is not None:
            return await ctx.send(
                f"This {ref} is already owned by <@{tag['user_id']}>!",
                allowed_mentions=discord.AllowedMentions.none()
            )

        args = (ctx.guild.id, tag['raw_name'], ctx.author.id)
        if tag['from_alias']:
            await self.tags.set_alias_author(*args)
        else:
            await self.tags.set_tag_author(*args)

        await ctx.send(
            'You now own the {} "{}"!'.format(ref, tag['raw_name'])
        )

    @tag.command(name='create')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tag_create(self, ctx: Context, name: str = NewTag, *, content: str = NewContent):
        """Create a tag.

name: The name of the tag. When using spaces, surround it with quotes as such:
    `tag create "my tag name" content`
content: The content of the tag."""
        await self.tags.add_tag(ctx.guild.id, name, content, ctx.author.id)
        await delete_and_reply(ctx, f'Created your new tag "{name}"!')

    @tag.command(name='delete', aliases=('remove',))
    async def tag_delete(self, ctx: Context, tag: VerboseTagDict = ExistingTag):
        """Delete one of your tags or aliases (or someone else's, if you have Manage Server permission)."""
        perms = ctx.author.guild_permissions
        if tag['user_id'] != ctx.author.id and not perms.manage_guild:
            return await ctx.send(
                'You cannot delete a tag made by someone else.'
            )

        tag_name = tag['tag_name']
        if tag['from_alias']:
            await self.tags.delete_alias(ctx.guild.id, tag['raw_name'])
            content = f'Successfully deleted an alias for "{tag_name}"!'
        else:
            await self.tags.delete_tag(ctx.guild.id, tag['raw_name'])
            content = f'Successfully deleted the tag "{tag_name}"!'

        await ctx.send(content)

    @tag.command(name='edit')
    async def tag_edit(
        self, ctx: Context,
        tag: VerboseTagDict = ExistingTag, *, content: str = NewContent
    ):
        """Edit one of your tags.

name: The name of the tag (aliases allowed). For names with multiple spaces, use quotes as such:
    `tag edit "my tag name" new content`
content: The new content to use."""
        if tag['user_id'] != ctx.author.id:
            return await ctx.send(
                'You cannot edit a tag made by someone else.'
            )

        await self.tags.edit_tag(ctx.guild.id, tag['tag_name'], content)
        await delete_and_reply(ctx, 'Successfully edited your tag!')

    @tag.command(name='info')
    async def tag_info(self, ctx: Context, *, tag: VerboseTagDict = ExistingTag):
        """Display information about a tag."""
        owner_id = tag['user_id']
        owner_mention = f'<@{owner_id}>' if owner_id else 'No owner'

        embed = discord.Embed(
            color=self.bot.get_bot_color()
        ).add_field(
            name='Owner',
            value=owner_mention
        ).add_field(
            name='Time of Creation',
            value=discord.utils.format_dt(tag['created_at'], 'F'),
            inline=False
        )

        if tag['from_alias']:
            title = tag['raw_name']
            embed.add_field(
                name='Original',
                value=tag['tag_name']
            )

        else:
            title = tag['raw_name']
            embed.add_field(
                name='Uses',
                value=format(tag['uses'], ',')
            )

            aliases = await self.tags.get_aliases(ctx.guild.id, tag['raw_name'])
            if aliases:
                embed.add_field(
                    name='Aliases',
                    value=', '.join(r['alias_name'] for r in aliases)
                )

            if tag['edited_at'] is not None:
                embed.add_field(
                    name='Last Edited',
                    value=discord.utils.format_dt(tag['edited_at'], 'F'),
                    inline=False
                )

        embed.description = f'**{title}**'

        await ctx.send(embed=embed)

    @tag.command(name='leaderboard')
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.member)
    async def tag_leaderboard(self, ctx: Context):
        """Browse through the top tags used in this server."""
        view = paging.PaginatorView(
            sources=TagPageSource(
                self.tags.yield_tags(ctx.guild.id, column='uses', reverse=True),
                bot=ctx.bot,
                row_format='**{i:,}.** {tag_name} ({n_uses}, {owned_by})',
                empty_message='This server currently has no tags to list.',
                title='Tag leaderboard',
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
    async def tag_list(self, ctx: Context, *, user: discord.Member = commands.Author):
        """Get a list of the top tags you or someone else owns."""
        empty_message = 'This user currently has no tags to list.'
        title = f'Tags owned by {user.display_name}'
        if user == ctx.author:
            empty_message = 'You do not have any tags to list.'
            title = 'Tags owned by you'

        view = paging.PaginatorView(
            sources=TagPageSource(
                self.tags.yield_tags(ctx.guild.id, column='uses', where={'user_id = ?': user.id}, reverse=True),
                bot=ctx.bot,
                row_format='**{i:,}.** {tag_name}',
                empty_message=empty_message,
                title=title,
                page_size=self.TAG_LEADERBOARD_MAX_DISPLAYED
            ),
            allowed_users={ctx.author.id},
            timeout=60
        )
        await view.start(ctx)
        await view.wait()

    @tag.command(name='raw')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tag_raw(self, ctx: Context, *, tag: VerboseTagDict = ExistingTag):
        """Show a tag in its raw form.

Useful for copying a tag with any of its markdown formatting."""
        escaped = utils.rawify_content(tag['content'])
        await ctx.send(escaped, allowed_mentions=discord.AllowedMentions.none())

    @tag.command(name='reset')
    @commands.cooldown(1, 60, commands.BucketType.guild)
    @commands.has_guild_permissions(manage_guild=True)
    async def tag_reset(self, ctx: Context):
        """Remove all tags in the server."""
        view = ConfirmationView(ctx.author)
        await view.start(
            ctx,
            color=self.bot.get_bot_color(),
            title="Are you sure you want to reset the server's tags?"
        )

        if await view.wait_for_confirmation():
            await self.tags.wipe(ctx.guild.id)
            await view.update('Wiped all tags!', color=view.YES)
        else:
            await view.update('Cancelled tag reset.', color=view.NO)


async def setup(bot: TheGameBot):
    await bot.add_cog(Tags(bot))

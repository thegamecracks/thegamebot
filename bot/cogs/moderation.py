#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import collections
import re
from typing import Optional, Any

import discord
from discord.ext import commands

from main import Context, TheGameBot


class PurgeLimitConverter(commands.Converter):
    MIN = 2
    MAX = 100

    def __init__(self, min: int = None, max: int = None):
        self.min = min or self.MIN
        self.max = max or self.MAX

    async def convert(self, ctx: Context, arg: str):
        if arg:
            n = int(arg)
        elif ctx.message.reference:
            # Assume they want the maximum
            return self.max
        else:
            raise commands.BadArgument('Please provide the number of messages to delete.')

        if n < self.min:
            raise commands.BadArgument('Must purge at least {} {}.'.format(
                self.min, ctx.bot.inflector.plural('message', self.min)
            ))
        elif n > self.max:
            raise commands.BadArgument('Cannot purge more than {} {} at a time.'.format(
                self.max, ctx.bot.inflector.plural('message', self.max)
            ))

        return n


class Moderation(commands.Cog):
    """Commands to be used in moderation."""

    INVITE_REGEX = re.compile(r'(?:https?://)?discord(?:app)?\.(?:com/invite|gg)/(?P<code>[a-zA-Z0-9]+)/?')

    def __init__(self, bot: TheGameBot):
        self.bot = bot

        self._invite_cache = {}  # str: Optional[discord.Invite]
        # NOTE: this should be a temporary cache but I'm lazy

    async def _invite_fetch_cached(self, m: re.Match) -> Optional[discord.Invite]:
        try:
            invite = self._invite_cache[m.group('code')]
        except KeyError:
            try:
                invite = await self.bot.fetch_invite(m.group())
            except discord.NotFound:
                invite = None

            self._invite_cache[m.group('code')] = invite
        return invite

    async def _invite_search_content(
            self, guild_id: int, content: str) -> Optional[discord.Invite]:
        # Find all invites in the message
        matches = tuple(self.INVITE_REGEX.finditer(content))
        if not matches:
            return

        # Return the first invite that doesn't link to the guild
        for m in matches:
            invite = await self._invite_fetch_cached(m)
            if invite is None:
                continue
            elif not invite.guild or invite.guild.id != guild_id:
                return invite

    async def _invite_delete_and_log(
            self,
            message: discord.Message,
            invite: discord.Invite,
            *,
            log_channel: Optional[discord.abc.Messageable],
            is_edited: bool
        ):
        if not log_channel:
            return await message.delete(delay=0)

        embed = discord.Embed(
            description='{sent} by: {mention}\nInvite: {url}'.format(
                sent='Edited' if is_edited else 'Sent',
                mention=message.author.mention,
                url=invite.url
            ),
            timestamp=message.created_at
        ).set_thumbnail(
            url=message.author.display_avatar.url
        ).set_footer(
            text='Message sent'
        )

        try:
            await message.delete()
        except discord.HTTPException:
            embed.title = 'Server Invite Detected'
            embed.description += f'\n[Jump to message]({message.jump_url})'
        else:
            embed.title = 'Server Invite Deleted'

        await log_channel.send(embed=embed)

    def get_moderation_settings(self, guild_id: int) -> dict[str, Any] | None:
        settings = self.bot.get_settings()
        guild_settings: dict = settings.get('moderation', 'configurations')
        return guild_settings.get(guild_id)

    @commands.Cog.listener('on_message')
    async def on_invite_message(self, message: discord.Message):
        """Delete and record messages that have guild invites in them."""
        # Ignore DMs and bots
        if not message.guild or message.author.bot:
            return

        # Check if this server wants invites deleted
        settings = self.get_moderation_settings(message.guild.id)
        if settings is None:
            return
        elif not settings['delete-invites']:
            return

        roles = settings['whitelisted-roles']
        if roles and any(message.author._roles.get(n) for n in roles):
            return

        invite = await self._invite_search_content(message.guild.id, message.content)
        if invite is None:
            return

        await self._invite_delete_and_log(
            message, invite,
            log_channel=message.guild.get_channel(settings['log-channel']),
            is_edited=False
        )

    @commands.Cog.listener('on_raw_message_edit')
    async def on_invite_message_edit(
            self, payload: discord.RawMessageUpdateEvent):
        if payload.guild_id is None:
            return

        settings = self.get_moderation_settings(payload.guild_id)
        if settings is None:
            return
        elif not settings['delete-invites']:
            return

        content = payload.data.get('content')
        if content is None:
            # Something else in the message was edited, e.g. embeds
            return

        invite = await self._invite_search_content(payload.guild_id, content)
        if invite is None:
            return

        # Resolve into Message object
        guild = self.bot.get_guild(payload.guild_id)
        sender_channel = guild.get_channel(payload.channel_id)
        message = await sender_channel.fetch_message(payload.message_id)

        if message.author.bot:
            return

        roles = settings['whitelisted-roles']
        if roles and any(message.author._roles.get(n) for n in roles):
            return

        await self._invite_delete_and_log(
            message, invite,
            log_channel=message.guild.get_channel(settings['log-channel']),
            is_edited=True
        )

    async def send_purged(
        self, channel: discord.abc.Messageable, messages: list[discord.Message]
    ):
        plural = self.bot.inflector.plural
        n = len(messages)
        c = collections.Counter(m.author for m in messages)
        return await channel.send(
            '{} {} {} deleted!\n\n{}'.format(
                n, plural('message', n), plural('was', n),
                '\n'.join([f'**{count}** - {member.display_name}'
                           for member, count in c.most_common()])
            ), delete_after=12
        )

    def get_purge_replied(self, ctx, limit):
        if ctx.message.reference:
            message = discord.Object(ctx.message.reference.message_id)
            if limit is None:
                return PurgeLimitConverter.MAX, message
            return limit, message
        return limit, None

    @commands.group(name='purge', invoke_without_command=True)
    @commands.cooldown(2, 10, commands.BucketType.channel)
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(
        manage_messages=True,
        read_message_history=True
    )
    async def client_purge(self, ctx: Context, limit: PurgeLimitConverter = None):
        """Bulk delete messages in the current channel.

You can reply to a message to only delete messages up to (but not including) that message.

limit: The number of messages to look through. (max: 100)"""
        limit, after = self.get_purge_replied(ctx, limit)
        if limit is None:
            return await ctx.send_help(ctx.command)

        messages = await ctx.channel.purge(
            limit=limit, before=ctx.message, after=after)
        await self.send_purged(ctx, messages)

    @client_purge.command(name='bot')
    @commands.cooldown(2, 10, commands.BucketType.channel)
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(
        manage_messages=True,
        read_message_history=True
    )
    async def client_purge_bot(self, ctx: Context, limit: PurgeLimitConverter = None):
        """Delete messages from bots.

You can reply to a message to only delete messages up to (but not including) that message.

limit: The number of messages to look through. (max: 100)"""
        def check(m):
            return m.author.bot

        limit, after = self.get_purge_replied(ctx, limit)
        if limit is None:
            return await ctx.send_help(ctx.command)

        messages = await ctx.channel.purge(
            limit=limit, check=check,
            before=ctx.message, after=after
        )
        await self.send_purged(ctx, messages)

    @client_purge.command(name='self')
    @commands.cooldown(2, 10, commands.BucketType.channel)
    @commands.guild_only()
    @commands.check_any(
        commands.has_permissions(manage_messages=True),
        commands.is_owner()
    )
    @commands.bot_has_permissions(read_message_history=True)
    async def client_purge_self(self, ctx: Context, limit: PurgeLimitConverter = None):
        """Delete messages from me.
This will also remove messages that appear to be invoking one of my commands if I have Manage Messages permission.

You can reply to a message to only delete messages up to (but not including) that message.

limit: The number of messages to look through. (max: 100)"""
        def check(m):
            return (
                m.author == ctx.me
                or ctx.bot_permissions.manage_messages
                and m.content.startswith(prefixes)
            )

        limit, after = self.get_purge_replied(ctx, limit)
        if limit is None:
            return await ctx.send_help(ctx.command)

        prefixes = ()
        if ctx.bot_permissions.manage_messages:
            prefixes = await ctx.bot.get_prefix(ctx.message)
            if isinstance(prefixes, str):
                prefixes = (prefixes,)
            else:
                prefixes = tuple(prefixes)

        messages = await ctx.channel.purge(
            limit=limit, check=check,
            before=ctx.message, after=after,
            bulk=ctx.bot_permissions.manage_messages
        )

        await self.send_purged(ctx, messages)


async def setup(bot):
    await bot.add_cog(Moderation(bot))

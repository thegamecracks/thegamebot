#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging
from typing import Collection

import discord
from discord.ext import commands

from bot.utils import ConfirmationView
from main import Context, TheGameBot

logger = logging.getLogger('discord')


class SyncFlags(commands.FlagConverter):
    everything: bool = False
    guilds: list[discord.Guild] = commands.flag(default=lambda ctx: [])


async def _sync_body(
    ctx: Context, *,
    copy_global: bool = False,
    everything: bool = False,
    guilds: Collection[discord.Guild] = None
):
    inflector = ctx.bot.inflector

    if everything:
        sync_global = True
        guilds = ctx.bot.guilds
    elif guilds is not None:
        sync_global = False
    else:
        sync_global = True
        guilds = ()

    # Format an appropriate message to send before syncing
    items = []

    if sync_global:
        n_commands = len(ctx.bot.tree.get_commands())
        text = inflector.inflect(
            "{0} plural('global command', {0})".format(n_commands)
        )
        items.append(text)

    if guilds:
        if copy_global:
            for guild in guilds:
                ctx.bot.tree.copy_global_to(guild=guild)

        n_commands = sum(
            len(ctx.bot.tree.get_commands(guild=guild))
            for guild in guilds
        )

        text = inflector.inflect(
            "{0} {type} plural('command', {0}) in "
            "{1} plural('guild', {1})".format(
                n_commands, len(guilds),
                type='global and guild' if copy_global else 'guild'
            )
        )
        items.append(text)

    item_text = inflector.join(items)
    message = await ctx.send(f'Synchronizing {item_text}...')

    if sync_global:
        await ctx.bot.tree.sync()
    for guild in guilds:
        await ctx.bot.tree.sync(guild=guild)

    await message.edit(content=f'Finished synchronizing {item_text}!')


class Owner(commands.Cog):
    def __init__(self, bot: TheGameBot):
        self.bot = bot

    async def cog_check(self, ctx: Context):
        return await ctx.bot.is_owner(ctx.author)

    @commands.group(invoke_without_command=True)
    async def sync(self, ctx: Context):
        """The base command for synchronizing application commands."""

    @sync.command(name='everything')
    async def sync_everything(self, ctx: Context):
        """Synchronize both global and guild application commands."""
        await _sync_body(ctx, everything=True)

    @sync.group(name='global', invoke_without_command=True)
    async def sync_global(self, ctx: Context):
        """Synchronize global application commands."""
        await _sync_body(ctx)

    @sync_global.group(name='to', invoke_without_command=True)
    async def sync_global_to(
        self, ctx: Context, guild: discord.Guild = commands.CurrentGuild
    ):
        """Override and synchronize global commands to a test guild."""
        await _sync_body(ctx, guilds=(guild,), copy_global=True)

    @sync_global_to.command(name='reload', aliases=('load', 'refresh'))
    async def sync_global_to_reload(
        self, ctx: Context, guild: discord.Guild = commands.CurrentGuild
    ):
        """Override only the internal command tree for a test guild.
Useful for reloaded cogs."""
        ctx.bot.tree.copy_global_to(guild=guild)
        loc = 'this guild' if guild == ctx.guild else 'the given guild'
        await ctx.send(f'Finished overriding the internal commands for {loc}!')

    @sync.command(name='guilds')
    async def sync_guilds(self, ctx: Context, *guilds: discord.Guild):
        """Synchronize application commands in one or more guilds."""
        await _sync_body(ctx, guilds=guilds)

    @commands.command()
    async def restart(self, ctx: Context):
        """Restarts the bot."""
        view = ConfirmationView(ctx.author)

        await view.start(
            ctx, color=ctx.bot.get_bot_color(),
            title='Are you sure you want to RESTART the bot?'
        )

        if await view.wait_for_confirmation():
            await view.update('Restarting now.', color=view.YES)
            logger.info(f'Initiating restart by {ctx.author}')
            await self.bot.restart()
        else:
            await view.update('Cancelled restart.', color=view.NO)

    @commands.command()
    async def shutdown(self, ctx: Context):
        """Shutdown the bot."""
        view = ConfirmationView(ctx.author)

        await view.start(
            ctx, color=ctx.bot.get_bot_color(),
            title='Are you sure you want to SHUTDOWN the bot?'
        )

        if await view.wait_for_confirmation():
            await view.update('Shutting down.', color=view.YES)
            logger.info(f'Initiating shutdown by {ctx.author}')
            await self.bot.shutdown()
        else:
            await view.update('Cancelled shutdown.', color=view.NO)


async def setup(bot: TheGameBot):
    await bot.add_cog(Owner(bot))

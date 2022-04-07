#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging

import discord
from discord.ext import commands

from bot.utils import ConfirmationView
from main import Context, TheGameBot

logger = logging.getLogger('discord')


class SyncFlags(commands.FlagConverter):
    everything: bool = False
    guilds: list[discord.Guild] = commands.flag(default=lambda ctx: [])


class Owner(commands.Cog):
    def __init__(self, bot: TheGameBot):
        self.bot = bot

    async def cog_check(self, ctx: Context):
        return await ctx.bot.is_owner(ctx.author)

    @commands.command()
    async def sync(self, ctx: Context, *, flags: SyncFlags):
        """Synchronizes application commands.

Available flags:
    everything: if yes, both global and guild commands are synchronized.
    guilds: a list of guild IDs to synchronize instead of global commands."""
        inflector = ctx.bot.inflector
        sync_guilds = []
        sync_global = True

        # Interpret flags
        if flags.everything and flags.guilds:
            return await ctx.send('You should only specify one flag at a time.')
        elif flags.everything:
            sync_guilds = ctx.bot.guilds
        elif flags.guilds:
            sync_guilds = flags.guilds
            sync_global = False

        # Format an appropriate message to send before syncing
        items = []
        command_types = list(discord.AppCommandType)
        if sync_global:
            n_global_commands = sum(
                len(ctx.bot.tree.get_commands(type=t))
                for t in command_types
            )
            text = inflector.inflect(
                "{0} plural('global command', {0})".format(n_global_commands)
            )
            items.append(text)
        if sync_guilds:
            n_guild_commands = sum(
                len(ctx.bot.tree.get_commands(guild=guild, type=t))
                for guild in sync_guilds
                for t in command_types
            )
            text = inflector.inflect(
                "{0} plural('guild command', {0}) in "
                "{1} plural('guild', {1})".format(
                    n_guild_commands, len(sync_guilds)
                )
            )
            items.append(text)

        message = await ctx.send('Synchronizing {}...'.format(inflector.join(items)))

        if sync_global:
            await ctx.bot.tree.sync()
        for guild in sync_guilds:
            await ctx.bot.tree.sync(guild=guild)

        await message.edit(content='Finished application command synchronization!')

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

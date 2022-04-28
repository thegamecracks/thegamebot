"""
On command:
1. Create and start the view

On starting the view (MemoryView.start()):
1. Listen for interactions (using queue) until timeout or game finishes
    - Handled in MemoryView.memory_worker()

On button click (MemoryButton.callback()):
1. Queue the player's action

On player action (MemoryView.memory_worker()):
1. Determine if player either:
    - Clicked free card
    - Made initial guess
    - Correctly guessed a pair
    - Incorrectly guessed a pair
2. Update message accordingly
"""
#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import datetime
import random
from typing import Optional

import discord
from discord.ext import commands

from bot import errors
from main import Context, TheGameBot
from . import EditViewMixin, Games, TimeoutView


class MemoryButton(discord.ui.Button["MemoryView"]):
    def __init__(self, x: int, y: int, emoji: str):
        super().__init__(style=discord.ButtonStyle.success, label='\u200b')
        self.x = x
        self.y = y
        self.stored = emoji

    async def callback(self, interaction: discord.Interaction):
        self.view.queue.put_nowait((self, interaction))
        raise errors.SkipInteractionResponse('Skip deferral')


class MemoryView(TimeoutView, EditViewMixin):
    FREE = '\N{PARTY POPPER}'
    EMOJIS = (
        '\N{ALIEN MONSTER}',
        '\N{FACE SCREAMING IN FEAR}',
        '\N{FACE WITH PLEADING EYES}',
        '\N{FACE WITH ROLLING EYES}',
        '\N{FACE WITH STUCK-OUT TONGUE AND WINKING EYE}',
        '\N{FLUSHED FACE}',
        '\N{POUTING FACE}',
        '\N{ROLLING ON THE FLOOR LAUGHING}',
        '\N{SLEEPING FACE}',
        '\N{SMILING FACE WITH HEART-SHAPED EYES}',
        '\N{SMILING FACE WITH HORNS}',
        '\N{SMILING FACE WITH OPEN MOUTH AND SMILING EYES}'
    )

    children: list[MemoryButton]
    message: discord.Message

    def __init__(self, player_id: Optional[int], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player_id = player_id
        self.start_time: datetime.datetime = discord.utils.utcnow()

        self.current: Optional[MemoryButton] = None
        # Indicates which emoji the user is currently matching

        self.queue: asyncio.Queue[
            tuple[MemoryButton, discord.Interaction]
        ] = asyncio.Queue(3)
        self.worker: Optional[asyncio.Task] = None

        # Generate emoji
        emojis = list(self.EMOJIS) * 2 + [self.FREE]
        random.shuffle(emojis)

        # Add buttons
        for i, e in enumerate(emojis):
            self.add_item(MemoryButton(*divmod(i, 5), e))  # type: ignore

    async def on_error(self, interaction, error, item):
        ignored_exc = (errors.SkipInteractionResponse, asyncio.QueueFull)
        if not isinstance(error, ignored_exc):
            return await super().on_error(interaction, error, item)

    async def on_timeout(self):
        if self.worker is not None:
            self.worker.cancel()
        for button in self.children:
            button.disabled = True
        await self.message.edit(
            content=self.timeout_done,
            view=self
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.bot:
            return False
        return self.player_id is None or interaction.user.id == self.player_id

    async def update(self, interaction):
        finished = all(b.disabled for b in self.children)
        if finished:
            content = f'Finished in __{self.elapsed_str}__'
        else:
            content = self.timeout_in

        try:
            await self.edit(interaction, content=content, view=self)
        except discord.HTTPException:
            pass
        else:
            if finished:
                self.stop()

    async def memory_worker(self):
        while self.is_dispatching():
            button, interaction = await self.queue.get()
            emoji = button.stored

            if button == self.current:
                # Thanks for giving the same button discord
                return await interaction.response.defer()

            button.disabled = True
            button.emoji = emoji
            if emoji == self.FREE:
                await self.update(interaction)
            elif self.current is None:
                # Initial guess
                self.current = button
                await self.update(interaction)
            elif emoji == self.current.stored:
                # Guessed correct pair
                self.current = None
                await self.update(interaction)
            else:
                # Incorrect guess
                await self.update(interaction)
                await asyncio.sleep(1.2)

                for b in (button, self.current):
                    b.disabled = False
                    b.emoji = None
                self.current = None
                await self.update(interaction)

    async def start(self, ctx: Context, *, wait=True) -> Optional[asyncio.Task]:
        self.message = await ctx.send(
            f'(ends {self.timeout_timestamp})',
            view=self
        )
        self.start_time = discord.utils.utcnow()
        if wait:
            await self.memory_worker()
        else:
            self.worker = asyncio.create_task(
                self.memory_worker(),
                name='memory-worker'
            )
            return self.worker


class MemoryFlags(commands.FlagConverter):
    everyone: bool = False


class _Memory(commands.Cog):
    def __init__(self, bot: TheGameBot, base: Games):
        self.bot = bot
        self.base = base

    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.member)
    async def memory(self, ctx: Context, *, flags: MemoryFlags):
        """Starts a memory game.
Times out after: 180s"""
        view = MemoryView(
            None if flags.everyone else ctx.author.id,
            timeout=180
        )
        await view.start(ctx)

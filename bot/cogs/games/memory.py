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
import asyncio
import collections
import random
import re
from typing import Optional, Sequence

import discord
from discord.ext import commands

from . import create_setup
from bot import errors


class MemoryButton(discord.ui.Button["MemoryView"]):
    def __init__(self, x: int, y: int, emoji: str):
        super().__init__(style=discord.ButtonStyle.success, label='\u200b')
        self.x = x
        self.y = y
        self.stored = emoji

    async def callback(self, interaction: discord.Interaction):
        self.view.queue.put_nowait((self, interaction))
        raise errors.SkipInteractionResponse('Skip deferral')


class MemoryView(discord.ui.View):
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
            self.add_item(MemoryButton(*divmod(i, 5), e))

    async def on_error(self, error, item, interaction):
        if not isinstance(
                error, (errors.SkipInteractionResponse, asyncio.QueueFull)
            ):
            return await super().on_error(error, item, interaction)

    async def on_timeout(self):
        if self.worker is not None:
            self.worker.cancel()
        await self.message.edit(content='Timed out!')

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return self.player_id is None or interaction.user.id == self.player_id

    async def update(self, interaction):
        if interaction.response.is_done():
            await interaction.edit_original_message(view=self)
        else:
            await interaction.response.edit_message(view=self)

        if all(b.disabled for b in self.children):
            self.stop()

    async def memory_worker(self):
        while self.is_dispatching():
            button, interaction = await self.queue.get()
            emoji = button.stored

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

    async def start(self, ctx, wait=True) -> Optional[asyncio.Task]:
        self.message = await ctx.send('\u200b', view=self)
        if wait:
            await self.memory_worker()
        else:
            self.worker = asyncio.create_task(
                self.memory_worker(),
                name='memory-worker'
            )
            return self.worker


class Memory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='memory')
    @commands.cooldown(1, 30, commands.BucketType.member)
    async def client_memory(self, ctx, everyone: bool = False):
        """Starts a memory game.
The only allowed player is you (for now)."""
        view = MemoryView(
            None if everyone else ctx.author.id,
            timeout=180
        )
        await view.start(ctx)










setup = create_setup(Memory)

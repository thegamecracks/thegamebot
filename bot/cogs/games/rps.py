#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import abc
import asyncio
import datetime
from typing import Callable, Iterable, Optional, Union, Coroutine, Any

import discord
from discord.ext import commands

from . import Games

UM = Union[discord.User, discord.Member]


class RPSButton(discord.ui.Button["BaseRPSView"]):
    def __init__(self, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value = value

    def __gt__(self, other):
        if not isinstance(other, RPSButton):
            return NotImplemented
        return (self.value + 1) % len(self.view.children) == other.value

    def beats(self, other):
        return self.__gt__(other)

    async def callback(self, interaction: discord.Interaction):
        await self.view.step(self, interaction)


class BaseRPSView(discord.ui.View, abc.ABC):
    children: list[RPSButton]
    message: discord.Message

    def __init__(self, buttons: Iterable[RPSButton], *args, **kwargs):
        super().__init__(*args, **kwargs)
        for button in buttons:
            self.add_item(button)

    @property
    def timeout_timestamp(self) -> str:
        ends = datetime.datetime.now() + datetime.timedelta(seconds=self.timeout)
        return discord.utils.format_dt(ends, style='R')

    async def on_timeout(self):
        for button in self.children:
            button.disabled = True
        timestamp = discord.utils.format_dt(datetime.datetime.now(), style='R')
        await self.message.edit(
            content=f'(ended {timestamp} from inactivity)',
            view=self
        )

    @abc.abstractmethod
    def get_winners(self) -> Optional[list[UM]]:
        """Returns the winners of the game."""

    @abc.abstractmethod
    def get_embed(self, winners: Optional[list[UM]]) -> discord.Embed:
        """Returns the embed used for displaying the game's state."""

    @abc.abstractmethod
    async def step(self, button: RPSButton, interaction: discord.Interaction):
        """Triggered after a move has been submitted."""

    async def update(self, interaction: discord.Interaction, **kwargs):
        """Edit the game message with the current view."""
        finished = all(b.disabled for b in self.children)
        content = None if finished else f'(ends {self.timeout_timestamp})'

        try:
            if interaction.response.is_done():
                await interaction.edit_original_message(
                    content=content, view=self, **kwargs)
            else:
                await interaction.response.edit_message(
                    content=content, view=self, **kwargs)
        except discord.HTTPException:
            pass
        else:
            if finished:
                self.stop()

    async def start(
        self,
        send_meth: Callable[..., Coroutine[Any, Any, discord.Message]],
        *, wait=True
    ):
        """Start the game."""
        embed = self.get_embed(self.get_winners())
        self.message = await send_meth(
            f'(ends {self.timeout_timestamp})',
            embed=embed, view=self
        )
        if wait:
            await self.wait()


class RPSDuelView(BaseRPSView):
    """A typical variant of RPS with two players."""
    moves: dict[UM, Optional[RPSButton]]

    def __init__(
            self, buttons: Iterable[RPSButton],
            players: set[UM],
            *args, **kwargs):
        super().__init__(buttons, *args, **kwargs)
        self.players = players
        self.moves = dict.fromkeys(players)

    @property
    def public(self) -> bool:
        """Indicates if anyone can join this game."""
        return len(self.players) < 2

    @property
    def n_ready(self) -> int:
        """Indicates the number of players that have selected a move."""
        return sum(v is not None for v in self.moves.values())

    @property
    def n_waiting(self) -> int:
        """Indicates the number of players that have not selected a move."""
        return 2 - self.n_ready

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.bot:
            return False
        # Check if they made a move already
        move = self.moves.get(interaction.user)
        if move is not None:
            return False
        elif self.public:
            # Check if there's room for another player
            return self.n_waiting > 0
        else:
            # Check if they are part of the game
            return interaction.user in self.players

    def get_winners(self) -> Optional[list[UM]]:
        if any(m is None for m in self.moves.values()):
            return None
        elif self.public and len(self.moves) < 2:
            return None

        (a, a_move), (b, b_move) = self.moves.items()
        if a_move.beats(b_move):
            return [a]
        elif b_move.beats(a_move):
            return [b]
        return []

    def get_base_embed(self) -> discord.Embed:
        return discord.Embed()

    def list_moves(self, *, reveal: bool) -> list[str]:
        move_list = []
        for player, button in self.moves.items():
            move = '\N{BLACK LARGE SQUARE}'
            if button is None:
                move = '\N{THINKING FACE}'
            elif reveal:
                move = button.emoji
            move_list.append(f'{move} {player.mention}')
        return move_list

    def get_embed(self, winners: Optional[list[UM]]) -> discord.Embed:
        description = []

        if winners:
            description.append(f'The winner is {winners[0].mention}!')
        elif winners is not None:
            description.append(f"It's a tie!")

        description.extend(self.list_moves(reveal=winners is not None))

        n = self.n_waiting
        if len(self.moves) < 2 and n:
            s = 's' if n != 1 else ''
            description.append(f'Waiting for {n} player{s}...')

        embed = self.get_base_embed()
        embed.description = '\n'.join(description)

        return embed

    async def step(self, button, interaction):
        self.moves[interaction.user] = button

        winners = self.get_winners()
        final_embed = self.get_embed(winners)

        if winners is not None:
            for button in self.children:
                button.disabled = True

            pause_embed = self.get_base_embed()
            pause_embed.description = '\n'.join(
                ['Revealing the winner...']
                + self.list_moves(reveal=False)
            )
            await self.update(interaction, embed=pause_embed)
            await asyncio.sleep(2)

        await self.update(interaction, embed=final_embed)


def _create_buttons(items: Iterable[tuple[int, dict[str, object]]]) -> tuple[RPSButton]:
    return tuple(RPSButton(value, **kwargs) for value, kwargs in items)


class _RPS(commands.Cog):
    STANDARD = (
        (2, {'emoji': '\N{ROCK}', 'style': discord.ButtonStyle.primary}),
        (1, {'emoji': '\N{NEWSPAPER}', 'style': discord.ButtonStyle.primary}),
        (0, {'emoji': '\N{BLACK SCISSORS}', 'style': discord.ButtonStyle.primary})
    )

    def __init__(self, bot, base: Games):
        self.bot = bot
        self.base = base

    @commands.command()
    @commands.cooldown(2, 15, commands.BucketType.member)
    async def rps(self, ctx, user: discord.User = None):
        """Start a game of rock, paper, scissors.

user: The user to duel (optional)."""
        view = RPSDuelView(
            _create_buttons(self.STANDARD),
            {ctx.author, user}
            if user and user != ctx.author
            else set(),
            timeout=180
        )

        await view.start(ctx.send)

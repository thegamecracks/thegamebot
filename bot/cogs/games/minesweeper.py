#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import enum
import itertools
import random
import re
from typing import Generator, Optional, Union, Literal

import discord
from discord.ext import commands

from bot import errors
from . import create_setup, EditViewMixin, TimeoutView

Coordinate = tuple[int, int]


class MSCell(enum.Flag):
    EMPTY = 0
    MINE = 1
    VISIBLE = 2
    FAIL = 3
    FLAGGED = 4

    def __eq__(self, other):
        # Adds support for comparing rendered cells
        if isinstance(other, str):
            return str(self) == other
        return super().__eq__(other)

    def __ne__(self, other):
        if isinstance(other, str):
            return str(self) != other
        return super().__ne__(other)

    def __str__(self):
        cls = type(self)
        if self & cls.FLAGGED:
            return 'F'
        elif not self & cls.VISIBLE:
            return '_'
        elif self & cls.MINE:
            return 'M'
        return ' '


class MSStatus(enum.Enum):
    START = enum.auto()
    ONGOING = enum.auto()
    FAIL = enum.auto()
    PASS = enum.auto()

    @classmethod
    def end_states(cls):
        return cls.FAIL, cls.PASS


class MSGame:
    """A standard minesweeper game.

    Args:
        y_size (int)
        x_size (int): The size of the board (positive only).
        n_mines (int): The number of mines to place in the board.
            If 0, calculates a reasonable number of mines.

    """
    X_COORDS = tuple('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    Y_COORDS = tuple(str(n) for n in range(1, len(X_COORDS) + 1))

    def __init__(self, y_size: int, x_size: int, n_mines: int = 0):
        if y_size > len(self.Y_COORDS):
            raise ValueError('y_size exceeds number of labels available')
        elif x_size > len(self.X_COORDS):
            raise ValueError('x_size exceeds number of labels available')

        self._board: list[list[MSCell]] = [
            [MSCell.EMPTY] * x_size for _ in range(y_size)
        ]
        self.n_mines = n_mines or self.optimal_mine_count(y_size, x_size)

    @staticmethod
    def optimal_mine_count(y_size: int, x_size: int) -> int:
        return int((y_size * x_size + 1) // ((y_size * x_size) ** 0.5))

    def yield_neighbors_pos(self, y: int, x: int) -> Generator[Coordinate, None, None]:
        """Return the coordinates of cells neighboring a given coordinate."""
        y_range = range(max(0, y - 1), min(self.y_size, y + 2))
        x_range = range(max(0, x - 1), min(self.x_size, x + 2))
        for neighbor in itertools.product(y_range, x_range):
            if neighbor != (y, x):
                yield neighbor

    def neighboring_mines(self, y: int, x: int) -> int:
        """Return the number of mines neighboring a given coordinate."""
        return sum(
            bool(self.board[y][x] & MSCell.MINE)
            for y, x in self.yield_neighbors_pos(y, x)
        )

    def render_cell(self, y: int, x: int) -> str:
        """Return the symbol for a given coordinate.
        Takes the number of neighboring mines into consideration.
        """
        cell = str(self.board[y][x])
        if cell == ' ':
            cell = str(self.neighboring_mines(y, x) or ' ')
        return cell

    @property
    def board(self) -> list[list[MSCell]]:
        return self._board

    @property
    def y_size(self) -> int:
        return len(self._board)

    @property
    def x_size(self) -> int:
        return len(self._board[0])

    @property
    def n_flags(self) -> int:
        """The number of flags remaining that can be placed down."""
        return self.n_mines - sum(
            bool(cell & MSCell.FLAGGED)
            for cell in self.yield_cells()
        )

    def yield_cells(self) -> Generator[MSCell, None, None]:
        """Yield each cell in the board in left-to-right, top-to-bottom order."""
        for row in self._board:
            for cell in row:
                yield cell

    def yield_cells_with_pos(self) -> Generator[tuple[Coordinate, MSCell], None, None]:
        """Yield each coordinate and corresponding cell in the board
        in left-to-right, top-to-bottom order.
        """
        for y, row in enumerate(self._board):
            for x, cell in enumerate(row):
                yield (y, x), cell

    def get_status(self) -> MSStatus:
        """Return the game's current status."""
        all_found = True
        has_mines = False

        for cell in self.yield_cells():
            if cell == MSCell.FAIL:
                return MSStatus.FAIL
            elif cell & MSCell.MINE:
                has_mines = True
            elif not cell & MSCell.VISIBLE:
                all_found = False

        if all_found:
            return MSStatus.PASS
        elif has_mines:
            return MSStatus.ONGOING
        return MSStatus.START

    def start(self, y: int, x: int):
        """Distribute mines across the board.
        This is automatically called on the first click.
        """
        cells = [coord for coord, _ in self.yield_cells_with_pos()]
        cells.remove((y, x))
        for y, x in random.sample(cells, self.n_mines):
            self._board[y][x] = MSCell.MINE

    def click(self, y: int, x: int):
        """Reveal a cell and potentially its neighbors."""
        def reveal(y: int, x: int):
            cell = self._board[y][x]
            if cell & MSCell.VISIBLE or cell & MSCell.FLAGGED:
                return

            self._board[y][x] |= MSCell.VISIBLE

            if not cell & MSCell.MINE and self.neighboring_mines(y, x) == 0:
                for neighbor in self.yield_neighbors_pos(y, x):
                    reveal(*neighbor)

        if self.get_status() == MSStatus.START:
            self.start(y, x)
        return reveal(y, x)

    def flag(self, y: int, x: int):
        """Add or remove a flag on a cell."""
        self._board[y][x] ^= MSCell.FLAGGED

    # def slice(
    #     self, y_bounds: Optional[tuple[int, int]] = None,
    #     x_bounds: Optional[tuple[int, int]] = None
    # ) -> list[list[MSCell]]:
    #     if y_bounds is None:
    #         y_bounds = (0, self.y_size)
    #     if x_bounds is None:
    #         x_bounds = (0, self.x_size)
    #
    #     new = []
    #     for row in itertools.islice(self._board, *y_bounds):
    #         new.append(row[slice(*x_bounds)])
    #     return new

    def render(
        self, y_bounds: Optional[tuple[int, int]] = None,
        x_bounds: Optional[tuple[int, int]] = None,
        highlighted_column: Optional[int] = None
    ) -> str:
        def highlighted_render(y, x):
            char = self.render_cell(y, x)
            if x == highlighted_column and char == MSCell.EMPTY:
                char = '-'
            return char

        if y_bounds is None:
            y_bounds = (0, self.y_size)
        if x_bounds is None:
            x_bounds = (0, self.x_size)

        padding = len(str(y_bounds[1]))
        header_padding = ' ' * (padding - 1)
        lines = ['#{}|{}|{}#'.format(
            header_padding,
            ' '.join(self.X_COORDS[slice(*x_bounds)]),
            header_padding
        )]
        for y, row in enumerate(itertools.islice(self._board, *y_bounds)):
            lines.append(
                '{}|{}|{}'.format(
                    f'{y + 1:<{padding}d}',
                    ' '.join(
                        [highlighted_render(y, x) for x in range(*x_bounds)]
                    ),
                    f'{y + 1:>{padding}d}'
                )
            )
        return '\n'.join(lines)


class CoordinateSelect(discord.ui.Select['MSView']):
    """A select menu for inputting a given coordinate on the board."""

    async def callback(self, interaction: discord.Interaction):
        def parse_coordinate() -> tuple[Optional[int], int]:
            # Examples: "A", "F4" (X-axis is always given)
            v = self.values[0]
            x = MSGame.X_COORDS.index(v[0])
            y = None
            if len(v) > 1:
                y = int(v[1:]) - 1
            return y, x

        def do_click(y: int, x: int):
            if self.view.flagging:
                self.view.game.flag(y, x)
            else:
                self.view.game.click(y, x)

        if self.values[0] == 'Cancel':
            self.view.x_coord = None
        else:
            y, x = parse_coordinate()
            if y is None:
                self.view.x_coord = x
            else:
                do_click(y, x)
                self.view.x_coord = None

        await self.view.update(interaction)

    def update(self):
        """Determine the axis that the user should input
        and update the available options.
        """
        def make_option(
            label: str, cell: Optional[MSCell] = None
        ) -> discord.SelectOption:
            kwargs = {}
            if cell is not None and cell & MSCell.FLAGGED:
                kwargs['emoji'] = '\N{TRIANGULAR FLAG ON POST}'
            return discord.SelectOption(label=label, **kwargs)

        def get_x_options() -> list[discord.SelectOption]:
            x_coords = range(*view.viewport[1])
            min_y, max_y = view.viewport[0]
            choices = []
            for x in x_coords:
                # Count the number of cells that can be selected
                n_valid, last_valid = 0, None
                for y, row in enumerate(
                        itertools.islice(view.game.board, min_y, max_y),
                        start=min_y):
                    if str(row[x]) in valid:
                        n_valid += 1
                        last_valid = y

                if n_valid < 1:
                    continue
                elif n_valid == 1:
                    # Column only has one selectable cell; use full coordinate
                    label = MSGame.X_COORDS[x] + MSGame.Y_COORDS[last_valid]
                else:
                    # User needs to input Y axis afterwards
                    label = MSGame.X_COORDS[x]
                choices.append(make_option(label))

            return choices

        def get_y_options() -> list[discord.SelectOption]:
            # pre-req: x_coord is not None
            min_y, max_y = view.viewport[0]
            x_name = MSGame.X_COORDS[view.x_coord]
            choices = [
                discord.SelectOption(emoji='\N{LARGE RED CIRCLE}', label='Cancel')
            ]
            for y, row in enumerate(
                    itertools.islice(view.game.board, min_y, max_y),
                    start=min_y):
                cell = row[view.x_coord]
                if str(cell) in valid:
                    label = x_name + MSGame.Y_COORDS[y]
                    choices.append(make_option(label, cell))
            return choices

        def get_full_options() -> list[discord.SelectOption]:
            choices = []
            for x in range(*view.viewport[1]):
                for y in range(*view.viewport[0]):
                    cell = view.game.board[y][x]
                    if str(cell) in valid:
                        label = MSGame.X_COORDS[x] + MSGame.Y_COORDS[y]
                        choices.append(make_option(label, cell))
            return choices

        view = self.view

        # NOTE: cells are rendered before checking membership
        # to make the logic more succinct
        # (e.g. non-visible cells should be valid, empty or not)
        valid = (MSCell.EMPTY,)
        if view.flagging:
            if view.game.n_flags <= 0:
                valid = (MSCell.FLAGGED,)
            else:
                valid = (MSCell.EMPTY, MSCell.FLAGGED)

        bounds_start = 0
        if sum(str(cell) in valid for cell in view.game.yield_cells()) <= 25:
            # Enough select options for full coordinates
            axis = 'XY'
            options = get_full_options()
            view.x_coord = None
        elif view.x_coord is None:
            axis = 'X'
            options = get_x_options()
        else:
            axis = 'Y'
            options = get_y_options()
            bounds_start += 1  # Skip cancel button

        bounds = ''
        if len(options) > 0:
            bounds = options[bounds_start].label
        if len(options) > 1:
            bounds += f'-{options[-1].label}'
        if bounds:
            bounds = f' ({bounds})'

        self.placeholder = f'Input {axis}-coordinate' + bounds
        self.options = options


# NOTE: add middle click option? \N{THREE BUTTON MOUSE}
class ClickToggle(discord.ui.Button['MSView']):
    """Toggle between opening and flagging cells."""

    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        self.view.flagging = not self.view.flagging
        await self.view.update(interaction)

    def update(self):
        if self.view.flagging:
            self.emoji = '\N{TRIANGULAR FLAG ON POST}'
        else:
            self.emoji = '\N{FOOT}'


class MSView(TimeoutView, EditViewMixin):
    children: list[Union[CoordinateSelect, ClickToggle]]
    message: discord.Message

    def __init__(self, player_ids: Optional[tuple[int]], *args, timeout, **kwargs):
        super().__init__(timeout=timeout)
        self.player_ids = player_ids
        self.start_time: datetime.datetime = discord.utils.utcnow()

        self.game = MSGame(*args, **kwargs)
        self.viewport: tuple[tuple[int, int], tuple[int, int]] \
            = ((0, self.game.y_size), (0, self.game.x_size))
        self.x_coord: Optional[int] = None
        self.flagging: bool = False

        self.add_item(CoordinateSelect())
        self.add_item(ClickToggle())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return self.player_ids is None or interaction.user.id in self.player_ids

    async def on_timeout(self):
        await self.update()

    async def update(self, interaction: Optional[discord.Interaction] = None):
        no_interaction = interaction is None

        # Buttons should update before rendering as they may change view state
        for child in self.children:
            child.update()

        status = self.game.get_status()
        kwargs = self.get_message_kwargs(status=status, timed_out=no_interaction)

        try:
            await self.edit(interaction, **kwargs)
        except discord.HTTPException:
            pass
        else:
            if status in MSStatus.end_states() or no_interaction:
                # Player picked an ending move or game timed out
                self.stop()

    def get_message_kwargs(self, *, status: MSStatus, timed_out: bool = False):
        """Generate the kwargs necessary to send/edit the current message.
        This includes rendering the board if the game hasn't timed out.
        """
        kwargs = {'view': None}

        color = discord.Embed.Empty
        if status == MSStatus.FAIL:
            kwargs['content'] = f'\N{COLLISION SYMBOL} Exploded in {self.elapsed_str}'
            color = 0xBB1A34
        elif status == MSStatus.PASS:
            kwargs['content'] = f'\N{SMILING FACE WITH SUNGLASSES} Cleared in {self.elapsed_str}'
            color = 0x3BA55D
        elif self.timeout is not None:
            if timed_out:
                kwargs['content'] = self.timeout_done
                color = 0xBB1A34
            else:
                kwargs['content'] = self.timeout_in
                kwargs['view'] = self
        else:
            kwargs['view'] = self

        if not timed_out:
            description = []
            if self.flagging:
                description.append(f' Flags: **{self.game.n_flags}**')
            description.append(
                '```py\n{}```'.format(
                    self.game.render(
                        *self.viewport,
                        highlighted_column=self.x_coord
                    )
                )
            )
            kwargs['embed'] = discord.Embed(
                color=color,
                description='\n'.join(description)
            )

        return kwargs

    async def start(self, ctx):
        for child in self.children:
            child.update()
        kwargs = self.get_message_kwargs(status=self.game.get_status())
        self.message = await ctx.send(**kwargs)
        self.start_time = discord.utils.utcnow()


class BoardSizeConverter(commands.Converter[tuple[int, int]]):
    REGEX = re.compile(r'(?P<x>\d+)x(?P<y>\d+)', re.IGNORECASE)

    async def convert(self, ctx, argument):
        m = self.REGEX.fullmatch(argument)
        if m is None:
            raise commands.UserInputError('Could not interpret your board size.')

        x, y = (int(n) for n in m.groups())

        if x > 24:
            # 25 select options - 1 for Y-axis cancel button
            raise errors.ErrorHandlerResponse(
                'The board can only be up to 24 cells wide!')
        elif y > 10:
            # Constrain lines to keep message compact
            raise errors.ErrorHandlerResponse(
                'The board can only be up to 10 cells tall!')
        return y, x


class MSCommandFlags(commands.FlagConverter):
    players: tuple[Union[Literal['everyone'], discord.User]] = ()
    size: BoardSizeConverter = (10, 15)


class _Minesweeper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='minesweeper', aliases=('ms',))
    @commands.max_concurrency(1, commands.BucketType.member)
    async def client_minesweeper(self, ctx, *, flags: MSCommandFlags):
        """Starts a game of minesweeper.

players: A list of members that can play the game or "everyone".
size: The size of the board (default: 15x10). Maximum size is 24x10."""
        y_size, x_size = flags.size
        if 'everyone' in flags.players:
            player_ids = None
        else:
            player_ids = set(p.id for p in flags.players)
            player_ids.add(ctx.author.id)
        view = MSView(
            player_ids=player_ids, timeout=300,
            y_size=y_size, x_size=x_size
            # y_size=10, x_size=15, n_mines=25
        )
        await view.start(ctx)
        await view.wait()










setup = create_setup(_Minesweeper)

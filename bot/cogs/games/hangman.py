#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import base64
import enum
import random
import re
import string
from typing import Optional

import discord
from discord.ext import commands

from . import Games


def read_wordlist(filename, min_length=0) -> set:
    s = set()
    with open(filename) as f:
        for line in f:
            line = line.strip()
            if len(line) < min_length:
                continue
            s.add(line.lower())
    return s


class HangmanGame:
    WORDLIST_FILENAME = 'data/wordlist.txt'
    MIN_LENGTH = 4
    WORDLIST_SET = read_wordlist(WORDLIST_FILENAME, MIN_LENGTH)
    WORDLIST_TUPLE = tuple(WORDLIST_SET)

    STAGES = ("""\
--------
|      |
|     _O_
|      |
|     / \\
|""", """\
--------
|      |
|     _O_
|      |
|     /
|""", """\
--------
|      |
|     _O_
|      |
|
|""", """\
--------
|      |
|     _O
|      |
|
|""", """\
--------
|      |
|      O
|      |
|""", """\
--------
|      |
|      O
|
|
|""", """\
--------
|      |
|
|
|
|""")

    def __init__(
            self, *, word: Optional[str] = None,
            guesses: Optional[set] = None):
        self.word = word or random.choice(self.WORDLIST_TUPLE)
        self.word_set = frozenset(self.word)
        self.guesses = guesses if guesses is not None else set()

    @property
    def wrong_guesses(self) -> set:
        return self.guesses - self.word_set

    @property
    def remaining_guesses(self) -> int:
        return len(self.STAGES) - len(self.wrong_guesses) - 1

    def get_status(self) -> Optional[bool]:
        if all(c in self.guesses for c in self.word):
            return True
        elif self.remaining_guesses == 0:
            return False
        return None

    def guess(self, char: str) -> bool:
        """Guess a character and return a boolean indicating
        if the guess was correct or not.

        This method does not check if the letter was already guessed.

        """
        self.guesses.add(char)
        return char in self.word

    def render_word(self, blank_char: str = '_', sep: str = ' ') -> str:
        if len(self.guesses) == 0:
            return sep.join(['_'] * len(self.word))

        string = []
        for letter in self.word:
            if letter in self.guesses:
                string.append(letter)
            else:
                string.append(blank_char)

        return sep.join(string)

    def render_person(self) -> str:
        i = min(len(self.STAGES), max(0, self.remaining_guesses))
        return self.STAGES[i]


class KeyboardSelect(discord.ui.Select['HangmanView']):
    def __init__(self, chars: list[str], **kwargs):
        super().__init__(
            options=[discord.SelectOption(label=c) for c in chars],
            placeholder=f'{chars[0]}-{chars[-1]}' if len(chars) > 1 else chars[0],
            **kwargs
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.update(interaction, self.values[0])


# noinspection PyArgumentList
CharFlag = enum.Flag('CharFlag', 'A B C D E F G H I J K L M N O P Q R S T U V W X Y Z')


class HangmanView(discord.ui.View):
    CHAR_SET = frozenset(string.ascii_lowercase)

    def __init__(
            self,
            player_id: int,
            word: Optional[str] = None,
            guesses: Optional[set] = None):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.game = HangmanGame(word=word, guesses=guesses)

        self.update_keyboard()

    @staticmethod
    def decode_guesses(guesses: str) -> set[str]:
        # noinspection PyUnresolvedReferences
        members, uncovered = enum._decompose(CharFlag, int(guesses))
        return {m._name_.lower() for m in members}

    @staticmethod
    def decode_word(word: str) -> str:
        """Decode the word from base 64."""
        return base64.b64decode(word.encode()).decode()

    def encode_guesses(self) -> int:
        """Get the corresponding flag value for each letter guess and
        return the total value.
        """
        return sum(
            getattr(CharFlag, c.upper())._value_
            for c in self.game.guesses
        )

    def encode_word(self) -> str:
        return base64.b64encode(self.game.word.encode()).decode()

    @classmethod
    def from_match(cls, m: re.Match):
        player_id = int(m.group('player_id'))
        word = cls.decode_word(m.group('word'))
        guesses = cls.decode_guesses(m.group('guesses'))
        return cls(player_id, word, guesses)

    def get_custom_id(self, keyboard_index: int):
        return 'hangman:{p}:{i}:{w}:{g}'.format(
            p=self.player_id,
            i=keyboard_index,
            w=self.encode_word(),
            g=self.encode_guesses()
        )

    def get_embed(self) -> tuple[discord.Embed, Optional[bool]]:
        guesses = ''
        wrong_guesses = self.game.wrong_guesses
        if wrong_guesses:
            guesses = '\nWrong guesses: {}'.format(', '.join(sorted(wrong_guesses)))

        status = self.game.get_status()
        finish_text = ''
        if status is True:
            finish_text = '\nYou won!'
        elif status is False:
            finish_text = f'\nYou lost! The word was {self.game.word}.'
        else:
            remaining = self.game.remaining_guesses
            finish_text = '\nYou have {} wrong guess{} left!'.format(
                remaining, 'es' * (remaining != 1)
            )

        embed = discord.Embed(
            description='{w}{g}{f} ```\n{p}```'.format(
                w=discord.utils.escape_markdown(
                    self.game.render_word(sep=' \u200b' * 3)
                ),
                g=guesses,
                f=finish_text,
                p=self.game.render_person()
            )
        )
        return embed, status

    def update_keyboard(self):
        self.clear_items()

        chars = sorted(self.CHAR_SET - self.game.guesses)
        if len(chars) <= 25:
            self.add_item(KeyboardSelect(chars, custom_id=self.get_custom_id(0)))
        else:
            for i in range(0, len(chars), 25):
                self.add_item(
                    KeyboardSelect(
                        chars[i:i + 25],
                        custom_id=self.get_custom_id(i // 25)
                    )
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.bot:
            return False
        return interaction.user.id == self.player_id

    async def update(self, interaction: discord.Interaction, guess: str):
        self.game.guess(guess)

        embed, status = self.get_embed()
        if status is None:
            self.update_keyboard()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=None)

    async def send_initial_message(self, channel: discord.abc.Messageable):
        embed, status = self.get_embed()
        await channel.send(f'<@{self.player_id}>', embed=embed, view=self)


class _Hangman(commands.Cog):
    CUSTOM_ID_REGEX = re.compile(
        r'hangman:(?P<player_id>\d+):(?P<keyboard>\d+):'
        r'(?P<word>.+):(?P<guesses>\d+)'
    )

    def __init__(self, bot, base: Games):
        self.bot = bot
        self.base = base


    @commands.Cog.listener()
    async def on_message_interaction(self, interaction: discord.Interaction):
        """Handle an interaction for a hangman game.

        This bypasses the existing message tracking to implement its own
        handling of views, allowing dynamic custom_ids which can
        contain the entire game state.

        """
        # NOTE: referenced from ConnectionState.parse_interaction_create
        custom_id = interaction.data['custom_id']
        m = self.CUSTOM_ID_REGEX.match(custom_id)
        if m is None:
            return

        # Create view to handle interaction
        view = HangmanView.from_match(m)
        item = view.children[int(m.group('keyboard'))]
        # NOTE: referenced from ViewStore.dispatch
        item._refresh_state(interaction.data)
        view._dispatch_item(item, interaction)
        view.stop()





    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.member)
    async def hangman(self, ctx):
        """Starts a game of hangman.
The only allowed player is you (for now)."""
        view = HangmanView(ctx.author.id)
        await view.send_initial_message(ctx)
        view.stop()

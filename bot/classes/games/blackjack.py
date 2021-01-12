import asyncio
from dataclasses import dataclass, field, replace
import functools
import itertools
import random
from typing import FrozenSet, List, Tuple, Union, Dict

import discord
from discord.ext import commands
import inflect

from bot.classes.get_reaction import get_reaction
from bot import settings


inflector = inflect.engine()


RANKS = tuple(str(n) for n in range(2, 11)) + ('JACK', 'QUEEN', 'KING', 'ACE')
SUITS = ('SPADE', 'HEART', 'DIAMOND', 'CLUB')


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str
    facedown: bool = False

    def __post_init__(self):
        if self.rank not in RANKS:
            raise ValueError(f'Unknown rank {self.rank!r}')
        if self.suit not in SUITS:
            raise ValueError(f'Unknown suit {self.suit!r}')

    def __str__(self):
        if self.facedown:
            return 'Hidden'
        return f'{self.rank.capitalize()} of {self.suit.capitalize()}s'

    @functools.cached_property
    def value(self) -> Union[int, Tuple[int, int]]:
        rank = self.rank
        if rank in ('JACK', 'QUEEN', 'KING'):
            return 10
        elif rank == 'ACE':
            return 1, 11
        return int(rank)

    @functools.cached_property
    def color(self):
        if self.suit in ('DIAMONDS', 'HEARTS'):
            return 'RED'
        elif self.suit in ('CLUBS', 'SPADES'):
            return 'BLACK'
        raise ValueError(f'Unknown suit {self.suit!r}')

    def replace(self, **kwargs):
        return replace(self, **kwargs)


@dataclass
class Hand:
    cards: List[Card] = field(default_factory=list)

    def __post_init__(self):
        self._cache_values = None
        self._cache_soft = None

    def __contains__(self, item):
        return item in self.cards

    def __delitem__(self, index):
        del self.cards[index]

    def __getitem__(self, index):
        return self.cards[index]

    def __iter__(self):
        return iter(self.cards)

    def __len__(self):
        return len(self.cards)

    def __setitem__(self, index, item):
        self.cards[index] = item

    def __str__(self):
        return inflector.join(self)

    def append(self, card: Card):
        """Add a card to the hand."""
        self.cards.append(card)

        # Clear cache and then compute new values
        self._clear_cache()
        values = self.values

    def _clear_cache(self):
        self._cache_values = None
        self._cache_soft = None

    def count(self, rank=None, suit=None) -> int:
        """Count the number of cards with a particular rank and/or suit."""
        count = 0
        for card in self:
            if rank is not None:
                if suit is not None:
                    count += card.rank == rank and card.suit == suit
                else:
                    count += card.rank == rank
            elif suit is not None:
                count += card.suit == suit
            else:
                raise ValueError('Rank or suit must be specified')

        return count

    @property
    def maximum(self) -> int:
        """Returns the maximum legal value of the hand.
        If there are no legal values, returns the minimum of the hand."""
        legal, over = [], []
        for v in self.values:
            if v <= 21:
                legal.append(v)
            else:
                over.append(v)

        if legal:
            return max(legal)
        return min(over)

    @property
    def minimum(self) -> int:
        """Returns the minimum value of the hand."""
        return min(self.values)

    def reveal(self) -> int:
        """Reveal any cards in the hand that are facedown.
        This returns the number of cards that were revealed."""
        revealed = 0
        for i, card in enumerate(self):
            if card.facedown:
                self[i] = card.replace(facedown=False)
                revealed += 1
        if revealed:
            self._clear_cache()
        return revealed

    @property
    def soft(self) -> bool:
        if self._cache_soft is None:
            # Soft is determined during calculation of values
            values = self.values
        return self._cache_soft

    @property
    def values(self) -> FrozenSet[int]:
        """Return a frozenset of possible values for the hand."""
        if self._cache_values is not None:
            return self._cache_values

        total = 0
        variables = []
        for card in self:
            value = card.value
            if card.facedown:
                continue
            elif isinstance(value, int):
                total += value
            else:
                variables.append(value)

        # Calculate all the possible values for the hand
        has_ace = self.count('ACE')
        values = {}  # map value to softness
        for comb in itertools.product(*variables):
            v = total + sum(comb)
            values.setdefault(v, False)
            values[v] = has_ace and 11 in comb or values[v]
        value_set = frozenset(val for val, soft in values.items())

        self._cache_values = value_set
        self._cache_soft = values[self.maximum]

        return value_set

    @property
    def val(self) -> str:
        value = self.maximum
        if value == 21:
            return 'blackjack'
        elif self.soft:
            return f'soft {value}'
        return str(value)


CARDS = tuple(Card(r, s) for r in RANKS for s in SUITS)


class BotBlackjackGame:
    """A one-use blackjack game."""

    CARD_CLUSTER_1 = 798370146867085332
    CARD_CLUSTER_2 = 798378538809032714

    EMOJI_DOWN = 798378635232149534
    EMOJI_HIT = 798381258257989653
    EMOJI_STAND = 798381243770470420
    EMOJI_DEFAULT = '\N{NO ENTRY}'

    TIMEOUT = 30

    def __init__(self, ctx):
        self._ctx: commands.Context = ctx
        self._client: discord.Client = ctx.bot
        self.color = int(settings.get_setting('bot_color'), 16)
        self.emojis = self.chunk_emojis()

        deck = list(CARDS)
        random.shuffle(deck)

        self.player = Hand([deck.pop(), deck.pop()])
        self.dealer = Hand([deck.pop(), deck.pop().replace(facedown=True)])

        self.deck = deck

    def embed_update(self, user=None, done=False) -> discord.Embed:
        """Return the embed for the current game.
        This includes both the running and final state of the game.

        Args:
            user (Optional[discord.User]): The user that played the last move.
            done (bool): If True, adds the result onto the embed.

        """
        user = self._ctx.author if user is None else user
        embed = discord.Embed(
            description='Result: ' if done else '',
            color=self.color
        ).set_author(
            name=user.display_name,
            icon_url=user.avatar_url
        )

        # deck = self.deck
        player = self.player
        dealer = self.dealer

        if done:
            win = None
            if player.maximum > 21:
                win = False
                embed.description += 'Bust'
            elif dealer.maximum > 21:
                win = True
                embed.description += 'Dealer Bust'
            elif player.maximum == 21:
                if dealer.maximum == 21:
                    embed.description += 'Tie'
                else:
                    win = True
                    embed.description += 'Blackjack'
            elif player.maximum == dealer.maximum:
                embed.description += 'Tie'
            else:
                win = player.maximum > dealer.maximum
                if win:
                    embed.description += 'Win'
                else:
                    embed.description += 'Loss'

            if win:
                embed.color = 0x77B255
            elif win is False:
                embed.color = 0xDD2E44

        embed.add_field(
            name='You',
            value=f'{self.list_emojis(player)}\n\nValue: {player.val.capitalize()}'
        )
        embed.add_field(
            name='Dealer',
            value=f'{self.list_emojis(dealer)}\n\nValue: {dealer.val.capitalize()}'
        )

        return embed

    @staticmethod
    def emoji_name(card: Card) -> str:
        """Return the emoji name for a given card."""
        if card.facedown:
            return 'down'

        rank = card.rank
        suit = card.suit[0]
        try:
            int(rank)
        except ValueError:
            # Take the first letter for non-numbered ranks
            rank = rank[0].lower()

        return '{}{}'.format(rank, suit)

    def chunk_emojis(self) -> Dict[str, discord.Emoji]:
        """Chunk all the emojis available."""
        d = {
            'hit': self._client.get_emoji(self.EMOJI_HIT),
            'stand': self._client.get_emoji(self.EMOJI_STAND),
            'down': self._client.get_emoji(self.EMOJI_DOWN)
        }

        cluster_1: discord.Guild = self._client.get_guild(self.CARD_CLUSTER_1)
        cluster_2: discord.Guild = self._client.get_guild(self.CARD_CLUSTER_2)
        for card in CARDS:
            name = self.emoji_name(card)
            if card.rank == 'QUEEN':
                d[name] = discord.utils.get(cluster_2.emojis, name=name)
            else:
                d[name] = discord.utils.get(cluster_1.emojis, name=name)

        for k, v in d.items():
            if v is None:
                print(f'Could not find emoji for {v}')
                d[k] = self.EMOJI_DEFAULT

        return d

    def emoji(self, card: Card) -> discord.Emoji:
        """Get the given emoji for a card.
        If the card or emoji does not exist, returns the default emoji."""
        name = self.emoji_name(card)
        return self.emojis.get(name, self.EMOJI_DEFAULT)

    def list_emojis(self, hand: Hand) -> str:
        """Return a string with a list of card emojis for a given hand."""
        return ' '.join([str(self.emoji(c)) for c in hand])

    async def run(self, *, channel=None, users=None):
        """
        Args:
            channel (Optional[discord.TextChannel]):
                The channel to send the message to.
                If None, uses `self._ctx.channel`.
            users (Optional[Union[True, List[discord.User]]]):
                A list of users that can participate in the game.
                If None, the author of self._ctx will be the only participant.
                If True, anyone can participate.
        """
        if users is None:
            # Allow only caller
            users = [self._ctx.author]
        elif users is True:
            # Allow all participants
            users = None
        if channel is None:
            channel = self._ctx.channel

        deck = self.deck
        player = self.player
        dealer = self.dealer

        emojis = [
            self.emojis['hit'],
            self.emojis['stand']
        ]

        # Send initial message
        message: discord.Message = await channel.send('Loading...')
        last_player = self._ctx.author
        actions = []

        for e in emojis:
            await message.add_reaction(e)
        await asyncio.sleep(1)

        while max(player.maximum, dealer.maximum) < 21:
            await message.edit(content='', embed=self.embed_update(user=last_player))
            try:
                reaction, last_player = await get_reaction(
                    self._client, message,
                    emojis, users,
                    timeout=self.TIMEOUT
                )
            except asyncio.TimeoutError:
                return await message.edit(
                    content='Ended game due to inactivity.')
            else:
                if reaction.emoji == emojis[0]:
                    # Hit
                    actions.append('hit')
                    player.append(deck.pop())
                elif reaction.emoji == emojis[1]:
                    # Stand
                    actions.append('stand')
                    dealer.reveal()
                    while dealer.maximum < 17:
                        dealer.append(deck.pop())
                    break
                else:
                    raise ValueError(f'Unknown reaction {reaction!r}')
            first_turn = False

        embed = self.embed_update(done=True)
        if actions:
            embed.description += f"\nActions: {', '.join(actions)}"
        else:
            embed.description += '\nActions: None'
        await message.edit(content='', embed=embed)

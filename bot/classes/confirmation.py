import abc
import asyncio
from dataclasses import dataclass
from typing import Optional

import discord


@dataclass(frozen=True)
class ConfirmationEmoji:
    emoji: str
    color: int

    @property
    def colour(self):
        return self.color


class EmbedConfirmation(abc.ABC):
    """The base class for embed confirmations.

    Args:
        ctx (discord.ext.commands.Context)
        color (int): The color of the embed.

    """
    def __init__(self, ctx, color=0):
        self.ctx = ctx
        self.color = color
        self.embed = None
        self.message = None

    @abc.abstractmethod
    def _create_embed(self, title: str) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            color=self.color
        ).set_author(
            name=self.ctx.author.display_name,
            icon_url=self.ctx.author.avatar_url
        )
        self.embed = embed
        return embed

    @abc.abstractmethod
    async def _prompt(self, title: str) -> discord.Message:
        """Send the message prompt."""
        embed = self._create_embed(title)
        message = await self.ctx.send(embed=embed)
        self.message = message

        return message

    async def confirm(self, title: str, timeout=30) -> Optional[bool]:
        """Ask the user to confirm.

        Returns:
            bool: The choice the user picked.
            None: Timed out.

        """
        await self._prompt(title)
        return await self.get_answer(timeout=timeout)

    @abc.abstractmethod
    async def get_answer(self, *, timeout: int) -> Optional[bool]:
        """Get the user's answer."""

    async def update(self, title: str, color=None):
        self.embed.title = title
        if color is not None:
            self.embed.color = color

        await self.message.edit(embed=self.embed)


class ReactionConfirmation(EmbedConfirmation):
    """An embed confirmation that takes its input using reactions."""
    def __init__(self, ctx, color=0):
        super().__init__(ctx, color)

        self.emoji_yes = ConfirmationEmoji(
            '\N{WHITE HEAVY CHECK MARK}', 0x77B255)
        self.emoji_no = ConfirmationEmoji(
            '\N{CROSS MARK}', 0xDD2E44)

    def _create_embed(self, title: str) -> discord.Embed:
        return EmbedConfirmation._create_embed(self, title)

    async def _prompt(self, title: str) -> discord.Message:
        message = await EmbedConfirmation._prompt(self, title)

        # Add reactions
        emoji = (self.emoji_yes.emoji, self.emoji_no.emoji)
        for e in emoji:
            await message.add_reaction(e)

        return message

    async def get_answer(self, *, timeout: int) -> Optional[bool]:
        def check(r, u):
            return (r.message == self.message and u == self.ctx.author
                    and r.emoji in emoji)

        emoji = (self.emoji_yes.emoji, self.emoji_no.emoji)

        try:
            reaction, user = await self.ctx.bot.wait_for(
                'reaction_add', check=check, timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
        else:
            return reaction.emoji == self.emoji_yes.emoji
        finally:
            try:
                await self.message.clear_reactions()
            except discord.Forbidden:
                pass


class TextConfirmation(EmbedConfirmation):
    """An embed confirmation that takes its input using messages.

    Args:
        yes (Union[str, Iterable[str]])
        no (Union[str, Iterable[str]])

    """
    def __init__(self, ctx, color=0, yes=('yes', 'y'), no=('no', 'n')):
        super().__init__(ctx, color)

        self.yes = (yes,) if isinstance(yes, str) else yes
        self.no = (no,) if isinstance(no, str) else no

    def _create_embed(self, title: str) -> discord.Embed:
        embed = EmbedConfirmation._create_embed(self, title)
        self.embed.set_footer(
            text='Respond by typing *{yes}* or *{no}*'.format(
                yes='/'.join([str(s) for s in self.yes]),
                no='/'.join([str(s) for s in self.no])
            )
        )
        return embed

    async def _prompt(self, title: str) -> discord.Message:
        return await EmbedConfirmation._prompt(self, title)

    async def get_answer(self, *, timeout: int) -> Optional[bool]:
        def check(m: discord.Message):
            if m.author == self.ctx.author and m.channel == self.message.channel:
                content = m.content.strip().lower()
                return content in self.yes or content in self.no
            return False

        try:
            message = await self.ctx.bot.wait_for(
                'message', check=check, timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
        else:
            content = message.content.strip().lower()
            return content in self.yes


class AdaptiveConfirmation(ReactionConfirmation, TextConfirmation):
    """An embed confirmation that uses reactions if possible,
    otherwise asks via text."""
    def __init__(self, ctx, color=0):
        super().__init__(ctx, color)

        # Determine whether to use reactions or text
        # Reactions will not work if in DMs without members intent
        mode = 'text'
        if ctx.guild is not None:
            bot_perms = self.ctx.me.permissions_in(self.ctx.channel)
            if bot_perms.add_reactions:
                mode = 'react'
        else:
            mode = 'react' if ctx.bot.intents.members else 'text'
        self.mode = mode

    def _create_embed(self, title: str) -> discord.Embed:
        if self.mode == 'react':
            return super()._create_embed(title)
        else:
            return super(ReactionConfirmation, self)._create_embed(title)

    async def _prompt(self, title: str) -> discord.Message:
        if self.mode == 'react':
            return await super()._prompt(title)
        else:
            return await super(ReactionConfirmation, self)._prompt(title)

    async def get_answer(self, *, timeout: int) -> Optional[bool]:
        if self.mode == 'react':
            return await super().get_answer(timeout=timeout)
        else:
            return await super(ReactionConfirmation, self).get_answer(timeout=timeout)

#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import abc
import asyncio
from typing import Optional, Union

import discord

Real = Union[float, int]


class EmbedConfirmation(abc.ABC):
    """The base class for embed confirmations.

    Instances of this class should be single-use.

    Args:
        ctx (discord.ext.commands.Context)
        color (int): The color of the embed.

    """
    YES = 0x77B255
    NO = 0xDD2E44

    def __init__(self, ctx, color=0):
        self.ctx = ctx
        self.color = color
        self.embed = None
        self.message = None

    def _create_embed(self, title: str) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            color=self.color
        ).set_author(
            name=self.ctx.author.display_name,
            icon_url=self.ctx.author.avatar.url
        )
        self.embed = embed
        return embed

    async def _prompt(self, title: str) -> discord.Message:
        """Send the message prompt."""
        embed = self._create_embed(title)
        message = await self.ctx.send(embed=embed)
        self.message = message

        return message

    async def confirm(self, title: str, timeout: Real = 30) -> Optional[bool]:
        """Ask the user to confirm.

        Returns:
            bool: The choice the user picked.
            None: Timed out.

        """
        await self._prompt(title)
        return await self.get_answer(timeout=timeout)

    @abc.abstractmethod
    async def get_answer(self, *, timeout: Real) -> Optional[bool]:
        """Get the user's answer.

        This method should not be called normally
        as it is used by confirm().

        """

    async def update(self, title: str, *, color=None):
        self.embed.title = title
        if color is not None:
            self.embed.color = color

        await self.message.edit(embed=self.embed)


class ReactionConfirmation(EmbedConfirmation):
    """An embed confirmation that takes its input using reactions."""
    def __init__(self, ctx, color=0, *,
                 yes: str = '\N{WHITE HEAVY CHECK MARK}',
                 no: str = '\N{CROSS MARK}'):
        super().__init__(ctx, color)

        self.yes = yes
        self.no = no

    async def _prompt(self, title: str) -> discord.Message:
        message = await super()._prompt(title)

        # Add reactions
        for e in (self.yes, self.no):
            await message.add_reaction(e)

        return message

    async def get_answer(self, *, timeout: Real) -> Optional[bool]:
        def check(p):
            def emoji_are_equal():
                if p.emoji.is_unicode_emoji():
                    return p.emoji.name in emojis
                return p.emoji in emojis

            return (p.message_id == self.message.id
                    and p.user_id == self.ctx.author.id
                    and emoji_are_equal())

        emojis = (self.yes, self.no)

        try:
            payload = await self.ctx.bot.wait_for(
                'raw_reaction_add', check=check, timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
        else:
            return str(payload.emoji) == self.yes
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
        embed = super()._create_embed(title)
        self.embed.set_footer(
            text='Respond by typing *{yes}* or *{no}*'.format(
                yes='/'.join([str(s) for s in self.yes]),
                no='/'.join([str(s) for s in self.no])
            )
        )
        return embed

    async def get_answer(self, *, timeout: Real) -> Optional[bool]:
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


def AdaptiveConfirmation(ctx, *args, **kwargs):
    """Return a Confirmation that works for the given context."""
    perms = ctx.channel.permissions_for(ctx.me)
    cls = ReactionConfirmation if perms.add_reactions else TextConfirmation
    return cls(ctx, *args, **kwargs)


class ButtonConfirmationView(discord.ui.View):
    def __init__(
            self, confirmation: 'ButtonConfirmation',
            yes: discord.ui.Button, no: discord.ui.Button,
            *args, **kwargs
        ):
        super().__init__(*args, **kwargs)
        self.confirmation = confirmation
        self.add_item(yes)
        self.add_item(no)


class ButtonConfirmation(EmbedConfirmation):
    """An embed confirmation that takes its input using buttons.

    Args:
        ctx (commands.Context): The context to use.
        color (int): The color of the embed.
        yes (Optional[discord.ui.Button]):
            The button to use for inputting a "yes" answer.
        no (Optional[discord.ui.Button]):
            The button to use for inputting a "no" answer.

    """
    def __init__(self, ctx, color=0, *, yes=None, no=None):
        super().__init__(ctx, color)

        if yes is None:
            yes = discord.ui.Button(
                style=discord.ButtonStyle.green,
                emoji='\N{HEAVY CHECK MARK}'
            )
        if no is None:
            no = discord.ui.Button(
                style=discord.ButtonStyle.red,
                emoji='\N{HEAVY MULTIPLICATION X}'
            )
        yes.callback = self._create_callback(yes, True)
        no.callback = self._create_callback(no, False)

        self.yes = yes
        self.no = no

        self._view = None
        self._answer = None

    def _create_callback(self, button, value: bool):
        async def callback(interaction: discord.Interaction):
            if self._answer is not None:
                return
            self._answer = value
            button.view.stop()

        return callback

    async def _prompt(self, title: str, timeout: Real) -> discord.Message:
        """Send the message prompt."""
        view = ButtonConfirmationView(self, self.yes, self.no, timeout=timeout)
        embed = self._create_embed(title)
        message = await self.ctx.send(embed=embed, view=view)
        self.message = message
        self._view = view

        return message

    async def confirm(self, title: str, timeout: Real = 30) -> Optional[bool]:
        await self._prompt(title, timeout)
        return await self.get_answer(timeout=timeout)

    async def get_answer(self, *, timeout: Real) -> Optional[bool]:
        await self._view.wait()
        return self._answer

    async def update(self, title: str, *, color=None):
        self.embed.title = title
        if color is not None:
            self.embed.color = color

        view = ButtonConfirmationView.from_message(self.message)
        for button in view.children:
            button.disabled = True

        await self.message.edit(embed=self.embed, view=view)

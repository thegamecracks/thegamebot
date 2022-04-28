#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import discord

from bot import errors


class ConfirmationButton(discord.ui.Button['ConfirmationView']):
    def __init__(self, value: bool, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value = value

    async def callback(self, interaction):
        self.view.value = self.value
        self.view._last_interaction = interaction
        self.view.stop()
        raise errors.SkipInteractionResponse('deferred confirmation response')

    @classmethod
    def create_from(cls, button: discord.ui.Button, value: bool):
        obj = cls(value)
        obj._underlying = button._underlying
        return obj


class ConfirmationView(discord.ui.View):
    """A view for choosing between yes and no.

    To use this, construct an instance of this class and then
    use the `start()` method to send a message along with
    `wait_for_confirmation()` to get the user's choice.

    To update the message after receiving their choice, use
    the `update()` method. If this is not called, the
    interaction will not be responded to.

    If you would like to send a message yourself, you can pass
    this view as an argument and update its `message` attribute::
        >>> view = ConfirmationView(...)
        >>> view.message = await channel.send(...)
        >>> if view.wait_for_confirmation():
        ...     ...

    :param yes:
        The button to use for inputting a "yes" answer.
        Defaults to a green button with a check mark.
    :param no:
        The button to use for inputting a "no" answer.
        Defaults to a red button with a cross mark.

    """
    YES = 0x77B255
    NO = 0xDD2E44

    children: list[ConfirmationButton]

    def __init__(
        self,
        author: discord.User | discord.Member,
        yes: discord.ui.Button = None, no: discord.ui.Button = None,
        *args, **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.author = author

        self.value: bool | None = None
        self.message: discord.Message | None = None
        self._last_interaction: discord.Interaction | None = None

        yes = yes or self.make_yes_button()
        no = no or self.make_no_button()
        self.add_item(ConfirmationButton.create_from(yes, True))
        self.add_item(ConfirmationButton.create_from(no, False))

    async def interaction_check(self, interaction):
        return interaction.user == self.author

    async def on_error(self, interaction, error, item):
        if not isinstance(error, errors.SkipInteractionResponse):
            await super().on_error(interaction, error, item)

    async def start(
        self, channel: discord.abc.Messageable,
        *, color: int, title: str
    ):
        """Generates an embed and sends a message to the given channel.

        :param channel: The channel to send to.
        :param color: The color of the embed.
        :param title: The title of the embed.

        """
        embed = discord.Embed(
            title=title,
            color=color
        ).set_author(
            name=self.author.display_name,
            icon_url=self.author.display_avatar.url
        )

        self.message = await channel.send(embed=embed, view=self)

    async def wait_for_confirmation(self) -> bool | None:
        """Returns the user's choice or None if the view timed out."""
        await self.wait()
        return self.value

    async def update(
        self, title: str = None, *, color: int = None,
        embed: discord.Embed = None
    ):
        """Disables all the view's components and updates the embed.

        After a message was sent, this method can be called multiple times.

        :param title: The new title the embed should have.
        :param color: The new color of the embed.
            For most purposes, the class attributes `YES` and `NO`
            can be used here.
        :param embed: An entirely new embed to replace the existing embed.
            If this is provided, the rest of the parameters are ignored.

        """
        if embed is None:
            embed = self.message.embeds[0]
            if title is not None:
                embed.title = title
            if color is not None:
                embed.color = color

        for button in self.children:
            button.disabled = True

        interaction: discord.Interaction = self._last_interaction
        if interaction is None:
            return await self.message.edit(embed=embed, view=self)

        try:
            if interaction.response.is_done():
                await interaction.edit_original_message(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        except discord.HTTPException:
            await self.message.edit(embed=embed, view=self)

    @staticmethod
    def make_yes_button():
        return discord.ui.Button(
            style=discord.ButtonStyle.green,
            emoji='\N{HEAVY CHECK MARK}'
        )

    @staticmethod
    def make_no_button():
        return discord.ui.Button(
            style=discord.ButtonStyle.red,
            emoji='\N{HEAVY MULTIPLICATION X}'
        )

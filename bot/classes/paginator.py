import asyncio

import discord
import disputils

from bot.classes.get_reaction import get_reaction


class RemovableReactEmbedPaginator(disputils.EmbedPaginator):
    """A paginator that also reacts to removing reactions,
    allowing the bot to not require manage messages permission.

    The page is deleted when the user(s) take too long to respond."""

    async def run(self, users=None, channel=None):
        """
        Runs the paginator.

        Args:
            users (Optional[List[discord.User]]):
                A list of `discord.User` that can control the pagination.
                If None or an empty list, any user can control the pagination
                (not recommended).
        channel (Optional[discord.TextChannel]):
            The text channel to send the embed to.
            Must only be specified if `self.message` is `None`.

        """
        if channel is None and self.message is not None:
            channel = self.message.channel
        elif channel is None:
            raise TypeError(
                "Missing argument. You need to specify a target channel.")

        self._embed = self.pages[0]

        if len(self.pages) == 1:  # no pagination needed in this case
            self.message = await channel.send(embed=self._embed)
            return

        self.message = await channel.send(embed=self.formatted_pages[0])
        current_page_index = 0

        for emoji in self.control_emojis:
            await self.message.add_reaction(emoji)

        while True:
            try:
                reaction, user = await get_reaction(
                    self._client, self.message,
                    self.control_emojis,
                    users, timeout=20
                )
            except asyncio.TimeoutError:
                # Timed out!
                if not isinstance(channel, discord.channel.GroupChannel):
                    await self.message.edit(
                        content='This page has expired.',
                        embed=None,
                        delete_after=10
                    )
                return

            emoji = reaction.emoji
            max_index = len(self.pages) - 1  # index for the last page

            if emoji == self.control_emojis[0]:
                load_page_index = 0

            elif emoji == self.control_emojis[1]:
                load_page_index = max(0, current_page_index - 1)

            elif emoji == self.control_emojis[2]:
                load_page_index = min(current_page_index + 1, max_index)

            elif emoji == self.control_emojis[3]:
                load_page_index = max_index

            else:
                await self.message.delete()
                return

            await self.message.edit(embed=self.formatted_pages[load_page_index])

            current_page_index = load_page_index


class RemovableReactBotEmbedPaginator(disputils.BotEmbedPaginator,
                                      RemovableReactEmbedPaginator):
    "Implements the BotEmbedPaginator interface."

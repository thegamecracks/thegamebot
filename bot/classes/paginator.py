import asyncio

import discord
import disputils


class RemovableReactEmbedPaginator(disputils.EmbedPaginator):
    """A paginator that also reacts to removing reactions,
    allowing the bot to not require manage messages permission.

    The page is deleted when the user(s) take too long to respond."""

    async def run(self, users, channel=None):
        """
        Runs the paginator.

        Args:
            users (List[discord.User]):
                A list of :class:`discord.User` that can control
                the pagination. Passing an empty list will grant access
                to all users. (Not recommended.)
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

        def check(r: discord.Reaction, u: discord.User):
            result = (
                r.message.id == self.message.id
                and r.emoji in self.control_emojis
            )

            if users:
                result = result and u.id in (u1.id for u1 in users)

            return result

        while True:
            # React to both reaction_add and reaction_remove
            # See https://stackoverflow.com/a/59433241 on
            # awaiting multiple events
            pending_tasks = [
                self._client.wait_for('reaction_add', check=check, timeout=20),
                self._client.wait_for('reaction_remove', check=check, timeout=20),
            ]
            try:
                completed_tasks, pending_tasks = await asyncio.wait(
                    pending_tasks, return_when=asyncio.FIRST_COMPLETED)
            except asyncio.TimeoutError:
                if (not isinstance(channel, discord.channel.DMChannel)
                        and not isinstance(channel, discord.channel.GroupChannel)):
                    await self.message.delete()
                return
            finally:
                for task in pending_tasks:
                    task.cancel()

            reaction, user = completed_tasks.pop().result()
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
    pass

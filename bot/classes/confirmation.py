import asyncio
from dataclasses import dataclass

import discord


@dataclass
class ConfirmationEmoji:
    emoji: str
    color: int

    @property
    def colour(self):
        return self.color


class Confirmation:
    def __init__(self, ctx, color=0):
        self.ctx = ctx
        self.color = color
        self.embed = discord.Embed(
            color=color
        ).set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.avatar_url
        )
        self.emoji_yes = ConfirmationEmoji(
            '\N{WHITE HEAVY CHECK MARK}', 0x77B255)
        self.emoji_no = ConfirmationEmoji(
            '\N{CROSS MARK}', 0xDD2E44)
        self.message = None

    async def confirm(self, title: str, timeout=30):
        """Ask the user to confirm.

        Returns:
            bool: The choice the user picked.
            None: Timed out.

        """
        async def clear_reactions(message):
            try:
                await message.clear_reactions()
            except discord.Forbidden:
                pass

        ctx = self.ctx

        self.embed.title = title

        # Send prompt
        message = await ctx.send(embed=self.embed)
        self.message = message

        # Add reactions
        emoji = [self.emoji_yes.emoji, self.emoji_no.emoji]
        for e in emoji:
            await message.add_reaction(e)

        # Wait for response
        def check(r, u):
            return (r.message == message and u == ctx.author
                    and r.emoji in emoji)

        try:
            reaction, user = await ctx.bot.wait_for(
                'reaction_add', check=check, timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
        else:
            return reaction.emoji == self.emoji_yes.emoji
        finally:
            await clear_reactions(message)

    async def update(self, title: str, color=None):
        self.embed.title = title
        if color is not None:
            self.embed.color = color

        await self.message.edit(embed=self.embed)

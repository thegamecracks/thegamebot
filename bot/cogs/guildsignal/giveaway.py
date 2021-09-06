#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import enum
import random
import re
from typing import Callable, Optional

import discord
from discord.ext import commands

from . import SignalHill
from bot import checks, converters, errors


class GiveawayStatus(enum.Enum):
    RUNNING = 0
    CANCELED = 1
    FINISHED = 2
    UNKNOWN = 3


def get_giveaway_status(m: discord.Message) -> GiveawayStatus:
    """Infer the status of a giveaway from the message."""
    if not m.embeds:
        return GiveawayStatus.UNKNOWN

    embed = m.embeds[0]
    title = str(embed.title).lower()
    if 'finish' in title:
        return GiveawayStatus.FINISHED
    elif 'cancel' in title:
        return GiveawayStatus.CANCELED

    return GiveawayStatus.RUNNING


def check_giveaway_status(
        giveaway_channel_id: int,
        check_func: Callable[[GiveawayStatus], bool],
        bad_response: str):
    """Check if the giveaway's status matches a condition.

    Searches through the last 10 messages for a giveaway message,
    i.e. where the status is not `GiveawayStatus.UNKNOWN`.

    This will add a `last_giveaway` attribute to the context which will
    be the giveaway message or None if it does not exist.

    """
    e = errors.ErrorHandlerResponse(bad_response)

    async def predicate(ctx):
        channel = ctx.bot.get_channel(giveaway_channel_id)

        ctx.last_giveaway = m = await channel.history(limit=10).find(
            lambda m: get_giveaway_status(m) != GiveawayStatus.UNKNOWN
        )
        if not m or not check_func(get_giveaway_status(m)):
            raise e

        return True

    return commands.check(predicate)


def is_giveaway_running(giveaway_channel_id):
    """Shorthand for checking if the giveaway's status is running."""
    return check_giveaway_status(
        giveaway_channel_id,
        lambda s: s == GiveawayStatus.RUNNING,
        'There is no giveaway running at the moment!'
    )


class GiveawayStartFlags(commands.FlagConverter, delimiter=' ', prefix='--'):
    end: Optional[converters.DatetimeConverter]
    description: str
    title: str


class GiveawayEditFlags(commands.FlagConverter, delimiter=' ', prefix='--'):
    end: Optional[converters.DatetimeConverter]
    description: Optional[str]
    title: Optional[str]

    @classmethod
    async def convert(cls, ctx, argument):
        instance = await super().convert(ctx, argument)

        # Make sure at least one flag was specified
        if all(getattr(instance, f.attribute) is None for f in cls.get_flags().values()):
            raise errors.ErrorHandlerResponse(
                'At least one giveaway embed field must be specified to edit.')

        return instance


class _SignalHill_Giveaway(commands.Cog):
    GIVEAWAY_CHANNEL_ID = 850965403328708659  # testing: 850953633671020576
    GIVEAWAY_EMOJI_ID = 815804214470770728  # testing: 340900129114423296

    def __init__(self, bot, base: SignalHill):
        self.bot = bot
        self.base = base

    @property
    def giveaway_channel(self):
        return self.bot.get_channel(self.GIVEAWAY_CHANNEL_ID)

    @property
    def giveaway_emoji(self):
        return self.bot.get_emoji(self.GIVEAWAY_EMOJI_ID)

    @commands.group(name='giveaway')
    @commands.cooldown(2, 5, commands.BucketType.channel)
    @commands.has_role('Staff')
    @checks.used_in_guild(SignalHill.GUILD_ID)
    async def client_giveaway(self, ctx):
        """Commands for setting up giveaways."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)


    async def _giveaway_get_message(self):
        """Get the latest giveaway message."""
        try:
            return await self.giveaway_channel.history(limit=1).next()
        except discord.NoMoreItems:
            return None


    def _giveaway_create_embed(
            self, end: Optional[datetime.datetime],
            title: str, description: str):
        """Create the running giveaway embed."""
        embed = discord.Embed(
            color=discord.Color.gold(),
            description=description,
            title=title,
            timestamp=end or datetime.datetime.now()
        ).set_footer(
            text='End date' if end else 'Start date'
        )

        return embed


    def _giveaway_finish_embed(self, embed, winners, total):
        """Edit a running embed so the giveaway is finished."""
        plural = self.bot.inflector.plural
        k = len(winners)

        embed.color = discord.Color.green()

        embed.title = '{}\nThis giveaway has finished with {:,} {}!'.format(
            embed.title, total, plural('participant', total)
        )

        embed.add_field(
            name='The {} {}:'.format(
                plural('winner', k), plural('is', k)
            ),
            value='{}\n Please create a support ticket to '
                  'receive your reward!'.format(
                self.bot.inflector.join([u.mention for u in winners])
            )
        ).set_footer(
            text='Finish date'
        )
        embed.timestamp = datetime.datetime.now()

        return embed


    def _giveaway_reroll_embed(self, embed, winners, total, reason):
        """Edit a finished embed to replace the winners."""
        plural = self.bot.inflector.plural
        k = len(winners)

        embed.title = '{}\nThis giveaway has finished with {:,} {}!'.format(
            embed.title.split('\n')[0], total, plural('participant', total)
        )

        embed.clear_fields()

        embed.add_field(
            name='The (rerolled) {} {}:'.format(
                plural('winner', k), plural('is', k)
            ),
            value='{}\n Please create a support ticket to '
                  'receive your reward!'.format(
                self.bot.inflector.join([u.mention for u in winners])
            )
        ).add_field(
            name='Reason for rerolling:',
            value=reason
        ).set_footer(
            text='Rerolled at'
        )
        embed.timestamp = datetime.datetime.now()

        return embed

    def _giveaway_find_field_by_name(self, embed, name):
        return discord.utils.find(lambda f: name in f.name, embed.fields)


    async def _giveaway_get_participants(self, message, *, ignored=None):
        if not ignored:
            ignored = (self.bot.user.id,)

        reaction = discord.utils.find(
            lambda r: getattr(r.emoji, 'id', 0) == self.GIVEAWAY_EMOJI_ID,
            message.reactions
        )

        if reaction is None:
            return None, None

        participants = []
        async for user in reaction.users():
            if user.id not in ignored:
                participants.append(user)

        return reaction, participants


    def _giveaway_get_winners(self, embed, participants):
        m = re.match('\d+', embed.title)
        k = int(m.group() if m else 1)
        return random.choices(participants, k=k)


    def _giveaway_parse_winners_from_field(
            self, field) -> list[int]:
        """Parse the winner mention from the winner field."""
        return [
            int(m.group(1))
            for m in re.finditer(r'<@!?(\d+)>', field.value)
        ]


    @client_giveaway.command(name='cancel')
    @is_giveaway_running(GIVEAWAY_CHANNEL_ID)
    async def client_giveaway_cancel(self, ctx, *, description: str = None):
        """Cancel the current giveaway.
If a description is given, this replaces the giveaway's current description
and adds a title saying the giveaway has been canceled.
The giveaway message is deleted if no description is given."""
        if description is None:
            await ctx.last_giveaway.delete()
            return await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

        embed = ctx.last_giveaway.embeds[0]
        embed.color = discord.Color.dark_red()
        embed.title = 'This giveaway has been canceled.'
        embed.description = description

        embed.set_footer(text=embed.Empty)
        embed.timestamp = embed.Empty

        await ctx.last_giveaway.edit(embed=embed)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


    @client_giveaway.command(name='edit')
    @is_giveaway_running(GIVEAWAY_CHANNEL_ID)
    async def client_giveaway_edit(self, ctx, *, flags: GiveawayEditFlags):
        """Edit the giveaway message.

Usage:
--title 3x Apex DLCs --description Hello again! --end unknown

end: A date when the giveaway is expected to end. The end date can be removed by inputting a non-date. Assumes UTC if you don't have a timezone set with the bot.
title: The title of the giveaway.
description: The description of the giveaway."""
        embed = ctx.last_giveaway.embeds[0]

        if flags.title is not None:
            embed.title = flags.title
        if flags.description is not None:
            embed.description = flags.description
        if flags.end is not None:
            try:
                dt = await converters.DatetimeConverter().convert(ctx, flags.end)
            except commands.BadArgument as e:
                embed.timestamp = ctx.last_giveaway.created_at
                embed.set_footer(text='Start date')
            else:
                embed.timestamp = dt
                embed.set_footer(text='End date')

        await ctx.last_giveaway.edit(embed=embed)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


    @client_giveaway.command(name='finish')
    @is_giveaway_running(GIVEAWAY_CHANNEL_ID)
    async def client_giveaway_finish(self, ctx, ping: bool = True):
        """End the current giveaway and decide who the winner is."""
        reaction, participants = await self._giveaway_get_participants(ctx.last_giveaway)
        if reaction is None:
            return await ctx.send(
                'Giveaway is missing reaction: {}'.format(self.giveaway_emoji))
        elif not participants:
            return await ctx.send('There are no participants to choose from!')

        embed = ctx.last_giveaway.embeds[0]
        winners = self._giveaway_get_winners(embed, participants)

        # Update embed
        embed = self._giveaway_finish_embed(
            embed, winners,
            total=len(participants)
        )
        await ctx.last_giveaway.edit(embed=embed)

        await ctx.send(
            '# of participants: {:,}\n{}: {}'.format(
                len(participants),
                ctx.bot.inflector.plural('Winner', len(winners)),
                ctx.bot.inflector.join([u.mention for u in winners])
            ),
            allowed_mentions=discord.AllowedMentions(users=ping)
        )


    @client_giveaway.command(name='reroll')
    @check_giveaway_status(
        GIVEAWAY_CHANNEL_ID,
        lambda s: s == GiveawayStatus.FINISHED,
        'You can only reroll the winner when there is a finished giveaway!'
    )
    async def client_giveaway_reroll(
            self, ctx, winner: Optional[discord.User], *, reason):
        """Reroll the winner for a giveaway that has already finished.
This will include members that reacted after the giveaway has finished.

winner: The specific winner to reroll.
reason: The reason for rerolling the winner."""
        embed = ctx.last_giveaway.embeds[0]

        win_f = self._giveaway_find_field_by_name(embed, 'winner')
        previous_winners = self._giveaway_parse_winners_from_field(win_f)

        replacement_index = -1
        if winner:
            try:
                replacement_index = previous_winners.index(winner.id)
            except ValueError:
                return await ctx.send('That user is not one of the winners!')

        reaction, participants = await self._giveaway_get_participants(
            ctx.last_giveaway, ignored=(ctx.me.id, *previous_winners))
        if reaction is None:
            return await ctx.send(
                'Giveaway is missing reaction: {}'.format(self.giveaway_emoji))
        elif not participants:
            return await ctx.send(
                'There are no other participants to choose from!')

        if winner:
            replacement = random.choice(participants)
            new_winners = previous_winners.copy()
            new_winners[replacement_index] = replacement
            # Convert the rest into discord.Users
            for i, v in enumerate(new_winners):
                if isinstance(v, int):
                    new_winners[i] = await ctx.bot.fetch_user(v)
        else:
            new_winners = self._giveaway_get_winners(embed, participants)

        embed = self._giveaway_reroll_embed(
            embed, new_winners,
            total=len(participants) + (len(previous_winners) - 1) * bool(winner),
            reason=reason
        )
        await ctx.last_giveaway.edit(embed=embed)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


    @client_giveaway.command(name='simulate')
    async def client_giveaway_simulate(self, ctx, *, flags: GiveawayStartFlags):
        """Generate a giveaway message in the current channel.

Usage:
--title 2x Apex DLCs --description Hello world! --end in 1 day

end: An optional date when the giveaway is expected to end. Assumes UTC if you don't have a timezone set with the bot.
title: The title of the giveaway.
description: The description of the giveaway."""
        embed = self._giveaway_create_embed(**dict(flags))
        await ctx.send(embed=embed)


    @client_giveaway.command(name='start')
    @check_giveaway_status(
        GIVEAWAY_CHANNEL_ID,
        lambda s: s != GiveawayStatus.RUNNING,
        'There is already a giveaway running! Please "finish" or "cancel" '
        'the giveaway before creating a new one!'
    )
    async def client_giveaway_start(self, ctx, *, flags: GiveawayStartFlags):
        """Start a new giveaway in the giveaway channel.
Only one giveaway can be running at a time, for now that is.

The number of winners is determined by a prefixed number in the title, i.e. "2x Apex DLCs". If this number is not present, defaults to 1 winner.

Usage:
--title 2x Apex DLCs --description Hello world! --end in 1 day

end: An optional date when the giveaway is expected to end. Assumes UTC if you don't have a timezone set with the bot.
title: The title of the giveaway.
description: The description of the giveaway."""
        embed = self._giveaway_create_embed(**dict(flags))

        message = await self.giveaway_channel.send('@everyone', embed=embed)

        try:
            await message.add_reaction(self.giveaway_emoji)
        except discord.HTTPException:
            await ctx.send(
                'Warning: failed to add the giveaway reaction ({})'.format(
                    self.giveaway_emoji
                )
            )
        else:
            await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import functools
import itertools
import zoneinfo

import discord
from discord import app_commands
from discord.ext import commands
import rapidfuzz

from main import TheGameBot

BASE_DATETIME = datetime.datetime.now()


@functools.cache
def available_timezones():
    return zoneinfo.available_timezones()


class TimezoneTransformer(app_commands.Transformer):
    @classmethod
    async def autocomplete(cls, interaction, value: str):
        matches = rapidfuzz.process.extract_iter(
            value, available_timezones(), score_cutoff=80
        )

        # return the first 5 matches
        return [
            app_commands.Choice(name=name, value=name)
            for name, score, index in itertools.islice(matches, 5)
        ]

    @classmethod
    async def transform(cls, interaction, value):
        try:
            return zoneinfo.ZoneInfo(value)
        except zoneinfo.ZoneInfoNotFoundError:
            raise commands.BadArgument(
                'Could not find a time zone with that name. '
                'See this [Time Zone Map](https://kevinnovak.github.io/Time-Zone-Picker/) '
                'for a list of valid time zones.'
            )


async def get_timezone(bot: TheGameBot, user):
    dt = await bot.localize_datetime(user, BASE_DATETIME)
    return dt.tzinfo if dt.tzinfo != datetime.timezone.utc else None


async def set_user_timezone(
    bot: TheGameBot, user_id: int, timezone: datetime.tzinfo = None
):
    async with bot.db.connect(writing=True) as conn:
        query = """
        INSERT INTO user (user_id, timezone) VALUES (?, ?)
        ON CONFLICT (user_id) DO UPDATE SET timezone = ?
        """
        timezone_str = str(timezone) if timezone is not None else None
        await conn.execute(query, user_id, timezone_str, timezone_str)


class Timezone(app_commands.Group):
    """Commands related to timezones and management of your timezone."""

    def __init__(self, bot: TheGameBot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @app_commands.command(name='map')
    async def _map(self, interaction: discord.Interaction):
        """Links to a handy timezone picker for finding different timezones."""
        await interaction.response.send_message(
            '<https://kevinnovak.github.io/Time-Zone-Picker/>',
            ephemeral=True
        )

    @app_commands.command()
    @app_commands.describe(
        timezone='The timezone to check. Defaults to your set timezone if any.'
    )
    async def show(
        self, interaction: discord.Interaction,
        timezone: app_commands.Transform[zoneinfo.ZoneInfo, TimezoneTransformer] = None
    ):
        """Check the current time in a timezone."""
        defaulted = timezone is None
        if defaulted:
            timezone = await get_timezone(self.bot, interaction.user.id)
            if timezone is None:
                return await interaction.response.send_message(
                    'You do not have a timezone set. Please specify a timezone '
                    'or set your own timezone using `/timezone set`.',
                    ephemeral=True
                )

        now = datetime.datetime.now(timezone)
        content = 'The current time in {ref} timezone `{tz}` is:\n{dt}'

        await interaction.response.send_message(
            content.format(
                ref='your' if defaulted else 'the',
                tz=str(timezone),
                dt=now.strftime('%A, %B %d %Y %H:%M:%S (%z)')
            ),
            ephemeral=True
        )

    @app_commands.command()
    @app_commands.describe(
        timezone='The timezone you want to use. If not provided '
                 'your currently set timezone will be removed.'
    )
    async def set(
        self, interaction: discord.Interaction,
        timezone: app_commands.Transform[zoneinfo.ZoneInfo, TimezoneTransformer] = None
    ):
        """Update your timezone preference. Certain commands can benefit from this, e.g. inputting dates."""
        last_timezone = await get_timezone(self.bot, interaction.user.id)

        if timezone is None and last_timezone is None:
            return await interaction.response.send_message(
                'You do not have any timezone currently set.',
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        await set_user_timezone(self.bot, interaction.user.id, timezone)

        if timezone is None:
            content = 'Your timezone preference has been cleared!'
        elif last_timezone is None:
            content = 'Successfully set your new timezone!'
        else:
            content = 'Successfully replaced your timezone!'

        return await interaction.followup.send(content, ephemeral=True)


async def setup(bot: TheGameBot):
    bot.tree.add_command(Timezone(bot))

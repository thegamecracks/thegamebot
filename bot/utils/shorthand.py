#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import contextlib

import discord
from discord.ext import commands


def get_bot_color(bot: commands.Bot):
    """Return the bot's color from settings."""
    return int(bot.get_cog('Settings').get('bot_color'), 16)


def get_user_color(bot, user, default_color=None):
    """Return a user's role color if they are in a guild."""
    return (
        user.color if isinstance(user, discord.Member)
        else default_color if default_color is not None
        else get_bot_color(bot)
    )


def iterable_has(iterable, *args):
    """Used for parsing *args in commands."""
    return any(s in iterable for s in args)


@contextlib.contextmanager
def update_text(before, after):
    """A context manager for printing one line of text and at the end,
    writing over it."""
    after += ' ' * (len(before) - len(after))
    try:
        yield print(before, end='\r', flush=True)
    finally:
        print(after)

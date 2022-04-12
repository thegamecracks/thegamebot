#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import argparse
import shlex

import discord

from .confirmation import *
from .dt import *
from .formatting import *
from . import paging


class RaisingArgumentParser(argparse.ArgumentParser):
    """A subclass of argparse.ArgumentParser that raises a RuntimeError
    when it fails to parse, rather than exiting the program.
    """
    def split_and_parse(self, args: str):
        """Convenience method for splitting a string before parsing it."""
        args = shlex.split(args)
        return self.parse_args(args)

    def error(self, message):
        raise RuntimeError(message)


class MockMessage:
    """A mock message object sufficient for most cooldown BucketTypes.

    BucketTypes supported:
        default (technically you don't need a message at all for this)
        user
        guild (guild parameter is still optional)
        channel (channel required)
        member (guild optional)
        category (channel required)
        role (author must be Member if channel is not DM)
        """
    def __init__(
        self, author,
        *, channel: discord.TextChannel = None,
        guild: discord.Guild = None
    ):
        self.author = author
        self.channel = channel
        self.guild = guild


async def getch_member(guild: discord.Guild, member_id: int):
    member = guild.get_member(member_id)
    if member is None:
        try:
            return await guild.fetch_member(member_id)
        except discord.HTTPException:
            pass
    return member

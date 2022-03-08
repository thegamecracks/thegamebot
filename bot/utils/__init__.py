#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import discord

from .arithmetic import *
from .dt import *
from .exceptions import *
from .files import *
from .formatting import *
from .money import *
from .parsing import *
from .shorthand import *


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
    def __init__(self, author, *, channel: discord.TextChannel = None,
                 guild: discord.Guild = None):
        self.author = author
        self.channel = channel
        self.guild = guild

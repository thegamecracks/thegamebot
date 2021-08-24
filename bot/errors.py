#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
from discord.ext import commands


class SkipInteractionResponse(Exception):
    """Raised during user-made button callbacks when the interaction
    should not be deferred."""


class ErrorHandlerResponse(commands.CommandError):
    """An exception with a message that the error handler should
    always send to the user."""


class DollarInputError(commands.BadArgument, ErrorHandlerResponse):
    """An invalid input was given while converting dollars."""
    def __init__(self, reason, argument):
        self.reason = reason
        self.argument = argument


class IndexOutOfBoundsError(commands.BadArgument, ErrorHandlerResponse):
    """An index given by the user was out of bounds."""


class UnknownTimezoneError(commands.BadArgument):
    """An invalid input was given while converting to a timezone."""
    def __init__(self, argument):
        self.argument = argument


class SettingsNotFound(Exception):
    """The Settings cog could not be loaded."""

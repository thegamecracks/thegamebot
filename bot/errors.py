from discord.ext import commands


class ErrorHandlerResponse(commands.CommandError):
    """An exception with a message that the error handler should
    always send to the user."""


class DollarInputError(commands.UserInputError, ErrorHandlerResponse):
    """An invalid input was given while converting dollars."""
    def __init__(self, reason, argument):
        self.reason = reason
        self.argument = argument


class IndexOutOfBoundsError(commands.UserInputError, ErrorHandlerResponse):
    """An index given by the user was out of bounds."""


class UnknownTimezoneError(commands.UserInputError):
    """An invalid input was given while converting to a timezone."""
    def __init__(self, argument):
        self.argument = argument


class SettingsNotFound(Exception):
    """The Settings cog could not be loaded."""

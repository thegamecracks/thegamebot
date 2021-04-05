from discord.ext import commands


class DollarInputError(commands.UserInputError):
    """An invalid input was given while converting dollars."""
    def __init__(self, reason, argument):
        self.reason = reason
        self.argument = argument


class UnknownTimezoneError(commands.UserInputError):
    """An invalid input was given while converting to a timezone."""
    def __init__(self, argument):
        self.argument = argument


class SettingsNotFound(Exception):
    """The Settings cog could not be loaded."""

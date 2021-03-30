from discord.ext import commands


class DollarInputError(commands.UserInputError):
    """An invalid input was given while converting dollars."""

class SettingsNotFound(Exception):
    """The Settings cog could not be loaded."""

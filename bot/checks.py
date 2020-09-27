from discord.ext import commands

from bot import settings


# Errors
class InvalidIdentification(commands.CheckFailure):
    """The base class for invalid identifications."""


class InvalidBotOwner(InvalidIdentification):
    """Raised when a command requires the user to be in OWNER_IDS."""


class InvalidBotAdmin(InvalidIdentification):
    """Raised when a command requires the user to be in ADMIN_IDS."""


# Checks
def is_bot_admin():
    async def predicate(ctx):
        if ctx.author.id in settings.get_setting('admin_ids'):
            return True
        else:
            raise InvalidBotAdmin
    return commands.check(predicate)


def is_bot_owner():
    async def predicate(ctx):
        if ctx.author.id in settings.get_setting('owner_ids'):
            return True
        else:
            raise InvalidBotOwner
    return commands.check(predicate)

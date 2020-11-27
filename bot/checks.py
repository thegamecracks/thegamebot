import collections

from discord.ext import commands

from bot import settings

COMMAND_COOLDOWN_SETTINGS = (15, 42, commands.BucketType.user)

global_checks_wrapped = [
    'command_cooldown',
]

GlobalCheckPredicate = collections.namedtuple(
    'GlobalCheckPredicate', ['predicate', 'call_once'],
    defaults={'call_once': False}
)


# Errors
class UserOnCooldown(commands.CheckFailure):
    """Raised when a user has invoked too many commands
    and is being ratelimited."""
    __slots__ = ('retry_after',)

    def __init__(self, retry_after, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after


class InvalidIdentification(commands.CheckFailure):
    """The base class for invalid identifications."""


class InvalidBotOwner(InvalidIdentification):
    """Raised when a command requires the user to be in OWNER_IDS."""


class InvalidBotAdmin(InvalidIdentification):
    """Raised when a command requires the user to be in ADMIN_IDS."""


# Global checks
def command_cooldown(bot):
    mapping = commands.CooldownMapping.from_cooldown(
        *COMMAND_COOLDOWN_SETTINGS)

    async def predicate(ctx):
        bucket = mapping.get_bucket(ctx.message)
        if bucket.update_rate_limit():
            # user is rate limited
            raise UserOnCooldown(
                bucket.get_retry_after(),
                'User is using commands too frequently.'
            )
        return True

    return GlobalCheckPredicate(predicate, call_once=True)


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


def setup(bot):
    for check in global_checks_wrapped:
        predicate, call_once = globals()[check](bot)
        bot.add_check(predicate, call_once=call_once)

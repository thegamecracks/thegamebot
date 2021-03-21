import collections

from discord.ext import commands


# Errors
class UserOnCooldown(commands.CommandError):
    """Raised when a user has invoked too many commands
    and is being globally ratelimited."""
    __slots__ = ('retry_after',)

    def __init__(self, retry_after, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after


# Checks
def is_in_guild(guild_id):
    async def predicate(ctx):
        guild = ctx.bot.get_guild(guild_id)
        if guild is None:
            return False

        return guild.get_member(ctx.author.id) is not None

    return commands.check(predicate)


class Checks(commands.Cog):
    """Global bot checks."""

    GLOBAL_COOLDOWN_SETTINGS = (15, 60, commands.BucketType.user)

    def __init__(self, bot, *, global_cooldown_settings=None):
        """
        Args:
            bot (commands.Bot): The discord bot.
            global_cooldown_settings (Optional[Tuple[int, int, commands.BucketType]]):
                The settings to use for the global cooldown (rate, per, type).
                Defaults to self.GLOBAL_COOLDOWN_SETTINGS.

        """
        self.bot = bot

        if global_cooldown_settings is None:
            global_cooldown_settings = self.GLOBAL_COOLDOWN_SETTINGS
        self.global_cooldown = commands.CooldownMapping.from_cooldown(
            *global_cooldown_settings)

    def bot_check_once(self, ctx):
        # Global cooldown
        bucket = self.global_cooldown.get_bucket(ctx.message)
        if bucket.update_rate_limit():
            raise UserOnCooldown(
                bucket.get_retry_after(),
                'User is using commands too frequently.'
            )

        return True


def setup(bot):
    bot.add_cog(Checks(bot))

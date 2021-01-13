# TODO: remove guild from database when removed
import discord
from discord.ext import commands
import inflect

from bot.database import PrefixDatabase
from bot import utils

inflector = inflect.engine()


def bot_owner_or_has_guild_permissions(**perms):
    original = commands.has_guild_permissions(**perms).predicate
    async def extended_check(ctx):
        if ctx.guild is None:
            return False
        return await original(ctx) or await ctx.bot.is_owner(ctx.author)
    return commands.check(extended_check)


class Prefix(commands.Cog):
    qualified_name = 'Prefix'
    description = "Commands for changing the bot's prefix."

    def __init__(self, bot):
        self.bot = bot
        self.prefixdb = PrefixDatabase
        self.mention_prefix_cooldown = commands.CooldownMapping.from_cooldown(
            1, 15, commands.BucketType.member)





    @commands.Cog.listener()
    async def on_message(self, message):
        "Send the bot's prefix if mentioned."
        def list_discard(seq, value):
            try:
                seq.remove(value)
            except ValueError:
                pass

        # Ignore messages that are from bot or didn't mention the bot
        if self.bot.user not in message.mentions:
            return
        if message.author == self.bot.user:
            return

        bot_mentions = (f'<@{self.bot.user.id}>', f'<@!{self.bot.user.id}>')

        # Ignore proper/invalid command invokations
        # ctx = await self.bot.get_context(message)
        # if ctx.valid:
        #     return
        if message.content not in bot_mentions:
            return

        # Check cooldown
        if self.mention_prefix_cooldown.update_rate_limit(message):
            return

        # Get prefix(es)
        prefix = await self.bot.get_prefix(message)

        if isinstance(prefix, str):
            prefix = [prefix]
        else:
            # Remove bot mentions in the prefixes
            for mention in bot_mentions:
                list_discard(prefix, mention + ' ')

        # Send available prefix(es)
        if len(prefix) == 1:
            await message.channel.send(f'My prefix here is "{prefix[0]}".')
        else:
            await message.channel.send('My prefixes here are {}.'.format(
                inflector.join([f'"{p}"' for p in prefix]))
            )





    @commands.command(name='changeprefix')
    @bot_owner_or_has_guild_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.cooldown(2, 30, commands.BucketType.guild)
    async def client_changeprefix(self, ctx, prefix):
        """Change the bot's prefix.

For prefixes ending with a space or multi-word prefixes, specify it with double quotes:
<command> "myprefix " """
        prefix = prefix.lstrip()

        if not prefix:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                'An empty prefix is not allowed.', delete_after=6)

        await ctx.trigger_typing()

        current_prefix = (
            await self.prefixdb.get_prefix(ctx.guild.id)
        )

        if prefix == current_prefix:
            await ctx.send('That is already the current prefix.',
                           delete_after=6)
        else:
            # Escape escape characters before printing
            clean_prefix = prefix.replace('\\', r'\\')
            await self.prefixdb.update_prefix(ctx.guild.id, prefix)
            await ctx.send(
                f'Successfully changed prefix to: "{clean_prefix}"')


    @client_changeprefix.error
    async def client_changeprefix_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, ValueError):
            # Prefix is too long
            await ctx.send(str(error))










def setup(bot):
    bot.add_cog(Prefix(bot))

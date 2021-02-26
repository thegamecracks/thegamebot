import asyncio
import calendar
import random
import time
from typing import Union

import discord
from discord.ext import commands

from bot.classes.confirmation import AdaptiveConfirmation
from bot import utils

WORDLIST_PATH = 'data/wordlist.txt'

# goodday command
CLIENT_GOODDAY_VARS = {
    'nightmessage': 'Have a good night.',
    'morningmessage': 'Have a good morning.',
    'afternoonmessage': 'Have a good afternoon.',
    'eveningmessage': 'Have a good evening.',
    'night': 4,
    'morning': 11,
    'afternoon': 16,
    'evening': 22,
    'firstday': calendar.SUNDAY
}

# detectenglish command
with open(WORDLIST_PATH) as f:
    WORDLIST = set(f.read().split())


# upsidedown text command
# sources: https://www.upsidedowntext.com/unicode
#          https://text-symbols.com/upside-down/
UPSIDEDOWN_MAPPING = {
    'a': 'ɐ', 'b': 'q', 'c': 'ɔ', 'd': 'p', 'e': 'ǝ',
    'f': 'ɟ', 'g': 'ƃ', 'h': 'ɥ', 'i': 'ᴉ', 'j': 'ɾ',
    'k': 'ʞ', 'l': 'l', 'm': 'ɯ', 'n': 'u', 'o': 'o',
    'p': 'd', 'q': 'b', 'r': 'ɹ', 's': 's', 't': 'ʇ',
    'u': 'n', 'v': 'ʌ', 'w': 'ʍ', 'x': 'x', 'y': 'ʎ',
    'z': 'z', 'A': '∀', 'B': 'ꓭ', 'C': 'Ɔ', 'D': 'ᗡ',
    'E': 'Ǝ', 'F': 'Ⅎ', 'G': 'פ', 'H': 'H', 'I': 'I',
    'J': 'ᒋ', 'K': 'ꓘ', 'L': '⅂', 'M': 'W', 'N': 'N',
    'O': 'O', 'P': 'Ԁ', 'Q': 'Ꝺ', 'R': 'ꓤ', 'S': 'S',
    'T': 'ꓕ', 'U': '∩', 'V': 'Ʌ', 'W': 'M', 'X': 'X',
    'Y': '⅄', 'Z': 'Z', '0': '0', '1': '⇂', '2': '↊',
    '3': 'Ɛ', '4': 'ߤ', '5': 'ϛ', '6': '9', '7': '𝘓',
    '8': '9', '9': '6', '"': ',,', "'": ',', '`': ',',
    '(': ')', ')': '(', '[': ']', ']': '[', '{': '}',
    '}': '{', '<': '>', '>': '<', '&': '⅋', '_': '‾',
    ',': '`', '.': '˙', '!': '¡', '?': '¿'
}


# dmtest/test command
def generate_test_message():
    kwargs = {
        'made': random.choice(('designed', 'designated', 'made', 'meant')),
        'testing1': random.choice((
            'administrative',
            'executive',
            'high-level',
            'official'
        )),
        'testing2': random.choice((
            'certifying',
            'validative',
            'legitimizing',
            'testing'
        )),
        'testing3': random.choice((
            'analysis',
            'experimentation',
            'verification'
        )),
        'input': random.choice((
            'manual connection',
            'electronically delivered input',
            'wirelessly transmitted signal'
        )),
        'from': random.choice((
            'derivative of',
            'deriving out of',
            'in accordance with',
        )),
        'user1': random.choice(('leading', 'primary')),
        'user2': random.choice(('expert', 'specialist'))
    }

    return (
        'This command is {made} for {testing1} {testing2} {testing3} via '
        '{input} {from} the {user1} {user2}.'.format(**kwargs)
    )


class Undefined(commands.Cog):
    """Uncategorized commands."""
    qualified_name = 'Undefined'

    def __init__(self, bot):
        self.bot = bot





    @commands.command(name='dmtest')
    @commands.cooldown(2, 30, commands.BucketType.user)
    async def client_dmtest(self, ctx):
        await ctx.author.send(generate_test_message())





    @commands.command(
        name='detectenglish',
        aliases=('isenglish', 'english'))
    @commands.cooldown(3, 10, commands.BucketType.member)
    async def client_english(self, ctx, word: str):
        """Determines if a word is english.

Dictionary comes from dwyl/english-words github."""
        if word.lower() in WORDLIST:
            await ctx.send(f'{word} is a word.')
        else:
            await ctx.send(f'{word} is not a word.')






    @commands.command(name='getlastmessage')
    @commands.cooldown(2, 10, commands.BucketType.channel)
    async def client_getlastmessage(self, ctx, channel: discord.TextChannel):
        """Get the last message of a text channel.
Not for sniping.

This command was written as an answer to:
https://stackoverflow.com/q/64080277/"""
        message = await channel.fetch_message(channel.last_message_id)
        # NOTE: channel.last_message_id could return None; needs a check

        await ctx.send(
            f'Last message in {channel.name} sent by {message.author.name}:\n'
            + message.clean_content
        )






    @commands.command(
        name='goodday',
        aliases=('gooday', 'gday'))
    @commands.cooldown(1, 40, commands.BucketType.channel)
    async def client_goodday(self, ctx):
        """Prints the time, date, and a good day message."""
        await ctx.channel.trigger_typing()

        time_local = time.localtime()
        text_calendar = calendar.TextCalendar(CLIENT_GOODDAY_VARS['firstday'])
        year, month = time_local.tm_year, time_local.tm_mon
        month_day, hour = time_local.tm_mday, time_local.tm_hour

        # Show time
        await ctx.send(time.strftime(
            'My time is %X %zUTC, or %I:%M %p.', time_local))
        await ctx.channel.trigger_typing()
        await asyncio.sleep(2)

        # Show date, and the monthly calendar in a code block
        date = time.strftime(
            'The date is %A, %B %d, %Y.', time_local) \
            + ' ```diff\n'  # use Diff formatting
        month = text_calendar.formatmonth(year, month)
        # Ignore first line of formatmonth(), which is the month and year
        month = month[month.index('\n') + 1:]
        # Add hashtag on the corresponding week for markdown formatting
        month = month.split('\n')
        found = False  # To optimize for-loop
        for i, line in enumerate(month):
            if found or line.find(str(month_day)) == -1:
                # Day not found; add padding
                month[i] = '  ' + line
            else:
                # Day found; add highlighting and pad the rest of the lines
                month[i] = '+ ' + line
                found = True
        month = '\n'.join(month).rstrip()  # Remove trailing newline

        date += month + '```'
        await ctx.send(date)

        await ctx.channel.trigger_typing()
        await asyncio.sleep(3)
        # Print goodday message
        if hour >= CLIENT_GOODDAY_VARS['evening'] \
           or hour <= CLIENT_GOODDAY_VARS['night']:
            await ctx.send(CLIENT_GOODDAY_VARS['nightmessage'])
        elif hour <= CLIENT_GOODDAY_VARS['morning']:
            await ctx.send(CLIENT_GOODDAY_VARS['morningmessage'])
        elif hour <= CLIENT_GOODDAY_VARS['afternoon']:
            await ctx.send(CLIENT_GOODDAY_VARS['afternoonmessage'])
        elif hour <= CLIENT_GOODDAY_VARS['evening']:
            await ctx.send(CLIENT_GOODDAY_VARS['eveningmessage'])





    @commands.command(name='leave')
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.cooldown(2, 60, commands.BucketType.guild)
    async def client_leave(self, ctx):
        """Ask the bot to leave.

This will remove data about your server but not any associated user
information such as notes or game scores."""
        prompt = AdaptiveConfirmation(ctx, utils.get_bot_color())

        confirmed = await prompt.confirm('Are you sure you want me to leave?')

        if confirmed:
            await prompt.update('Goodbye world!', prompt.emoji_no.color)
            await ctx.guild.leave()
            # TODO: remove user information after some time
            await self.bot.dbguilds.remove_guild(ctx.guild.id)
        else:
            await prompt.update('Thanks for keeping me along!',
                                prompt.emoji_yes.color)





    @commands.command(name='test')
    @commands.cooldown(2, 30, commands.BucketType.user)
    async def client_test(self, ctx):
        await ctx.send(generate_test_message())





    @commands.command(name='rotate', aliases=('flip', 'upsidedown'))
    @commands.cooldown(4, 10, commands.BucketType.user)
    async def client_upsidedowntext(self, ctx, *, message):
        """Rotate your text 180 degrees using unicode letters.
Supports a-z 0-9 ,.!?"'` ()[]{}<> and &_.
Any other characters will be passed through."""
        s = []
        for c in reversed(message):
            s.append(UPSIDEDOWN_MAPPING.get(c, c))
        s = ''.join(s)
        await ctx.send(s)










def setup(bot):
    bot.add_cog(Undefined(bot))

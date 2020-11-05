import asyncio
import calendar
import time

import discord
from discord.ext import commands

from bot import utils

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
with open('data/wordlist.txt') as f:
    WORDLIST = set(f.read().split())


class Undefined(commands.Cog):
    qualified_name = 'Undefined'
    description = 'Uncategorized commands.'

    def __init__(self, bot):
        self.bot = bot





    @commands.command(
        name='dmtest')
    @commands.cooldown(2, 30, commands.BucketType.user)
    async def client_dmtest(self, ctx):
        await ctx.author.send(
            'This command is designated for administrative validative \
analysis via manual connection deriving out of the primary specialist.')






    @commands.command(
        name='echo',
        aliases=('say',))
    @commands.cooldown(3, 15, commands.BucketType.user)
    async def client_echo(self, ctx, *, content):
        """Repeats what you say."""
        await ctx.send(discord.utils.escape_mentions(content))





    @commands.command(
        name='detectenglish',
        brief='Detects if a word is probably english.',
        aliases=('isenglish', 'english'))
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_english(self, ctx, word: str):
        """Goes through a list of words and checks if the given word is in it.

List of words comes from dwyl/english-words github."""
        if word.lower() in WORDLIST:
            await ctx.send(f'{word} is a word.')
        else:
            await ctx.send(f'{word} is not a word.')






    @commands.command(
        name='getlastmessage')
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_getlastmessage(self, ctx, ID):
        """Get the last message of a text channel.

This command was written as an answer to:
https://stackoverflow.com/q/64080277/"""
        channel = self.bot.get_channel(int(ID))
        if channel is None:
            return await ctx.send('Could not find that channel.')
        elif not isinstance(channel, discord.TextChannel):
            # NOTE: get_channel can return a TextChannel, VoiceChannel,
            # or CategoryChannel
            return await ctx.send('The channel must be a text channel.')

        message = await channel.fetch_message(
            channel.last_message_id)
        # NOTE: channel.last_message_id could return None; needs a check

        await ctx.send(
            f'Last message in {channel.name} sent by {message.author.name}:\n'
            + message.clean_content
        )






    @commands.command(
        name='goodday',
        aliases=('gooday', 'gday'))
    @commands.cooldown(1, 30, commands.BucketType.channel)
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
           or hour <= CLIENT_GOODDAY_VARS['night']: await ctx.send(
            CLIENT_GOODDAY_VARS['nightmessage'])
        elif hour <= CLIENT_GOODDAY_VARS['morning']: await ctx.send(
            CLIENT_GOODDAY_VARS['morningmessage'])
        elif hour <= CLIENT_GOODDAY_VARS['afternoon']: await ctx.send(
            CLIENT_GOODDAY_VARS['afternoonmessage'])
        elif hour <= CLIENT_GOODDAY_VARS['evening']: await ctx.send(
            CLIENT_GOODDAY_VARS['eveningmessage'])





    @commands.command(
        name='test')
    @commands.cooldown(2, 30, commands.BucketType.user)
    async def client_test(self, ctx):
        await ctx.send(
            'This command is designated for administrative validative \
analysis via manual connection deriving out of the primary specialist.')





    @commands.command(name='utctime', aliases=['utc'])
    @commands.cooldown(3, 15, commands.BucketType.user)
    async def client_timeutc(self, ctx):
        """Get the current date and time in UTC."""
        await ctx.send(time.asctime(time.gmtime()) + ' (UTC)')










def setup(bot):
    bot.add_cog(Undefined(bot))

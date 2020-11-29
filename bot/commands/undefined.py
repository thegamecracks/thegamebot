import asyncio
import calendar
import collections
import csv
import random
import time

import discord
from discord.ext import commands
import inflect

from bot import settings
from bot import utils

inflector = inflect.engine()

get_bot_color = lambda: int(settings.get_setting('bot_color'), 16)

WORDLIST_PATH = 'data/wordlist.txt'
UNTURNED_ITEM_IDS_PATH = 'data/unturned_item_ids.csv'

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


# phasmophobia commands
class Ghost:
    __slots__ = ('name', 'evidences', 'url')

    def __init__(self, name, evidences, url):
        self.name = name
        self.evidences = evidences
        self.url = url


GHOST_EVIDENCE = [
    Ghost('Banshee',
          ('EMF Level 5', 'Fingerprints', 'Freezing Temperatures'),
          'https://phasmophobia.fandom.com/wiki/Banshee'),
    Ghost('Demon',
          ('Freezing Temperatures', 'Ghost Writing', 'Spirit Box'),
          'https://phasmophobia.fandom.com/wiki/Demon'),
    Ghost('Jinn',
          ('EMF Level 5', 'Ghost Orb', 'Spirit Box'),
          'https://phasmophobia.fandom.com/wiki/Jinn'),
    Ghost('Mare',
          ('Freezing Temperatures', 'Ghost Orb', 'Spirit Box'),
          'https://phasmophobia.fandom.com/wiki/Mare'),
    Ghost('Oni',
          ('EMF Level 5', 'Ghost Writing', 'Spirit Box'),
          'https://phasmophobia.fandom.com/wiki/Oni'),
    Ghost('Phantom',
          ('EMF Level 5', 'Freezing Temperatures', 'Ghost Orb'),
          'https://phasmophobia.fandom.com/wiki/Phantom'),
    Ghost('Poltergeist',
          ('Fingerprints', 'Ghost Orb', 'Spirit Box'),
          'https://phasmophobia.fandom.com/wiki/Poltergeist'),
    Ghost('Revenant',
          ('EMF Level 5', 'Fingerprints', 'Ghost Writing'),
          'https://phasmophobia.fandom.com/wiki/Revenant'),
    Ghost('Shade',
          ('EMF Level 5', 'Ghost Orb', 'Ghost Writing'),
          'https://phasmophobia.fandom.com/wiki/Shade'),
    Ghost('Spirit',
          ('Fingerprints', 'Ghost Writing', 'Spirit Box'),
          'https://phasmophobia.fandom.com/wiki/Spirit'),
    Ghost('Wraith',
          ('Fingerprints', 'Freezing Temperatures', 'Spirit Box'),
          'https://phasmophobia.fandom.com/wiki/Wraith'),
    Ghost('Yurei',
          ('Freezing Temperatures', 'Ghost Orb', 'Ghost Writing'),
          'https://phasmophobia.fandom.com/wiki/Yurei')
]
EVIDENCES = [
    'EMF Level 5', 'Freezing Temperatures', 'Fingerprints',
    'Ghost Orb', 'Ghost Writing', 'Spirit Box'
]


def phasmophobia_match_ghost_evidence(evidences):
    possible_ghosts = GHOST_EVIDENCE

    for e in evidences:
        new_ghosts = []

        for g in possible_ghosts:
            if e.lower() in [gev.lower() for gev in g.evidences]:
                new_ghosts.append(g)

        possible_ghosts = new_ghosts

        if len(possible_ghosts) == 0:
            return possible_ghosts

    return possible_ghosts


# unturned commands
UNTURNED_ITEM_IDS = {}
UnturnedItem = collections.namedtuple(
    'UnturnedItem', ['id', 'name', 'rarity', 'url'])
with open(UNTURNED_ITEM_IDS_PATH) as f:
    reader = csv.reader(f)
    header = next(reader)
    for id_, name, rarity, url in reader:
        id_ = int(id_)
        UNTURNED_ITEM_IDS[id_] = UnturnedItem(id_, name, rarity, url)
del reader, header, id_, name, rarity


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
    qualified_name = 'Undefined'
    description = 'Uncategorized commands.'

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
    async def client_getlastmessage(self, ctx, ID):
        """Get the last message of a text channel.
Not for sniping.

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
           or hour <= CLIENT_GOODDAY_VARS['night']: await ctx.send(
            CLIENT_GOODDAY_VARS['nightmessage'])
        elif hour <= CLIENT_GOODDAY_VARS['morning']: await ctx.send(
            CLIENT_GOODDAY_VARS['morningmessage'])
        elif hour <= CLIENT_GOODDAY_VARS['afternoon']: await ctx.send(
            CLIENT_GOODDAY_VARS['afternoonmessage'])
        elif hour <= CLIENT_GOODDAY_VARS['evening']: await ctx.send(
            CLIENT_GOODDAY_VARS['eveningmessage'])





    @commands.group(name='phasmophobia', invoke_without_command=True)
    async def client_phasmophobia(self, ctx):
        """Commands related to the game Phasmophobia."""


    @client_phasmophobia.command(name='evidence')
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_phasmophobia_ghost_evidence(self, ctx, *, evidences):
        """Determine the ghost(s) based on evidence.
Example usage:
    <command> emf level 5, fingerprints, freezing temp
Available evidences:
EMF Level 5
Freezing Temperatures
Fingerprints
Ghost Orb
Ghost Writing
Spirit Box"""
        def show_evidence(evidences, has_corrected):
            if not has_corrected:
                return ''
            return f" ({', '.join(evidences)})"

        evidences = [s.strip() for s in evidences.split(',') if s.strip()]

        # Fuzzy match the evidence
        corrected_evidence = False
        for i, e in enumerate(evidences):
            match = utils.fuzzy_match_word(e, EVIDENCES)
            if not match:
                return await ctx.send(f'Unknown evidence: "{e}"')
            elif match == e:
                continue
            evidences[i] = match
            corrected_evidence = True

        # Determine ghosts
        ghosts = phasmophobia_match_ghost_evidence(evidences)

        title = None
        embed = None
        if not ghosts:
            title = 'No ghosts match the given evidence{}.'.format(
                show_evidence(evidences, corrected_evidence)
            )
        elif len(ghosts) == 1:
            title = 'One ghost matches the given evidence{}:'.format(
                show_evidence(evidences, corrected_evidence)
            )

            g = ghosts[0]
            embed = discord.Embed(
                description='[{}]({})'.format(g.name, g.url),
                color=get_bot_color()
            )
        else:
            title = '{} ghosts match the given evidence{}:'.format(
                inflector.number_to_words(
                    len(ghosts), threshold=10).capitalize(),
                show_evidence(evidences, corrected_evidence)
            )

            embed = discord.Embed(
                description='\n'.join([
                    '[{}]({}) ({})'.format(
                        g.name, g.url, ', '.join(g.evidences))
                    for g in ghosts
                ]),
                color=get_bot_color()
            )

        await ctx.send(title, embed=embed)





    @commands.command(name='test')
    @commands.cooldown(2, 30, commands.BucketType.user)
    async def client_test(self, ctx):
        await ctx.send(generate_test_message())





    @commands.group(name='unturned', invoke_without_command=True)
    async def client_unturned(self, ctx):
        """Commands related to the game Unturned."""


    @client_unturned.command(name='item')
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_unturned_item(self, ctx, *, item):
        """Search for an Unturned item by ID or name.
Information was pre-scraped from https://unturneditems.com/.
Up to date as of 3.20.15.0."""
        def get_item_by_name(name):
            result = discord.utils.get(UNTURNED_ITEM_IDS.values(), name=name)
            if result is None:
                raise ValueError(f'Could not find {name!r}')
            return result

        def item_embed(entry):
            id_, name, rarity, url = (entry.id, entry.name,
                                      entry.rarity, entry.url)

            return discord.Embed(
                color=(  0x777777 if rarity == 'Common'
                    else 0x71BA51 if rarity == 'Uncommon'
                    else 0x3D8EB9 if rarity == 'Rare'
                    else 0x8870FF if rarity == 'Epic'
                    else 0xD33257 if rarity == 'Legendary'
                    else 0x637C63
                ),
                description=(
                    f'[{name}]({url})\n'
                    f'ID: {id_}\n'
                    f'Rarity: {rarity}'
                )
            )

        # Search by ID
        try:
            item_id = int(item)
        except ValueError:
            pass
        else:
            entry = UNTURNED_ITEM_IDS.get(item_id)

            if entry is None:
                return await ctx.send('Could not find an item with that ID.')

            return await ctx.send(embed=item_embed(entry))

        # Search by name
        result = utils.fuzzy_match_word(
            item, tuple(entry.name for entry in UNTURNED_ITEM_IDS.values()),
            return_possible=True
        )

        if isinstance(result, str):
            entry = get_item_by_name(result)
            await ctx.send(embed=item_embed(entry))
        elif not result:
            await ctx.send('Could not find an item with that name.')
        elif len(result) > 1:
            # Get the first 5 results and convert to UnturnedItem,
            # then list the possible matches
            too_many_results = len(results) > 5
            result = [get_item_by_name(name) for name in result[:5]]

            description = '\n'.join([entry.name for entry in results])
            if too_many_results:
                description += '\n...'

            embed = discord.Embed(
                color=get_bot_color(),
                description=description
            )

            await ctx.send('Multiple items were matched:', embed=embed)











def setup(bot):
    bot.add_cog(Undefined(bot))

import asyncio
import calendar
import collections
from concurrent.futures import ThreadPoolExecutor
import csv
import json
import math
import random
import time
import typing

import discord
from discord.ext import commands
import inflect

from bot import checks
from bot import settings
from bot import utils

inflector = inflect.engine()

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


# unturned commands
class UnturnedItem:
    __slots__ = ('id', 'name', 'rarity', 'url', 'dimensions', 'recipe_data')

    def __init__(self, id_, name, rarity, url, dimensions, recipe_data):
        self.id = id_
        self.name = name
        self.rarity = rarity
        self.url = url
        self.dimensions = dimensions
        self.recipe_data = recipe_data

    def __repr__(self):
        return '{}({!r}, {!r})'.format(
            self.__class__.__name__,
            self.id,
            self.name
        )


class UnturnedDatabase:
    UNTURNED_ITEM_IDS_PATH = 'data/unturned_item_ids.csv'
    UNTURNED_ITEM_RECIPES_PATH = 'data/unturned_recipes.json'

    def __init__(self, items):
        self.items = items

    @classmethod
    def _get_items_from_files(cls):
        with open(cls.UNTURNED_ITEM_RECIPES_PATH) as f:
            recipes = json.load(f)

        items = {}
        with open(cls.UNTURNED_ITEM_IDS_PATH) as f:
            reader = csv.reader(f)
            header = next(reader)
            for id_, name, rarity, url in reader:
                rec = recipes.get(id_)
                dimensions = rec['dimensions'] if rec else None
                recipe_data = (
                    {'primitive': rec['primitive'],
                     'recipes': rec['recipes']}
                    if rec else None
                )
                id_ = int(id_)
                items[id_] = UnturnedItem(
                    id_, name, rarity, url, dimensions, recipe_data)

        return items

    @classmethod
    async def _get_items_from_files_nonblocking(cls):
        executor = ThreadPoolExecutor()
        loop = asyncio.get_running_loop()

        with open(cls.UNTURNED_ITEM_RECIPES_PATH) as f:
            recipes = json.loads(await loop.run_in_executor(executor, f.read))

        with open(cls.UNTURNED_ITEM_IDS_PATH) as f:
            raw_lines = await loop.run_in_executor(executor, f.readlines)

        items = {}
        reader = csv.reader(raw_lines)
        next(reader)  # skip header

        for ID, name, rarity, url in reader:
            rec = recipes.get(ID)
            dimensions = rec['dimensions'] if rec else None
            recipe_data = (
                {'primitive': rec['primitive'],
                 'recipes': rec['recipes']}
                if rec else None
            )

            ID = int(ID)
            items[ID] = UnturnedItem(ID, name, rarity, url,
                                     dimensions, recipe_data)

        return items

    def reload_items(self):
        """Regenerate self.items from the data files."""
        self.items = self._get_items_from_files()

    async def reload_items_nonblocking(self):
        """Regenerate self.items from the data files.
        Uses a thread pool to read files."""
        self.items = await self._get_items_from_files_nonblocking()

    def unturned_get_item(self, search):
        """Search for an item from UNTURNED_ITEM_IDS either by name or ID.

        Returns:
            List[UnturnedItem]: multiple matches were found.
            None: no matches were found.
            UnturnedItem: the search term matches one item.

        """
        def get_item_by_name(name):
            result = discord.utils.get(self.items.values(), name=name)
            if result is None:
                raise ValueError(f'Could not find an item with that name.')
            return result

        # Search by ID
        try:
            item_id = int(search)
        except ValueError:
            pass
        else:
            return self.items.get(item_id)

        # Search by name
        result = utils.fuzzy_match_word(
            search, tuple(entry.name for entry in self.items.values()),
            return_possible=True
        )

        if isinstance(result, str):
            return get_item_by_name(result)
        elif isinstance(result, collections.abc.Iterable):
            return [get_item_by_name(name) for name in result]
        elif result is None:
            return

    @classmethod
    def from_files(cls):
        return cls(cls._get_items_from_files())


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
        self.unturneddb = UnturnedDatabase.from_files()





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
                color=utils.get_bot_color()
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
                color=utils.get_bot_color()
            )

        await ctx.send(title, embed=embed)





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





    @commands.group(name='unturned', invoke_without_command=True)
    async def client_unturned(self, ctx):
        """Commands related to the game Unturned."""


    @staticmethod
    def unturned_could_not_find_item(search):
        """Create a message for when an item search
        does not return anything."""
        try:
            int(search)
        except ValueError:
            return 'Could not find an item with that name.'
        else:
            return 'Could not find an item with that ID.'


    @staticmethod
    def unturned_get_rarity_color(rarity):
        """Return the color for a given item rarity.

        Args:
            UnturnedItem

        Returns:
            int

        """
        return ( 0x777777 if rarity == 'Common'
            else 0x71BA51 if rarity == 'Uncommon'
            else 0x3D8EB9 if rarity == 'Rare'
            else 0x8870FF if rarity == 'Epic'
            else 0xD33257 if rarity == 'Legendary'
            else 0x637C63
        )


    @staticmethod
    def unturned_multiple_matches(results, *, threshold=5):
        """Create a message and embed showing multiple matches.

        Args:
            List[UnturnedItem]

        Returns:
            Tuple[str, discord.Embed]

        """
        # List the first five possible matches
        amount = len(results)
        results = results[:threshold]

        description = [entry.name for entry in results]
        if amount > threshold:
            description.append('...')
        description = '\n'.join(description)

        embed = discord.Embed(
            color=utils.get_bot_color(),
            description=description
        )

        content = '{} items were matched:'.format(
            inflector.number_to_words(amount, threshold=10).capitalize()
        )

        return content, embed


    @client_unturned.command(name='item', aliases=['i'])
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_unturned_item(self, ctx, *, item):
        """Search for an Unturned item by ID or name.
Information was pre-scraped from https://unturneditems.com/.
Up to date as of 3.20.15.0."""
        def item_embed(entry):
            id_, name, rarity, url, dimensions, recipe_data = (
                entry.id, entry.name, entry.rarity, entry.url,
                entry.dimensions, entry.recipe_data
            )

            description = (
                f'[**{name}**]({url})\n'
                f'ID: {id_}\n'
                f'Rarity: {rarity}\n'
            )

            if dimensions is not None:
                description += f'Dimensions: {dimensions[0]}x{dimensions[1]}\n'

            if recipe_data is not None:
                # List every recipe
                recipes_str = []
                for recipe in recipe_data['recipes']:
                    amount, items_raw, skills = (
                        recipe['amount'], recipe['recipe'], recipe['skills']
                    )
                    # Distinguish between consumed and required items
                    items_consumed, items_required = [], []
                    for raw_id, quantity in items_raw:
                        item = self.unturneddb.unturned_get_item(raw_id)
                        if quantity == 0:
                            items_required.append(item.name)
                        else:
                            items_consumed.append((item, quantity))

                    rec_str = []
                    first = True
                    # List consumed items
                    for item in items_consumed:
                        rec_str.append('> ')
                        if not first:
                            rec_str.append('+ ')
                        rec_str.append(f'{item[1]} x {item[0].name}\n')
                        first = False

                    # Show product
                    rec_str.append(f'> = {amount} x {name}\n')

                    if items_required:
                        rec_str.append('> (Uses {})\n'.format(
                            inflector.join(items_required)
                        ))

                    requires = skills.copy()

                    # Include other conditions in requirements
                    if recipe['requires_heat']:
                        requires.append('Heat')

                    if requires:
                        rec_str.append(f'> (Requires {inflector.join(requires)})')

                    recipes_str.append(''.join(rec_str))

                recipes_str = '> OR:\n'.join(recipes_str)

                if recipes_str:
                    description += f'Recipes:\n{recipes_str}\n'

            return discord.Embed(
                color=self.unturned_get_rarity_color(rarity),
                description=description
            ).set_thumbnail(
                url=f'https://unturneditems.com/media/{id_}.png'
            )

        result = self.unturneddb.unturned_get_item(item)

        if isinstance(result, list):
            content, embed = self.unturned_multiple_matches(result)

            await ctx.send(content, embed=embed)
        elif result is None:
            await ctx.send(self.unturned_could_not_find_item(item))
        else:
            await ctx.send(embed=item_embed(result))


    @client_unturned.command(name='craft', aliases=['c'])
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_unturned_craft(
            self, ctx, amount: typing.Optional[int] = 1, *, item):
        """Get the materials required to craft an item.

amount: The number of the given item to craft. This parameter must be included.
item: The name or ID of the item to look up.

Note: There are only a few items with recipe data since I have to manually enter this myself."""
        def get_recipe_requirements(item, amount=None, frontier=None):
            """Return the requirements for a recipe.

            Dictionary returned is structured like so:
                'tree': [
                    [item, amount,
                     [...],
                     {'other': True, ...}],
                    ...
                ],
                # stores the tree structure that is being pathed
                'remainders': [[item, amount], ...],
                # any excess materials
                'skills': {'Crafting': 3, ...},
                # all skills that are needed
                'other': {'requires_heat': True, ...},
                # other information about the recipe
                'total_raw': [[item, amount], ...],
                # contains all the raw materials required

            The design is to navigate through the item's recipe tree,
            recursively acquiring materials from the recipe of each
            material in the item.
            This lends to several considerations:
                1. How are skills acquired?
                2. What if a recipe produces extra items?
                3. What if an item is marked as primitive?
                4. What if a recipe is cyclic? (as in a recipe of an item
                    has that same item in its recipe)

            1. Skills are stored in a dictionary where the key is the name
            of the skill, and the value being the level.
            When a recursive call returns a dictionary, it is merged
            into the current stack's skills, keeping the maximum level of each
            skill.

            2. Extra items are stored as a list containing pairs of items
            and their amount. The items are initially non-unique but at
            the top level, the amounts are aggregated together by mapping
            the item ID to their amount, and then converted back into a list.

            3. Primitive items like Metal Scrap means that their recipes
            should not be recursed into. [...]

            [incomplete documentation]
            """
            def create_output(*, tree=None, remainders=None,
                              skills=None, total_raw=None,
                              other=None):
                d = {
                    'tree': tree if tree is not None else [],
                    'remainders': remainders if remainders is not None else [],
                    'skills': skills if skills is not None else {},
                    'other': other if other is not None else {}
                }
                if total_raw is not None:
                    d['total_raw'] = total_raw
                return d

            def parse_skills(skills):
                skill_dict = {}
                for s in skills:
                    skill_name, level = s.split()
                    skill_dict[skill_name] = int(level)
                return skill_dict

            def get_total_raw(tree):
                "Recursively summarize the raw materials of a tree."
                materials = {}
                if not tree:
                    return materials
                for item, amount, branch, _other in tree:
                    if branch:
                        # Item is broken down into more materials
                        branch_raw = get_total_raw(branch)
                        if branch_raw:
                            for item_id, item_and_amount in branch_raw.items():
                                item, amount = item_and_amount
                                materials.setdefault(item_id, [item, 0])
                                materials[item_id][1] += amount
                    else:
                        # Leaf node; must be primitive/uncraftable; store it
                        materials.setdefault(item.id, [item, 0])
                        materials[item.id][1] += amount
                return materials

            top_level = frontier is None

            if (    item.recipe_data is None
                    or not item.recipe_data['recipes']
                    or item.recipe_data['primitive'] and not top_level):
                # No recipes/primitive item
                if top_level:
                    return create_output(total_raw=[[item, amount]])
                return create_output()

            recipe = item.recipe_data['recipes'][0]
            # TODO: using only the first recipe will add limitations to
            # how it figures out the requirements (ignoring other recipes
            # that could work) but since most items only have one recipe,
            # this generally won't have any issue

            materials, amount_produced = recipe['recipe'], recipe['amount']

            other = {'requires_heat': recipe.get('requires_heat', False)}

            if amount is None:
                amount = recipe['amount']

            if amount == 0:
                # Item is only required but not consumed
                if top_level:
                    raise ValueError('amount cannot be 0')
                return create_output()

            if top_level:
                frontier = set()

            if item.id in frontier:
                # Item already seen; do not recurse into its recipes
                return create_output(tree=[[item, amount, [], other]])

            frontier.add(item.id)

            tree = []
            remainders = []

            # Parse skills into their name and level
            skills = parse_skills(recipe['skills'])

            if amount % amount_produced != 0:
                # Recipe will result in excess produce
                remainders.append((item, amount % amount_produced))

            # Recursively get requirements of recipe materials
            for mat_id, mat_amount in materials:
                mat = self.unturneddb.unturned_get_item(mat_id)
                if mat is None:
                    raise ValueError(
                        f'unknown item in recipe: {mat_id}')

                branched_frontier = frontier.copy()

                amount_to_craft = math.ceil(
                    amount / amount_produced) * mat_amount

                mat_req = get_recipe_requirements(
                    mat,
                    amount_to_craft,
                    branched_frontier
                )

                tree.append(
                    [mat, amount_to_craft, mat_req['tree'], mat_req['other']]
                )

                remainders.extend(mat_req['remainders'])

                # Collect skills
                for name, level in mat_req['skills'].items():
                    skills.setdefault(name, 0)
                    skills[name] = max(skills[name], level)

                # Collect other booleans if top level
                if top_level:
                    for k, v in mat_req['other'].items():
                        other.setdefault(k, False)
                        other[k] = max(other[k], v)

            # collect items
            if top_level:
                total_raw = list(get_total_raw(tree).values())

                collected_remainders = {}
                for mat, mat_amount in remainders:
                    collected_remainders.setdefault(mat.id, [mat, 0])
                    collected_remainders[mat.id][1] += mat_amount
                collected_remainders = list(collected_remainders.values())

                return create_output(
                    tree=tree,
                    remainders=collected_remainders,
                    skills=skills,
                    total_raw=total_raw,
                    other=other
                )
            return create_output(
                tree=tree,
                remainders=remainders,
                skills=skills,
                other=other
            )

        def humanize_other(other):
            """Convert a dictionary of other booleans from
            get_recipe_requirements into a list of human-readable strings."""
            d = {'requires_heat': 'Heat'}
            s = []
            for k, v in other.items():
                if v:
                    s.append(d[k])
            return s

        def tree_str(tree, level=1):
            """Example tree produced by get_recipe_requirements:

            Wire:
            [
             Metal Bar, 3, [[Metal Scrap, 2, []],
                            [Blowtorch, 0]],
             Blowtorch, 0, []
            ]

            """
            if not tree:
                return tree

            s = []
            indent = '> ' * level

            for item, amount, branch, other in tree:
                if amount:
                    # Skip unconsumed items, those are handled separately
                    s.append(f'{indent}{amount} x {item.name}')

                for other_str in humanize_other(other):
                    s.append(f"{'> ' * (level + 1)}{other_str}")

                s.extend(tree_str(branch, level=level + 1))

            return s

        result = self.unturneddb.unturned_get_item(item)

        if isinstance(result, list):
            content, embed = self.unturned_multiple_matches(result)

            return await ctx.send(content, embed=embed)
        elif result is None:
            return await ctx.send(self.unturned_could_not_find_item(item))

        if result.recipe_data is None:
            return await ctx.send(
                "Unfortunately I don't have the recipe data for this.")

        if amount <= 0:
            return await ctx.send(
                embed=discord.Embed(
                    color=utils.get_bot_color(),
                    description=(
                        f'{result.name}\n'
                        f'ID: {result.id}\n'
                        'Total raw:\n**nothing**'
                    )
                ).set_thumbnail(
                    url=f'https://unturneditems.com/media/{result.id}.png'
                )
            )

        requirements = get_recipe_requirements(result, amount)
        tree = requirements['tree']
        remainders = requirements['remainders']
        skills = requirements['skills']
        total_raw = requirements['total_raw']

        # Fix inflector sometimes not properly pluralizing the name
        # if it starts with a capital letter
        is_name_capitalized = result.name[0].isupper()
        plural_name = result.name
        plural_name = plural_name[0].lower() + plural_name[1:]
        plural_name = inflector.plural(plural_name, amount)
        if is_name_capitalized:
            plural_name = plural_name[0].upper() + plural_name[1:]

        description = [
            f'{amount} {plural_name}',
            f'ID: {result.id}'
        ]

        if tree:
            description.extend((
                'Recipe tree:',
                '\n'.join(tree_str(tree))
            ))
        # Else item is primitive/has no recipes

        items_consumed, items_required = [], []
        for item, quantity in total_raw:
            if quantity == 0:
                items_required.append(item.name)
            else:
                items_consumed.append((item, quantity))

        description.append('Total raw:')

        # List consumed and required items
        for item, amount in items_consumed:
            description.append(f'> {amount} x {item.name}')
        for item in items_required:
            description.append(f'> {item}')

        # List excess material
        if remainders:
            description.append('Remainders:')
            description.extend(f'> {amount} x {item.name}'
                               for item, amount in remainders)

        # Parse skill dict back into list of strings
        # and add other conditions here
        requires = [f'{k} {v}' for k, v in skills.items()]
        requires.extend(humanize_other(requirements['other']))

        if requires:
            description.append(f'Requires {inflector.join(requires)}')

        embed = discord.Embed(
            color=self.unturned_get_rarity_color(result.rarity),
            description='\n'.join(description)
        ).set_thumbnail(
            url=f'https://unturneditems.com/media/{result.id}.png'
        )

        await ctx.send(embed=embed)


    @client_unturned.command(name='reload')
    @checks.is_bot_admin()
    @commands.cooldown(1, 20, commands.BucketType.default)
    async def client_unturned_reload_db(self, ctx):
        """Reload the item database."""
        await self.unturneddb.reload_items_nonblocking()
        await ctx.send('Item database reloaded.')










def setup(bot):
    bot.add_cog(Undefined(bot))

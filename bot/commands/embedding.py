import asyncio
import collections
import datetime
import functools

import discord
from discord.ext import commands

from bot import utils


class Embedding(commands.Cog):
    qualified_name = 'Embedding'
    description = 'Commands for creating embeds.'

    embed_specs = {
        'title':    ('--title', '-T'),
        'titleurl': ('--titleurl', '-TU'),
        'footer':     ('--footer', '-F'),
        'footericon': ('--footericon', '-FU'),
        'image':        ('--image', '-I'),
        'thumbnail':        ('--thumbnail', '-TN'),
        'author':             ('--author', '-A'),
        'authorurl':          ('--authorurl', '-AU')
    }

    def __init__(self, bot):
        self.bot = bot





    @commands.command(
        name='embed',
        brief='Create an embed.')
    @commands.cooldown(3, 30, commands.BucketType.channel)
    async def client_createembed(
            self, ctx,
            color: functools.partial(int, base=16),
            description,
            *parameters):
        """Create an embed.
Example:
    embed 0xDDA212 "description with \\"quotes\\"" --title "Title"
If you want to stop links from being embedded in your message,
you can use code block tags like so:
    embed FFCC22 description `​`​` --title Title `​`​`

-T  --title        "<text>"
-TU --titleurl     <url>
-F  --footer       "<text>"
-FU --footericon   <url>
-I  --image        <url>
-TN --thumbnail    <url>
-A  --author       "<text>"
-AU --authorurl    <url>
-FI --field<n>     "<subtitle>"
-FT --fieldtext<n> "<text>"
-FO --fieldnotinline<n>
Note: Field title and text must both be specified.

These are the limits set by Discord:
          Title: 256 characters
    Description: 2048 characters
         Fields: 25 fields
     Field Name: 256 characters
     Field Text: 1024 characters
         Footer: 2048 characters
    Author Name: 256 characters
    Total Limit: 6000 characters"""
        def char_separate_num(string):
            chars, nums = [], []
            for c in string:
                if c.isdigit():
                    nums.append(c)
                else:
                    chars.append(c)
            return ''.join(chars), ''.join(nums)

        def default_field(field_num):
            fields.setdefault(
                field_num, {'inline': True, 'name': '', 'value': ''}
            )

        args = collections.deque(parameters)
        del parameters

        embed_dict = {'color': color, 'description': description}
        fields = {}
        while args:
            argv = args.popleft()

            if argv == '```':
                # Code block formatting used by user to hide links
                continue

            elif argv in self.embed_specs['title']:
                embed_dict['title'] = args.popleft()

            elif argv in self.embed_specs['titleurl']:
                embed_dict['url'] = args.popleft()

            elif argv in self.embed_specs['footer']:
                embed_dict.setdefault('footer', {})
                embed_dict['footer']['text'] = args.popleft()

            elif argv in self.embed_specs['footericon']:
                embed_dict.setdefault('footer', {})
                embed_dict['footer']['icon_url'] = args.popleft()

            elif argv in self.embed_specs['image']:
                embed_dict['image'] = {'url': args.popleft()}

            elif argv in self.embed_specs['thumbnail']:
                embed_dict['thumbnail'] = {'url': args.popleft()}

            elif argv in self.embed_specs['author']:
                embed_dict.setdefault('author', {})
                embed_dict['author']['name'] = args.popleft()

            elif argv in self.embed_specs['authorurl']:
                embed_dict.setdefault('author', {})
                embed_dict['author']['url'] = args.popleft()

            else:
                chars, num = char_separate_num(argv)
                if chars == '--field' \
                        or chars == '-FI':
                    value = args.popleft()
                    default_field(num)
                    fields[num]['name'] = value

                elif chars == '--fieldtext' \
                        or chars == '-FT':
                    value = args.popleft()
                    default_field(num)
                    fields[num]['value'] = value

                elif chars == '--fieldnotinline' \
                        or chars == '-FO':
                    default_field(num)
                    fields[num]['inline'] = False

        if fields:
            embed_dict['fields'] = list(fields.values())
        embed = discord.Embed.from_dict(embed_dict)
        embed.timestamp = datetime.datetime.now().astimezone()
        await ctx.send(embed=embed)





    @commands.group(name='hyperlink', invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.member)
    async def client_hyperlink(self, ctx):
        """Commands for using the Embed's hyperlink feature.

These commands only work in servers."""
        await ctx.send(f'Unknown {ctx.command.name} subcommand given.')
        ctx.command.reset_cooldown(ctx)


    @client_hyperlink.command(name='procedure')
    @commands.guild_only()
    async def client_hyperlink_procedure(self, ctx):
        """Create a hyperlink with custom display text in two steps.

You will be DM'd for your parameters."""
        async def cancel_message(message):
            await message.edit(
                content=f'~~{message.content}~~ Canceled hyperlink.')

        def check(message):
            "Wait for a message in the author's DMs."
            return message.channel == ctx.author.dm_channel

        link_request = await ctx.author.send(
            'What link would you like to show?')

        # Get link from user
        try:
            link = await ctx.bot.wait_for(
                'message', check=check, timeout=30)
        except asyncio.TimeoutError:
            # User took too long to respond
            return await cancel_message(link_request)

        if link.author != ctx.author:
            # Bot DM'd the user; cancel hyperlink command
            return await cancel_message(link_request)

        # TODO: Verify link with regex

        text_request = await ctx.author.send(
            'What display text would you like the link to have?')

        # Get display text from user
        try:
            text = await ctx.bot.wait_for(
                'message', check=check, timeout=30)
        except asyncio.TimeoutError:
            await cancel_message(link_request)
            return await cancel_message(text_request)

        # Escape markdown (mentions don't work in embeds so no need to escape)
        link = discord.utils.escape_markdown(link.content)
        text = text.content

        embed = discord.Embed(
            title=f'{ctx.author.display_name}',
            description=f'[{text}]({link})',
            color=utils.get_user_color(ctx.author),
            timestamp=datetime.datetime.now().astimezone()
        )

        await ctx.send(embed=embed)


    @client_hyperlink.command(
        name='quick',
        description='Create an embed directly out of a message.')
    @commands.guild_only()
    async def client_hyperlink_quick(self, ctx):
        """Create an embed directly out of a message, allowing hyperlinks via markdown formatting.
To create hyperlinks with custom display text:
    text [display text](https://mylink.com/) text
Make sure there's a space before and after the hyperlink.

You will be DM'd for your parameters."""
        async def cancel_message(message):
            await message.edit(
                content=f'~~{message.content}~~ Canceled hyperlink.')

        def check(message):
            "Wait for a message in the author's DMs."
            return message.channel == ctx.author.dm_channel

        message_request = await ctx.author.send(
            'Send your message here to embed it:')

        # Get message from user
        try:
            message = await ctx.bot.wait_for(
                'message', check=check, timeout=30)
        except asyncio.TimeoutError:
            # User took too long to respond
            return await cancel_message(message_request)

        if message.author != ctx.author:
            # Bot DM'd the user; cancel hyperlink command
            return await cancel_message(message_request)

        embed = discord.Embed(
            title=f'{ctx.author.display_name}',
            description=message.content,
            color=utils.get_user_color(ctx.author),
            timestamp=datetime.datetime.now().astimezone()
        )

        await ctx.send(embed=embed)










def setup(bot):
    bot.add_cog(Embedding(bot))

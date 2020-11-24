import json
import os
import random

import aiohttp
import discord
from discord.ext import commands

from bot import utils

CAT_API_URL = 'https://api.thecatapi.com/v1/images/search'
CAT_API_KEY = os.getenv('PyDiscordBotAPICatKey')


class Images(commands.Cog):
    qualified_name = 'Images'
    description = 'Commands for getting images.'

    def __init__(self, bot):
        self.bot = bot





    @commands.command(
        name='meow')
    @commands.cooldown(1, 20, commands.BucketType.channel)
    @commands.max_concurrency(3)
    async def client_getcatimage(self, ctx):
        """cat pic"""
        if CAT_API_KEY is None:
            await ctx.send(
                'Sorry, but the bot currently cannot query a cat image.')
            raise ValueError('API key unavailable')

        search = '?mime_types=jpg,png'

        await ctx.trigger_typing()

        async with aiohttp.ClientSession(
                headers={'x-api-key': CAT_API_KEY}) as session:
            async with session.get(CAT_API_URL + search) as response:

                if response.status >= 400:
                    await ctx.send('Could not get a cat image: '
                                   f'status code {response.status}')
                    raise ValueError(f'{response.status}: {response.reason}')

                # Acquire the json, disabling content-type check
                cat = (await response.json(content_type=None))[0]

                embed = discord.Embed(
                    color=utils.get_user_color(ctx.author)
                ).set_footer(
                    text=f'Requested by {ctx.author.name}',
                    icon_url=ctx.author.avatar_url
                ).set_image(
                    url=cat['url']
                )

                await ctx.send(embed=embed)










def setup(bot):
    bot.add_cog(Images(bot))

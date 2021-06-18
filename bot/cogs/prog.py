#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import autopep8
import discord
from discord.ext import commands, menus

from bot.converters import CodeBlock


class CodeBlockSource(menus.ListPageSource):
    def __init__(self, cb: CodeBlock, prefix=''):
        p = commands.Paginator(f'{prefix}```{cb.language}')
        for line in cb.code.split('\n'):
            p.add_line(line)

        super().__init__(p.pages, per_page=1)

    async def format_page(self, menu, page):
        return page


class CodeBlockMenuPages(menus.MenuPages):
    def __init__(self, *args, reply_to_author=False, **kwargs):
        super().__init__(CodeBlockSource(*args), **kwargs)
        self.reply_to_author = reply_to_author

    async def send_initial_message(self, ctx, channel):
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        if self.reply_to_author and ctx.message.channel == channel:
            kwargs['reference'] = ctx.message
        return await channel.send(**kwargs)


class Programming(commands.Cog):
    """Commands related to programming."""

    def __init__(self, bot):
        self.bot = bot
        self._cooldown = commands.CooldownMapping.from_cooldown(
            1, 5, commands.BucketType.user
        )

    def cog_check(self, ctx):
        retry_after = self._cooldown.update_rate_limit(ctx.message)
        if retry_after:
            raise commands.CommandOnCooldown(
                self._cooldown._cooldown,  # commands.Cooldown
                retry_after
            )
        return True





    @commands.command(name='pep8')
    @commands.max_concurrency(1, commands.BucketType.member)
    async def client_pep8(self, ctx, *, code: CodeBlock):
        """Format Python code using autopep8."""
        if code.language not in (None, 'py', 'python'):
            return await ctx.send('The code block must be python!')
        code.language = 'py'

        code.code = await ctx.bot.loop.run_in_executor(
            None, autopep8.fix_code, code.code
        )

        prefix, reply = ctx.author.mention, True
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            prefix = ''
        else:
            reply = False

        pages = CodeBlockMenuPages(
            code, prefix,
            clear_reactions_after=True,
            reply_to_author=reply
        )
        await pages.start(ctx, wait=True)










def setup(bot):
    bot.add_cog(Programming(bot))

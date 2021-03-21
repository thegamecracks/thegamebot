"""
get current invites, store

on member join:
   get and store new invites
    check invites to see if one has incremented
    if one has, that's your invite, return

    else:
        if an invite is missing, it might be it was a limited use one or expired- add it to a list of things to return
        check vanity invite to see if it incremented
             if it did, return that
        poll audit log to see if any invites were created recently
             if one was, add that to things to return, return
			 else :mystery:
"""
from typing import Dict, Optional

import discord
from discord.ext import commands


class InviteTracker(commands.Cog):
    """Track invite usage across guilds.

    Requires manage_guild permissions in each guild,
    and members + invites intents.

    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.invites = {}       # guild.id: {invite.id: invite.uses}
        self.last_invited = {}  # guild.id: (member.id, invite.id)
        self.invited_by = {}    # (guild.id, member.id): invite.id

        self.bot.loop.create_task(self.overwrite_invites())

    def has_required_intents(self):
        intents = self.bot.intents
        return intents.members and intents.invites

    async def fetch_all_invites(self):
        """Fetch all invites.

        Returns:
            Dict[int, Dict[int, int]]:
                Maps guild IDs to mappings of invite ID to uses.

        """
        guilds = {}
        for guild in self.bot.guilds:
            try:
                guilds[guild.id] = await self.fetch_guild_invites(guild)
            except discord.HTTPException:
                # Missing manage_guild permissions
                pass

        return guilds

    async def fetch_guild_invites(self, guild: discord.Guild):
        """Fetch invites from a guild, including its vanity invite.

        Returns:
            Dict[int, int]: Maps the invite ID to its uses.

        Raises:
            HTTPException: failed to fetch invites.
                This is caught for the vanity invite.

        """
        invites = {}

        # Fetch all invites
        for inv in await guild.invites():
            invites[inv.id] = inv.uses

        # Fetch vanity invite
        if 'VANITY_URL' in guild.features:
            try:
                vanity_inv = await guild.vanity_invite()
            except discord.HTTPException:
                # No vanity invite exists
                pass
            else:
                invites[vanity_inv.id] = vanity_inv.uses

        return invites

    async def overwrite_invites(self):
        """Fetch and overwrite the `invites` attribute."""
        await self.bot.wait_until_ready()
        self.invites = await self.fetch_all_invites()

    def update_member_invite(self, guild_id: int, member_id: int, invite_id: int,
                             new_invites: dict = None):
        if new_invites is not None:
            self.invites = new_invites
        self.last_invited[guild_id] = (member_id, invite_id)
        self.invited_by[(guild_id, member_id)] = invite_id


    async def cog_check(self, ctx):
        return self.has_required_intents()


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Find the invite that updated
        guild: discord.Guild = member.guild
        new_invites = await self.fetch_guild_invites(guild.id)
        old_invites = self.invites[guild.id]

        removed_invites = []

        for old_id, old_uses in old_invites.items():
            new_uses = new_invites.get(old_id)
            if new_uses > old_uses:
                # Found invite
                return self.update_member_invite(
                    member.guild.id, member.id, old_id, new_invites)
        else:
            # Missing invite; might be limited use
            new_vanity: Optional[discord.Invite] = None
            try:
                new_vanity = await guild.vanity_invite()
            except discord.HTTPException:
                # no vanity invite / missing manage_guild permission
                pass

            if new_vanity is not None:
                old_vanity_uses = old_invites.get(new_vanity.id)
                if new_vanity.uses > old_vanity_uses:
                    # Vanity invite used
                    return self.update_member_invite(
                        member.guild.id, member.id, new_vanity.id, new_invites)

            # TODO: Check audit log
            pass










def setup(bot):
    bot.add_cog(InviteTracker(bot))

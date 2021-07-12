def create_setup(cog_class):
    def setup(bot):
        cog = cog_class(bot)
        bot.add_cog(cog)
        game_cog = bot.get_cog('Games') or None
        for c in cog.get_commands():
            c.cog = game_cog
            c.original_cog = cog
    return setup

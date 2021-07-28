def create_setup(cog_class):
    def setup(bot):
        cog = cog_class(bot)
        bot.add_cog(cog)
        for c in cog.get_commands():
            c.injected_cog = 'Games'
    return setup

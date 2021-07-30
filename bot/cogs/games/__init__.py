#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
def create_setup(cog_class):
    def setup(bot):
        cog = cog_class(bot)
        bot.add_cog(cog)
        for c in cog.get_commands():
            c.injected_cog = 'Games'
    return setup

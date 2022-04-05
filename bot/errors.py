#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
from discord.ext import commands


class SkipInteractionResponse(Exception):
    """Raised during user-made button callbacks when the interaction
    should not be deferred."""


class SettingsNotFound(Exception):
    """The Settings cog could not be loaded."""

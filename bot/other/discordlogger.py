#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging

logger = None


def get_logger():
    """Create or return the current logger."""
    global logger

    if logger is None:
        logger = logging.getLogger('discord')
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(
            filename='discord.log', encoding='utf-8', mode='w')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        logger.addHandler(handler)

    return logger

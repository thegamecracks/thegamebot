#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
from typing import List, Iterable, Union, Optional

import discord
from discord.ext.commands.view import StringView


def fuzzy_match_word(s, choices: Iterable[str], return_possible=False) \
        -> Optional[Union[str, List[str]]]:
    """Matches a string to given choices by token (case-insensitive).

    Choices can be matched even if the given string has tokens out of order:
        >>> fuzzy_match_word('orb ghost', ['Ghost Orb', 'Ghost Writing'])
        'Ghost Orb'

    `choices` does not get mutated.

    Args:
        s (str)
        choices (Iterable[str])
        return_possible (bool): If this is True and there are multiple matches,
            a list of those matches will be returned.

    Returns:
        None: Returned if there are multiple matches and
              `return_possible` is False.
        str
        List[str]: Returned if there are multiple matches and
                   `return_possible` is True.

    """
    possible = list(choices) if not isinstance(choices, list) else choices
    possible_lower = [s.lower() for s in possible]

    # See if the phrase already exists
    try:
        i = possible_lower.index(s.lower())
        return possible[i]
    except ValueError:
        pass

    length = len(s)
    for word in s.lower().split():
        new = []

        for p, pl in zip(possible, possible_lower):
            if word in pl:
                new.append(p)

        possible = new

        count = len(possible)
        if count == 0:
            return
        elif count == 1:
            return possible[0]

        possible_lower = [s.lower() for s in possible]

    return possible if return_possible and possible else None


def parse_status(status='online'):
    status = status.casefold()

    if status in ('online', 'green', 'on', 'active'):
        return discord.Status.online
    elif status in ('idle', 'yellow', 'away', 'afk'):
        return discord.Status.idle
    elif status in ('dnd', 'red', 'donotdisturb'):
        return discord.Status.dnd
    elif status in ('invisible', 'grey', 'gray', 'black', 'offline', 'off'):
        return discord.Status.invisible
    else:
        raise ValueError('Unknown status')


def parse_var_positional(s):
    """Parse a string in the same way as done in a command *args.

    Returns:
        List[str]

    Raises:
        discord.ext.commands.ExpectedClosingQuoteError
        discord.ext.commands.InvalidEndOfQuotedStringError
        discord.ext.commands.UnexpectedQuoteError

    """
    view = StringView(s)
    words = []
    while not view.eof:
        view.skip_ws()
        w = view.get_quoted_word()
        if w != ' ':
            words.append(w)
    return words

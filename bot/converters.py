#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import re
from typing import Optional

from discord.ext import commands


class CodeBlock:
    REGEX = re.compile(
        r'```(?:(?P<language>\w*)(?:\n))?\s*(?P<code>.*?)\s*```',
        re.IGNORECASE | re.DOTALL
    )

    def __init__(self, language: str | None, code: str):
        self.language = language or None
        self.code = code

    @classmethod
    def from_search(cls, s: str) -> Optional['CodeBlock']:
        match = cls.REGEX.search(s)
        return None if match is None else cls(**match.groupdict())

    @classmethod
    async def convert(cls, ctx, arg, required=False):
        """Converts a code block with an optional language name
        and strips whitespace from the following block.

        If `required`, commands.UserInputError is raised when the argument
        is not a code block.

        """
        match = cls.REGEX.match(arg)
        if match is None:
            if required:
                raise commands.UserInputError('Argument must be a code block.')
            return cls(language=None, code=arg)
        return cls(**match.groupdict())

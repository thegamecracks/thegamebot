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


def truncate_message(
        message: str, max_size: int = 2000, max_lines: Optional[int] = None,
        placeholder: str = '[...]') -> str:
    """Truncate a message to a given amount of characters or lines.

    This should be used when whitespace needs to be retained as
    `textwrap.shorten` will collapse whitespace.

    Message is stripped of whitespace initially, then after cutting the
    message to just under max_size, trailing whitespace is stripped.

    The placeholder will be prefixed with a newline if the trailing whitespace
    that was stripped includes a newline, or if excess lines were removed.
    Otherwise it will prefix with a space.

    The placeholder will not be prefixed if it would exceed the max_size.
        >>> truncate_message('Hello world!', 11, placeholder='[...]')
        'Hello [...]'
        >>> truncate_message('Hello world!', 10, placeholder='[...]')
        'Hello[...]'

    If the message is completely wiped and the placeholder exceeds max_size,
    an empty string is returned.
        >>> truncate_message('Hello world!', 5, placeholder='[...]')
        '[...]'
        >>> truncate_message('Hello world!', 4, placeholder='[...]')
        ''

    Args:
        message (str): The message to truncate.
        max_size (int): The max length the message can be.
        max_lines (Optional[int]): The max number of lines
            the message can have.
        placeholder (str): The placeholder to append if the message
            gets truncated.

    Returns:
        str

    """
    def get_trailing_whitespace(s):
        stripped = s.rstrip()
        whitespace = s[len(stripped):]
        return stripped, whitespace

    # Check arguments
    if max_size < 0:
        raise ValueError(f'Max size cannot be negative ({max_size!r})')
    elif max_size == 0:
        return ''
    if max_lines is not None:
        if max_lines < 0:
            raise ValueError(f'Max lines cannot be negative ({max_lines!r})')
        elif max_lines == 0:
            return ''

    message = message.strip()

    # Check if the message needs to be truncated
    under_size = len(message) <= max_size
    if under_size and max_lines is None:
        return message
    lines = message.split('\n')
    excess_lines = len(lines) - max_lines if max_lines is not None else 0
    if max_lines is not None:
        if under_size and excess_lines <= 0:
            return message
        else:
            # Remove excess lines
            for _ in range(excess_lines):
                lines.pop()

    in_code_block = 0
    placeholder_len = len(placeholder)
    length = 0
    placeholder_prefix = '\n' if excess_lines > 0 else ' '
    # Find the line that exceeds max_size
    for line_i, line in enumerate(lines):
        in_code_block = (in_code_block + line.count('```')) % 2

        new_length = length + len(line)
        # Adjust size to compensate for newlines, length of placeholder,
        # and completing the code block if needed
        max_size_adjusted = (max_size - line_i - placeholder_len
                             - in_code_block * 3)

        if new_length > max_size_adjusted:
            # This line exceeds max_size_adjusted
            placeholder_prefix = ' ' if line else '\n'
            if line:
                # Find the word that exceeds the length
                words = line.split(' ')
                words_len = len(words)
                length_sub = length
                wi = 0
                if words_len > 1:
                    for wi, w in enumerate(words):
                        # NOTE: This for-loop should always break
                        length_sub += len(w)

                        if length_sub > max_size_adjusted:
                            # This word exceeds the max size; truncate to here
                            break

                        if wi != words_len:
                            length_sub += 1  # Add 1 for space

                # Replace with truncated line
                line = ' '.join(words[:wi])
                lines[line_i] = line
            break
        else:
            length = new_length

    # Join lines together
    final = '\n'.join(lines[:line_i + 1])

    # Strip trailing whitespace
    final, whitespace = get_trailing_whitespace(final)
    final_len = len(final) + placeholder_len + in_code_block * 3
    if '\n' in whitespace:
        placeholder_prefix = '\n'
    if not final or final_len + len(placeholder_prefix) > max_size:
        placeholder_prefix = ''
        if final_len > max_size:
            return ''

    return (f'{final}{placeholder_prefix}{placeholder}'
            f"{'```' * in_code_block}")

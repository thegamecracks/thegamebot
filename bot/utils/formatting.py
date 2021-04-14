import itertools
from typing import List, Optional


def format_table(
        rows: List[List[str]],
        divs=(1,), div_char='=', col_sep=' | ',
        *, strip_trailing=False) -> str:
    """Format a table of rows into a string.

    Args:
        rows (List[List[str]]): The rows to format.
        divs (Iterable[int]): The indices for where to insert dividers.
            This defaults to 1, intended for separating the column
            names from the row data.
        div_char (str): The string to use for the dividers.
        col_sep (str): The string for separating columns.
        strip_trailing (bool): Strip trailing whitespace from each line.

    Returns:
        str

    """
    def rcenter(s, w):
        if len(s) % 2 != w % 2:
            return ' ' + f'{s:^{w-1}}'
        return f'{s:^{w}}'

    def render_row(r):
        middle = len(r) // 2
        cols = zip(r, widths)
        render = [rcenter(s, w) for s, w in itertools.islice(cols, middle)]
        render.extend(f'{s:^{w}}' for s, w in cols)
        return col_sep.join(render)

    # Duplicate table for implicit cast to string
    rows = [[str(x) for x in row] for row in rows]

    widths = [max(len(r[col]) for r in rows) for col in range(len(rows[0]))]

    render = [render_row(r) for r in rows]

    if strip_trailing:
        render = [r.rstrip() for r in render]

    if divs:
        length = max(len(r) for r in render)
        div = div_char * length
        done_divs = []
        for i in divs:
            render.insert(i + sum(x < i for x in done_divs), div)
            done_divs.append(i)

    return '\n'.join(render)


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


def truncate_simple(message: str, width: int, placeholder: str = '[...]') -> str:
    """Truncate a message to width characters.

    Args:
        message (str): The message to truncate.
        width (int): The max number of characters.
        placeholder (str): The string to use if the message is truncated.

    Returns:
        str

    """
    if len(message) <= width:
        return message
    return message[:width - len(placeholder)] + placeholder
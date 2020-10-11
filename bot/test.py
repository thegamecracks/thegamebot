def truncate_message(
        message, size=2000, size_lines=None, placeholder='[...]'):
    """Truncate a message to a given amount of characters or lines.

    This should be used when whitespace needs to be retained as
    `textwrap.shorten` will collapse whitespace.

    Message is stripped of whitespace.

    """
    message = message.strip()

    lines = message.split('\n')
    chars = 0
    for line_i, line in enumerate(lines):
        if size_lines is not None and i == size_lines:
            # Reached maximum lines
            break

        new_chars = chars + len(line)
        if new_chars > size:
            # This line exceeds max size; truncate it by word
            words = line.split(' ')
            last_word = len(words) - 1  # for compensating space split
            line_chars = chars

            for word_i, word in enumerate(words):
                new_line_chars = line_chars + len(word)

                if new_line_chars > size - len(placeholder):
                    # This word exceeds the max size; truncate to here
                    break

                if word_i != last_word:
                    new_line_chars += 1

                line_chars = new_line_chars
            else:
                raise RuntimeError(f'line {line_i:,} exceeded max size but '
                                   'failed to determine where to '
                                   'truncate the line')

            if word_i == 0:
                # Line becomes empty; go back to last line
                # and add placeholder
                break
            else:
                # Truncate line and return new message
                print('truncated line')
                line = ' '.join(words[:word_i] + [placeholder])
                return '\n'.join(lines[:line_i] + [line])
        else:
            chars = new_chars
    else:
        # Message did not exceed max size or lines; no truncation
        print('no truncation')
        return message
    # Message exceeded max lines but not max size; truncate to line
    print('truncated lines')
    return '\n'.join(lines[:line_i]) + f' {placeholder}'

#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import pathlib
import sys
import traceback

import prettify_exceptions

from bot.other import discordlogger

logger = discordlogger.get_logger()


def exception_message(
        exc_type=None, exc_value=None, exc_traceback=None,
        header: str = '', log_handler=logger) -> str:
    """Create a message out of the last exception handled by try/except.

    Args:
        header (Optional[str]): The header to place above the message.
        log_handler (Optional): The logger to run the exception() method on.

    Returns:
        str: The string containing the exception message.

    """
    if exc_type is None and exc_value is None and exc_traceback is None:
        exc_type, exc_value, exc_traceback = sys.exc_info()
    elif exc_type is None or exc_value is None or exc_traceback is None:
        raise ValueError('An exception type/value/traceback was passed '
                         'but is missing the other values')

    # Header message with padded border
    msg = ''
    if header:
        msg = '{:=^{length}}\n'.format(
            header, length=len(header) * 2 + len(header) % 2)

    if log_handler is not None:
        # Log the exception; doesn't require creating a message
        log_handler.exception(msg)

    # Create the message to return, containing the traceback and exception
    for frame in traceback.extract_tb(exc_traceback):
        if frame.name == '<module>':
            # Bottom of the stack; stop here
            break

        msg += f'Frame {frame.name!r}\n'
        # Show only the path starting from project using instead of
        # just the full path inside frame.filename
        project_path = pathlib.Path().resolve()
        trace_path = pathlib.Path(frame.filename)
        try:
            filename = trace_path.relative_to(project_path)
        except ValueError:
            # Trace must be outside of project; use that then
            filename = trace_path

        msg += f'Within file "{filename}"\n'
        msg += f'at line number {frame.lineno}:\n'
        msg += f'   {frame.line}\n'
    msg += f'\n{exc_type.__name__}: {exc_value}'

    return msg


def exception_message_pretty(
        exc_type=None, exc_value=None, exc_traceback=None,
        header: str = '', log_handler=logger) -> str:
    """Create a traceback message using the prettify_exceptions module.
    This acts similar to `exception_message`."""
    if exc_type is None and exc_value is None and exc_traceback is None:
        exc_type, exc_value, exc_traceback = sys.exc_info()
    elif exc_type is None or exc_value is None or exc_traceback is None:
        raise ValueError('An exception type/value/traceback was passed '
                         'but is missing the other values')

    if log_handler is not None:
        log_handler.exception('')

    return '\n'.join(
        prettify_exceptions.DefaultFormatter().format_exception(
            exc_type, exc_value, exc_traceback)
    )

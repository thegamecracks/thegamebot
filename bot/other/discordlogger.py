import logging

logger = None
level = logging.INFO


def get_logger() -> logging.Logger:
    """Create or return the current logger."""
    global logger

    if logger is None:
        logger = logging.getLogger('discord')
        logger.setLevel(level)
        handler = logging.FileHandler(
            filename='discord.log', encoding='utf-8', mode='w')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        logger.addHandler(handler)

    return logger

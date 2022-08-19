# thegamebot

A personal bot with several random features such as unit conversions,
reminders, note taking, graphing, and of course, games.

## Hosting

My bot instance will not be available for public invitations, but you are
free to host this yourself and use the source code as the repository's
[license](LICENSE) permits.

### Prerequisites

- Python 3.10+
- [Poetry][1] for dependency management

### Setup instructions

1. Clone this repository

2. Create a virtual environment however you would like
   ([venv][2], [virtualenv][3], [pyenv][4], [PyCharm][5], etc.)

3. Install the bot's dependencies using poetry the `poetry install` command

4. Create a .env file and add the following entry:

```
BotToken=[your discord bot token from discord.com/developers/applications]
```

5. Disable the guild-specific cogs in main.py
    1. Find where the extension list is specified
    2. Remove any lines starting with "guild"

6. Start the bot through the `main.py` script

## License
This project is licensed under [MPL-2.0][10].

[1]: https://python-poetry.org/
[2]: https://docs.python.org/3/library/venv.html
[3]: https://virtualenv.pypa.io/en/latest/index.html
[4]: https://github.com/pyenv/pyenv
[5]: https://www.jetbrains.com/help/pycharm/creating-virtual-environment.html
[10]: https://choosealicense.com/licenses/mpl-2.0/

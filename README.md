## thegamebot
A bot that does plenty of random things such as arithmetic/unit conversions,
timezone translations, storage and recall of user-provided text, image generation,
and of course, games.

### Invitation

Since this bot is written for personal use, the bot will not be available
for public invitations. However, if you would like to host this yourself,
the instructions for doing so are listed below.

### Instructions to set up

1. Have Python 3.10 or above installed

2. Create a virtual environment, specifically with the folder name ".venv"

3. Install dependencies in your environment:

```shell
pip install -r requirements.txt
```

4. Create a .env file and add the following entries:

```
BotToken=[your discord bot token, retrieved from discord.com/developers/applications]
CatAPIKey=[optional: your api key for thecatapi.com, used in the Images cog]
DogAPIKey=[optional: your api key for thedogapi.com, used in the Images cog]
```

5. Disable the guild-specific cogs in main.py
    1. Find where the extension list is specified
    2. Remove any lines starting with "guild"

## License
This project is licensed under [MPL-2.0](https://choosealicense.com/licenses/mpl-2.0/).

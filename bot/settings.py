"""Provides functions to interact with the configuration file.

==================  ====================================================
Function            Arguments: Description
==================  ====================================================
write_setting       (key, value): Write a new value to a given setting.
load_settings       (): Return the config file as a dictionary.
get_setting         (key): Get a specific setting.
overwrite_settings  (settings: dict): Overwrite the config file.
setup               (): Initialize the config file.
update_settings     (settings: dict): Update the config file.
==================  ====================================================
"""
import json
import pathlib

SETTINGS_LOCATION = 'settings.json'


def load_settings():
    """Return the config file as a dictionary.

    Missing settings file is handled but not corrupt settings.

    """
    if not pathlib.Path(SETTINGS_LOCATION).exists():
        setup()
    with open(SETTINGS_LOCATION) as f:
        return json.load(f)


def get_setting(key):
    """Get a specific setting from the config file."""
    config = load_settings()
    return config[key]


def overwrite_settings(settings: dict):
    """Overwrite the current config file with new settings."""
    with open(SETTINGS_LOCATION, mode='w') as f:
        json.dump(
            settings, f,
            indent=4,
            sort_keys=True
        )


def update_settings(settings: dict):
    """Update the current config file with new settings."""
    config = load_settings()
    config.update(obj)
    overwrite_settings(config)


def write_setting(key, value):
    """Write a new value to a given setting in the config file."""
    config = load_settings()
    config[key] = value
    overwrite_settings(config)


def setup():
    """Generate/verify the settings and return a dictionary of it."""
    SETTINGS_DEFAULT = {
        'admin_ids': [153551102443257856, ],
        'bgtask_ListGuildsDelay': 600,
        'bgtask_RandomPresenceMinDelay': 120,
        'bgtask_RandomPresenceMaxDelay': 600,
        'bgtask_RandomPresenceOnStartup': True,
        'bgtask_RandomPresenceRandomStatusChance': 30,
        'bgtask_RandomPresences': [
            {'activity': 'watching',
             'title': 'my existential crisis'},
            {'activity': 'playing',
             'title': 'nothing'},
            {'status': 'away', 'activity': 'watching',
             'title': 'something'},
            {'status': 'dnd', 'activity': 'playing',
             'title': 'against a hacker'},
            {'activity': 'listening',
             'title': 'ASMR'},
            {'activity': 'watching',
             'title': 'you'},
            {'activity': 'watching',
             'title': 'YouTube'},
            {'activity': 'watching',
             'title': 'humanity'},
            {'activity': 'playing',
             'title': 'foobar2000'},
            {'activity': 'watching',
             'title': 'Jon Rick'},
            {'activity': 'listening',
             'title': 'a lecture'},
            {'activity': 'listening',
             'title': 'Audibill'},
            {'activity': 'watching',
             'title': 'Mitchell Keeves'},
            {'activity': 'listening',
             'title': "spiderdan's pizza"},
            {'activity': 'playing',
             'title': 'with a plane'},
            {'activity': 'watching',
             'title': 'animated toys'},
            {'activity': 'playing',
             'title': 'poker'},
            {'activity': 'watching',
             'title': 'Skillzhare'},
            {'activity': 'listening',
             'title': 'beep bop behop'},
            {'activity': 'playing',
             'title': 'as a car'},
            {'activity': 'watching',
             'title': 'my creator'},
            {'activity': 'playing',
             'title': 'with a rocket'},
            {'activity': 'playing',
             'title': 'on a computer'},
            {'activity': 'playing',
             'title': 'dueturn.py'},
            {'activity': 'playing',
             'title': 'with an arm'},
            {'activity': 'watching',
             'title': 'Copper Man'},
            {'activity': 'listening',
             'title': 'paint drying'},
            {'activity': 'playing',
             'title': 'cavejohnsonremaster.py'},
            {'activity': 'watching',
             'title': 'Wick and Warty'},
            # {'activity': 'playing',
            #  'title': ''},
            # {'status': 'online', 'activity': 'playing',
            #  'title': ''},
        ],
        'bgtask_TimestampDelay': 300,
        'default_StreamingURL': 'https://www.twitch.tv/thegamecracks',
        'deniedmessages': [
            'Nope.',
            "Not havin' it.",
            'Denied.',
            'Negative.',
            'Uh, no.',
            'Sorry, no.',
            'No go.',
            'Ineffective.',
        ],
        'message_size': 2000,
        'message_limit': 1,
        'owner_ids': [153551102443257856, ],
        'prefix': '\\',
        'print_error_mode': 'raise'  # raise, print, None
    }

    def generate_settings(filename):
        print(f'Writing new settings to {filename}')
        with open(filename, 'w') as f:
            json.dump(
                SETTINGS_DEFAULT, f,
                indent=4,
                sort_keys=True
            )
        print('Generated new settings')

    def backup():
        fn = SETTINGS_LOCATION + '.backup'
        print(f'Backing up settings to {fn}')
        with open(fn, 'w') as backup:
            with open(SETTINGS_LOCATION) as broken:
                for line in iter(broken.readline, ''):
                    backup.write(line)
        print('Backed up settings')

    # Verify integrity of settings file
    try:
        # Check that file can be found and parsed
        with open(SETTINGS_LOCATION) as f:
            settings = json.load(f)
    except FileNotFoundError:
        print('Could not find settings file')
        generate_settings(SETTINGS_LOCATION)
    except json.decoder.JSONDecodeError as e:
        print(f'Failed to parse the settings file: {e}')
        backup()
        generate_settings(SETTINGS_LOCATION)
    else:
        # Check that every key in SETTINGS_DEFAULT exists in the file
        # If a key is missing, add it
        backed_up = False
        for k, v in SETTINGS_DEFAULT.items():
            if k not in settings:
                print(f'Missing key {k!r} in settings, adding default')
                if not backed_up:
                    backup()
                    backed_up = True
                settings[k] = v
        else:
            if backed_up:
                overwrite_settings(settings)
            else:
                print('Verified settings integrity')

            return settings

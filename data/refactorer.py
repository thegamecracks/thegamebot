"""
ID: {
    'dimensions': [1, 2],
    'name': str,
    'recipes': [
        {
            'amount': AMOUNT,
            'recipe': [[ID, QUANTITY], ...],
            'requires_heat': False,
            'skills': ['Crafting 3'],
        },
        ...
    ],
    'primitive': True,
}
"""
import copy
import json


PATH = 'unturned_recipes.json'
BACKUP = 'unturned_recipes.json.backup'


def save(d):
    with open(PATH, 'w') as f:
        json.dump(
            d, f,
            indent=4,
            sort_keys=True
        )


with open(PATH) as f:
    with open(BACKUP, 'w') as fbackup:
        fbackup.write(f.read())
    f.seek(0)
    recipes = json.load(f)


# Remove name field
new_recipes = {}
for ID, entry in recipes.items():
    new_entry = copy.deepcopy(entry)

    del new_entry['name']

    new_recipes[ID] = new_entry

save(new_recipes)

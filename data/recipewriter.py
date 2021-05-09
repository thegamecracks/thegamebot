"""
ID: {
    'dimensions': [1, 2],
    'name': str,
    'recipes': [
        {
            'amount': AMOUNT,
            'recipe': [[ID, QUANTITY], ...],
            'skills': ['Crafting 3'],
            'uses_heat': False,
        },
        ...
    ],
    'primitive': True,
}
"""
#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import collections
import csv
import json


PATH = 'unturned_recipes.json'
UNTURNED_ITEM_IDS_PATH = 'unturned_item_ids.csv'


item_mapping = {}
id_mapping = {}
with open(UNTURNED_ITEM_IDS_PATH) as f:
    reader = csv.reader(f)
    header = next(reader)
    for id_, name, rarity, url in reader:
        item_mapping[name] = int(id_)
        id_mapping[int(id_)] = name
del reader, header, id_, name, rarity


def save(d):
    with open(PATH, 'w') as f:
        json.dump(
            d, f,
            indent=4,
            sort_keys=True
        )


def find_item(s):
    i = item_mapping.get(s)
    if i is None:
        try:
            s = int(s)
        except ValueError:
            return
        return id_mapping.get(s)
    return i


def find_id(s):
    try:
        n = int(s)
    except ValueError:
        return item_mapping.get(s)
    return n if n in id_mapping else None


def find_item_and_id(s):
    try:
        n = int(s)
    except ValueError:
        ID = item_mapping.get(s)
        if ID is not None:
            return s, ID
        return None, None
    name = id_mapping.get(n)
    if name is not None:
        return name, n
    return None, None


with open(PATH) as f:
    recipes = json.load(f)


while True:
    # Get item
    name = input('Name of Item: ' )
    ID = item_mapping.get(name)
    while ID is None:
        name = input('Unknown item: ')
        ID = item_mapping.get(name)
    ID = str(ID)

    # Check if recipe is already added
    if ID in recipes:
        print('This item already exists!\n')
        continue
    print(ID)

    # Get dimensions field
    dim_y, dim_x = input('Dimensions (Y X): ').split()
    dim_y, dim_x = int(dim_y), int(dim_x)

    # Get recipes
    new_recipes = []
    while input('Add a recipe? '):
        rec = []
        search = input('Recipe Item: ')
        while search:
            item_name, item_id = find_item_and_id(search)

            if item_name:
                quantity = int(input(f'{item_name} quantity: '))
                if quantity < 0:
                    print('Canceled item')
                    item = input('Recipe Item: ')
                    continue

                rec.append([item_id, quantity])

                search = input('Recipe Item: ')
            else:
                search = input('Unknown Recipe Item: ')
        amount = int(input('Crafted amount (defaults to 1): ') or 1)
        requires_heat = bool(input('Does this require heat? '))
        new_recipes.append(
            {'amount': amount, 'recipe': rec,
             'requires_heat': requires_heat}
        )
        print()

    # Get primitive status
    primitive = bool(input('Type anything to set this item as a primitive! '))

    # Get skills for all recipes
    skills = []
    s = input('Skill (press 1 to shortcut Crafting): ')
    while s:
        if s == '1':
            s = input('Crafting <?>: ')
            skills.append(f'Crafting {s}')
        else:
            skills.append(s)
        s = input('Skill: ')

    # Add skills to all recipes
    for rec in new_recipes:
        rec['skills'] = skills

    # Create and show entry
    entry = {
        'dimensions': [dim_y, dim_x],
        'primitive': primitive,
        'recipes': new_recipes,
    }
    print(ID, ':', entry)

    # Add and save entry
    recipes[ID] = entry
    save(recipes)
    print('Saved')

    print()

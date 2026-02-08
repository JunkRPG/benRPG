"""
CSV Card Importer for JunkRPG

Bulk-import cards from a CSV file into the cards/ directory and card_index.json.

Usage:
    python csv_card_importer.py input.csv [--deck deck_name] [--dry-run] [--use-name-as-id] [--generate-template]

Options:
    input.csv           Path to the CSV file to import
    --deck DECK_NAME    Create or append to a deck file in decks/
    --dry-run           Validate all rows without saving any files
    --use-name-as-id    Generate IDs from card names instead of UUIDs
    --generate-template Output a CSV template with all columns and example rows
"""

import argparse
import csv
import json
import os
import sys

from card_utils import (
    save_card_to_file, add_to_card_index, validate_all_card_fields,
    card_exists, load_card_index, _name_to_id
)
from deck_utils import resolve_deck_path


# All possible columns in the universal CSV format
# Top-level card fields
TOP_LEVEL_COLUMNS = [
    "card_type", "subclass", "blueprint_subclass", "states",
]

# Common data fields shared across card types
COMMON_DATA_FIELDS = [
    "Name", "Description", "Health", "Movement",
    "Melee Damage", "Projectile Damage", "Projectile Range",
    "Allegiance", "Special_Skill",
    "Background Image File Path", "Enemy Image File Path",
    "NPC Image File Path", "Quest Image File Path",
    "Junk Image", "Background Image",
]

# Weapon/ammo fields
WEAPON_FIELDS = [
    "Range_Type", "Range_Distance", "Include_Position", "Exclude_Adjacent",
    "Requires_Ammo", "Compatible_Ammo",
    "Ammo_Type", "Ammo_Damage", "Runout_Chance", "Compatible_Weapons",
]

# Tool/accessory fields
TOOL_FIELDS = [
    "Type", "Extra_Tool_Slots",
    "Effect_Range_Type", "Effect_Range_Distance",
    "Effect_Include_Position", "Effect_Exclude_Adjacent",
]

# Junk card fields
JUNK_FIELDS = [
    "Raw Material Value", "Refined Material Value", "Metal Value", "Wood Value",
    "Price",
    "Requirements: Raw Materials", "Requirements: Refined Materials",
    "Requirements: Wood", "Requirements: Metal", "Requirements: Specific Cards",
]

# Quest card fields
QUEST_FIELDS = [
    "Template_Text", "Placeholders",
    "Success_Conditions", "Failure_Conditions", "Rewards", "Chain_Config",
]

# Instance/Transition fields
EVENT_FIELDS = [
    "Outcomes", "Choices",
]

# Mount fields
MOUNT_FIELDS = [
    "Mount_Movement",
]

# JSON fields stored as strings in the card data
JSON_DATA_FIELDS = [
    "Outcomes", "Choices", "Placeholders",
    "Success_Conditions", "Failure_Conditions", "Rewards",
    "Chain_Config", "Upgrade_Material_Cost",
]

# 2nd state prefix fields
SECOND_STATE_FIELDS = [
    "2nd_state_Name", "2nd_state_Description", "2nd_state_Template_Text",
    "2nd_state_Type", "2nd_state_Item Image",
    "2nd_state_Use_HP", "2nd_state_Use_Placeholder",
    "2nd_state_Quest Image File Path",
    "2nd_state_Health", "2nd_state_Movement",
    "2nd_state_Melee Damage", "2nd_state_Projectile Damage",
    "2nd_state_Projectile Range",
    "2nd_state_Allegiance", "2nd_state_Special_Skill",
    "2nd_state_Background Image File Path",
    "2nd_state_Enemy Image File Path", "2nd_state_NPC Image File Path",
    "2nd_state_Outcomes", "2nd_state_Choices",
    "2nd_state_Range_Type", "2nd_state_Range_Distance",
    "2nd_state_Include_Position", "2nd_state_Exclude_Adjacent",
    "2nd_state_Requires_Ammo", "2nd_state_Compatible_Ammo",
    "2nd_state_Ammo_Type", "2nd_state_Ammo_Damage",
    "2nd_state_Runout_Chance", "2nd_state_Compatible_Weapons",
    "2nd_state_Mount_Movement",
]

ALL_DATA_FIELDS = (
    COMMON_DATA_FIELDS + WEAPON_FIELDS + TOOL_FIELDS + JUNK_FIELDS +
    QUEST_FIELDS + EVENT_FIELDS + MOUNT_FIELDS + SECOND_STATE_FIELDS
)

ALL_COLUMNS = TOP_LEVEL_COLUMNS + ALL_DATA_FIELDS


def generate_template_csv(output_path="card_import_template.csv"):
    """Generate a template CSV file with all columns and example rows."""
    examples = [
        {
            "card_type": "Enemy Card", "subclass": "", "blueprint_subclass": "",
            "states": "1", "Name": "Example Wolf", "Health": "20",
            "Movement": "5", "Melee Damage": "8", "Projectile Damage": "0",
            "Projectile Range": "0",
        },
        {
            "card_type": "NPC Card", "subclass": "", "blueprint_subclass": "",
            "states": "1", "Name": "Example Villager", "Health": "10",
            "Movement": "3", "Melee Damage": "2", "Projectile Damage": "0",
            "Allegiance": "Neutral",
        },
        {
            "card_type": "Junk Card", "subclass": "Junk_to_Weapon",
            "blueprint_subclass": "", "states": "2",
            "Name": "Example Broken Sword", "Description": "A bent blade",
            "Raw Material Value": "1", "Price": "3",
            "2nd_state_Name": "Repaired Sword", "2nd_state_Type": "Weapon",
            "2nd_state_Melee Damage": "12",
        },
        {
            "card_type": "Quest Card", "subclass": "Hunt",
            "blueprint_subclass": "", "states": "2",
            "Name": "Example Hunt Quest",
            "Template_Text": "Defeat [Enemy1] near [Location1].",
            "Placeholders": '[{"id":"Enemy1","type":"Enemy Card","spawn":true,"spawn_near":"player"}]',
            "Success_Conditions": '[{"type":"unit_death","params":{"unit":"Enemy1"}}]',
            "Failure_Conditions": '[{"type":"player_death"}]',
            "Rewards": '{"cards":["Junk1"]}',
            "2nd_state_Name": "Quest Complete",
        },
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=ALL_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        for example in examples:
            writer.writerow(example)

    print(f"Template CSV generated: {output_path}")
    print(f"  {len(ALL_COLUMNS)} columns, {len(examples)} example rows")


def parse_csv_row(row, row_num):
    """Parse a CSV row into card_data dict.

    Returns: (card_data, errors)
    """
    errors = []

    card_type = row.get("card_type", "").strip()
    if not card_type:
        errors.append(f"Row {row_num}: Missing card_type")
        return None, errors

    name = row.get("Name", "").strip()
    if not name:
        errors.append(f"Row {row_num}: Missing Name")
        return None, errors

    states = 1
    states_str = row.get("states", "1").strip()
    if states_str:
        try:
            states = int(states_str)
        except ValueError:
            errors.append(f"Row {row_num}: Invalid states value '{states_str}'")
            return None, errors

    subclass = row.get("subclass", "").strip() or None
    blueprint_subclass = row.get("blueprint_subclass", "").strip() or None

    # Build data dict from all non-empty data fields
    data = {}
    for field in ALL_DATA_FIELDS:
        value = row.get(field, "").strip()
        if value:
            data[field] = value

    card_data = {
        "card_type": card_type,
        "subclass": subclass,
        "blueprint_subclass": blueprint_subclass,
        "states": states,
        "data": data,
    }

    return card_data, errors


def validate_card(card_data, row_num):
    """Validate a parsed card. Returns list of error strings."""
    errors = []

    is_valid, validation_errors = validate_all_card_fields(card_data)
    if not is_valid:
        for err in validation_errors:
            errors.append(f"Row {row_num}: {err}")

    return errors


def import_csv(csv_path, deck_name=None, dry_run=False, use_name_as_id=False):
    """Import cards from a CSV file.

    Returns: (imported_count, skipped_count, error_messages)
    """
    if not os.path.exists(csv_path):
        return 0, 0, [f"CSV file not found: {csv_path}"]

    imported = 0
    skipped = 0
    all_errors = []
    imported_ids = []
    existing_index = load_card_index(silent=True)

    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            card_data, parse_errors = parse_csv_row(row, row_num)
            if parse_errors:
                all_errors.extend(parse_errors)
                skipped += 1
                continue

            # Validate
            validation_errors = validate_card(card_data, row_num)
            if validation_errors:
                all_errors.extend(validation_errors)
                skipped += 1
                continue

            # Check for ID collision
            if use_name_as_id:
                card_id = _name_to_id(card_data["data"].get("Name", ""))
                if card_id in existing_index or card_exists(card_id):
                    all_errors.append(f"Row {row_num}: ID collision - '{card_id}' already exists")
                    skipped += 1
                    continue

            if dry_run:
                name = card_data["data"].get("Name", "Unknown")
                print(f"  [DRY RUN] Row {row_num}: {card_data['card_type']} - {name} (OK)")
                imported += 1
                continue

            # Save card
            card_id_result, result_path = save_card_to_file(
                card_data, use_name_as_id=use_name_as_id
            )
            if card_id_result is None:
                all_errors.append(f"Row {row_num}: {result_path}")  # result_path is error msg
                skipped += 1
                continue

            # Add to index
            add_to_card_index(card_id_result, card_data)
            imported_ids.append(card_id_result)
            imported += 1
            name = card_data["data"].get("Name", "Unknown")
            print(f"  Imported: {name} -> {card_id_result}")

    # Create/update deck if requested
    if deck_name and imported_ids and not dry_run:
        _update_deck(deck_name, imported_ids)

    return imported, skipped, all_errors


def _update_deck(deck_name, card_ids):
    """Create or append to a deck file."""
    os.makedirs("decks", exist_ok=True)

    # Ensure .json extension
    if not deck_name.endswith('.json'):
        deck_name = deck_name + '.json'

    deck_path = resolve_deck_path(deck_name)
    deck_data = {"name": deck_name.replace('.json', ''), "cards": []}

    if os.path.exists(deck_path):
        try:
            with open(deck_path, 'r') as f:
                deck_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    existing_cards = set(deck_data.get("cards", []))
    new_cards = [cid for cid in card_ids if cid not in existing_cards]
    deck_data["cards"] = deck_data.get("cards", []) + new_cards

    with open(deck_path, 'w') as f:
        json.dump(deck_data, f, indent=2)

    print(f"  Deck updated: {deck_path} ({len(new_cards)} cards added, {len(deck_data['cards'])} total)")


def main():
    parser = argparse.ArgumentParser(
        description="Import cards from CSV into JunkRPG card system"
    )
    parser.add_argument("csv_file", nargs="?", help="Path to CSV file to import")
    parser.add_argument("--deck", help="Create or append to a deck file in decks/")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate all rows without saving")
    parser.add_argument("--use-name-as-id", action="store_true",
                        help="Generate IDs from card names instead of UUIDs")
    parser.add_argument("--generate-template", action="store_true",
                        help="Output a CSV template with all columns")

    args = parser.parse_args()

    if args.generate_template:
        generate_template_csv()
        return

    if not args.csv_file:
        parser.print_help()
        sys.exit(1)

    print(f"Importing cards from: {args.csv_file}")
    if args.dry_run:
        print("  (DRY RUN - no files will be created)")

    imported, skipped, errors = import_csv(
        args.csv_file,
        deck_name=args.deck,
        dry_run=args.dry_run,
        use_name_as_id=args.use_name_as_id
    )

    print(f"\nSummary: {imported} imported, {skipped} skipped")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for err in errors:
            print(f"  {err}")
        sys.exit(1 if imported == 0 else 0)


if __name__ == "__main__":
    main()

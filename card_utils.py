"""
Card Utilities - Centralized card loading with error handling for JunkRPG.

This module provides safe card loading functions that handle missing files
and invalid JSON gracefully instead of crashing.
"""

import os
import json

# The directory where card files are stored
CARDS_DIR = "cards"
CARD_INDEX_FILE = os.path.join(CARDS_DIR, "card_index.json")


class CardLoadError(Exception):
    """Exception raised when a card cannot be loaded."""
    pass


def get_card_path(card_id):
    """
    Get the full path to a card file.

    Args:
        card_id: The card identifier (filename without .json extension)

    Returns:
        Full path to the card file
    """
    if not card_id:
        return None
    return os.path.join(CARDS_DIR, f"{card_id}.json")


def card_exists(card_id):
    """
    Check if a card file exists.

    Args:
        card_id: The card identifier

    Returns:
        True if card file exists, False otherwise
    """
    path = get_card_path(card_id)
    return path is not None and os.path.exists(path)


def load_card(card_id, silent=False):
    """
    Safely load a card from file.

    Args:
        card_id: The card identifier
        silent: If True, don't print error messages

    Returns:
        Card data dictionary, or None if loading failed

    Note:
        This function never raises exceptions - it returns None on failure.
    """
    if not card_id:
        if not silent:
            print(f"Warning: Empty card_id provided")
        return None

    card_path = get_card_path(card_id)

    if not os.path.exists(card_path):
        if not silent:
            print(f"Warning: Card file not found: {card_path}")
        return None

    try:
        with open(card_path, 'r') as f:
            card_data = json.load(f)
        card_data["id"] = card_id  # Ensure ID is set
        return card_data
    except json.JSONDecodeError as e:
        if not silent:
            print(f"Error: Invalid JSON in card file {card_path}: {e}")
        return None
    except Exception as e:
        if not silent:
            print(f"Error: Failed to load card {card_path}: {e}")
        return None


def load_card_strict(card_id):
    """
    Load a card from file, raising an exception on failure.

    Args:
        card_id: The card identifier

    Returns:
        Card data dictionary

    Raises:
        CardLoadError: If the card cannot be loaded
    """
    if not card_id:
        raise CardLoadError("Empty card_id provided")

    card_path = get_card_path(card_id)

    if not os.path.exists(card_path):
        raise CardLoadError(f"Card file not found: {card_path}")

    try:
        with open(card_path, 'r') as f:
            card_data = json.load(f)
        card_data["id"] = card_id
        return card_data
    except json.JSONDecodeError as e:
        raise CardLoadError(f"Invalid JSON in card file {card_path}: {e}")
    except Exception as e:
        raise CardLoadError(f"Failed to load card {card_path}: {e}")


def load_card_index(silent=False):
    """
    Safely load the card index.

    Args:
        silent: If True, don't print error messages

    Returns:
        Card index dictionary, or empty dict if loading failed
    """
    if not os.path.exists(CARD_INDEX_FILE):
        if not silent:
            print(f"Warning: Card index not found: {CARD_INDEX_FILE}")
        return {}

    try:
        with open(CARD_INDEX_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        if not silent:
            print(f"Error: Invalid JSON in card index: {e}")
        return {}
    except Exception as e:
        if not silent:
            print(f"Error: Failed to load card index: {e}")
        return {}


def validate_card_references(card_ids, silent=False):
    """
    Validate that all card IDs reference existing files.

    Args:
        card_ids: List of card identifiers to validate
        silent: If True, don't print warnings

    Returns:
        Tuple of (valid_ids, invalid_ids)
    """
    valid = []
    invalid = []

    for card_id in card_ids:
        if card_exists(card_id):
            valid.append(card_id)
        else:
            invalid.append(card_id)
            if not silent:
                print(f"Warning: Card not found: {card_id}")

    return valid, invalid


# ========== JSON FIELD VALIDATION ==========

# Fields that should contain valid JSON
JSON_FIELDS = {
    "Outcomes",
    "2nd_state_Outcomes",
    "Choices",
    "2nd_state_Choices",
    "Placeholders",
    "Success_Conditions",
    "Failure_Conditions",
    "Rewards",
    "Upgrade_Material_Cost",
}

# Valid values for weapon/ammunition system fields
VALID_RANGE_TYPES = {"line_of_sight", "area_effect", "echo", "multi_echo", "perimeter", "mist_shadow"}
VALID_AMMO_TYPES = {"Arrow", "Bolt", "Stone", "Bullet", "Dart", "None", ""}
VALID_BOOL_VALUES = {"true", "false", "True", "False", ""}
VALID_ACCESSORY_TYPES = {"Tool", "Tool_Belt", "Accessory", "Belt", "Pouch"}


def validate_json_string(value, field_name="field"):
    """
    Validate that a string contains valid JSON.

    Args:
        value: The string to validate
        field_name: Name of the field (for error messages)

    Returns:
        Tuple of (is_valid, parsed_value_or_error_message)
        - If valid: (True, parsed JSON object)
        - If invalid: (False, error message string)
    """
    if not value or value.strip() == "":
        # Empty is valid (will be treated as empty array/object)
        return True, None

    try:
        parsed = json.loads(value)
        return True, parsed
    except json.JSONDecodeError as e:
        # Create a user-friendly error message
        error_msg = f"{field_name}: Invalid JSON - {e.msg} at position {e.pos}"
        return False, error_msg


def validate_json_array(value, field_name="field"):
    """
    Validate that a string contains a valid JSON array.

    Args:
        value: The string to validate
        field_name: Name of the field (for error messages)

    Returns:
        Tuple of (is_valid, parsed_array_or_error_message)
    """
    if not value or value.strip() == "":
        return True, []

    is_valid, result = validate_json_string(value, field_name)
    if not is_valid:
        return False, result

    if result is not None and not isinstance(result, list):
        return False, f"{field_name}: Expected JSON array, got {type(result).__name__}"

    return True, result if result is not None else []


def validate_json_object(value, field_name="field"):
    """
    Validate that a string contains a valid JSON object.

    Args:
        value: The string to validate
        field_name: Name of the field (for error messages)

    Returns:
        Tuple of (is_valid, parsed_object_or_error_message)
    """
    if not value or value.strip() == "":
        return True, {}

    is_valid, result = validate_json_string(value, field_name)
    if not is_valid:
        return False, result

    if result is not None and not isinstance(result, dict):
        return False, f"{field_name}: Expected JSON object, got {type(result).__name__}"

    return True, result if result is not None else {}


def validate_card_json_fields(card_data):
    """
    Validate all JSON fields in a card's data.

    Args:
        card_data: Dictionary containing card data with a "data" key

    Returns:
        Tuple of (is_valid, list_of_errors)
        - If all valid: (True, [])
        - If errors: (False, ["error1", "error2", ...])
    """
    errors = []
    data = card_data.get("data", {})

    # Fields that should be arrays
    array_fields = {
        "Outcomes", "2nd_state_Outcomes",
        "Choices", "2nd_state_Choices",
        "Placeholders",
        "Success_Conditions", "Failure_Conditions"
    }

    # Fields that should be objects
    object_fields = {
        "Rewards", "Upgrade_Material_Cost"
    }

    for field_name in array_fields:
        if field_name in data and data[field_name]:
            is_valid, result = validate_json_array(data[field_name], field_name)
            if not is_valid:
                errors.append(result)

    for field_name in object_fields:
        if field_name in data and data[field_name]:
            is_valid, result = validate_json_object(data[field_name], field_name)
            if not is_valid:
                errors.append(result)

    return len(errors) == 0, errors


def get_json_field_help(field_name):
    """
    Get example JSON format for a specific field.

    Args:
        field_name: Name of the JSON field

    Returns:
        String with example format
    """
    examples = {
        "Outcomes": '[{"probability": 0.5, "type": "damage_player", "text": "You take damage!", "params": {"damage": 5}}]',
        "2nd_state_Outcomes": '[{"probability": 1.0, "type": "none", "text": "Nothing happens."}]',
        "Choices": '[{"name": "Search", "action": "draw_card", "costs_action": true, "params": {"deck": "junk_deck.json"}}]',
        "2nd_state_Choices": '[{"name": "Leave", "action": "close", "costs_action": false}]',
        "Placeholders": '[{"id": "NPC1", "type": "NPC Card", "count": 1, "spawn": true, "spawn_near": "player"}]',
        "Success_Conditions": '[{"type": "unit_death", "params": {"unit_id": "NPC1"}}]',
        "Failure_Conditions": '[{"type": "player_death"}]',
        "Rewards": '{"experience": 100, "cards": ["reward_card_id"]}',
        "Upgrade_Material_Cost": '{"metal": 10, "wood": 5}',
    }
    return examples.get(field_name, "[]")


# ========== WEAPON/AMMUNITION FIELD VALIDATION ==========

def validate_weapon_fields(card_data):
    """
    Validate weapon-specific fields (range properties, ammo requirements).

    Args:
        card_data: Dictionary containing card data with a "data" key

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    data = card_data.get("data", {})

    # Check range type validity
    for prefix in ["", "2nd_state_"]:
        range_type = data.get(f"{prefix}Range_Type", "")
        if range_type and range_type not in VALID_RANGE_TYPES:
            errors.append(f"{prefix}Range_Type: Invalid value '{range_type}'. Valid: {', '.join(VALID_RANGE_TYPES)}")

        # Validate boolean fields
        for bool_field in ["Include_Position", "Exclude_Adjacent", "Requires_Ammo"]:
            value = data.get(f"{prefix}{bool_field}", "")
            if value and str(value).lower() not in VALID_BOOL_VALUES:
                errors.append(f"{prefix}{bool_field}: Expected 'true' or 'false', got '{value}'")

        # Validate Range_Distance is numeric
        range_dist = data.get(f"{prefix}Range_Distance", "")
        if range_dist:
            try:
                int(range_dist)
            except ValueError:
                errors.append(f"{prefix}Range_Distance: Expected integer, got '{range_dist}'")

    return len(errors) == 0, errors


def validate_ammunition_fields(card_data):
    """
    Validate ammunition-specific fields.

    Args:
        card_data: Dictionary containing card data with a "data" key

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    data = card_data.get("data", {})

    for prefix in ["", "2nd_state_"]:
        # Check ammo type validity
        ammo_type = data.get(f"{prefix}Ammo_Type", "")
        if ammo_type and ammo_type not in VALID_AMMO_TYPES:
            errors.append(f"{prefix}Ammo_Type: Invalid value '{ammo_type}'. Valid: {', '.join(VALID_AMMO_TYPES)}")

        # Validate Ammo_Damage is numeric
        ammo_damage = data.get(f"{prefix}Ammo_Damage", "")
        if ammo_damage:
            try:
                int(ammo_damage)
            except ValueError:
                errors.append(f"{prefix}Ammo_Damage: Expected integer, got '{ammo_damage}'")

        # Validate Runout_Chance is numeric and in range
        runout = data.get(f"{prefix}Runout_Chance", "")
        if runout:
            try:
                val = int(runout)
                if val < 0 or val > 100:
                    errors.append(f"{prefix}Runout_Chance: Value {val} out of range (0-100)")
            except ValueError:
                errors.append(f"{prefix}Runout_Chance: Expected integer (0-100), got '{runout}'")

    return len(errors) == 0, errors


def validate_accessory_fields(card_data):
    """
    Validate accessory/tool belt fields.

    Args:
        card_data: Dictionary containing card data with a "data" key

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    data = card_data.get("data", {})

    for prefix in ["", "2nd_state_"]:
        # Validate Extra_Tool_Slots is numeric and reasonable
        extra_slots = data.get(f"{prefix}Extra_Tool_Slots", "")
        if extra_slots:
            try:
                val = int(extra_slots)
                if val < 0 or val > 5:
                    errors.append(f"{prefix}Extra_Tool_Slots: Value {val} out of range (0-5)")
            except ValueError:
                errors.append(f"{prefix}Extra_Tool_Slots: Expected integer (0-5), got '{extra_slots}'")

    return len(errors) == 0, errors


def validate_effect_range_fields(card_data):
    """
    Validate effect range fields for tools and consumables (healing at range, etc.).

    Args:
        card_data: Dictionary containing card data with a "data" key

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    data = card_data.get("data", {})

    for prefix in ["", "2nd_state_"]:
        # Validate Effect_Range_Type
        range_type = data.get(f"{prefix}Effect_Range_Type", "")
        if range_type and range_type not in VALID_RANGE_TYPES:
            errors.append(f"{prefix}Effect_Range_Type: Invalid value '{range_type}'. Valid: {', '.join(VALID_RANGE_TYPES)}")

        # Validate Effect_Range_Distance is numeric
        range_dist = data.get(f"{prefix}Effect_Range_Distance", "")
        if range_dist:
            try:
                val = int(range_dist)
                if val < 0 or val > 20:
                    errors.append(f"{prefix}Effect_Range_Distance: Value {val} out of reasonable range (0-20)")
            except ValueError:
                errors.append(f"{prefix}Effect_Range_Distance: Expected integer, got '{range_dist}'")

        # Validate boolean fields
        include_pos = data.get(f"{prefix}Effect_Include_Position", "")
        if include_pos and include_pos not in VALID_BOOL_VALUES:
            errors.append(f"{prefix}Effect_Include_Position: Expected 'true' or 'false', got '{include_pos}'")

        exclude_adj = data.get(f"{prefix}Effect_Exclude_Adjacent", "")
        if exclude_adj and exclude_adj not in VALID_BOOL_VALUES:
            errors.append(f"{prefix}Effect_Exclude_Adjacent: Expected 'true' or 'false', got '{exclude_adj}'")

    return len(errors) == 0, errors


def validate_all_card_fields(card_data):
    """
    Comprehensive validation of all card fields including JSON and weapon/ammo fields.

    Args:
        card_data: Dictionary containing card data

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    all_errors = []

    # Validate JSON fields
    is_valid, errors = validate_card_json_fields(card_data)
    all_errors.extend(errors)

    # Validate weapon fields if applicable
    is_valid, errors = validate_weapon_fields(card_data)
    all_errors.extend(errors)

    # Validate ammunition fields if applicable
    is_valid, errors = validate_ammunition_fields(card_data)
    all_errors.extend(errors)

    # Validate accessory fields if applicable
    is_valid, errors = validate_accessory_fields(card_data)
    all_errors.extend(errors)

    # Validate effect range fields for tools/consumables
    is_valid, errors = validate_effect_range_fields(card_data)
    all_errors.extend(errors)

    return len(all_errors) == 0, all_errors

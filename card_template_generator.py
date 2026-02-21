"""
Card Template Generator for JunkRPG

Generate multiple card variants from a JSON template with randomized stats.

Usage:
    python card_template_generator.py template.json [--count 20] [--deck deck_name]
                                                     [--seed 42] [--use-name-as-id]
                                                     [--dry-run]

Template config files are stored in card_templates/ directory.
"""

import argparse
import json
import math
import os
import random
import sys

from card_utils import (
    save_card_to_file, add_to_card_index, validate_all_card_fields,
    card_exists, _name_to_id
)
from deck_utils import resolve_deck_path


def generate_name(naming_config, index, rng):
    """Generate a card name based on naming mode.

    Args:
        naming_config: Dict with mode, base_name, prefixes/suffixes/names
        index: Card index (0-based)
        rng: Random instance

    Returns:
        Generated name string
    """
    mode = naming_config.get("mode", "sequential")
    base_name = naming_config.get("base_name", "Card")

    if mode == "prefix_list":
        prefixes = naming_config.get("prefixes", [])
        if prefixes:
            prefix = rng.choice(prefixes)
            return f"{prefix} {base_name}"
        return f"{base_name} #{index + 1}"

    elif mode == "suffix_list":
        suffixes = naming_config.get("suffixes", [])
        if suffixes:
            suffix = rng.choice(suffixes)
            return f"{base_name} {suffix}"
        return f"{base_name} #{index + 1}"

    elif mode == "name_list":
        names = naming_config.get("names", [])
        if names:
            return names[index % len(names)]
        return f"{base_name} #{index + 1}"

    else:  # sequential
        return f"{base_name} #{index + 1}"


def _resolve_randomizable(value, rng):
    """Recursively resolve values that may contain randomization directives.

    Conventions:
        {"min": X, "max": Y} -> random int (if both int) or float
        {"min": X, "max": Y, "decimals": N} -> random float with N decimals
        {"options": [a, b, c]} -> random choice from list
        dict -> recursively resolve values
        list -> recursively resolve items
        primitive -> pass through
    """
    if isinstance(value, dict):
        keys = set(value.keys())
        if keys <= {"min", "max", "decimals"} and "min" in value and "max" in value:
            if "decimals" in value or isinstance(value["min"], float) or isinstance(value["max"], float):
                decimals = value.get("decimals", 2)
                return round(rng.uniform(float(value["min"]), float(value["max"])), decimals)
            return rng.randint(value["min"], value["max"])
        if keys == {"options"}:
            return rng.choice(value["options"])
        return {k: _resolve_randomizable(v, rng) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_randomizable(item, rng) for item in value]
    return value


def _resolve_json_template(field_config, generated_fields, rng):
    """Resolve a json_template field to a JSON string.

    Supported template_modes:
        outcome_pool - Pick outcomes from a weighted pool (Instance/Transition cards)
        placeholder_pool - Pick quest placeholders from a pool
        condition_pool - Pick quest conditions from a pool
        rewards - Generate rewards object from a template
        chain_config - Generate chain config object from a template
        fixed - Serialize a fixed JSON value
    """
    mode = field_config.get("template_mode", "outcome_pool")

    if mode == "outcome_pool":
        return _gen_outcome_pool(field_config, rng)
    elif mode == "placeholder_pool":
        return _gen_placeholder_pool(field_config, rng)
    elif mode == "condition_pool":
        return _gen_condition_pool(field_config, rng)
    elif mode == "rewards":
        return _gen_rewards(field_config, rng)
    elif mode == "chain_config":
        return _gen_chain_config(field_config, rng)
    elif mode == "fixed":
        return json.dumps(field_config.get("value", []))
    return json.dumps([])


def _gen_outcome_pool(field_config, rng):
    """Generate outcomes JSON by picking from a weighted pool of possible outcomes.

    Each pool entry: {type, text_options, params, weight}
    Params values can use randomization directives (min/max, options).
    """
    pool = field_config.get("outcome_pool", [])
    pick_config = field_config.get("pick_count", {"min": 3, "max": 5})
    auto_balance = field_config.get("auto_balance_probabilities", True)
    allow_dupes = field_config.get("allow_duplicate_types", False)

    if isinstance(pick_config, dict):
        pick_count = rng.randint(pick_config["min"], pick_config["max"])
    else:
        pick_count = int(pick_config)

    if not pool:
        return json.dumps([])

    if not allow_dupes:
        pick_count = min(pick_count, len(pool))

    # Weighted selection
    weights = [entry.get("weight", 1) for entry in pool]

    if allow_dupes:
        selected = rng.choices(pool, weights=weights, k=pick_count)
    else:
        # Sample without replacement using weights
        selected = []
        available_indices = list(range(len(pool)))
        avail_weights = list(weights)
        for _ in range(pick_count):
            if not available_indices:
                break
            picks = rng.choices(range(len(available_indices)),
                                weights=avail_weights, k=1)
            idx = picks[0]
            selected.append(pool[available_indices[idx]])
            available_indices.pop(idx)
            avail_weights.pop(idx)

    # Build outcome objects
    outcomes = []
    for entry in selected:
        text_options = entry.get("text_options", [""])
        text = rng.choice(text_options) if text_options else ""

        params = _resolve_randomizable(entry.get("params", {}), rng)

        outcome = {
            "probability": 0.0,
            "type": entry.get("type", "none"),
            "text": text,
            "params": params
        }
        outcomes.append(outcome)

    # Auto-balance probabilities to sum to 1.0
    if auto_balance and outcomes:
        raw_weights = [rng.random() + 0.1 for _ in outcomes]
        total = sum(raw_weights)
        for i, outcome in enumerate(outcomes):
            outcome["probability"] = round(raw_weights[i] / total, 2)
        # Fix rounding error
        diff = round(1.0 - sum(o["probability"] for o in outcomes), 2)
        outcomes[0]["probability"] = round(outcomes[0]["probability"] + diff, 2)

    return json.dumps(outcomes)


def _gen_placeholder_pool(field_config, rng):
    """Generate quest placeholders JSON from a pool of definitions."""
    pool = field_config.get("placeholder_pool", [])
    pick_config = field_config.get("pick_count", {"min": 1, "max": 3})

    if isinstance(pick_config, dict):
        pick_count = rng.randint(pick_config["min"], pick_config["max"])
    else:
        pick_count = int(pick_config)

    pick_count = min(pick_count, len(pool))
    selected = rng.sample(pool, pick_count) if pool else []

    return json.dumps([_resolve_randomizable(entry, rng) for entry in selected])


def _gen_condition_pool(field_config, rng):
    """Generate quest conditions JSON from a pool of definitions."""
    pool = field_config.get("condition_pool", [])
    pick_config = field_config.get("pick_count", {"min": 1, "max": 2})

    if isinstance(pick_config, dict):
        pick_count = rng.randint(pick_config["min"], pick_config["max"])
    else:
        pick_count = int(pick_config)

    pick_count = min(pick_count, len(pool))
    selected = rng.sample(pool, pick_count) if pool else []

    return json.dumps([_resolve_randomizable(entry, rng) for entry in selected])


def _gen_rewards(field_config, rng):
    """Generate quest rewards JSON object from a template."""
    template = field_config.get("rewards_template", {})
    return json.dumps(_resolve_randomizable(template, rng))


def _gen_chain_config(field_config, rng):
    """Generate quest chain config JSON object from a template."""
    template = field_config.get("chain_template", {})
    return json.dumps(_resolve_randomizable(template, rng))


def resolve_field_value(field_config, generated_fields, rng):
    """Resolve a field value based on its type config.

    Args:
        field_config: Dict with type and value parameters
        generated_fields: Already-generated fields (for scaled type)
        rng: Random instance

    Returns:
        String value for the field
    """
    field_type = field_config.get("type", "fixed")

    if field_type == "fixed":
        return str(field_config.get("value", ""))

    elif field_type == "int":
        min_val = field_config.get("min", 0)
        max_val = field_config.get("max", 100)
        return str(rng.randint(min_val, max_val))

    elif field_type == "float":
        min_val = field_config.get("min", 0.0)
        max_val = field_config.get("max", 1.0)
        decimals = field_config.get("decimals", 1)
        val = rng.uniform(min_val, max_val)
        return str(round(val, decimals))

    elif field_type == "choice":
        options = field_config.get("options", [""])
        return str(rng.choice(options))

    elif field_type == "scaled":
        base_field = field_config.get("base_field", "")
        multiplier = field_config.get("multiplier", 1.0)
        base_val = generated_fields.get(base_field, "0")
        try:
            result = float(base_val) * multiplier
            return str(int(math.floor(result)))
        except (ValueError, TypeError):
            return "0"

    elif field_type == "text_choice":
        options = field_config.get("options", [""])
        text = str(rng.choice(options))
        # Substitute {FieldName} references with already-generated values
        for key, val in generated_fields.items():
            text = text.replace(f"{{{key}}}", str(val))
        return text

    elif field_type == "json_template":
        return _resolve_json_template(field_config, generated_fields, rng)

    elif field_type == "json_string":
        return json.dumps(field_config.get("value", ""))

    return str(field_config.get("value", ""))


def generate_card(template, index, rng):
    """Generate a single card from a template.

    Args:
        template: Template config dict
        index: Card index (0-based)
        rng: Random instance

    Returns:
        (card_data, name) tuple
    """
    card_type = template.get("card_type", "Enemy Card")
    states = template.get("states", 1)
    subclass = template.get("subclass", None)
    blueprint_subclass = template.get("blueprint_subclass", None)

    # Generate name
    naming = template.get("naming", {"mode": "sequential", "base_name": "Card"})
    name = generate_name(naming, index, rng)

    # Generate state 1 fields
    fields_config = template.get("fields", {})
    generated = {"Name": name}

    # First pass: non-scaled fields
    for field_name, field_config in fields_config.items():
        if field_config.get("type") != "scaled":
            generated[field_name] = resolve_field_value(field_config, generated, rng)

    # Second pass: scaled fields (depend on other fields)
    for field_name, field_config in fields_config.items():
        if field_config.get("type") == "scaled":
            generated[field_name] = resolve_field_value(field_config, generated, rng)

    # Build data dict
    data = {}
    data["Name"] = name
    for field_name, value in generated.items():
        if field_name != "Name":
            data[field_name] = value

    # Generate state 2 fields if applicable
    if states >= 2:
        state2_config = template.get("state2_fields", {})
        state2_generated = {}

        # Non-scaled first
        for field_name, field_config in state2_config.items():
            if field_config.get("type") != "scaled":
                state2_generated[field_name] = resolve_field_value(
                    field_config, {**generated, **state2_generated}, rng
                )

        # Scaled second
        for field_name, field_config in state2_config.items():
            if field_config.get("type") == "scaled":
                state2_generated[field_name] = resolve_field_value(
                    field_config, {**generated, **state2_generated}, rng
                )

        for field_name, value in state2_generated.items():
            # Auto-prefix with 2nd_state_ if not already prefixed
            if not field_name.startswith("2nd_state_"):
                data[f"2nd_state_{field_name}"] = value
            else:
                data[field_name] = value

    card_data = {
        "card_type": card_type,
        "subclass": subclass,
        "blueprint_subclass": blueprint_subclass,
        "states": states,
        "data": data,
    }

    return card_data, name


def generate_cards(template_path, count=None, deck_name=None, seed=None,
                   use_name_as_id=False, dry_run=False):
    """Generate cards from a template file.

    Returns: (generated_count, skipped_count, error_messages)
    """
    if not os.path.exists(template_path):
        return 0, 0, [f"Template file not found: {template_path}"]

    try:
        with open(template_path, 'r') as f:
            template = json.load(f)
    except json.JSONDecodeError as e:
        return 0, 0, [f"Invalid JSON in template: {e}"]

    # Override count if specified on command line
    if count is None:
        count = template.get("count", 10)

    # Override deck if specified on command line
    if deck_name is None:
        deck_name = template.get("deck")

    # Set up RNG
    rng = random.Random(seed)

    generated = 0
    skipped = 0
    all_errors = []
    generated_ids = []
    used_names = set()

    template_name = template.get("template_name", "Unknown")
    print(f"Template: {template_name}")
    print(f"Generating {count} cards of type: {template.get('card_type', 'Unknown')}")

    for i in range(count):
        card_data, name = generate_card(template, i, rng)

        # Ensure unique names
        original_name = name
        suffix = 1
        while name in used_names:
            suffix += 1
            name = f"{original_name} {suffix}"
            card_data["data"]["Name"] = name
        used_names.add(name)

        # Validate
        is_valid, errors = validate_all_card_fields(card_data)
        if not is_valid:
            for err in errors:
                all_errors.append(f"Card '{name}': {err}")
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY RUN] {name}: {_summarize_stats(card_data)}")
            generated += 1
            continue

        # Check collision
        if use_name_as_id:
            card_id = _name_to_id(name)
            if card_exists(card_id):
                all_errors.append(f"Card '{name}': ID collision - '{card_id}' already exists")
                skipped += 1
                continue

        # Save
        card_id, result_path = save_card_to_file(
            card_data, use_name_as_id=use_name_as_id
        )
        if card_id is None:
            all_errors.append(f"Card '{name}': {result_path}")
            skipped += 1
            continue

        add_to_card_index(card_id, card_data)
        generated_ids.append(card_id)
        generated += 1
        print(f"  Created: {name} -> {card_id}")

    # Create/update deck
    if deck_name and generated_ids and not dry_run:
        _update_deck(deck_name, generated_ids)

    return generated, skipped, all_errors


def _summarize_stats(card_data):
    """Create a brief summary of card stats for dry-run output."""
    data = card_data.get("data", {})
    parts = []
    for field in ["Health", "Movement", "Melee Damage", "Projectile Damage"]:
        val = data.get(field)
        if val and val != "0":
            parts.append(f"{field}={val}")
    # Summarize narrative card JSON fields
    for field in ["Outcomes", "Placeholders", "Success_Conditions",
                   "Failure_Conditions", "Choices"]:
        val = data.get(field)
        if val:
            try:
                items = json.loads(val)
                if isinstance(items, list):
                    parts.append(f"{field}: {len(items)} items")
            except (json.JSONDecodeError, TypeError):
                pass
    if data.get("Description"):
        desc = data["Description"]
        if len(desc) > 40:
            desc = desc[:37] + "..."
        parts.append(f'"{desc}"')
    return ", ".join(parts) if parts else "(no stats)"


def _update_deck(deck_name, card_ids):
    """Create or append to a deck file."""
    os.makedirs("decks", exist_ok=True)

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
        description="Generate card variants from a JSON template for JunkRPG"
    )
    parser.add_argument("template", help="Path to template JSON file")
    parser.add_argument("--count", type=int, help="Number of cards to generate (overrides template)")
    parser.add_argument("--deck", help="Create or append to a deck file in decks/")
    parser.add_argument("--seed", type=int, help="Random seed for reproducible generation")
    parser.add_argument("--use-name-as-id", action="store_true",
                        help="Generate IDs from card names instead of UUIDs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be generated without saving")

    args = parser.parse_args()

    generated, skipped, errors = generate_cards(
        args.template,
        count=args.count,
        deck_name=args.deck,
        seed=args.seed,
        use_name_as_id=args.use_name_as_id,
        dry_run=args.dry_run
    )

    print(f"\nSummary: {generated} generated, {skipped} skipped")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for err in errors:
            print(f"  {err}")
        sys.exit(1 if generated == 0 else 0)


if __name__ == "__main__":
    main()

import json
import os
import datetime
import random
import logging
from inventory_card import InventoryCard
from card_utils import load_card, load_card_index
from deck_utils import resolve_deck_path

logger = logging.getLogger("JunkRPG")


class CardManager:
    def __init__(self):
        self.card_types = ["Junk Card", "Document Card", "Enemy Card", "NPC Card", "Location Card", "Quest Card", "Instance Card", "Boss Card"]

    def get_cards_for_game(self, card_type=None, filters=None):
        index = load_card_index()
        if not index:
            return []

        cards = []
        for card_id, info in index.items():
            if card_type and info['type'] != card_type:
                continue
            card_data = load_card(card_id, silent=True)
            if not card_data:
                continue
            if filters and not self._apply_filters(card_data, filters):
                continue
            is_valid, _ = self.validate_card_for_game(card_data)
            if is_valid:
                cards.append(card_data)
        return cards

    def _apply_filters(self, card_data, filters):
        for field, condition in filters.items():
            if field not in card_data['data']:
                return False
            value = card_data['data'][field]
            if isinstance(condition, str) and condition.startswith(('>', '<', '=')):
                try:
                    operator = condition[0]
                    threshold = float(condition[1:])
                    value = float(value)
                    if operator == '>' and value <= threshold:
                        return False
                    elif operator == '<' and value >= threshold:
                        return False
                    elif operator == '=' and value != threshold:
                        return False
                except ValueError:
                    return False
            elif value != condition:
                return False
        return True

    def validate_card_for_game(self, card_data):
        required_fields = {
            "Enemy Card": ["Name", "Health", "Movement", "Melee Damage"],
            "Boss Card": ["Name", "Health", "Movement", "Melee Damage"],
            "NPC Card": ["Name", "Health", "Movement", "Melee Damage", "Allegiance (Hostile, Neutral, Allied)"],
            "Location Card": ["Name"],
            "Junk Card": ["Name"],
            "Document Card": ["Name"],
            "Quest Card": ["Name", "Template_Text"],
            "Instance Card": ["Name", "Outcomes"],
            "Transition Card": ["Name", "Outcomes"]
        }
        card_type = card_data.get("card_type")
        if card_type not in required_fields:
            return False, f"Unsupported card type: {card_type}"
        data = card_data.get("data", {})
        missing_fields = [field for field in required_fields[card_type] if field not in data or not data[field]]
        if missing_fields:
            return False, f"Missing fields: {', '.join(missing_fields)}"
        numeric_fields = {
            "Enemy Card": ["Health", "Movement", "Melee Damage", "Projectile Damage", "Projectile Range"],
            "Boss Card": ["Health", "Movement", "Melee Damage", "Projectile Damage", "Projectile Range"],
            "NPC Card": ["Health", "Movement", "Melee Damage", "Projectile Damage", "Projectile Range"]
        }
        if card_type in numeric_fields:
            for field in numeric_fields[card_type]:
                if field in data and data[field]:
                    try:
                        value = float(data[field])
                        if value < 0:
                            return False, f"Invalid {field}: must be non-negative"
                    except ValueError:
                        return False, f"Invalid numeric {field}"
        return True, "Valid"

    def draw_from_deck(self, deck_file):
        """Draw a random card from a deck file and return it as an InventoryCard."""
        try:
            with open(deck_file, 'r') as f:
                deck_data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading deck {deck_file}: {e}")
            return None

        cards = deck_data.get("cards", [])
        if not cards:
            return None

        card_id = random.choice(cards)
        card_data = load_card(card_id)
        if not card_data:
            return None
        return InventoryCard(card_data)

    def track_card_usage(self, card_id, usage_context):
        usage_log = os.path.join("cards", "usage_log.json")
        try:
            if os.path.exists(usage_log):
                with open(usage_log, 'r') as f:
                    usage_data = json.load(f)
            else:
                usage_data = {}
            if card_id not in usage_data:
                usage_data[card_id] = []
            usage_data[card_id].append({"timestamp": datetime.datetime.now().isoformat(), "context": usage_context})
            with open(usage_log, 'w') as f:
                json.dump(usage_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error with usage log: {e}")

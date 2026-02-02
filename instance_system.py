"""
Instance System for JunkRPG
Handles random event cards that trigger during gameplay with multiple possible outcomes.
"""

import json
import random
import os


class InstanceCard:
    """Wrapper for instance card data."""

    def __init__(self, card_data):
        self.card_data = card_data
        self.card_id = card_data.get("id", "unknown")
        self.name = card_data.get("data", {}).get("Name", "Unknown Event")
        self.description = card_data.get("data", {}).get("Description", "")
        self.image_path = card_data.get("data", {}).get("Image_File_Path", "")
        self.subclass = card_data.get("subclass", "Environmental")

        # Parse outcomes from JSON string
        outcomes_raw = card_data.get("data", {}).get("Outcomes", "[]")
        if isinstance(outcomes_raw, str):
            try:
                self.outcomes = json.loads(outcomes_raw)
            except json.JSONDecodeError:
                print(f"Error parsing outcomes for instance card: {self.name}")
                self.outcomes = []
        else:
            self.outcomes = outcomes_raw if outcomes_raw else []

    def roll_outcome(self):
        """Weighted random selection of outcome. Returns the selected outcome dict."""
        if not self.outcomes:
            return {"probability": 1.0, "type": "none", "text": "Nothing happens.", "params": {}}

        # Normalize probabilities
        total_prob = sum(outcome.get("probability", 0) for outcome in self.outcomes)
        if total_prob <= 0:
            return random.choice(self.outcomes)

        # Roll for outcome
        roll = random.random() * total_prob
        cumulative = 0

        for outcome in self.outcomes:
            cumulative += outcome.get("probability", 0)
            if roll <= cumulative:
                return outcome

        # Fallback to last outcome
        return self.outcomes[-1]


class InstanceManager:
    """Manages instance card deck, triggers, and outcome resolution."""

    def __init__(self, card_manager, hex_grid=None):
        self.card_manager = card_manager
        self.hex_grid = hex_grid
        self.instance_deck = []  # Available instance cards
        self.trigger_chance = 0.0  # Instances are triggered by cards/locations, not randomly
        self.pending_instance = None  # Card waiting for resolution
        self.pending_outcome = None  # Outcome waiting for resolution
        self.pending_choice = None  # Player choice waiting for input
        self.last_result_text = ""  # Last outcome result for display

    def set_hex_grid(self, hex_grid):
        """Set the hex grid reference (called when game starts)."""
        self.hex_grid = hex_grid

    def set_trigger_chance(self, chance):
        """Set by transition card or level settings."""
        self.trigger_chance = max(0.0, min(1.0, chance))

    def load_instance_deck(self, deck_file):
        """Load instance cards from a deck file."""
        self.instance_deck = []

        # Try both deck locations for compatibility
        if deck_file.startswith("cards") or os.path.sep in deck_file:
            deck_path = deck_file
        else:
            deck_path = os.path.join("cards", "decks", deck_file)
            if not os.path.exists(deck_path):
                deck_path = os.path.join("decks", deck_file)

        try:
            with open(deck_path, 'r') as f:
                deck_data = json.load(f)
        except Exception as e:
            print(f"Error loading instance deck {deck_path}: {e}")
            return False

        card_ids = deck_data.get("cards", [])
        for card_id in card_ids:
            card_file = os.path.join("cards", f"{card_id}.json")
            try:
                with open(card_file, 'r') as f:
                    card_data = json.load(f)

                if card_data.get("card_type") == "Instance Card":
                    card_data["id"] = card_id
                    self.instance_deck.append(InstanceCard(card_data))
            except Exception as e:
                print(f"Error loading instance card {card_id}: {e}")

        print(f"Loaded {len(self.instance_deck)} instance cards from {deck_file}")
        return len(self.instance_deck) > 0

    def add_instance_card(self, card_data):
        """Add a single instance card to the deck."""
        if card_data.get("card_type") == "Instance Card":
            self.instance_deck.append(InstanceCard(card_data))

    def check_trigger(self):
        """Roll to see if an instance event triggers. Returns InstanceCard or None."""
        if not self.instance_deck:
            return None

        if random.random() < self.trigger_chance:
            # Draw a random instance card
            instance_card = random.choice(self.instance_deck)
            self.pending_instance = instance_card
            return instance_card

        return None

    def resolve_instance(self, instance_card, hex_grid, player):
        """Roll for outcome and apply effects. Returns (outcome_text, needs_player_choice)."""
        if not instance_card:
            return "Nothing happens.", False

        outcome = instance_card.roll_outcome()
        self.pending_outcome = outcome

        outcome_type = outcome.get("type", "none")
        outcome_text = outcome.get("text", "Something happens...")
        params = outcome.get("params", {})

        # Check if this outcome requires player choice
        if outcome_type == "player_choice":
            self.pending_choice = params.get("choices", [])
            return outcome_text, True

        # Apply the outcome immediately
        result_text = self.apply_outcome(outcome_type, params, hex_grid, player)
        self.last_result_text = result_text
        self.pending_instance = None
        self.pending_outcome = None

        return f"{outcome_text}\n{result_text}" if result_text else outcome_text, False

    def resolve_player_choice(self, choice_index, hex_grid, player):
        """Resolve the player's choice with risk/reward. Returns result_text."""
        if not self.pending_choice or choice_index >= len(self.pending_choice):
            self.clear_pending()
            return "Invalid choice."

        choice = self.pending_choice[choice_index]
        choice_name = choice.get("name", "Unknown")
        risk = choice.get("risk", 0)

        result_text = f"You chose: {choice_name}\n"

        # Roll for success/failure based on risk
        if risk > 0 and random.random() < risk:
            # Failure
            failure = choice.get("failure", {})
            failure_type = failure.get("type", "none")
            failure_params = {k: v for k, v in failure.items() if k != "type"}
            effect_text = self.apply_outcome(failure_type, failure_params, hex_grid, player)
            result_text += f"Failed! {effect_text}"
        else:
            # Success (or no risk)
            success = choice.get("success", choice.get("effect", {}))
            success_type = success.get("type", "none")
            success_params = {k: v for k, v in success.items() if k != "type"}
            effect_text = self.apply_outcome(success_type, success_params, hex_grid, player)
            if risk > 0:
                result_text += f"Success! {effect_text}"
            else:
                result_text += effect_text

        self.last_result_text = result_text
        self.clear_pending()
        return result_text

    def apply_outcome(self, outcome_type, params, hex_grid, player):
        """Apply a specific outcome effect. Returns log message."""
        if outcome_type == "none":
            return params.get("text", "")

        elif outcome_type == "damage_player":
            damage = params.get("damage", 0)
            if player:
                old_hp = player.hp
                player.hp = max(0, player.hp - damage)
                return f"You take {damage} damage! ({old_hp} -> {player.hp} HP)"
            return ""

        elif outcome_type == "heal_player":
            amount = params.get("amount", 0)
            if player:
                old_hp = player.hp
                player.hp = min(player.max_hp, player.hp + amount)
                actual_heal = player.hp - old_hp
                return f"You recover {actual_heal} HP! ({old_hp} -> {player.hp} HP)"
            return ""

        elif outcome_type == "draw_card":
            card_type = params.get("card_type", "Junk Card")
            deck_file = params.get("deck", None)
            count = params.get("count", 1)

            cards_drawn = []
            for _ in range(count):
                card = self._draw_card(card_type, deck_file)
                if card:
                    cards_drawn.append(card)

            if cards_drawn:
                names = [c.get_current_data().get("Name", "Unknown") for c in cards_drawn]
                return f"Drew {len(cards_drawn)} card(s): {', '.join(names)}"
            return "Failed to draw any cards."

        elif outcome_type == "damage_enemy":
            damage = params.get("damage", 0)
            target_mode = params.get("target", "random")
            return self._apply_damage_to_units(damage, target_mode, "Hostile", hex_grid)

        elif outcome_type == "damage_ally":
            damage = params.get("damage", 0)
            target_mode = params.get("target", "random")
            return self._apply_damage_to_units(damage, target_mode, "Allied", hex_grid)

        elif outcome_type == "spawn_enemy":
            deck_file = params.get("deck", None)
            spawn_near = params.get("spawn_near", "player")
            count = params.get("count", 1)
            return self._spawn_units(deck_file, spawn_near, count, "Hostile", hex_grid, player)

        elif outcome_type == "spawn_ally":
            deck_file = params.get("deck", None)
            spawn_near = params.get("spawn_near", "player")
            count = params.get("count", 1)
            return self._spawn_units(deck_file, spawn_near, count, "Allied", hex_grid, player)

        elif outcome_type == "modify_stat":
            stat = params.get("stat", "")
            amount = params.get("amount", 0)
            # TODO: Implement temporary stat modifications with duration
            return f"Stat modification: {stat} {'+' if amount >= 0 else ''}{amount}"

        elif outcome_type == "teleport_player":
            distance = params.get("distance", 1)
            direction = params.get("direction", "random")
            # TODO: Implement player teleportation
            return f"Teleported {distance} hex(es) {direction}!"

        return ""

    def _draw_card(self, card_type, deck_file):
        """Draw a card from a deck or by type."""
        from inventory_card import InventoryCard

        if deck_file:
            # Draw from specific deck - try both locations
            if deck_file.startswith("cards") or os.path.sep in deck_file:
                deck_path = deck_file
            else:
                deck_path = os.path.join("cards", "decks", deck_file)
                if not os.path.exists(deck_path):
                    deck_path = os.path.join("decks", deck_file)
            card = self.card_manager.draw_from_deck(deck_path)
            if card:
                # Add to player inventory
                import JunkRPG34
                JunkRPG34.game.player.inventory.append(card)
                return card
        else:
            # Draw random card of type from all available
            cards = self.card_manager.get_cards_for_game(card_type=card_type)
            if cards:
                card_data = random.choice(cards)
                card = InventoryCard(card_data)
                import JunkRPG34
                JunkRPG34.game.player.inventory.append(card)
                return card

        return None

    def _apply_damage_to_units(self, damage, target_mode, allegiance, hex_grid):
        """Apply damage to units of a specific allegiance."""
        if not hex_grid:
            return ""

        targets = [u for u in hex_grid.units if u.allegiance == allegiance]

        if not targets:
            return f"No {allegiance.lower()} units to damage."

        messages = []

        if target_mode == "all":
            for unit in targets:
                old_hp = unit.hp
                unit.hp = max(0, unit.hp - damage)
                messages.append(f"{unit.name} takes {damage} damage ({old_hp} -> {unit.hp})")
        elif target_mode == "nearest":
            # Find nearest to player
            import JunkRPG34
            player_pos = JunkRPG34.game.player.position
            if player_pos:
                nearest = min(targets, key=lambda u: hex_grid.get_distance(player_pos, u.position) if u.position else float('inf'))
                old_hp = nearest.hp
                nearest.hp = max(0, nearest.hp - damage)
                messages.append(f"{nearest.name} takes {damage} damage ({old_hp} -> {nearest.hp})")
        else:  # random
            target = random.choice(targets)
            old_hp = target.hp
            target.hp = max(0, target.hp - damage)
            messages.append(f"{target.name} takes {damage} damage ({old_hp} -> {target.hp})")

        return "\n".join(messages)

    def _spawn_units(self, deck_file, spawn_near, count, allegiance, hex_grid, player):
        """Spawn units near player or randomly."""
        if not hex_grid or not deck_file:
            return "Failed to spawn units."

        from unit import Unit
        from inventory_card import InventoryCard

        # Try both deck locations for compatibility
        if deck_file.startswith("cards") or os.path.sep in deck_file:
            deck_path = deck_file
        else:
            deck_path = os.path.join("cards", "decks", deck_file)
            if not os.path.exists(deck_path):
                deck_path = os.path.join("decks", deck_file)

        spawned = []
        for _ in range(count):
            card = self.card_manager.draw_from_deck(deck_path)
            if not card:
                continue

            # Find spawn position
            spawn_pos = None
            if spawn_near == "player" and player and player.position:
                # Find adjacent empty hex
                adjacent = hex_grid.get_adjacent_hexes(*player.position)
                for adj in adjacent:
                    if hex_grid.is_valid_position(*adj):
                        cell = hex_grid.grid[adj[0]][adj[1]]
                        if not cell.get("unit") and cell.get("type") != "obstacle":
                            spawn_pos = adj
                            break

            if not spawn_pos:
                # Find random empty hex
                for _ in range(50):  # Try 50 times
                    row = random.randint(0, hex_grid.rows - 1)
                    col = random.randint(0, hex_grid.cols - 1)
                    if hex_grid.is_valid_position(row, col):
                        cell = hex_grid.grid[row][col]
                        if not cell.get("unit") and cell.get("type") != "obstacle":
                            spawn_pos = (row, col)
                            break

            if spawn_pos:
                # Create unit from card - Unit takes card_data dict
                card_data = card.card_data.copy()
                # Override allegiance if specified
                if "data" in card_data:
                    card_data["data"] = card_data["data"].copy()
                    card_data["data"]["Allegiance (Hostile, Neutral, Allied)"] = allegiance

                unit = Unit(card_data)
                hex_grid.place_unit(unit, *spawn_pos)
                spawned.append(unit.name)

        if spawned:
            return f"Spawned: {', '.join(spawned)}"
        return "Failed to spawn any units."

    def clear_pending(self):
        """Clear all pending state."""
        self.pending_instance = None
        self.pending_outcome = None
        self.pending_choice = None

    def has_pending_event(self):
        """Check if there's a pending event that needs resolution."""
        return self.pending_instance is not None

    def has_pending_choice(self):
        """Check if there's a pending player choice."""
        return self.pending_choice is not None and len(self.pending_choice) > 0

    def get_pending_choices(self):
        """Get the list of pending choices for UI display."""
        return self.pending_choice if self.pending_choice else []

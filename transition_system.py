"""
Transition System for JunkRPG
Handles transition cards that have a turn in the cycle, triggering world events
like spawning enemies from map edges, weather changes, drawing cards, etc.
"""

import json
import random
import os


class TransitionCard:
    """Wrapper for transition card data with two possible states."""

    def __init__(self, card_data):
        self.card_data = card_data
        self.card_id = card_data.get("id", "unknown")
        self.states = card_data.get("states", 1)
        self.current_state = 1

        # State 1 data
        self.name = card_data.get("data", {}).get("Name", "Unknown Transition")
        self.description = card_data.get("data", {}).get("Description", "")

        # Parse outcomes for state 1
        outcomes_raw = card_data.get("data", {}).get("Outcomes", "[]")
        if isinstance(outcomes_raw, str):
            try:
                self.outcomes = json.loads(outcomes_raw)
            except json.JSONDecodeError:
                print(f"Error parsing outcomes for transition card: {self.name}")
                self.outcomes = []
        else:
            self.outcomes = outcomes_raw if outcomes_raw else []

        # State 2 data (if exists)
        self.state2_name = card_data.get("data", {}).get("2nd_state_Name", self.name)
        self.state2_description = card_data.get("data", {}).get("2nd_state_Description", "")

        outcomes2_raw = card_data.get("data", {}).get("2nd_state_Outcomes", "[]")
        if isinstance(outcomes2_raw, str):
            try:
                self.state2_outcomes = json.loads(outcomes2_raw)
            except json.JSONDecodeError:
                self.state2_outcomes = []
        else:
            self.state2_outcomes = outcomes2_raw if outcomes2_raw else []

    def get_current_name(self):
        """Get name for current state."""
        return self.name if self.current_state == 1 else self.state2_name

    def get_current_description(self):
        """Get description for current state."""
        return self.description if self.current_state == 1 else self.state2_description

    def get_current_outcomes(self):
        """Get outcomes list for current state."""
        return self.outcomes if self.current_state == 1 else self.state2_outcomes

    def flip_state(self):
        """Toggle between state 1 and state 2."""
        if self.states == 2:
            self.current_state = 2 if self.current_state == 1 else 1
            return True
        return False

    def roll_outcome(self):
        """Weighted random selection of outcome for current state. Returns the selected outcome dict."""
        outcome, _ = self.roll_outcome_with_index()
        return outcome

    def roll_outcome_with_index(self):
        """Weighted random selection of outcome. Returns (outcome_dict, index) tuple."""
        outcomes = self.get_current_outcomes()

        if not outcomes:
            return {"probability": 1.0, "type": "none", "text": "Nothing happens.", "params": {}}, -1

        # Normalize probabilities
        total_prob = sum(outcome.get("probability", 0) for outcome in outcomes)
        if total_prob <= 0:
            idx = random.randint(0, len(outcomes) - 1)
            return outcomes[idx], idx

        # Roll for outcome
        roll = random.random() * total_prob
        cumulative = 0

        for i, outcome in enumerate(outcomes):
            cumulative += outcome.get("probability", 0)
            if roll <= cumulative:
                return outcome, i

        # Fallback to last outcome
        return outcomes[-1], len(outcomes) - 1


class TransitionManager:
    """Manages transition cards and their effects in the turn cycle."""

    def __init__(self, card_manager, instance_manager=None):
        self.card_manager = card_manager
        self.instance_manager = instance_manager
        self.active_transition = None  # The current transition card in the cycle
        self.weather_effect = None  # Current active weather effect
        self.weather_modifiers = {}  # Active stat modifiers from weather

    def set_instance_manager(self, instance_manager):
        """Set reference to instance manager for triggering instance events."""
        self.instance_manager = instance_manager

    def load_transition_card(self, card_id):
        """Load a specific transition card by ID."""
        card_file = os.path.join("cards", f"{card_id}.json")
        try:
            with open(card_file, 'r') as f:
                card_data = json.load(f)

            if card_data.get("card_type") == "Transition Card":
                card_data["id"] = card_id
                self.active_transition = TransitionCard(card_data)
                print(f"Loaded transition card: {self.active_transition.name}")
                return True
        except Exception as e:
            print(f"Error loading transition card {card_id}: {e}")
        return False

    def load_from_level_data(self, level_data):
        """Load transition card specified in level data."""
        transition_id = level_data.get("transition_card")
        if transition_id:
            return self.load_transition_card(transition_id)
        return False

    def set_transition_card(self, transition_card):
        """Set a transition card directly."""
        self.active_transition = transition_card

    def has_active_transition(self):
        """Check if there's an active transition card."""
        return self.active_transition is not None

    def process_transition_turn(self, hex_grid, player):
        """
        Process the transition card's turn in the cycle.
        Returns (outcome_text, log_messages) tuple.
        """
        if not self.active_transition:
            return None, []

        outcome = self.active_transition.roll_outcome()
        outcome_type = outcome.get("type", "none")
        outcome_text = outcome.get("text", "")
        params = outcome.get("params", {})

        log_messages = [f"[{self.active_transition.get_current_name()}] {outcome_text}"]

        # Process outcome based on type
        result = self.apply_outcome(outcome_type, params, hex_grid, player)
        if result:
            log_messages.append(result)

        return outcome_text, log_messages

    def process_transition_turn_with_index(self, hex_grid, player):
        """
        Process the transition card's turn and return selected outcome index.
        Returns (selected_index, result_text, log_messages) tuple.
        """
        if not self.active_transition:
            return -1, "No transition card active.", []

        # Roll for outcome and find its index
        outcome, selected_index = self.active_transition.roll_outcome_with_index()
        outcome_type = outcome.get("type", "none")
        outcome_text = outcome.get("text", "")
        params = outcome.get("params", {})

        log_messages = [f"[{self.active_transition.get_current_name()}] {outcome_text}"]

        # Process outcome based on type
        result = self.apply_outcome(outcome_type, params, hex_grid, player)

        # Build result text
        result_text = outcome_text
        if result:
            result_text += f"\n{result}"
            log_messages.append(result)

        return selected_index, result_text, log_messages

    def apply_outcome(self, outcome_type, params, hex_grid, player):
        """Apply a transition outcome. Returns result message."""

        if outcome_type == "none":
            return params.get("text", "")

        elif outcome_type == "draw_instance":
            # Trigger an instance event
            if self.instance_manager and self.instance_manager.instance_deck:
                instance_card = random.choice(self.instance_manager.instance_deck)
                self.instance_manager.pending_instance = instance_card
                return f"Instance event triggered: {instance_card.name}"
            return "No instance cards available."

        elif outcome_type == "spawn_enemy":
            edge = params.get("edge", "random")
            deck = params.get("deck", None)
            count = params.get("count", 1)
            return self._spawn_from_edge(hex_grid, edge, deck, "Hostile", count)

        elif outcome_type == "spawn_npc":
            edge = params.get("edge", "random")
            deck = params.get("deck", None)
            count = params.get("count", 1)
            allegiance = params.get("allegiance", "Neutral")
            return self._spawn_from_edge(hex_grid, edge, deck, allegiance, count)

        elif outcome_type == "draw_junk":
            deck = params.get("deck", None)
            count = params.get("count", 1)
            return self._draw_cards("Junk Card", deck, count, player)

        elif outcome_type == "draw_document":
            deck = params.get("deck", None)
            count = params.get("count", 1)
            return self._draw_cards("Document Card", deck, count, player)

        elif outcome_type == "weather":
            effect = params.get("effect", "clear")
            return self._apply_weather(effect, params, hex_grid)

        elif outcome_type == "flip_state":
            if self.active_transition.flip_state():
                new_state = "State 2" if self.active_transition.current_state == 2 else "State 1"
                return f"Transition changed to {new_state}: {self.active_transition.get_current_name()}"
            return ""

        elif outcome_type == "modify_instance_chance":
            # Modify the instance trigger chance
            if self.instance_manager:
                chance = params.get("chance", 0.15)
                self.instance_manager.set_trigger_chance(chance)
                return f"Instance event chance set to {int(chance * 100)}%"
            return ""

        return ""

    def _spawn_from_edge(self, hex_grid, edge, deck_file, allegiance, count):
        """Spawn units from a map edge."""
        from unit import Unit

        if not deck_file:
            return "No deck specified for spawning."

        # Handle deck path - try both deck locations for compatibility
        if os.path.sep in deck_file:
            deck_path = deck_file
        else:
            # Try cards/decks first, then decks
            deck_path = os.path.join("cards", "decks", deck_file)
            if not os.path.exists(deck_path):
                deck_path = os.path.join("decks", deck_file)

        spawned = []
        for _ in range(count):
            card = self.card_manager.draw_from_deck(deck_path)
            if not card:
                continue

            # Get spawn position on edge
            spawn_pos = hex_grid.get_edge_spawn_position(edge)
            if not spawn_pos:
                continue

            # Create unit from card - Unit takes card_data dict
            card_data = card.card_data.copy()
            # Override allegiance if specified
            if "data" in card_data:
                card_data["data"] = card_data["data"].copy()
                card_data["data"]["Allegiance (Hostile, Neutral, Allied)"] = allegiance

            unit = Unit(card_data)
            hex_grid.place_unit(unit, *spawn_pos)
            spawned.append(f"{unit.name} ({edge})")

        if spawned:
            return f"Spawned from edge: {', '.join(spawned)}"
        return "Failed to spawn units."

    def _draw_cards(self, card_type, deck_file, count, player):
        """Draw cards to player inventory."""
        from inventory_card import InventoryCard

        cards_drawn = []
        for _ in range(count):
            if deck_file:
                # Try both deck locations for compatibility
                if deck_file.startswith("cards") or os.path.sep in deck_file:
                    deck_path = deck_file
                else:
                    deck_path = os.path.join("cards", "decks", deck_file)
                    if not os.path.exists(deck_path):
                        deck_path = os.path.join("decks", deck_file)
                card = self.card_manager.draw_from_deck(deck_path)
            else:
                # Draw random card of type
                cards = self.card_manager.get_cards_for_game(card_type=card_type)
                if cards:
                    card_data = random.choice(cards)
                    card = InventoryCard(card_data)
                else:
                    card = None

            if card:
                player.inventory.append(card)
                cards_drawn.append(card.get_current_data().get("Name", "Unknown"))

        if cards_drawn:
            return f"Found: {', '.join(cards_drawn)}"
        return "Nothing found."

    def _apply_weather(self, effect, params, hex_grid):
        """Apply a weather effect."""
        old_weather = self.weather_effect
        self.weather_effect = effect

        # Clear old modifiers
        self.weather_modifiers = {}

        # Apply new modifiers based on weather type
        if effect == "rain":
            self.weather_modifiers["movement"] = params.get("movement_modifier", -1)
            self.weather_modifiers["projectile_range"] = params.get("range_modifier", -1)
        elif effect == "fog":
            self.weather_modifiers["projectile_range"] = params.get("range_modifier", -2)
            self.weather_modifiers["visibility"] = params.get("visibility", 3)
        elif effect == "storm":
            self.weather_modifiers["movement"] = params.get("movement_modifier", -2)
            self.weather_modifiers["projectile_range"] = params.get("range_modifier", -2)
        elif effect == "clear":
            # No modifiers for clear weather
            pass

        if old_weather != effect:
            return f"Weather changed: {effect.title()}"
        return f"Weather continues: {effect.title()}"

    def get_weather_modifier(self, stat):
        """Get the current weather modifier for a stat."""
        return self.weather_modifiers.get(stat, 0)

    def get_weather_display(self):
        """Get weather description for UI display."""
        if not self.weather_effect or self.weather_effect == "clear":
            return "Clear"

        effect_names = {
            "rain": "Raining",
            "fog": "Foggy",
            "storm": "Stormy",
            "snow": "Snowing",
            "wind": "Windy"
        }
        return effect_names.get(self.weather_effect, self.weather_effect.title())

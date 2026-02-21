"""
Transition System for JunkRPG
Handles transition cards that have a turn in the cycle, triggering world events
like spawning enemies from map edges, weather changes, drawing cards, etc.
"""

import json
import random
from sound_manager import play_card_acquired_sound
import os
from deck_utils import resolve_deck_path
from card_utils import load_card


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
        self.player_transition = None          # TransitionCard for player events
        self.unit_transition = None            # TransitionCard for unit events
        self.unit_transition_trigger_chance = 0.20  # Probability gate (0.0-1.0)

    def set_instance_manager(self, instance_manager):
        """Set reference to instance manager for triggering instance events."""
        self.instance_manager = instance_manager

    def load_transition_card(self, card_id):
        """Load a specific transition card by ID."""
        card_data = load_card(card_id)
        if not card_data:
            return False

        if card_data.get("card_type") == "Transition Card":
            self.active_transition = TransitionCard(card_data)
            print(f"Loaded transition card: {self.active_transition.name}")
            return True
        return False

    def load_from_level_data(self, level_data):
        """Load transition card specified in level data."""
        transition_id = level_data.get("transition_card")
        if transition_id:
            return self.load_transition_card(transition_id)
        return False

    def load_player_transition_card(self, card_id):
        """Load a transition card for player turn events."""
        card_data = load_card(card_id)
        if not card_data:
            return False
        if card_data.get("card_type") == "Transition Card":
            self.player_transition = TransitionCard(card_data)
            print(f"Loaded player transition card: {self.player_transition.name}")
            return True
        return False

    def load_unit_transition_card(self, card_id):
        """Load a transition card for unit turn events."""
        card_data = load_card(card_id)
        if not card_data:
            return False
        if card_data.get("card_type") == "Transition Card":
            self.unit_transition = TransitionCard(card_data)
            print(f"Loaded unit transition card: {self.unit_transition.name}")
            return True
        return False

    def set_unit_transition_trigger_chance(self, chance):
        """Set the probability gate for unit transition events."""
        self.unit_transition_trigger_chance = max(0.0, min(1.0, float(chance)))

    def has_player_transition(self):
        """Check if there's an active player transition card."""
        return self.player_transition is not None

    def has_unit_transition(self):
        """Check if there's an active unit transition card."""
        return self.unit_transition is not None

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

    def process_player_transition_turn(self, hex_grid, player):
        """Process the player transition card at the start of a player's turn.
        Returns (selected_index, outcome_text, result_text, log_messages) or None if outcome is 'none'."""
        if not self.player_transition:
            return None

        outcome, selected_index = self.player_transition.roll_outcome_with_index()
        outcome_type = outcome.get("type", "none")
        outcome_text = outcome.get("text", "")
        params = outcome.get("params", {})

        if outcome_type == "none":
            return None

        log_messages = [f"[{self.player_transition.get_current_name()}] {outcome_text}"]

        result = self.apply_outcome(outcome_type, params, hex_grid, player)
        result_text = outcome_text
        if result:
            result_text += f"\n{result}"
            log_messages.append(result)

        return selected_index, outcome_text, result_text, log_messages

    def process_unit_transition_turn(self, hex_grid, unit):
        """Process the unit transition card at the start of a unit's turn.
        Returns (outcome_type, result_text, log_messages) or None."""
        if not self.unit_transition:
            return None

        # Probability gate check
        if random.random() > self.unit_transition_trigger_chance:
            return None

        outcome, _ = self.unit_transition.roll_outcome_with_index()
        outcome_type = outcome.get("type", "none")
        outcome_text = outcome.get("text", "")
        params = outcome.get("params", {})

        if outcome_type == "none":
            return None

        if outcome_type == "trip_fall":
            damage = params.get("damage", 3)
            unit.hp -= damage
            result_text = f"{unit.name} trips and falls! ({damage} damage)"
            log_messages = [result_text]
            return "trip_fall", result_text, log_messages

        # For other outcome types, apply normally
        log_messages = [f"[{self.unit_transition.get_current_name()}] {outcome_text}"]
        result = self.apply_outcome(outcome_type, params, hex_grid, None)
        result_text = outcome_text
        if result:
            result_text += f"\n{result}"
            log_messages.append(result)

        return outcome_type, result_text, log_messages

    def apply_outcome(self, outcome_type, params, hex_grid, player):
        """Apply a transition outcome. Returns result message."""

        if outcome_type == "none":
            return params.get("text", "")

        elif outcome_type == "draw_instance":
            # Trigger an instance event
            if self.instance_manager and self.instance_manager.instance_deck:
                instance_card = random.choice(self.instance_manager.instance_deck)
                self.instance_manager.pending_instance = instance_card
                self.instance_manager.pending_instance_player = player
                return f"Instance event triggered: {instance_card.name}"
            return "No instance cards available."

        elif outcome_type == "spawn_enemy":
            edge = params.get("edge", "random")
            deck = params.get("deck", None)
            count = params.get("count", 1)
            return self._spawn_from_edge(hex_grid, edge, deck, "Hostile", count)

        elif outcome_type == "spawn_boss":
            edge = params.get("edge", "random")
            deck = params.get("deck", None)
            count = params.get("count", 1)
            return self._spawn_from_edge(hex_grid, edge, deck, "Hostile", count)

        elif outcome_type == "spawn_npc":
            edge = params.get("edge", "random")
            deck = params.get("deck", None)
            count = params.get("count", 1)
            allegiance = params.get("allegiance", "Neutral")
            return self._spawn_npc_from_location(hex_grid, edge, deck, allegiance, count)

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

        elif outcome_type == "spawn_horse":
            deck = params.get("deck", None)
            count = params.get("count", 1)
            return self._spawn_horse_from_stable(hex_grid, deck, count)

        elif outcome_type == "spawn_wild_mount":
            deck = params.get("deck", None)
            count = params.get("count", 1)
            return self._spawn_wild_mount(hex_grid, deck, count)

        elif outcome_type == "quest_npc_spawn":
            npc_deck = params.get("npc_deck", "")
            quest_deck = params.get("quest_deck", "")
            if npc_deck and quest_deck:
                return self._spawn_quest_npc(npc_deck, quest_deck, hex_grid, player)
            return "Missing npc_deck or quest_deck for quest NPC spawn."

        elif outcome_type == "trip_fall":
            # Handled directly in process_unit_transition_turn for unit context
            # If called from world transition, just return text
            damage = params.get("damage", 3)
            return f"A stumble in the darkness... ({damage} damage)"

        return ""

    def _spawn_from_edge(self, hex_grid, edge, deck_file, allegiance, count):
        """Spawn units from a map edge or adjacent to active spawn locations."""
        from unit import Unit

        if not deck_file:
            return "No deck specified for spawning."

        # Check for active spawn locations first
        active_spawn_locations = hex_grid.get_active_spawn_locations()

        spawned = []
        for _ in range(count):
            spawn_pos = None
            actual_deck = deck_file
            spawn_source = edge

            # If spawn locations exist, spawn adjacent to a random one
            if active_spawn_locations:
                spawn_location_pos, spawn_loc_data = random.choice(active_spawn_locations)
                # Use spawn location's deck if specified, otherwise use the transition deck
                loc_spawn_deck = spawn_loc_data.get("spawn_enemy_deck")
                if loc_spawn_deck:
                    actual_deck = loc_spawn_deck

                # Find an empty adjacent hex to the spawn location
                spawn_pos = self._get_spawn_adjacent_position(hex_grid, spawn_location_pos)

                # Get location name for message
                loc_card = spawn_loc_data.get("card")
                loc_name = loc_card.get_current_data().get("Name", "Spawn Location") if loc_card else "Spawn Location"
                spawn_source = loc_name

            # Fallback to edge spawning if no spawn locations or no adjacent position available
            if not spawn_pos:
                spawn_pos = hex_grid.get_edge_spawn_position(edge)
                spawn_source = edge

            if not spawn_pos:
                continue

            # Draw card from the appropriate deck
            deck_path = resolve_deck_path(actual_deck)
            card = self.card_manager.draw_from_deck(deck_path)
            if not card:
                continue

            # Create unit from card - Unit takes card_data dict
            card_data = card.card_data.copy()
            # Override allegiance if specified
            if "data" in card_data:
                card_data["data"] = card_data["data"].copy()
                card_data["data"]["Allegiance (Hostile, Neutral, Allied)"] = allegiance

            unit = Unit(card_data)
            hex_grid.place_unit(unit, *spawn_pos)
            spawned.append(f"{unit.name} ({spawn_source})")

        if spawned:
            return f"Spawned: {', '.join(spawned)}"
        return "Failed to spawn units."

    def _get_spawn_adjacent_position(self, hex_grid, location_pos):
        """Get a random empty position adjacent to a spawn location."""
        row, col = location_pos
        # Get neighbor offsets based on column parity
        if col % 2 == 0:
            offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1)]
        else:
            offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (1, -1), (1, 1)]

        candidates = []
        for dr, dc in offsets:
            nr, nc = row + dr, col + dc
            if 0 <= nr < hex_grid.rows and 0 <= nc < hex_grid.cols:
                cell = hex_grid.grid[nr][nc]
                if cell.get("unit") is None and cell.get("accessible", True):
                    candidates.append((nr, nc))

        if candidates:
            return random.choice(candidates)
        return None

    def _spawn_npc_from_location(self, hex_grid, edge, deck_file, allegiance, count):
        """Spawn NPCs from NPC spawn locations (churches) or from map edges as fallback."""
        from unit import Unit

        if not deck_file:
            return "No deck specified for spawning."

        # Check for active NPC spawn locations (churches) first
        active_npc_locations = hex_grid.get_active_npc_spawn_locations()

        spawned = []
        for _ in range(count):
            spawn_pos = None
            actual_deck = deck_file
            spawn_source = edge

            # If NPC spawn locations (churches) exist, spawn adjacent to a random one
            if active_npc_locations:
                npc_location_pos, npc_loc_data = random.choice(active_npc_locations)
                # Use church's NPC deck if specified, otherwise use the transition deck
                loc_npc_deck = npc_loc_data.get("npc_spawn_deck")
                if loc_npc_deck:
                    actual_deck = loc_npc_deck

                # Find an empty adjacent hex to the church
                spawn_pos = self._get_spawn_adjacent_position(hex_grid, npc_location_pos)

                # Get location name for message
                loc_card = npc_loc_data.get("card")
                loc_name = loc_card.get_current_data().get("Name", "Church") if loc_card else "Church"
                spawn_source = loc_name

            # Fallback to edge spawning if no NPC spawn locations or no adjacent position available
            if not spawn_pos:
                spawn_pos = hex_grid.get_edge_spawn_position(edge)
                spawn_source = edge

            if not spawn_pos:
                continue

            # Draw card from the appropriate deck
            deck_path = resolve_deck_path(actual_deck)
            card = self.card_manager.draw_from_deck(deck_path)
            if not card:
                continue

            # Create unit from card - Unit takes card_data dict
            card_data = card.card_data.copy()
            # Override allegiance if specified
            if "data" in card_data:
                card_data["data"] = card_data["data"].copy()
                card_data["data"]["Allegiance (Hostile, Neutral, Allied)"] = allegiance

            unit = Unit(card_data)
            hex_grid.place_unit(unit, *spawn_pos)
            spawned.append(f"{unit.name} ({spawn_source})")

        if spawned:
            return f"Spawned: {', '.join(spawned)}"
        return "Failed to spawn NPCs."

    def _spawn_horse_from_stable(self, hex_grid, deck_file, count):
        """Spawn horses from horse stables or from map edges as fallback.

        Stables with an assigned NPC spawn allied (state 2) horses.
        Stables without an assigned NPC spawn neutral (state 1) horses.
        """
        from unit import Unit

        if not deck_file:
            return "No horse deck specified."

        # Find NPC spawn locations that use a horse deck
        active_npc_locations = hex_grid.get_active_npc_spawn_locations()
        horse_stables = []
        if active_npc_locations:
            for loc_pos, loc_data in active_npc_locations:
                npc_deck = loc_data.get("npc_spawn_deck", "")
                if npc_deck and "horse" in npc_deck.lower():
                    horse_stables.append((loc_pos, loc_data))

        spawned = []
        for _ in range(count):
            spawn_pos = None
            spawn_source = "the wilds"
            has_assigned_npc = False

            # If horse stables exist, spawn adjacent to a random one
            if horse_stables:
                stable_pos, stable_data = random.choice(horse_stables)
                spawn_pos = self._get_spawn_adjacent_position(hex_grid, stable_pos)

                # Check if stable has an assigned NPC (upgraded)
                has_assigned_npc = stable_data.get("assigned_npc_id") is not None

                loc_card = stable_data.get("card")
                spawn_source = loc_card.get_current_data().get("Name", "Horse Stable") if loc_card else "Horse Stable"

            # Fallback to edge spawning if no stables or no adjacent position
            if not spawn_pos:
                spawn_pos = hex_grid.get_edge_spawn_position("random")
                spawn_source = "the wilds"
                has_assigned_npc = False

            if not spawn_pos:
                continue

            # Draw card from horse deck
            deck_path = resolve_deck_path(deck_file)
            card = self.card_manager.draw_from_deck(deck_path)
            if not card:
                continue

            # Create unit from card
            card_data = card.card_data.copy()
            if "data" in card_data:
                card_data["data"] = card_data["data"].copy()

                if has_assigned_npc:
                    # Stable has NPC caretaker: spawn allied (state 2) horse
                    card_data["data"]["Allegiance (Hostile, Neutral, Allied)"] = "Allied"
                else:
                    # No caretaker: spawn neutral (state 1) horse
                    card_data["data"]["Allegiance (Hostile, Neutral, Allied)"] = "Neutral"

            unit = Unit(card_data)

            # If stable has NPC, set horse to state 2 (tamed)
            if has_assigned_npc and hasattr(unit, 'current_state'):
                unit.current_state = 2
                # Update stats to state 2 values
                state2_data = card_data.get("data", {})
                unit.name = state2_data.get("2nd_State_Name", unit.name)
                unit.max_hp = int(state2_data.get("2nd_State_Health", unit.max_hp))
                unit.hp = unit.max_hp
                unit.movement = int(state2_data.get("2nd_State_Movement", unit.movement))
                unit.set_allegiance("Allied")

            hex_grid.place_unit(unit, *spawn_pos)
            spawned.append(f"{unit.name} ({spawn_source})")

        if spawned:
            return f"Spawned: {', '.join(spawned)}"
        return "No horses appeared."

    def _spawn_wild_mount(self, hex_grid, deck_file, count):
        """Spawn wild mount animals at random positions anywhere on the map."""
        from unit import Unit

        if not deck_file:
            return "No wild mount deck specified."

        spawned = []
        for _ in range(count):
            spawn_pos = hex_grid.get_random_spawn_position()
            if not spawn_pos:
                continue

            deck_path = resolve_deck_path(deck_file)
            card = self.card_manager.draw_from_deck(deck_path)
            if not card:
                continue

            card_data = card.card_data.copy()
            if "data" in card_data:
                card_data["data"] = card_data["data"].copy()
                card_data["data"]["Allegiance (Hostile, Neutral, Allied)"] = "Neutral"

            unit = Unit(card_data)
            hex_grid.place_unit(unit, *spawn_pos)
            spawned.append(unit.name)

        if spawned:
            return f"A wild creature appears: {', '.join(spawned)}"
        return "No wild animals appeared."

    def _spawn_quest_npc(self, npc_deck, quest_deck, hex_grid, player):
        """Spawn a quest-giving NPC who approaches the player and offers a quest."""
        from unit import Unit

        # Draw NPC card from npc_deck
        npc_deck_path = resolve_deck_path(npc_deck)
        npc_card = self.card_manager.draw_from_deck(npc_deck_path)
        if not npc_card:
            return "No NPC card available for quest giver."

        # Draw quest card ID from quest_deck
        quest_card_id = None
        try:
            quest_deck_path = resolve_deck_path(quest_deck)
            if os.path.exists(quest_deck_path):
                with open(quest_deck_path, 'r') as f:
                    deck_data = json.load(f)
                card_ids = deck_data.get("cards", [])
                if card_ids:
                    quest_card_id = random.choice(card_ids)
        except Exception as e:
            print(f"Error reading quest deck for quest NPC: {e}")

        if not quest_card_id:
            return "No quest card available for quest giver."

        # Create unit from NPC card
        card_data = npc_card.card_data.copy()
        if "data" in card_data:
            card_data["data"] = card_data["data"].copy()
            card_data["data"]["Allegiance (Hostile, Neutral, Allied)"] = "Neutral"

        unit = Unit(card_data)
        unit.quest_offer_card_id = quest_card_id
        unit.avoid_location_hexes = True

        # Set follow target to the player
        if player and hasattr(player, 'position'):
            # Determine player index for target reference
            if hasattr(hex_grid, 'players') and hex_grid.players:
                for i, p in enumerate(hex_grid.players):
                    if p is player:
                        unit.quest_offer_target = f"player_{i}"
                        break
                else:
                    unit.quest_offer_target = "player_0"
            else:
                unit.quest_offer_target = "player_0"
            unit.behavior_follow_target = unit.quest_offer_target

        # Spawn at map edge
        spawn_pos = hex_grid.get_edge_spawn_position("random")
        if not spawn_pos:
            return "No valid spawn position for quest NPC."

        hex_grid.place_unit(unit, *spawn_pos)
        return f"A quest giver ({unit.name}) has appeared!"

    def _draw_cards(self, card_type, deck_file, count, player):
        """Draw cards to player inventory."""
        from inventory_card import InventoryCard

        cards_drawn = []
        for _ in range(count):
            if deck_file:
                deck_path = resolve_deck_path(deck_file)
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
                play_card_acquired_sound(card)
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

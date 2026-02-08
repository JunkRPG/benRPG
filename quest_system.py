"""
Quest System for JunkRPG

Implements a "Madlib" style quest system where Quest Cards contain template text
with placeholders (e.g., [NPC1], [Location1], [3 junk]) that get dynamically
filled when activated.
"""

import json
import os
import random
from inventory_card import InventoryCard
from unit import Unit
from deck_utils import resolve_deck_path
from card_utils import load_card


class PlaceholderResolver:
    """Resolves placeholders in quest templates by drawing cards and spawning units."""

    def __init__(self, card_manager, hex_grid):
        self.card_manager = card_manager
        self.hex_grid = hex_grid
        # resolved = {"NPC1": {"cards": [], "unit": Unit, "position": (r,c), "name": "Bob"}}
        self.resolved = {}

    def resolve_placeholders(self, placeholders_json, player_position):
        """
        Resolve all placeholders by drawing cards and optionally spawning units.

        Args:
            placeholders_json: JSON string or list of placeholder definitions
            player_position: (row, col) of player for spawn_near="player"

        Returns:
            dict mapping placeholder IDs to resolved data
        """
        try:
            if isinstance(placeholders_json, str):
                placeholders = json.loads(placeholders_json)
            else:
                placeholders = placeholders_json
        except json.JSONDecodeError:
            print(f"Error parsing placeholders JSON: {placeholders_json}")
            return {}

        # First pass: resolve all placeholders that don't depend on others
        for placeholder in placeholders:
            placeholder_id = placeholder.get("id")
            if not placeholder_id:
                continue

            spawn_near = placeholder.get("spawn_near")
            spawn_at = placeholder.get("spawn_at")

            # Skip placeholders that depend on others for now
            if spawn_near and spawn_near != "player" and spawn_near not in self.resolved:
                continue
            if spawn_at and spawn_at not in self.resolved:
                continue

            self._resolve_single_placeholder(placeholder, player_position)

        # Second pass: resolve remaining placeholders
        for placeholder in placeholders:
            placeholder_id = placeholder.get("id")
            if placeholder_id and placeholder_id not in self.resolved:
                self._resolve_single_placeholder(placeholder, player_position)

        return self.resolved

    def _resolve_single_placeholder(self, placeholder, player_position):
        """Resolve a single placeholder definition."""
        placeholder_id = placeholder.get("id")
        card_type = placeholder.get("type")
        filters = placeholder.get("filter", {})
        deck_file = placeholder.get("deck_file")
        spawn = placeholder.get("spawn", False)
        spawn_near = placeholder.get("spawn_near")
        spawn_at = placeholder.get("spawn_at")
        spawn_distance = placeholder.get("spawn_distance", 3)
        count = placeholder.get("count", 1)

        # Draw cards
        cards = self._draw_cards(card_type, filters, deck_file, count)
        if not cards:
            print(f"Warning: Could not draw cards for placeholder {placeholder_id}")
            return

        resolved_data = {
            "cards": cards,
            "unit": None,
            "position": None,
            "name": cards[0].get_current_data().get("Name", "Unknown") if cards else "Unknown"
        }

        # Spawn unit if configured
        if spawn and card_type in ["NPC Card", "Enemy Card"]:
            base_position = self._get_spawn_base_position(
                spawn_near, spawn_at, player_position
            )
            if base_position:
                spawn_pos = self.hex_grid.find_empty_hex_near(base_position, spawn_distance)
                if spawn_pos:
                    unit = self._create_unit_from_card(cards[0])
                    if unit:
                        success, _ = self.hex_grid.place_unit(unit, spawn_pos[0], spawn_pos[1])
                        if success:
                            resolved_data["unit"] = unit
                            resolved_data["position"] = spawn_pos

        # For location cards, we need to find/assign a location hex
        if card_type == "Location Card" and not spawn:
            # Try to find an existing location hex or use the card's assigned position
            resolved_data["position"] = self._find_location_position(cards[0])

        self.resolved[placeholder_id] = resolved_data

    def _draw_cards(self, card_type, filters, deck_file, count):
        """Draw cards of the specified type."""
        cards = []

        if deck_file:
            # Draw from specific deck
            deck_path = resolve_deck_path(deck_file)
            try:
                with open(deck_path, 'r') as f:
                    deck_data = json.load(f)
                card_ids = deck_data.get("cards", [])
                if card_ids:
                    selected_ids = random.sample(card_ids, min(count, len(card_ids)))
                    for card_id in selected_ids:
                        card = self._load_card(card_id)
                        if card:
                            cards.append(card)
            except Exception as e:
                print(f"Error loading deck {deck_file}: {e}")
        else:
            # Draw from card manager
            available_cards = self.card_manager.get_cards_for_game(card_type, filters)
            if available_cards:
                selected = random.sample(available_cards, min(count, len(available_cards)))
                for card_data in selected:
                    card = InventoryCard(card_data)
                    cards.append(card)

        return cards

    def _load_card(self, card_id):
        """Load a card by ID."""
        card_data = load_card(card_id)
        if not card_data:
            return None
        return InventoryCard(card_data)

    def _get_spawn_base_position(self, spawn_near, spawn_at, player_position):
        """Get the base position to spawn near/at."""
        if spawn_at and spawn_at in self.resolved:
            return self.resolved[spawn_at].get("position")

        if spawn_near == "player":
            return player_position
        elif spawn_near and spawn_near in self.resolved:
            return self.resolved[spawn_near].get("position")

        return player_position  # Default to player

    def _create_unit_from_card(self, card):
        """Create a Unit from an InventoryCard."""
        card_data = {
            "id": card.card_data.get("id", ""),
            "card_type": card.card_data.get("card_type", "NPC Card"),
            "states": card.states,
            "data": card.get_current_data()
        }
        return Unit(card_data)

    def _find_location_position(self, location_card):
        """Find position for a location card (existing location hex)."""
        # Search for location hexes that match
        for pos, loc_data in self.hex_grid.location_data.items():
            if loc_data.get("card"):
                loc_card = loc_data["card"]
                if loc_card.get_current_data().get("Name") == location_card.get_current_data().get("Name"):
                    return pos

        # If no matching location, try to find any unassigned location hex
        for pos, loc_data in self.hex_grid.location_data.items():
            if not loc_data.get("card"):
                return pos

        return None

    def fill_template(self, template_text):
        """Replace [placeholder_id] with resolved names."""
        result = template_text
        for placeholder_id, data in self.resolved.items():
            pattern = f"[{placeholder_id}]"
            replacement = data.get("name", placeholder_id)
            result = result.replace(pattern, replacement)
        return result

    def get_resolved_cards(self, placeholder_ids):
        """Get resolved cards for the given placeholder IDs."""
        cards = []
        for pid in placeholder_ids:
            if pid in self.resolved:
                cards.extend(self.resolved[pid].get("cards", []))
        return cards


class ActiveQuest:
    """Represents an active quest with resolved placeholders and condition tracking."""

    def __init__(self, quest_card, hex_grid, player, card_manager):
        self.quest_card = quest_card
        self.hex_grid = hex_grid
        self.player = player
        self.card_manager = card_manager
        self.resolver = None
        self.tracked_units = {}    # {"NPC1": Unit}
        self.tracked_locations = {}  # {"Location1": (row, col)}
        self.turn_count = 0
        self.is_complete = False
        self.is_failed = False

    def initialize(self, inherited_context=None):
        """Resolve placeholders and spawn units.

        Args:
            inherited_context: Optional dict of pre-resolved placeholder data
                               carried forward from a previous quest in a chain.
        """
        quest_data = self.quest_card.get_current_data()
        placeholders_json = quest_data.get("Placeholders", "[]")

        self.resolver = PlaceholderResolver(self.card_manager, self.hex_grid)

        # Pre-seed resolver with inherited placeholder data from chain
        if inherited_context:
            self.resolver.resolved.update(inherited_context)

        self.resolver.resolve_placeholders(placeholders_json, self.player.position)

        # Track spawned units and locations
        for placeholder_id, data in self.resolver.resolved.items():
            if data.get("unit"):
                self.tracked_units[placeholder_id] = data["unit"]
            if data.get("position"):
                self.tracked_locations[placeholder_id] = data["position"]

        # Set quest target positions on NPCs based on success conditions
        self._set_unit_quest_targets()

        return True

    def _set_unit_quest_targets(self):
        """Set quest_target_position on units that need to reach a location."""
        quest_data = self.quest_card.get_current_data()
        success_conditions_json = quest_data.get("Success_Conditions", "[]")

        try:
            success_conditions = json.loads(success_conditions_json) if isinstance(success_conditions_json, str) else success_conditions_json
        except json.JSONDecodeError:
            return

        for condition in success_conditions:
            if condition.get("type") == "unit_reaches_location":
                params = condition.get("params", {})
                unit_placeholder = params.get("unit")
                location_placeholder = params.get("location")

                # Get the unit and location position
                unit = self.tracked_units.get(unit_placeholder)
                location_pos = self.tracked_locations.get(location_placeholder)

                if unit and location_pos:
                    unit.quest_target_position = location_pos
                    unit.quest_movement_priority = params.get("priority", "rush")
                    print(f"Set quest target for {unit.name}: {location_pos} (priority: {unit.quest_movement_priority})")

    def get_display_name(self):
        """Return quest name with placeholders filled."""
        quest_data = self.quest_card.get_current_data()
        name = quest_data.get("Name", "Unknown Quest")
        if self.resolver:
            return self.resolver.fill_template(name)
        return name

    def get_filled_description(self):
        """Return Template_Text with placeholders filled."""
        quest_data = self.quest_card.get_current_data()
        template = quest_data.get("Template_Text", "")
        if self.resolver:
            return self.resolver.fill_template(template)
        return template

    def check_conditions(self, event_type, event_data):
        """
        Check win/fail conditions against an event.

        Returns: "success", "failure", or None
        """
        if self.is_complete or self.is_failed:
            return None

        quest_data = self.quest_card.get_current_data()

        # Check success conditions
        success_conditions_json = quest_data.get("Success_Conditions", "[]")
        try:
            success_conditions = json.loads(success_conditions_json) if isinstance(success_conditions_json, str) else success_conditions_json
        except json.JSONDecodeError:
            success_conditions = []

        if self._check_condition_list(success_conditions, event_type, event_data):
            self.is_complete = True
            return "success"

        # Check failure conditions
        failure_conditions_json = quest_data.get("Failure_Conditions", "[]")
        try:
            failure_conditions = json.loads(failure_conditions_json) if isinstance(failure_conditions_json, str) else failure_conditions_json
        except json.JSONDecodeError:
            failure_conditions = []

        if self._check_condition_list(failure_conditions, event_type, event_data):
            self.is_failed = True
            return "failure"

        return None

    def _check_condition_list(self, conditions, event_type, event_data):
        """Check if any condition in the list is met."""
        for condition in conditions:
            cond_type = condition.get("type")
            params = condition.get("params", {})

            if cond_type == "unit_death":
                if event_type == "unit_death":
                    unit_placeholder = params.get("unit")
                    dead_unit = event_data.get("unit")
                    tracked = self.tracked_units.get(unit_placeholder)
                    if tracked and dead_unit == tracked:
                        return True

            elif cond_type == "player_death":
                if event_type == "player_death":
                    return True

            elif cond_type == "unit_reaches_location":
                if event_type == "unit_moved":
                    unit_placeholder = params.get("unit")
                    location_placeholder = params.get("location")
                    moved_unit = event_data.get("unit")
                    new_position = event_data.get("position")

                    tracked_unit = self.tracked_units.get(unit_placeholder)
                    target_location = self.tracked_locations.get(location_placeholder)

                    if tracked_unit and moved_unit == tracked_unit:
                        if target_location and new_position == target_location:
                            return True

            elif cond_type == "turn_limit":
                if event_type == "turn_end":
                    max_turns = params.get("turns", 0)
                    if self.turn_count >= max_turns:
                        return True

            elif cond_type == "enemy_defeated":
                if event_type == "unit_death":
                    enemy_placeholder = params.get("enemy")
                    dead_unit = event_data.get("unit")
                    tracked = self.tracked_units.get(enemy_placeholder)
                    if tracked and dead_unit == tracked:
                        return True

        return False

    def increment_turn(self):
        """Increment the turn counter."""
        self.turn_count += 1

    def get_rewards(self):
        """Return resolved reward cards."""
        quest_data = self.quest_card.get_current_data()
        rewards_json = quest_data.get("Rewards", "{}")

        try:
            rewards = json.loads(rewards_json) if isinstance(rewards_json, str) else rewards_json
        except json.JSONDecodeError:
            return []

        reward_cards = []
        card_placeholders = rewards.get("cards", [])

        if self.resolver:
            reward_cards = self.resolver.get_resolved_cards(card_placeholders)

        return reward_cards

    def start_npc_location_animations(self):
        """
        Start animations for NPCs moving to their destination locations.
        Returns a list of pending arrivals to be tracked by QuestManager.
        """
        pending_arrivals = []
        quest_data = self.quest_card.get_current_data()
        success_conditions_json = quest_data.get("Success_Conditions", "[]")

        try:
            success_conditions = json.loads(success_conditions_json) if isinstance(success_conditions_json, str) else success_conditions_json
        except json.JSONDecodeError:
            return pending_arrivals

        for condition in success_conditions:
            if condition.get("type") == "unit_reaches_location":
                params = condition.get("params", {})
                unit_placeholder = params.get("unit")
                location_placeholder = params.get("location")

                # Get the unit and location position
                unit = self.tracked_units.get(unit_placeholder)
                location_pos = self.tracked_locations.get(location_placeholder)

                if unit and location_pos and unit.position:
                    # Check if unit is already animating (from their movement to the location)
                    # If so, don't start a new animation - just track them for removal when done
                    if not unit.animating:
                        # Unit is not animating, check if they need to move
                        if unit.position != location_pos:
                            # Start animation to move NPC to location
                            unit.animate_move(self.hex_grid, location_pos[0], location_pos[1])
                        # If already at location and not animating, they'll be removed immediately
                        # by update_pending_arrivals since animating is False

                    # Add to pending arrivals (will wait for animation to complete)
                    pending_arrivals.append({
                        "unit": unit,
                        "location_pos": location_pos,
                        "hex_grid": self.hex_grid
                    })

                    # Remove from tracked units since they're being moved
                    del self.tracked_units[unit_placeholder]

        return pending_arrivals

    def move_npcs_to_locations(self):
        """Legacy method - immediately move NPCs to locations (no animation)."""
        quest_data = self.quest_card.get_current_data()
        success_conditions_json = quest_data.get("Success_Conditions", "[]")

        try:
            success_conditions = json.loads(success_conditions_json) if isinstance(success_conditions_json, str) else success_conditions_json
        except json.JSONDecodeError:
            return

        for condition in success_conditions:
            if condition.get("type") == "unit_reaches_location":
                params = condition.get("params", {})
                unit_placeholder = params.get("unit")
                location_placeholder = params.get("location")

                # Get the unit and location position
                unit = self.tracked_units.get(unit_placeholder)
                location_pos = self.tracked_locations.get(location_placeholder)

                if unit and location_pos:
                    # Move NPC from map to location
                    success, msg = self.hex_grid.add_npc_to_location(unit, location_pos)
                    if success:
                        print(f"Quest: {msg}")
                        # Remove from tracked units since they're now at a location
                        del self.tracked_units[unit_placeholder]

    def get_chain_config(self):
        """Parse and return Chain_Config from quest card data, or None."""
        quest_data = self.quest_card.get_current_data()
        chain_json = quest_data.get("Chain_Config", "")
        if not chain_json or chain_json.strip() == "":
            return None
        try:
            config = json.loads(chain_json) if isinstance(chain_json, str) else chain_json
            if isinstance(config, dict):
                return config
        except json.JSONDecodeError:
            print(f"Warning: Invalid Chain_Config JSON in quest {self.get_display_name()}")
        return None

    def get_inherited_context(self, placeholder_ids):
        """Extract resolved placeholder data for specified IDs to carry forward.

        For on_failure chains, only carries name/position (units may be dead).
        For on_success chains, carries full data including living units.

        Args:
            placeholder_ids: List of placeholder ID strings to inherit

        Returns:
            dict mapping placeholder IDs to resolved data
        """
        if not self.resolver or not placeholder_ids:
            return {}

        context = {}
        for pid in placeholder_ids:
            if pid in self.resolver.resolved:
                source = self.resolver.resolved[pid]
                context[pid] = {
                    "cards": source.get("cards", []),
                    "unit": source.get("unit"),
                    "position": source.get("position"),
                    "name": source.get("name", "Unknown")
                }
        return context

    def cleanup(self):
        """Remove spawned units on failure."""
        for placeholder_id, unit in self.tracked_units.items():
            if unit and unit.position:
                self.hex_grid.grid[unit.position[0]][unit.position[1]]["unit"] = None
                if unit in self.hex_grid.units:
                    self.hex_grid.units.remove(unit)


class QuestManager:
    """Manages all quest-related functionality."""

    MAX_ACTIVE_QUESTS = 5

    def __init__(self, card_manager):
        self.card_manager = card_manager
        self.active_quests = []
        self.completed_quests = []
        self.failed_quests = []
        # Track NPCs animating to their destinations after quest completion
        # Each entry: {"unit": Unit, "location_pos": (row, col), "hex_grid": HexGrid}
        self.pending_arrivals = []
        # Pending chain quest to be handled by game loop
        # {"quest_card": InventoryCard, "mode": str, "message": str, "inherited_context": dict}
        self.pending_chain = None

    def can_accept_quest(self):
        """Check if player can accept another quest."""
        return len(self.active_quests) < self.MAX_ACTIVE_QUESTS

    def activate_quest(self, quest_card, hex_grid, player):
        """
        Activate a quest card.

        Returns: (success, message)
        """
        if not self.can_accept_quest():
            return False, "Quest log is full (max 5 active quests)"

        quest = ActiveQuest(quest_card, hex_grid, player, self.card_manager)
        success = quest.initialize()

        if success:
            self.active_quests.append(quest)
            return True, f"Quest accepted: {quest.get_display_name()}"
        else:
            return False, "Failed to initialize quest"

    def update(self, event_type, event_data, hex_grid, player):
        """
        Check all active quests for win/fail conditions.

        Returns: list of (quest, result, message) tuples
        """
        results = []

        for quest in self.active_quests[:]:  # Copy to allow removal
            result = quest.check_conditions(event_type, event_data)

            if result == "success":
                self._complete_quest(quest, player)
                results.append((quest, "success", f"Quest completed: {quest.get_display_name()}"))
            elif result == "failure":
                self._fail_quest(quest)
                results.append((quest, "failure", f"Quest failed: {quest.get_display_name()}"))

        # Handle turn_end event for turn counting
        if event_type == "turn_end":
            for quest in self.active_quests:
                quest.increment_turn()

        return results

    def _complete_quest(self, quest, player):
        """Handle quest completion: grant rewards, flip card, start NPC animations to locations, process chain."""
        self.active_quests.remove(quest)
        self.completed_quests.append(quest)

        # Start animations for NPCs moving to their destination locations (for escort quests)
        pending = quest.start_npc_location_animations()
        self.pending_arrivals.extend(pending)

        # Grant rewards
        rewards = quest.get_rewards()
        for reward_card in rewards:
            player.inventory.append(reward_card)

        # Flip quest card to state 2 if it has 2 states
        if quest.quest_card.states == 2:
            quest.quest_card.toggle_state()

        # Process quest chain on success
        chain_config = quest.get_chain_config()
        if chain_config:
            on_success = chain_config.get("on_success")
            if on_success and on_success.get("mode", "none") != "none":
                inherited = quest.get_inherited_context(on_success.get("inherit_placeholders", []))
                self._process_chain_branch(on_success, inherited)

    def _fail_quest(self, quest):
        """Handle quest failure: cleanup spawned units, process chain."""
        self.active_quests.remove(quest)
        self.failed_quests.append(quest)

        # Process quest chain on failure (before cleanup, so we can read context)
        chain_config = quest.get_chain_config()
        if chain_config:
            on_failure = chain_config.get("on_failure")
            if on_failure and on_failure.get("mode", "none") != "none":
                # For failure chains, inherit names/positions only (units may be dead)
                inherited_ids = on_failure.get("inherit_placeholders", [])
                inherited = {}
                if quest.resolver and inherited_ids:
                    for pid in inherited_ids:
                        if pid in quest.resolver.resolved:
                            source = quest.resolver.resolved[pid]
                            inherited[pid] = {
                                "cards": source.get("cards", []),
                                "unit": None,  # Don't inherit potentially dead units
                                "position": source.get("position"),
                                "name": source.get("name", "Unknown")
                            }
                self._process_chain_branch(on_failure, inherited)

        # Cleanup spawned units
        quest.cleanup()

    def _process_chain_branch(self, branch_config, inherited_context):
        """Store a chain quest for the game loop to handle.

        Args:
            branch_config: Dict with mode, quest_card_id, quest_deck, message
            inherited_context: Pre-resolved placeholder data to carry forward
        """
        mode = branch_config.get("mode", "none")
        if mode == "none":
            return

        quest_card_id = branch_config.get("quest_card_id")
        quest_deck = branch_config.get("quest_deck")
        message = branch_config.get("message", "")

        quest_card = self._load_chain_quest(quest_card_id, quest_deck)
        if not quest_card:
            print(f"Warning: Could not load chain quest (id={quest_card_id}, deck={quest_deck})")
            return

        self.pending_chain = {
            "quest_card": quest_card,
            "mode": mode,
            "message": message,
            "inherited_context": inherited_context
        }

    def _load_chain_quest(self, quest_card_id, quest_deck):
        """Load a quest card by ID or draw from a deck.

        Returns:
            InventoryCard or None
        """
        from inventory_card import InventoryCard

        if quest_card_id:
            card_data = load_card(quest_card_id)
            if card_data:
                return InventoryCard(card_data)
            return None

        if quest_deck:
            deck_path = resolve_deck_path(quest_deck)
            try:
                with open(deck_path, 'r') as f:
                    deck_data = json.load(f)
                card_ids = deck_data.get("cards", [])
                if card_ids:
                    selected_id = random.choice(card_ids)
                    card_data = load_card(selected_id)
                    if card_data:
                        return InventoryCard(card_data)
            except Exception as e:
                print(f"Error loading chain quest from deck {quest_deck}: {e}")

        return None

    def get_pending_chain(self):
        """Return and clear the pending chain quest. Called by game loop."""
        chain = self.pending_chain
        self.pending_chain = None
        return chain

    def activate_chain_quest(self, quest_card, hex_grid, player, inherited_context=None):
        """Activate a quest with inherited context from a chain.

        Returns: (success, message)
        """
        if not self.can_accept_quest():
            return False, "Quest log is full (max 5 active quests)"

        quest = ActiveQuest(quest_card, hex_grid, player, self.card_manager)
        success = quest.initialize(inherited_context=inherited_context)

        if success:
            self.active_quests.append(quest)
            return True, f"Quest accepted: {quest.get_display_name()}"
        else:
            return False, "Failed to initialize chain quest"

    def abandon_quest(self, quest):
        """Abandon an active quest."""
        if quest in self.active_quests:
            self.active_quests.remove(quest)
            quest.cleanup()
            self.failed_quests.append(quest)
            return True, f"Quest abandoned: {quest.get_display_name()}"
        return False, "Quest not found"

    def get_quest_by_name(self, name):
        """Find an active quest by its display name."""
        for quest in self.active_quests:
            if quest.get_display_name() == name:
                return quest
        return None

    def update_pending_arrivals(self):
        """
        Check pending NPC arrivals and finalize when animations complete.
        Should be called each frame from the game loop.

        Returns: list of messages for completed arrivals
        """
        messages = []
        completed = []

        for arrival in self.pending_arrivals:
            unit = arrival["unit"]
            location_pos = arrival["location_pos"]
            hex_grid = arrival["hex_grid"]

            # Check if animation is complete
            if not unit.animating:
                # Animation finished, move unit to location
                success, msg = hex_grid.add_npc_to_location(unit, location_pos)
                if success:
                    messages.append(msg)
                completed.append(arrival)

        # Remove completed arrivals
        for arrival in completed:
            self.pending_arrivals.remove(arrival)

        return messages

    def has_pending_arrivals(self):
        """Check if there are any NPCs still animating to locations."""
        return len(self.pending_arrivals) > 0

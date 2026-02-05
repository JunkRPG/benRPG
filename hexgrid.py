import pygame
import math
from heapq import heappush, heappop
import os
import json
import random
from collections import deque
from player import Player  # Import Player for type checking
from unit import Unit      # Import Unit for instantiation
from inventory_card import InventoryCard
from terrain_config import (
    TERRAIN_CONFIG,
    get_terrain_color,
    is_terrain_accessible,
    does_terrain_block_los
)
from deck_utils import resolve_deck_path
from card_utils import load_card

# Hexagonal directions for LOS
DIRECTIONS = [
    (1, 0, -1), (1, -1, 0), (0, -1, 1),
    (-1, 0, 1), (-1, 1, 0), (0, 1, -1)
]

class HexGrid:
    def __init__(self, rows, cols, hex_size, window_width, window_height):
        self.rows = rows
        self.cols = cols
        self.hex_size = hex_size
        # Grid stores a dict with "unit", "accessible", and "terrain" keys
        self.grid = [[{"unit": None, "accessible": True, "terrain": "grass"} for _ in range(cols)] for _ in range(rows)]
        self.player = None
        self.players = []  # For multiplayer mode - list of players
        self.units = []
        self.selected_hex = None
        self.card_drawing_hexes = []
        self.deck_data = {}
        # Location hex system
        self.location_hexes = []
        self.location_data = {}  # {(row,col): {"card": InventoryCard, "shop": [], "turns": 0, "visited": False}}
        # Calculate initial offsets based on provided dimensions
        grid_width = self.cols * self.hex_size * 1.5
        grid_height = self.rows * self.hex_size * 1.732
        self.view_offset_x = (window_width - grid_width) / 2 if grid_width < window_width else 0
        self.view_offset_y = (window_height - grid_height) / 2 if grid_height < window_height else 0
        # Font for rendering unit names and damage text
        self.font = pygame.font.Font(None, 18)
        self.game_over = False  # Flag to indicate if the player is defeated
        # Animation state for targeting visuals
        self.pulse_time = 0

    def load_level(self, level_file, card_manager, player):
        try:
            with open(level_file, 'r') as f:
                level_data = json.load(f)
            # Set grid dimensions from the level file
            self.rows = level_data["grid"]["rows"]
            self.cols = level_data["grid"]["columns"]
            self.hex_size = level_data.get("hex_size", 30)  # Default to 30 if not specified
            # Rebuild the grid with the new dimensions
            self.grid = [[{"unit": None, "accessible": True, "terrain": "grass"} for _ in range(self.cols)] for _ in range(self.rows)]
            self.card_drawing_hexes = level_data.get("card_drawing_hexes", [])

            # Load terrain data if present
            terrain_data = level_data.get("terrain", [])
            for row in range(self.rows):
                for col in range(self.cols):
                    if row < len(terrain_data) and col < len(terrain_data[row]):
                        terrain_type = terrain_data[row][col]
                        self.grid[row][col]["terrain"] = terrain_type
                        # Set accessibility based on terrain type
                        if not is_terrain_accessible(terrain_type):
                            self.grid[row][col]["accessible"] = False

            # Mark additional inaccessible hexes (from level editor toggle)
            for hex in level_data.get("inaccessible_hexes", []):
                row, col = hex["row"], hex["column"]
                if 0 <= row < self.rows and 0 <= col < self.cols:
                    self.grid[row][col]["accessible"] = False
            
            # Place the player at the specified start position
            player_start = level_data.get("player_start")
            if player_start and player:
                self.place_unit(player, player_start["row"], player_start["column"])
            elif player:
                # Fallback to center if no player_start is specified
                self.place_unit(player, self.rows // 2, self.cols // 2)

            # Load starting inventory for player
            starting_inventory = level_data.get("starting_inventory", [])
            if player and starting_inventory:
                for item in starting_inventory:
                    card_id = item.get("card_id") if isinstance(item, dict) else item
                    card_data = load_card(card_id)
                    if card_data:
                        inv_card = InventoryCard(card_data)
                        # Check if card should start in state 2 (crafted)
                        if isinstance(item, dict) and item.get("state", 1) == 2:
                            inv_card.current_state = 2
                        player.inventory.append(inv_card)
                        print(f"Added starting item: {inv_card.get_current_data().get('Name', card_id)}")
                    else:
                        print(f"Warning: Starting inventory card '{card_id}' not found")

            # Load and place units
            for unit_data in level_data.get("units", []):
                card_id = unit_data.get("card_id")
                card_data = load_card(card_id)
                if card_data is None:
                    print(f"Skipping unit: card '{card_id}' not found")
                    continue
                unit = Unit(card_data)
                self.place_unit(unit, unit_data["position"]["row"], unit_data["position"]["column"])
                card_manager.track_card_usage(unit.card_id, {
                    "action": "spawned",
                    "screen": "game",
                    "position": (unit_data["position"]["row"], unit_data["position"]["column"])
                })

            # Preload deck data for card-drawing hexes
            for hex_data in self.card_drawing_hexes:
                if "deck_file" in hex_data and hex_data["deck_file"]:
                    deck_file = resolve_deck_path(hex_data["deck_file"])
                    if deck_file not in self.deck_data:
                        try:
                            with open(deck_file, 'r') as df:
                                self.deck_data[deck_file] = json.load(df)
                            print(f"Loaded deck: {deck_file}, contents: {self.deck_data[deck_file]}")
                        except Exception as e:
                            print(f"Error loading deck {deck_file}: {e}")

            # Load location hexes
            self.location_hexes = level_data.get("location_hexes", [])
            self.location_data = {}
            for loc_hex in self.location_hexes:
                row, col = loc_hex["row"], loc_hex["column"]
                self.location_data[(row, col)] = {
                    "card": None,
                    "shop": loc_hex.get("shop_inventory", []),
                    "turns": loc_hex.get("turns_since_cycle", 0),
                    "visited": loc_hex.get("visited_this_turn", False),
                    "deck_file": loc_hex.get("location_deck_file"),
                    "assigned_card_id": loc_hex.get("assigned_location_card_id"),
                    "assigned_npc_id": loc_hex.get("assigned_npc_card_id"),
                    "state": loc_hex.get("location_state", 1),
                    "available_npcs": []  # NPCs waiting to be recruited at this location
                }
                # Load pre-assigned location card if specified
                if loc_hex.get("assigned_location_card_id"):
                    card_id = loc_hex["assigned_location_card_id"]
                    card_data = load_card(card_id)
                    if card_data:
                        self.location_data[(row, col)]["card"] = InventoryCard(card_data)
                        # Set the card state if specified
                        if loc_hex.get("location_state", 1) == 2:
                            self.location_data[(row, col)]["card"].current_state = 2
                    else:
                        print(f"Warning: Location card '{card_id}' not found")
                # Preload location deck
                if loc_hex.get("location_deck_file"):
                    deck_file = resolve_deck_path(loc_hex["location_deck_file"])
                    if deck_file not in self.deck_data:
                        try:
                            with open(deck_file, 'r') as df:
                                self.deck_data[deck_file] = json.load(df)
                        except Exception as e:
                            print(f"Error loading location deck {deck_file}: {e}")
            
            # Recalculate view offsets based on new grid size
            grid_width = self.cols * self.hex_size * 1.5
            grid_height = self.rows * self.hex_size * 1.732
            self.view_offset_x = (pygame.display.Info().current_w - grid_width) / 2 if grid_width < pygame.display.Info().current_w else 0
            self.view_offset_y = (pygame.display.Info().current_h - grid_height) / 2 if grid_height < pygame.display.Info().current_h else 0

        except Exception as e:
            print(f"Error loading level: {e}")
            # Fallback to default setup only on error
            self.rows, self.cols, self.hex_size = 16, 24, 30
            self.grid = [[{"unit": None, "accessible": True, "terrain": "grass"} for _ in range(self.cols)] for _ in range(self.rows)]
            if player:
                self.place_unit(player, self.rows // 2, self.cols // 2)

    def get_hex_center(self, row, col):
        x = self.view_offset_x + col * self.hex_size * 1.5
        y = self.view_offset_y + row * self.hex_size * 1.732 + (col % 2) * self.hex_size * 0.866
        return x, y

    def get_hex_at_pixel(self, x, y):
        grid_left = self.view_offset_x
        grid_right = self.view_offset_x + (self.cols * self.hex_size * 1.5)
        grid_top = self.view_offset_y
        grid_bottom = self.view_offset_y + (self.rows * self.hex_size * 1.732)
        padding = self.hex_size
        if not (grid_left - padding <= x <= grid_right + padding and grid_top - padding <= y <= grid_bottom + padding):
            return None
        min_dist = float('inf')
        selected_hex = None
        for row in range(self.rows):
            for col in range(self.cols):
                center_x, center_y = self.get_hex_center(row, col)
                dist = (x - center_x) ** 2 + (y - center_y) ** 2
                if dist < min_dist and dist < (self.hex_size ** 2):
                    min_dist = dist
                    selected_hex = (row, col)
        return selected_hex

    def place_unit(self, unit, row, col):
        if (0 <= row < self.rows and 0 <= col < self.cols and 
            self.grid[row][col]["unit"] is None and self.grid[row][col]["accessible"]):
            self.grid[row][col]["unit"] = unit
            unit.position = (row, col)
            if isinstance(unit, Player):
                self.player = unit
            else:
                self.units.append(unit)
            return True, f"{unit.class_name if isinstance(unit, Player) else unit.name} placed at ({row}, {col})"
        else:
            print(f"Cannot place unit at ({row}, {col}): out of bounds, occupied, or inaccessible")
            return False, ""

    def move_unit(self, unit, new_row, new_col):
        if (0 <= new_row < self.rows and 0 <= new_col < self.cols and 
            self.grid[new_row][new_col]["unit"] is None and self.grid[new_row][new_col]["accessible"]):
            unit.animate_move(self, new_row, new_col)
            return True, f"{unit.class_name if isinstance(unit, Player) else unit.name} moved to ({new_row}, {new_col})"
        return False, ""

    def draw_card(self, row, col, card_manager):
        for hex_data in self.card_drawing_hexes:
            if hex_data["row"] == row and hex_data["column"] == col:
                if "linked_level" in hex_data and hex_data["linked_level"]:
                    # This hex is a portal to another level
                    return None, f"Portal to {hex_data['linked_level']}"
                elif "deck_file" in hex_data and hex_data["deck_file"]:
                    deck_file = resolve_deck_path(hex_data["deck_file"])
                    deck = self.deck_data.get(deck_file)
                    if not deck or not deck["cards"]:
                        return None, "Deck is empty"
                    card_id = hex_data.get("card_id") or random.choice(deck["cards"])
                    card_data = load_card(card_id)
                    if not card_data:
                        return None, f"Card '{card_id}' not found"
                    card = InventoryCard(card_data)
                    card_manager.track_card_usage(card_id, {"action": "drawn", "screen": "game", "position": (row, col)})
                    return card, f"Drew {card.get_current_data().get('Name', 'Unnamed')}"
        return None, "No deck or linked level at this hex"

    # ========== LOCATION SYSTEM METHODS ==========

    def is_location_hex(self, row, col):
        """Check if a hex is designated as a location hex."""
        return (row, col) in self.location_data

    def get_location_card(self, row, col):
        """Get the assigned location card for a hex."""
        loc_data = self.location_data.get((row, col))
        if loc_data:
            return loc_data.get("card")
        return None

    def draw_location_card(self, row, col, card_manager):
        """Draw a random location card from the hex's location deck and assign it."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return None, "Not a location hex"

        if loc_data.get("card"):
            return loc_data["card"], "Location already assigned"

        deck_file = loc_data.get("deck_file")
        if not deck_file:
            return None, "No location deck assigned"

        deck_path = resolve_deck_path(deck_file)
        deck = self.deck_data.get(deck_path)
        if not deck or not deck.get("cards"):
            return None, "Location deck is empty"

        card_id = random.choice(deck["cards"])
        # Remove the drawn card from the deck so it can't be drawn again
        deck["cards"].remove(card_id)

        card_data = load_card(card_id)
        if not card_data:
            return None, f"Location card '{card_id}' not found"

        location_card = InventoryCard(card_data)
        loc_data["card"] = location_card
        loc_data["assigned_card_id"] = card_id

        # Initialize shop inventory
        self._initialize_shop(row, col)

        card_manager.track_card_usage(card_id, {
            "action": "location_assigned",
            "screen": "game",
            "position": (row, col)
        })
        return location_card, f"Discovered {card_data['data'].get('Name', 'Unknown Location')}"

    def _initialize_shop(self, row, col):
        """Initialize or refresh the shop inventory for a location."""
        loc_data = self.location_data.get((row, col))
        if not loc_data or not loc_data.get("card"):
            return

        card = loc_data["card"]
        card_data = card.get_current_data()

        shop_deck_file = card_data.get("Shop_Deck")
        shop_size = int(card_data.get("Shop_Size", 3) or 3)

        if not shop_deck_file:
            loc_data["shop"] = []
            return

        deck_path = resolve_deck_path(shop_deck_file)
        if deck_path not in self.deck_data:
            try:
                with open(deck_path, 'r') as df:
                    self.deck_data[deck_path] = json.load(df)
            except Exception as e:
                print(f"Error loading shop deck {shop_deck_file}: {e}")
                loc_data["shop"] = []
                return

        deck = self.deck_data.get(deck_path)
        if not deck or not deck.get("cards"):
            loc_data["shop"] = []
            return

        # Draw cards for shop inventory
        shop_items = []
        available_cards = deck["cards"].copy()
        for _ in range(min(shop_size, len(available_cards))):
            if not available_cards:
                break
            card_id = random.choice(available_cards)
            available_cards.remove(card_id)

            item_data = load_card(card_id)
            if not item_data:
                print(f"Skipping shop item: card '{card_id}' not found")
                continue

            item_card = InventoryCard(item_data)
            # Calculate price
            price = self._calculate_item_price(item_card, card_data)
            shop_items.append({"card": item_card, "price": price})

        loc_data["shop"] = shop_items

    def _calculate_item_price(self, item_card, location_data):
        """Calculate the price for a shop item."""
        item_data = item_card.get_current_data()
        currency_type = location_data.get("Shop_Currency", "metal")

        # Try to get price from item data
        if "Price" in item_data:
            try:
                amount = int(item_data["Price"])
                return {"type": currency_type, "amount": amount}
            except (ValueError, TypeError):
                pass

        # Calculate from material values
        total_value = 0
        value_fields = ["Raw Material Value", "Refined Material Value", "Metal Value", "Wood Value"]
        for field in value_fields:
            try:
                total_value += int(item_data.get(field, 0) or 0)
            except (ValueError, TypeError):
                pass

        # Apply markup
        total_value = max(1, int(total_value * 1.5))
        return {"type": currency_type, "amount": total_value}

    def trigger_location_outcome(self, row, col):
        """Trigger a weighted random outcome for the location (if not visited this turn)."""
        loc_data = self.location_data.get((row, col))
        if not loc_data or not loc_data.get("card"):
            return None, "No location at this hex"

        if loc_data.get("visited"):
            return None, "Already triggered outcome this turn"

        card = loc_data["card"]
        card_data = card.get_current_data()

        outcomes_str = card_data.get("Outcomes", "[]")
        try:
            outcomes = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
        except json.JSONDecodeError:
            outcomes = []

        if not outcomes:
            return None, "No outcomes defined for this location"

        # Weighted random selection
        total_prob = sum(o.get("probability", 0) for o in outcomes)
        if total_prob <= 0:
            return None, "Invalid outcome probabilities"

        roll = random.random() * total_prob
        cumulative = 0
        selected_outcome = None
        for outcome in outcomes:
            cumulative += outcome.get("probability", 0)
            if roll <= cumulative:
                selected_outcome = outcome
                break

        if not selected_outcome:
            return None, "No outcome selected"

        card_type = selected_outcome.get("card_type")
        if card_type == "None" or not card_type:
            return None, "Nothing found"

        deck_file = selected_outcome.get("deck_file")
        if not deck_file:
            return None, f"No deck specified for {card_type}"

        deck_path = resolve_deck_path(deck_file)
        if deck_path not in self.deck_data:
            try:
                with open(deck_path, 'r') as df:
                    self.deck_data[deck_path] = json.load(df)
            except Exception as e:
                return None, f"Error loading outcome deck: {e}"

        deck = self.deck_data.get(deck_path)
        if not deck or not deck.get("cards"):
            return None, "Outcome deck is empty"

        card_id = random.choice(deck["cards"])
        outcome_card_data = load_card(card_id)
        if not outcome_card_data:
            return None, f"Outcome card '{card_id}' not found"

        outcome_card = InventoryCard(outcome_card_data)
        return outcome_card, f"Found {outcome_card_data['data'].get('Name', 'Unknown Item')}"

    def upgrade_location(self, row, col, npc_card=None, doc_card=None):
        """Upgrade a location to its second state (requires NPC or document conditions)."""
        loc_data = self.location_data.get((row, col))
        if not loc_data or not loc_data.get("card"):
            return False, "No location at this hex"

        card = loc_data["card"]
        if card.states != 2:
            return False, "This location cannot be upgraded"

        if card.current_state == 2:
            return False, "Location already upgraded"

        card_data = card.get_current_data()

        # Check NPC requirement
        required_npc_type = card_data.get("Upgrade_NPC_Type")
        if required_npc_type and npc_card:
            npc_data = npc_card.get_current_data() if hasattr(npc_card, 'get_current_data') else npc_card
            npc_allegiance = npc_data.get("Allegiance (Hostile, Neutral, Allied)", "")
            if required_npc_type not in npc_allegiance:
                return False, f"Requires {required_npc_type} NPC"

        # Check material cost
        material_cost_str = card_data.get("Upgrade_Material_Cost", "{}")
        try:
            material_cost = json.loads(material_cost_str) if isinstance(material_cost_str, str) else material_cost_str
        except json.JSONDecodeError:
            material_cost = {}

        # Flip the card to state 2
        card.toggle_state()
        loc_data["state"] = 2
        loc_data["assigned_npc_id"] = npc_card.card_data.get("id") if npc_card and hasattr(npc_card, 'card_data') else None

        # Refresh shop with new state's shop deck
        self._initialize_shop(row, col)

        new_name = card.get_current_data().get("Name", "Upgraded Location")
        return True, f"Location upgraded to {new_name}"

    def add_npc_to_location(self, unit, location_pos):
        """
        Remove an NPC unit from the map and add them to a location's available NPCs.
        Used when a quest NPC reaches their destination.

        Args:
            unit: The Unit object to move to the location
            location_pos: (row, col) tuple of the target location

        Returns: (success, message)
        """
        loc_data = self.location_data.get(location_pos)
        if not loc_data:
            return False, "No location at that position"

        # Stop any animations on the unit to prevent game freeze
        unit.animating = False
        unit.target_pos = None

        # Remove unit from map
        if unit.position:
            self.grid[unit.position[0]][unit.position[1]]["unit"] = None
        if unit in self.units:
            self.units.remove(unit)

        # Create NPC card data from unit
        npc_data = {
            "id": unit.card_id,
            "name": unit.name,
            "card_type": unit.card_type,
            "hp": unit.hp,
            "max_hp": unit.max_hp,
            "movement": unit.movement,
            "melee_damage": unit.melee_damage,
            "projectile_damage": unit.projectile_damage,
            "projectile_range": unit.projectile_range,
            "allegiance": unit.allegiance
        }

        # Add to location's available NPCs
        loc_data["available_npcs"].append(npc_data)

        return True, f"{unit.name} arrived at the location"

    def get_available_npcs(self, row, col):
        """Get NPCs available for recruitment at a location."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return []
        return loc_data.get("available_npcs", [])

    def recruit_npc_from_location(self, row, col, npc_index):
        """Remove an NPC from location's available list and return their data."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return None, "No location at this position"

        available = loc_data.get("available_npcs", [])
        if npc_index < 0 or npc_index >= len(available):
            return None, "Invalid NPC selection"

        npc_data = available.pop(npc_index)
        return npc_data, f"{npc_data['name']} joined your party"

    def get_shop_inventory(self, row, col):
        """Get the current shop inventory for a location."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return []
        return loc_data.get("shop", [])

    def purchase_from_shop(self, row, col, item_index, player_inventory, materials_offered=None):
        """Purchase an item from a location's shop."""
        loc_data = self.location_data.get((row, col))
        if not loc_data or not loc_data.get("card"):
            return None, "No shop at this location"

        shop = loc_data.get("shop", [])
        if item_index < 0 or item_index >= len(shop):
            return None, "Invalid item selection"

        shop_item = shop[item_index]
        price = shop_item.get("price", {})

        # Validate payment
        if price.get("type") == "cards":
            # Card-based trading
            required_type = price.get("card_type")
            required_count = price.get("count", 1)
            matching_cards = [c for c in (materials_offered or [])
                           if c.card_data.get("card_type") == required_type]
            if len(matching_cards) < required_count:
                return None, f"Need {required_count} {required_type} cards"
        else:
            # Material-based payment
            currency = price.get("type", "metal")
            amount = price.get("amount", 0)

            # Calculate total material value from offered cards
            offered_value = 0
            currency_to_field = {
                "metal": "Metal Value",
                "wood": "Wood Value",
                "raw_materials": "Raw Material Value",
                "refined_materials": "Refined Material Value"
            }
            field = currency_to_field.get(currency, "Metal Value")

            for card in (materials_offered or []):
                card_data = card.get_current_data()
                try:
                    offered_value += int(card_data.get(field, 0) or 0)
                except (ValueError, TypeError):
                    pass

            if offered_value < amount:
                return None, f"Need {amount} {currency}, offered {offered_value}"

        # Complete purchase
        purchased_card = shop_item["card"]
        shop.pop(item_index)

        # Replenish shop slot
        self._replenish_shop_slot(row, col)

        return purchased_card, f"Purchased {purchased_card.get_current_data().get('Name', 'Item')}"

    def _replenish_shop_slot(self, row, col):
        """Replenish a single shop slot after a purchase."""
        loc_data = self.location_data.get((row, col))
        if not loc_data or not loc_data.get("card"):
            return

        card = loc_data["card"]
        card_data = card.get_current_data()
        shop_deck_file = card_data.get("Shop_Deck")
        shop_size = int(card_data.get("Shop_Size", 3) or 3)

        if not shop_deck_file:
            return

        deck_path = resolve_deck_path(shop_deck_file)
        deck = self.deck_data.get(deck_path)
        if not deck or not deck.get("cards"):
            return

        shop = loc_data.get("shop", [])
        if len(shop) >= shop_size:
            return

        # Get card IDs already in shop
        shop_card_ids = [item["card"].card_data.get("id") for item in shop if item.get("card")]
        available_cards = [cid for cid in deck["cards"] if cid not in shop_card_ids]

        if not available_cards:
            available_cards = deck["cards"].copy()

        card_id = random.choice(available_cards)
        item_data = load_card(card_id)
        if not item_data:
            print(f"Skipping shop replenishment: card '{card_id}' not found")
            return

        item_card = InventoryCard(item_data)
        price = self._calculate_item_price(item_card, card_data)
        shop.append({"card": item_card, "price": price})

    def cycle_shop_inventory(self, row, col):
        """Refresh all shop items for a location."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return

        loc_data["shop"] = []
        loc_data["turns"] = 0
        self._initialize_shop(row, col)

    def on_turn_end(self):
        """Called at end of turn cycle. Increments turn counters and checks for shop cycles."""
        for pos, loc_data in self.location_data.items():
            if not loc_data.get("card"):
                continue

            card = loc_data["card"]
            card_data = card.get_current_data()

            # Increment turn counter
            loc_data["turns"] = loc_data.get("turns", 0) + 1

            # Check for shop cycle
            cycle_turns = int(card_data.get("Shop_Cycle_Turns", 0) or 0)
            if cycle_turns > 0 and loc_data["turns"] >= cycle_turns:
                self.cycle_shop_inventory(pos[0], pos[1])

    def mark_location_visited(self, row, col):
        """Mark a location as visited this turn (prevents multiple outcomes)."""
        loc_data = self.location_data.get((row, col))
        if loc_data:
            loc_data["visited"] = True

    def reset_location_visits(self):
        """Reset all location visited flags at turn start."""
        for loc_data in self.location_data.values():
            loc_data["visited"] = False

    def create_location_hex(self, row, col, location_card):
        """
        Create a new location hex from a Location_Plan card.

        Args:
            row, col: Position to place the location
            location_card: InventoryCard (Location_Plan in state 2) to use

        Returns:
            tuple: (success, message)
        """
        # Validate position
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return False, "Position is out of bounds"

        # Check if hex is accessible terrain
        cell = self.grid[row][col]
        if not cell.get("accessible", True):
            return False, "Cannot build on inaccessible terrain"

        # Check if there's already a location here
        if (row, col) in self.location_data:
            return False, "A location already exists at this position"

        # Check if there's a unit here
        if cell.get("unit") is not None:
            return False, "Cannot build on an occupied hex"

        # Get card data (should be in state 2 - the actual location)
        card_data = location_card.get_current_data()
        loc_name = card_data.get("Name", "Built Location")

        # Add to location_hexes list
        loc_hex_data = {
            "row": row,
            "column": col,
            "shop_inventory": [],
            "turns_since_cycle": 0,
            "visited_this_turn": False
        }
        self.location_hexes.append(loc_hex_data)

        # Add to location_data dict
        self.location_data[(row, col)] = {
            "card": location_card,
            "shop": [],
            "turns": 0,
            "visited": False,
            "deck_file": None,
            "assigned_card_id": location_card.card_data.get("id"),
            "assigned_npc_id": None,
            "state": location_card.current_state,
            "available_npcs": []
        }

        # Initialize shop if defined in card
        self._initialize_shop(row, col)

        return True, f"Built {loc_name} at ({row}, {col})"

    def get_location_choices(self, row, col):
        """Get the available choices for a location."""
        loc_data = self.location_data.get((row, col))
        if not loc_data or not loc_data.get("card"):
            return []

        card = loc_data["card"]
        card_data = card.get_current_data()

        choices_str = card_data.get("Choices", "[]")
        try:
            choices = json.loads(choices_str) if isinstance(choices_str, str) else choices_str
        except json.JSONDecodeError:
            choices = []

        return choices

    # ========== END LOCATION SYSTEM METHODS ==========

    # ========== EDGE SPAWNING METHODS ==========

    def get_edge_spawn_position(self, edge="random"):
        """
        Get a random empty spawn position on a map edge.
        edge: "north", "south", "east", "west", or "random"
        Returns (row, col) tuple or None if no valid position found.
        """
        if edge == "random":
            edge = random.choice(["north", "south", "east", "west"])

        candidates = []

        if edge == "north":
            # Top row (row 0)
            for col in range(self.cols):
                if self._is_valid_spawn(0, col):
                    candidates.append((0, col))
        elif edge == "south":
            # Bottom row
            for col in range(self.cols):
                if self._is_valid_spawn(self.rows - 1, col):
                    candidates.append((self.rows - 1, col))
        elif edge == "west":
            # Left column (col 0)
            for row in range(self.rows):
                if self._is_valid_spawn(row, 0):
                    candidates.append((row, 0))
        elif edge == "east":
            # Right column
            for row in range(self.rows):
                if self._is_valid_spawn(row, self.cols - 1):
                    candidates.append((row, self.cols - 1))

        if candidates:
            return random.choice(candidates)
        return None

    def _is_valid_spawn(self, row, col):
        """Check if a position is valid for spawning (empty and accessible)."""
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return False
        cell = self.grid[row][col]
        return cell.get("unit") is None and cell.get("accessible", True)

    def get_edge_positions(self, edge):
        """Get all positions on a specific edge of the map."""
        positions = []
        if edge == "north":
            positions = [(0, col) for col in range(self.cols)]
        elif edge == "south":
            positions = [(self.rows - 1, col) for col in range(self.cols)]
        elif edge == "west":
            positions = [(row, 0) for row in range(self.rows)]
        elif edge == "east":
            positions = [(row, self.cols - 1) for row in range(self.rows)]
        return positions

    # ========== END EDGE SPAWNING METHODS ==========

    def offset_to_cube(self, col, row):
        x = col
        z = row - (col // 2)
        y = -x - z
        return x, y, z

    def cube_to_offset(self, x, z):
        col = x
        row = z + (x // 2)
        return row, col

    def hex_distance(self, pos1, pos2):
        row1, col1 = pos1
        row2, col2 = pos2
        x1, y1, z1 = self.offset_to_cube(col1, row1)
        x2, y2, z2 = self.offset_to_cube(col2, row2)
        return max(abs(x1 - x2), abs(y1 - y2), abs(z1 - z2))

    def get_line(self, start_row, start_col, direction, max_distance):
        start_x, start_y, start_z = self.offset_to_cube(start_col, start_row)
        dir_x, dir_y, dir_z = direction
        line = []
        for k in range(1, max_distance + 1):
            x = start_x + k * dir_x
            y = start_y + k * dir_y
            z = start_z + k * dir_z
            row, col = self.cube_to_offset(x, z)
            if 0 <= row < self.rows and 0 <= col < self.cols:
                line.append((row, col))
            else:
                break
        return line

    def is_aligned(self, start_pos, target_pos, max_distance):
        start_row, start_col = start_pos
        target_row, target_col = target_pos
        lines = [self.get_line(start_row, start_col, dir, max_distance) for dir in DIRECTIONS]
        return any((target_row, target_col) in line for line in lines)

    def get_line_between(self, start_row, start_col, end_row, end_col):
        distance = self.hex_distance((start_row, start_col), (end_row, end_col))
        for dir in DIRECTIONS:
            line = self.get_line(start_row, start_col, dir, distance)
            if (end_row, end_col) in line:
                idx = line.index((end_row, end_col))
                return line[:idx + 1]
        return []

    def has_clear_line_of_sight(self, start_pos, target_pos):
        start_row, start_col = start_pos
        end_row, end_col = target_pos
        line = self.get_line_between(start_row, start_col, end_row, end_col)
        if not line:
            return False
        for row, col in line[1:-1]:
            if self.grid[row][col]["unit"] is not None or not self.grid[row][col]["accessible"]:
                return False
        return True

    def get_neighbors(self, row, col, goal=None):
        if col % 2 == 0:
            offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1)]
        else:
            offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (1, -1), (1, 1)]
        neighbors = [(row + dr, col + dc) for dr, dc in offsets]
        return [(r, c) for r, c in neighbors if 0 <= r < self.rows and 0 <= c < self.cols and 
                self.grid[r][c]["accessible"] and ((goal and (r, c) == goal) or self.grid[r][c]["unit"] is None)]

    def find_path(self, start, goal):
        frontier = [(0, start)]
        came_from = {start: None}
        cost_so_far = {start: 0}
        while frontier:
            _, current = heappop(frontier)
            if current == goal:
                break
            for next_pos in self.get_neighbors(*current, goal=goal):
                new_cost = cost_so_far[current] + 1
                if next_pos not in cost_so_far or new_cost < cost_so_far[next_pos]:
                    cost_so_far[next_pos] = new_cost
                    priority = new_cost + self.hex_distance(next_pos, goal)
                    heappush(frontier, (priority, next_pos))
                    came_from[next_pos] = current
        if goal not in came_from:
            return None
        path = []
        current = goal
        while current != start:
            path.append(current)
            current = came_from[current]
        path.append(start)
        return path[::-1]

    def get_movement_range(self, start, movement):
        reachable = set()
        frontier = deque([(0, start)])
        visited = set([start])
        while frontier:
            cost, current = frontier.popleft()
            if cost > movement:
                continue
            reachable.add(current)
            for neighbor in self.get_neighbors(*current):
                if neighbor not in visited and self.grid[neighbor[0]][neighbor[1]]["unit"] is None:
                    visited.add(neighbor)
                    frontier.append((cost + 1, neighbor))
        return reachable

    def get_valid_moves(self, start, movement):
        reachable = self.get_movement_range(start, movement)
        return [pos for pos in reachable if pos != start and self.grid[pos[0]][pos[1]]["unit"] is None]

    def get_hexes_at_distance(self, position, distance):
        """Return list of hex positions exactly 'distance' away from position."""
        if distance == 0:
            return [position]

        result = []
        row, col = position
        center_x, center_y, center_z = self.offset_to_cube(col, row)

        # Use hex ring algorithm - walk around the ring at given distance
        # Start at one corner and walk in each of 6 directions
        for direction_idx in range(6):
            # Starting position for this edge of the ring
            dir_x, dir_y, dir_z = DIRECTIONS[direction_idx]
            # Move to the starting corner
            start_dir = DIRECTIONS[(direction_idx + 2) % 6]
            x = center_x + distance * start_dir[0]
            y = center_y + distance * start_dir[1]
            z = center_z + distance * start_dir[2]

            # Walk along this edge of the ring
            for step in range(distance):
                hex_row, hex_col = self.cube_to_offset(x, z)
                if 0 <= hex_row < self.rows and 0 <= hex_col < self.cols:
                    if (hex_row, hex_col) not in result:
                        result.append((hex_row, hex_col))
                x += dir_x
                y += dir_y
                z += dir_z

        return result

    def get_adjacent_hexes(self, row, col):
        """Return list of all adjacent hex positions (distance 1), including occupied ones."""
        return self.get_hexes_at_distance((row, col), 1)

    def find_empty_hex_near(self, position, max_distance):
        """Find an accessible empty hex within max_distance of position."""
        for dist in range(1, max_distance + 1):
            candidates = self.get_hexes_at_distance(position, dist)
            # Shuffle to add randomness
            random.shuffle(candidates)
            for pos in candidates:
                r, c = pos
                if (0 <= r < self.rows and 0 <= c < self.cols and
                    self.grid[r][c]["accessible"] and
                    self.grid[r][c]["unit"] is None):
                    return pos
        return None

    def get_attack_range(self, start, range_limit, is_projectile=False):
        if is_projectile:
            attack_hexes = set()
            row, col = start
            for dir in DIRECTIONS:
                line = self.get_line(row, col, dir, range_limit)
                for hex_pos in line:
                    distance = self.hex_distance(start, hex_pos)
                    if 1 < distance <= range_limit and self.has_clear_line_of_sight(start, hex_pos):
                        attack_hexes.add(hex_pos)
            return attack_hexes
        else:
            # For melee, get all adjacent hexes (including those with units)
            return set(self.get_adjacent_hexes(*start))

    def calculate_range(self, pos, distance, pattern, include_pos=False, exclude_adj=False):
        """
        Calculate range hexes based on pattern type and modifiers.

        Patterns:
        - line_of_sight: Standard projectile range along hex lines with LOS check
        - melee: Adjacent hexes only (distance 1)
        - area_effect: All reachable hexes within distance (like movement)
        - echo: Hexes at odd distances only
        - multi_echo: Hexes at even distances only
        - perimeter: Hexes at exactly the specified distance
        - mist_shadow: 6 directional lines (bisecting hex directions)

        Args:
            pos: Starting position (row, col)
            distance: Maximum range distance
            pattern: Pattern type string
            include_pos: Include caster's hex in range
            exclude_adj: Exclude adjacent hexes from range

        Returns:
            set: Set of (row, col) positions in range
        """
        if distance < 0:
            return set()

        range_set = set()

        if pattern == "line_of_sight":
            range_set = self.get_attack_range(pos, distance, is_projectile=True)

        elif pattern == "melee":
            range_set = self.get_attack_range(pos, distance, is_projectile=False)

        elif pattern == "area_effect":
            # All hexes within distance (uses movement range logic but includes blocked hexes for targeting)
            range_set = self._get_area_effect_range(pos, distance)

        elif pattern == "echo":
            # Hexes at odd distances only
            base_range = self._get_area_effect_range(pos, distance)
            range_set = {hex_pos for hex_pos in base_range
                        if self.hex_distance(pos, hex_pos) % 2 == 1 and
                        self.grid[hex_pos[0]][hex_pos[1]]["accessible"]}

        elif pattern == "multi_echo":
            # Hexes at even distances only
            base_range = self._get_area_effect_range(pos, distance)
            range_set = {hex_pos for hex_pos in base_range
                        if self.hex_distance(pos, hex_pos) % 2 == 0 and
                        self.grid[hex_pos[0]][hex_pos[1]]["accessible"]}

        elif pattern == "perimeter":
            # Hexes at exactly the specified distance
            base_range = self._get_area_effect_range(pos, distance)
            range_set = {hex_pos for hex_pos in base_range
                        if self.hex_distance(pos, hex_pos) == distance and
                        self.grid[hex_pos[0]][hex_pos[1]]["accessible"]}

        elif pattern == "mist_shadow":
            # 6 directional lines bisecting hex directions
            range_set = self._get_mist_shadow_range(pos, distance)

        else:
            # Default to line of sight
            range_set = self.get_attack_range(pos, distance, is_projectile=True)

        # Apply include_pos modifier
        if include_pos:
            range_set.add(pos)
        elif pos in range_set:
            range_set.remove(pos)

        # Apply exclude_adjacent modifier
        if exclude_adj:
            adjacent = set(self.get_adjacent_hexes(*pos))
            range_set -= adjacent

        return range_set

    def _get_area_effect_range(self, start, max_distance):
        """Get all hexes within max_distance (flood fill without requiring path)."""
        result = set()
        for dist in range(0, max_distance + 1):
            hexes_at_dist = self.get_hexes_at_distance(start, dist)
            for hex_pos in hexes_at_dist:
                r, c = hex_pos
                if 0 <= r < self.rows and 0 <= c < self.cols:
                    result.add(hex_pos)
        return result

    def _get_mist_shadow_range(self, pos, distance):
        """
        Calculate mist/shadow range pattern - 6 directional lines that bisect
        the standard hex directions (30°, 90°, 150°, 210°, 270°, 330°).
        """
        range_set = set()
        row, col = pos
        is_odd_col = col % 2 != 0

        # Define step offsets for diagonal angles based on column parity
        # These create lines that bisect the standard hex directions
        step_offsets = {
            30: [(-1, 1), (-3, 2), (-4, 3), (-6, 4)] if is_odd_col else [(-2, 1), (-3, 2), (-5, 3), (-6, 4)],
            150: [(2, 1), (3, 2), (5, 3), (6, 4)] if is_odd_col else [(1, 1), (3, 2), (4, 3), (6, 4)],
            210: [(2, -1), (3, -2), (5, -3), (6, -4)] if is_odd_col else [(1, -1), (3, -2), (4, -3), (6, -4)],
            330: [(-1, -1), (-3, -2), (-4, -3), (-6, -4)] if is_odd_col else [(-2, -1), (-3, -2), (-5, -3), (-6, -4)]
        }

        angles = [30, 90, 150, 210, 270, 330]

        for angle in angles:
            line = []

            if angle in [90, 270]:
                # Horizontal directions: step by 2 columns
                steps = min(4, distance)
                for step in range(1, steps + 1):
                    new_c = col + (2 * step if angle == 90 else -2 * step)
                    new_pos = (row, new_c)

                    if (0 <= row < self.rows and 0 <= new_c < self.cols and
                        self.hex_distance(pos, new_pos) <= distance):
                        if self.grid[row][new_c]["accessible"]:
                            line.append(new_pos)
                        else:
                            break  # Stop at obstruction
                    else:
                        break
            else:
                # Diagonal directions: use predefined offsets
                offsets = step_offsets[angle]
                for dr, dc in offsets[:min(4, distance)]:
                    new_r, new_c = row + dr, col + dc
                    new_pos = (new_r, new_c)

                    if (0 <= new_r < self.rows and 0 <= new_c < self.cols and
                        self.hex_distance(pos, new_pos) <= distance):
                        if self.grid[new_r][new_c]["accessible"]:
                            line.append(new_pos)
                        else:
                            break  # Stop at obstruction
                    else:
                        break

            range_set.update(line)

        return range_set

    def is_in_range(self, attacker_pos, target_pos, distance, pattern, include_pos=False, exclude_adj=False):
        """
        Check if a target position is within attack range using specified pattern.

        Args:
            attacker_pos: Attacker's position (row, col)
            target_pos: Target's position (row, col)
            distance: Maximum range distance
            pattern: Pattern type string
            include_pos: Include caster's hex in range
            exclude_adj: Exclude adjacent hexes from range

        Returns:
            bool: True if target is in range
        """
        range_set = self.calculate_range(attacker_pos, distance, pattern, include_pos, exclude_adj)
        return target_pos in range_set

    def get_targetable_units(self, attack_range, attacker_allegiance="player"):
        """
        Get list of units that can be targeted within the given attack range.

        Args:
            attack_range: Set of (row, col) positions that can be attacked
            attacker_allegiance: "player", "Allied", "Neutral", or "Hostile"

        Returns:
            List of units that are valid targets within range
        """
        if not attack_range:
            return []

        targetable = []
        for pos in attack_range:
            row, col = pos
            if 0 <= row < self.rows and 0 <= col < self.cols:
                unit = self.grid[row][col].get("unit")
                if unit and hasattr(unit, 'allegiance'):
                    # Player targets hostile units
                    if attacker_allegiance == "player" and unit.allegiance == "Hostile":
                        targetable.append(unit)
                    # Allied units target hostile units
                    elif attacker_allegiance == "Allied" and unit.allegiance == "Hostile":
                        targetable.append(unit)
                    # Hostile units target player and allies
                    elif attacker_allegiance == "Hostile" and unit.allegiance in ["Allied", "player"]:
                        targetable.append(unit)

        return targetable

    def draw(self, surface, movement_range=None, attack_range=None, colors=None, targetable_units=None):
        if colors is None:
            colors = {
                'BLUE': (0, 0, 255),
                'DARK_RED_ALPHA': (100, 0, 0, 128),
                'LIGHT_GREEN': (144, 238, 144),
                'YELLOW': (255, 255, 0),
                'GOLDEN_YELLOW': (255, 215, 0),
                'GREEN': (0, 255, 0),
                'RED': (255, 0, 0),
                'GRAY': (128, 128, 128),
                'WHITE': (255, 255, 255),
                'PURPLE': (128, 0, 128),
                'ORANGE': (255, 165, 0)
            }
        hex_surface = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
        for row in range(self.rows):
            for col in range(self.cols):
                x, y = self.get_hex_center(row, col)
                points = [(x + self.hex_size * math.cos(math.radians(60 * i)),
                           y + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]

                # Draw terrain color as base
                terrain_type = self.grid[row][col].get("terrain", "grass")
                terrain_color = get_terrain_color(terrain_type)
                pygame.draw.polygon(hex_surface, terrain_color, points, 0)

                # Draw overlay for inaccessible hexes (darker tint)
                if not self.grid[row][col]["accessible"]:
                    # Darken the terrain color for manually marked inaccessible
                    if is_terrain_accessible(terrain_type):
                        dark_overlay = pygame.Surface((self.hex_size * 2, self.hex_size * 2), pygame.SRCALPHA)
                        dark_points = [(self.hex_size + self.hex_size * math.cos(math.radians(60 * i)),
                                       self.hex_size + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]
                        pygame.draw.polygon(dark_overlay, (0, 0, 0, 80), dark_points, 0)
                        hex_surface.blit(dark_overlay, (x - self.hex_size, y - self.hex_size))

                # Draw movement range overlay
                if movement_range and (row, col) in movement_range:
                    move_overlay = pygame.Surface((self.hex_size * 2, self.hex_size * 2), pygame.SRCALPHA)
                    move_points = [(self.hex_size + self.hex_size * math.cos(math.radians(60 * i)),
                                   self.hex_size + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]
                    pygame.draw.polygon(move_overlay, (0, 100, 255, 100), move_points, 0)
                    hex_surface.blit(move_overlay, (x - self.hex_size, y - self.hex_size))

                # Draw attack range overlay
                if attack_range and (row, col) in attack_range:
                    attack_overlay = pygame.Surface((self.hex_size * 2, self.hex_size * 2), pygame.SRCALPHA)
                    attack_points = [(self.hex_size + self.hex_size * math.cos(math.radians(60 * i)),
                                     self.hex_size + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]
                    pygame.draw.polygon(attack_overlay, (255, 0, 0, 80), attack_points, 0)
                    hex_surface.blit(attack_overlay, (x - self.hex_size, y - self.hex_size))

                # Draw special hex indicators
                for hex_data in self.card_drawing_hexes:
                    if hex_data["row"] == row and hex_data["column"] == col:
                        if "linked_level" in hex_data and hex_data["linked_level"]:
                            pygame.draw.polygon(hex_surface, colors['PURPLE'], points, 3)  # Purple for linked levels
                        elif "deck_file" in hex_data and hex_data["deck_file"] or "card_id" in hex_data and hex_data["card_id"]:
                            pygame.draw.polygon(hex_surface, colors['LIGHT_GREEN'], points, 3)  # Green for card-drawing
                        break
                # Draw location hex indicators
                if (row, col) in self.location_data:
                    loc_data = self.location_data[(row, col)]
                    pygame.draw.polygon(hex_surface, colors['ORANGE'], points, 3)  # Orange border for locations
                    # Draw house icon if location is assigned
                    if loc_data.get("card"):
                        is_upgraded = loc_data.get("state", 1) == 2
                        icon_color = colors['GREEN'] if is_upgraded else colors['ORANGE']
                        # Simple house shape (triangle roof + rectangle base)
                        house_size = self.hex_size * 0.3
                        house_x, house_y = x, y
                        roof_points = [
                            (house_x, house_y - house_size * 0.8),  # Top
                            (house_x - house_size * 0.6, house_y - house_size * 0.2),  # Bottom left
                            (house_x + house_size * 0.6, house_y - house_size * 0.2)   # Bottom right
                        ]
                        base_rect = pygame.Rect(
                            house_x - house_size * 0.4,
                            house_y - house_size * 0.2,
                            house_size * 0.8,
                            house_size * 0.6
                        )
                        pygame.draw.polygon(hex_surface, icon_color, roof_points)
                        pygame.draw.rect(hex_surface, icon_color, base_rect)
                if self.selected_hex == (row, col):
                    pygame.draw.polygon(hex_surface, colors['YELLOW'], points, 0)
                pygame.draw.polygon(hex_surface, colors['GOLDEN_YELLOW'], points, 1)

        # Second pass: Draw location names on top of hexes
        for (row, col), loc_data in self.location_data.items():
            if loc_data.get("card"):
                loc_card = loc_data["card"]
                loc_name = loc_card.get_current_data().get("Name", "")
                if loc_name:
                    x, y = self.get_hex_center(row, col)
                    house_size = self.hex_size * 0.3
                    name_surface = self.font.render(loc_name, True, colors['WHITE'])
                    name_rect = name_surface.get_rect(centerx=x, top=y + house_size * 0.5)
                    hex_surface.blit(name_surface, name_rect)

        # Update pulse time for targeting visuals
        self.pulse_time = pygame.time.get_ticks()

        # Third pass: Draw all units on top of hexes (for proper z-ordering)
        # This ensures animating units are visible and don't go under hexes
        # Collect all players (multiplayer mode or single player)
        all_players = self.players if self.players else ([self.player] if self.player else [])
        all_units = list(self.units) + all_players
        for unit in all_units:
            if unit and unit.position:
                # Use render_pos for animating units, otherwise use hex center
                if unit.animating and unit.render_pos:
                    pos = unit.render_pos
                else:
                    pos = self.get_hex_center(*unit.position)

                if isinstance(unit, Player) and unit.image:
                    scale_factor = (self.hex_size * 1.5 * unit.image_scale_factor) / unit.image.get_height()
                    scaled_image = pygame.transform.scale(unit.image,
                                                         (int(unit.image.get_width() * scale_factor),
                                                          int(unit.image.get_height() * scale_factor)))
                    image_rect = scaled_image.get_rect(center=(int(pos[0]), int(pos[1])))
                    hex_surface.blit(scaled_image, image_rect)
                    health_bar_y = image_rect.top - 5
                else:
                    # Use player's custom color if available (multiplayer), otherwise default colors
                    if isinstance(unit, Player):
                        color = unit.player_color if hasattr(unit, 'player_color') else colors['GREEN']
                    elif unit.allegiance == "Hostile":
                        color = colors['RED']
                    elif unit.allegiance == "Allied":
                        color = colors['BLUE']
                    else:
                        color = colors['GRAY']
                    radius = max(10, int(self.hex_size / 3))
                    pygame.draw.circle(hex_surface, colors['WHITE'] if unit.attack_flash else color,
                                       (int(pos[0]), int(pos[1])), radius)
                    health_bar_y = pos[1] - radius - 5  # Position health bar just above the circle

                    # Draw player number for multiplayer mode
                    if isinstance(unit, Player) and hasattr(unit, 'player_number') and len(all_players) > 1:
                        number_font = pygame.font.Font(None, int(radius * 1.5))
                        number_surface = number_font.render(str(unit.player_number), True, colors['WHITE'])
                        number_rect = number_surface.get_rect(center=(int(pos[0]), int(pos[1])))
                        hex_surface.blit(number_surface, number_rect)

                    # Draw unit name above health bar (with proper spacing)
                    name = unit.class_name if isinstance(unit, Player) else unit.name
                    # In multiplayer, prefix with "P1:" or "P2:"
                    if isinstance(unit, Player) and hasattr(unit, 'player_number') and len(all_players) > 1:
                        name = f"P{unit.player_number}: {name}"
                    text_surface = self.font.render(name, True, colors['WHITE'])
                    name_y = health_bar_y - 12  # Name above health bar with gap
                    text_rect = text_surface.get_rect(centerx=pos[0], bottom=name_y)
                    hex_surface.blit(text_surface, text_rect)
                    # Draw damage text if present (above the name)
                    if unit.damage_text:
                        damage_surface = self.font.render(unit.damage_text, True, colors['RED'])
                        damage_rect = damage_surface.get_rect(centerx=pos[0], bottom=text_rect.top - 2)
                        hex_surface.blit(damage_surface, damage_rect)
                unit.draw_health_bar(hex_surface, (pos[0], health_bar_y))

        surface.blit(hex_surface, (0, 0))

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
from attack_animations import AttackAnimationManager
from sound_manager import sound_manager

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
        self.hovered_hex = None  # Hex currently under mouse cursor
        self.hover_extra_lines = []  # Extra tooltip lines set by game screen (e.g. damage preview)
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
        self.active_turn_unit = None  # Unit/player whose turn is currently active (for glow ring)
        # Animation state for targeting visuals
        self.pulse_time = 0
        # Attack animation manager
        self.attack_anims = AttackAnimationManager(sound_mgr=sound_manager)

    def load_level(self, level_file, card_manager, player):
        try:
            with open(level_file, 'r') as f:
                level_data = json.load(f)
            # Set grid dimensions from the level file (support both formats)
            if "grid" in level_data:
                self.rows = level_data["grid"]["rows"]
                self.cols = level_data["grid"]["columns"]
            else:
                self.rows = level_data.get("grid_rows", self.rows)
                self.cols = level_data.get("grid_cols", self.cols)
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
                start_col = player_start.get("column", player_start.get("col", 0))
                self.place_unit(player, player_start["row"], start_col)
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
                    "available_npcs": [],  # NPCs waiting to be recruited at this location
                    # Enemy spawn location fields
                    "health": 0,
                    "max_health": 0,
                    "is_spawn_location": False,
                    "spawn_enemy_deck": None,
                    # NPC spawn location fields (churches)
                    "npc_health": 0,
                    "npc_max_health": 0,
                    "is_npc_spawn_location": False,
                    "npc_spawn_deck": None,
                    # Defensive location fields
                    "defenses": [],
                    "garrison_npcs": []
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
                        # Load spawn location properties from card data
                        self._init_spawn_location_data((row, col), card_data, loc_hex.get("location_state", 1))
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
            window_width = pygame.display.Info().current_w
            window_height = pygame.display.Info().current_h
            if grid_width < window_width and grid_height < window_height:
                # Small grid: center the entire grid on screen
                self.view_offset_x = (window_width - grid_width) / 2
                self.view_offset_y = (window_height - grid_height) / 2
            elif player_start:
                # Large grid: center view on player start position
                player_row = player_start["row"]
                player_col = player_start.get("column", player_start.get("col", 0))
                player_pixel_x = player_col * self.hex_size * 1.5
                player_pixel_y = player_row * self.hex_size * 1.732 + (player_col % 2) * self.hex_size * 0.866
                self.view_offset_x = window_width / 2 - player_pixel_x
                self.view_offset_y = window_height / 2 - player_pixel_y
            else:
                self.view_offset_x = 0
                self.view_offset_y = 0

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

    def _init_spawn_location_data(self, pos, card_data, state=1):
        """Initialize spawn location data from a location card (both enemy and NPC spawns)."""
        if pos not in self.location_data:
            return

        loc_data = self.location_data[pos]
        data = card_data.get("data", {})

        # Get the correct state data (use 2nd_state_ prefix if state 2)
        if state == 2:
            # Enemy spawn fields
            is_spawn = data.get("2nd_state_Is_Spawn_Location", "false")
            health_str = data.get("2nd_state_Health", "0")
            spawn_deck = data.get("2nd_state_Spawn_Enemy_Deck", "")
            # NPC spawn fields
            is_npc_spawn = data.get("2nd_state_Is_NPC_Spawn_Location", "false")
            npc_health_str = data.get("2nd_state_NPC_Health", "0")
            npc_spawn_deck = data.get("2nd_state_NPC_Spawn_Deck", "")
        else:
            # Enemy spawn fields
            is_spawn = data.get("Is_Spawn_Location", "false")
            health_str = data.get("Health", "0")
            spawn_deck = data.get("Spawn_Enemy_Deck", "")
            # NPC spawn fields
            is_npc_spawn = data.get("Is_NPC_Spawn_Location", "false")
            npc_health_str = data.get("NPC_Health", "0")
            npc_spawn_deck = data.get("NPC_Spawn_Deck", "")

        # Parse enemy spawn values
        is_spawn_location = str(is_spawn).lower() == "true"
        try:
            health = int(health_str) if health_str else 0
        except (ValueError, TypeError):
            health = 0

        loc_data["is_spawn_location"] = is_spawn_location
        loc_data["health"] = health
        loc_data["max_health"] = health
        loc_data["spawn_enemy_deck"] = spawn_deck if spawn_deck else None

        # Parse NPC spawn values
        is_npc_spawn_location = str(is_npc_spawn).lower() == "true"
        try:
            npc_health = int(npc_health_str) if npc_health_str else 0
        except (ValueError, TypeError):
            npc_health = 0

        loc_data["is_npc_spawn_location"] = is_npc_spawn_location
        loc_data["npc_health"] = npc_health
        loc_data["npc_max_health"] = npc_health
        loc_data["npc_spawn_deck"] = npc_spawn_deck if npc_spawn_deck else None

        # Parse defense data (up to 2 attack definitions)
        loc_data["defenses"] = []
        for prefix in ["Defense_", "Defense2_"]:
            state_prefix = "2nd_state_" if state == 2 else ""
            enabled = str(data.get(f"{state_prefix}{prefix}Enabled", "false")).lower() == "true"
            if not enabled:
                continue
            try:
                damage = int(data.get(f"{state_prefix}{prefix}Damage", 0) or 0)
            except (ValueError, TypeError):
                damage = 0
            try:
                range_distance = int(data.get(f"{state_prefix}{prefix}Range_Distance", 0) or 0)
            except (ValueError, TypeError):
                range_distance = 0
            try:
                passthrough = int(data.get(f"{state_prefix}{prefix}Passthrough_Chance", 0) or 0)
            except (ValueError, TypeError):
                passthrough = 0
            try:
                color_r = int(data.get(f"{state_prefix}{prefix}Color_R", 255) or 255)
                color_g = int(data.get(f"{state_prefix}{prefix}Color_G", 165) or 165)
                color_b = int(data.get(f"{state_prefix}{prefix}Color_B", 0) or 0)
            except (ValueError, TypeError):
                color_r, color_g, color_b = 255, 165, 0
            defense = {
                "requires_npc": str(data.get(f"{state_prefix}{prefix}Requires_NPC", "false")).lower() == "true",
                "damage": damage,
                "range_type": data.get(f"{state_prefix}{prefix}Range_Type", "area_effect"),
                "range_distance": range_distance,
                "include_position": str(data.get(f"{state_prefix}{prefix}Include_Position", "false")).lower() == "true",
                "exclude_adjacent": str(data.get(f"{state_prefix}{prefix}Exclude_Adjacent", "false")).lower() == "true",
                "passthrough_chance": passthrough,
                "color": (color_r, color_g, color_b)
            }
            if defense["damage"] > 0 and defense["range_distance"] > 0:
                loc_data["defenses"].append(defense)

    # ========== SPAWN LOCATION METHODS ==========

    def is_attackable_location(self, row, col):
        """Check if a location at this hex can be attacked (is a spawn location with health > 0)."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return False
        return loc_data.get("is_spawn_location", False) and loc_data.get("health", 0) > 0

    def get_active_spawn_locations(self):
        """Get all spawn locations that are still active (health > 0).
        Returns list of ((row, col), loc_data) tuples."""
        active = []
        for pos, loc_data in self.location_data.items():
            if loc_data.get("is_spawn_location", False) and loc_data.get("health", 0) > 0:
                active.append((pos, loc_data))
        return active

    def damage_location(self, row, col, damage):
        """Apply damage to a spawn location.
        Returns (damage_dealt, destroyed, message)."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return 0, False, "Not a location hex"

        if not loc_data.get("is_spawn_location", False):
            return 0, False, "This location cannot be attacked"

        current_health = loc_data.get("health", 0)
        if current_health <= 0:
            return 0, False, "Location already destroyed"

        # Apply damage
        damage_dealt = min(damage, current_health)
        loc_data["health"] = current_health - damage_dealt

        # Get location name
        card = loc_data.get("card")
        loc_name = card.get_current_data().get("Name", "Location") if card else "Location"

        if loc_data["health"] <= 0:
            # Location destroyed - flip to state 2 (ruins)
            self._destroy_spawn_location(row, col)
            return damage_dealt, True, f"{loc_name} destroyed!"

        return damage_dealt, False, f"Dealt {damage_dealt} damage to {loc_name} ({loc_data['health']} HP remaining)"

    def _destroy_spawn_location(self, row, col):
        """Handle destruction of a spawn location - flip card to state 2 (ruins)."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return

        loc_data["health"] = 0
        loc_data["is_spawn_location"] = False
        loc_data["state"] = 2

        # Flip the card to state 2 if it has 2 states
        card = loc_data.get("card")
        if card and card.is_two_state():
            card.current_state = 2
            # Re-initialize with new state data (ruins usually have no spawn properties)
            self._init_spawn_location_data((row, col), card.card_data, 2)

    # ========== NPC SPAWN LOCATION METHODS (Churches) ==========

    def is_attackable_npc_location(self, row, col):
        """Check if an NPC spawn location (church) can be attacked by enemies."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return False
        return loc_data.get("is_npc_spawn_location", False) and loc_data.get("npc_health", 0) > 0

    def get_active_npc_spawn_locations(self):
        """Get all NPC spawn locations (churches) that are still active (npc_health > 0).
        Returns list of ((row, col), loc_data) tuples."""
        active = []
        for pos, loc_data in self.location_data.items():
            if loc_data.get("is_npc_spawn_location", False) and loc_data.get("npc_health", 0) > 0:
                active.append((pos, loc_data))
        return active

    def damage_npc_location(self, row, col, damage):
        """Apply damage to an NPC spawn location (church) from an enemy attack.
        Returns (damage_dealt, destroyed, message)."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return 0, False, "Not a location hex"

        if not loc_data.get("is_npc_spawn_location", False):
            return 0, False, "This location cannot be attacked"

        current_health = loc_data.get("npc_health", 0)
        if current_health <= 0:
            return 0, False, "Location already destroyed"

        # Apply damage
        damage_dealt = min(damage, current_health)
        loc_data["npc_health"] = current_health - damage_dealt

        # Get location name
        card = loc_data.get("card")
        loc_name = card.get_current_data().get("Name", "Church") if card else "Church"

        if loc_data["npc_health"] <= 0:
            # Location destroyed - flip to state 2 (ruins)
            self._destroy_npc_spawn_location(row, col)
            return damage_dealt, True, f"{loc_name} destroyed!"

        return damage_dealt, False, f"{loc_name} takes {damage_dealt} damage ({loc_data['npc_health']} HP remaining)"

    def _destroy_npc_spawn_location(self, row, col):
        """Handle destruction of an NPC spawn location (church) - flip card to state 2 (ruins)."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return

        loc_data["npc_health"] = 0
        loc_data["is_npc_spawn_location"] = False
        loc_data["state"] = 2

        # Flip the card to state 2 if it has 2 states
        card = loc_data.get("card")
        if card and card.is_two_state():
            card.current_state = 2
            # Re-initialize with new state data (ruins usually have no spawn properties)
            self._init_spawn_location_data((row, col), card.card_data, 2)

    def repair_npc_location(self, row, col, heal_amount, can_rebuild=True):
        """Repair an NPC spawn location (church).
        If the church is destroyed (state 2) and can_rebuild=True, it will be rebuilt.
        Returns (success, healed_amount, rebuilt, message)."""
        loc_data = self.location_data.get((row, col))
        if not loc_data:
            return False, 0, False, "Not a location hex"

        card = loc_data.get("card")
        if not card:
            return False, 0, False, "No location card assigned"

        # Check if this is/was an NPC spawn location (church)
        card_data = card.card_data.get("data", {})

        # Check state 1 for NPC spawn location property
        is_church_state1 = str(card_data.get("Is_NPC_Spawn_Location", "false")).lower() == "true"

        if not is_church_state1:
            return False, 0, False, "This location cannot be repaired"

        current_state = loc_data.get("state", 1)
        current_health = loc_data.get("npc_health", 0)
        max_health = loc_data.get("npc_max_health", 0)

        # If destroyed (state 2), rebuild it first
        rebuilt = False
        if current_state == 2 and can_rebuild:
            # Flip card back to state 1
            card.current_state = 1
            loc_data["state"] = 1
            # Re-initialize spawn location data with state 1 values
            self._init_spawn_location_data((row, col), card.card_data, 1)
            # Update local references after re-init
            max_health = loc_data.get("npc_max_health", 0)
            current_health = 0  # Start at 0, will heal below
            rebuilt = True

        # Now heal the location
        if max_health <= 0:
            return False, 0, rebuilt, "Location has no health to repair"

        if current_health >= max_health and not rebuilt:
            return False, 0, False, "Location is already at full health"

        # Apply healing
        old_health = current_health
        new_health = min(max_health, current_health + heal_amount)
        loc_data["npc_health"] = new_health
        healed = new_health - old_health

        loc_name = card.get_current_data().get("Name", "Church")

        if rebuilt:
            return True, healed, True, f"{loc_name} rebuilt and repaired! ({new_health}/{max_health} HP)"
        else:
            return True, healed, False, f"{loc_name} repaired for {healed} HP ({new_health}/{max_health} HP)"

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

        # Initialize spawn location data if this is a spawn location
        self._init_spawn_location_data((row, col), card_data, 1)

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

        # Check if this shop sells both states (wild/tamed pairs)
        sell_both_states = str(card_data.get("Shop_Sell_Both_States", "false")).lower() == "true"

        # Draw cards for shop inventory
        shop_items = []
        available_cards = deck["cards"].copy()

        if sell_both_states:
            # Draw half as many unique cards, then create wild/tamed pairs
            draw_count = min(shop_size // 2, len(available_cards))
            for _ in range(draw_count):
                if not available_cards:
                    break
                card_id = random.choice(available_cards)
                available_cards.remove(card_id)

                item_data = load_card(card_id)
                if not item_data:
                    print(f"Skipping shop item: card '{card_id}' not found")
                    continue

                # Only create both-states entries for 2-state cards
                if item_data.get("states", 1) == 2:
                    # State 1 (Wild) - discounted at 60%
                    wild_card = InventoryCard(item_data)
                    wild_price = self._calculate_item_price(wild_card, card_data)
                    wild_price["amount"] = max(1, int(wild_price["amount"] * 0.6))
                    wild_name = wild_card.get_current_data().get("Name", "Unknown")
                    shop_items.append({
                        "card": wild_card, "price": wild_price,
                        "display_name": f"{wild_name} (Wild)", "sell_state": 1
                    })

                    # State 2 (Tamed) - premium at 200%
                    tamed_card = InventoryCard(item_data)
                    tamed_card.current_state = 2
                    tamed_price = self._calculate_item_price(tamed_card, card_data)
                    tamed_price["amount"] = max(1, int(tamed_price["amount"] * 2.0))
                    tamed_name = item_data["data"].get("2nd_State_Name", "Unknown")
                    shop_items.append({
                        "card": tamed_card, "price": tamed_price,
                        "display_name": f"{tamed_name} (Tamed)", "sell_state": 2
                    })
                else:
                    item_card = InventoryCard(item_data)
                    price = self._calculate_item_price(item_card, card_data)
                    shop_items.append({"card": item_card, "price": price})
        else:
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

    def trigger_location_outcome(self, row, col, card_manager=None):
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
            # No deck specified - draw a random card of that type from all available
            if card_manager:
                cards = card_manager.get_cards_for_game(card_type=card_type)
                if cards:
                    card_data = random.choice(cards)
                    outcome_card = InventoryCard(card_data)
                    return outcome_card, f"Found {card_data['data'].get('Name', 'Unknown Item')}"
            return None, "Nothing found"

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

        # Re-parse state 2 spawn/defense data
        self._init_spawn_location_data((row, col), card.card_data, 2)

        # Auto-garrison the upgrading NPC if this is a defensive location
        defenses = loc_data.get("defenses", [])
        has_npc_defense = any(d.get("requires_npc") for d in defenses)
        if has_npc_defense and npc_card:
            npc_data_obj = npc_card.get_current_data() if hasattr(npc_card, 'get_current_data') else npc_card
            garrison_entry = {
                "id": npc_card.card_data.get("id") if hasattr(npc_card, 'card_data') else npc_data_obj.get("id", ""),
                "name": npc_data_obj.get("Name", npc_data_obj.get("name", "Unknown")),
                "hp": int(npc_data_obj.get("Health", npc_data_obj.get("hp", 10))),
                "max_hp": int(npc_data_obj.get("Health", npc_data_obj.get("max_hp", 10))),
                "melee_damage": int(npc_data_obj.get("Melee Damage", npc_data_obj.get("melee_damage", 0))),
                "projectile_damage": int(npc_data_obj.get("Projectile Damage", npc_data_obj.get("projectile_damage", 0))),
                "allegiance": npc_data_obj.get("Allegiance (Hostile, Neutral, Allied)", npc_data_obj.get("allegiance", "Allied"))
            }
            loc_data["garrison_npcs"].append(garrison_entry)

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

    def garrison_npc_to_location(self, npc_data, location_pos):
        """Add an NPC data dict to a location's garrison (max 3).
        Args:
            npc_data: dict with id, name, hp, max_hp, melee_damage, etc.
            location_pos: (row, col) tuple
        Returns: (success, message)
        """
        loc_data = self.location_data.get(location_pos)
        if not loc_data:
            return False, "No location at that position"
        garrison = loc_data.get("garrison_npcs", [])
        if len(garrison) >= 3:
            return False, "Garrison is full (max 3)"
        garrison.append(npc_data)
        loc_data["garrison_npcs"] = garrison
        return True, f"{npc_data.get('name', 'NPC')} garrisoned at location"

    def garrison_map_npc_to_location(self, unit, location_pos):
        """Remove an allied Unit from the map and add to a location's garrison.
        Args:
            unit: The Unit object to garrison
            location_pos: (row, col) tuple
        Returns: (success, message)
        """
        loc_data = self.location_data.get(location_pos)
        if not loc_data:
            return False, "No location at that position"
        garrison = loc_data.get("garrison_npcs", [])
        if len(garrison) >= 3:
            return False, "Garrison is full (max 3)"

        # Stop any animations
        unit.animating = False
        unit.target_pos = None

        # Remove unit from map
        if unit.position:
            self.grid[unit.position[0]][unit.position[1]]["unit"] = None
        if unit in self.units:
            self.units.remove(unit)

        # Create NPC data dict from unit
        npc_data = {
            "id": unit.card_id,
            "name": unit.name,
            "hp": unit.hp,
            "max_hp": unit.max_hp,
            "melee_damage": unit.melee_damage,
            "projectile_damage": unit.projectile_damage,
            "allegiance": unit.allegiance
        }
        garrison.append(npc_data)
        loc_data["garrison_npcs"] = garrison
        return True, f"{unit.name} garrisoned at location"

    def get_active_defensive_locations(self):
        """Return list of (pos, loc_data) for locations in state 2 with garrison NPCs
        and at least one requires_npc defense."""
        result = []
        for pos, loc_data in self.location_data.items():
            if loc_data.get("state", 1) != 2:
                continue
            garrison = loc_data.get("garrison_npcs", [])
            if not garrison:
                continue
            defenses = loc_data.get("defenses", [])
            if any(d.get("requires_npc") for d in defenses):
                result.append((pos, loc_data))
        return result

    def get_all_defensive_locations(self):
        """Return list of (pos, loc_data) for all locations with any defense definitions."""
        result = []
        for pos, loc_data in self.location_data.items():
            defenses = loc_data.get("defenses", [])
            if defenses:
                result.append((pos, loc_data))
        return result

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

        sell_both_states = str(card_data.get("Shop_Sell_Both_States", "false")).lower() == "true"

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

        if sell_both_states and item_data.get("states", 1) == 2:
            # Add wild/tamed pair if there's room
            wild_card = InventoryCard(item_data)
            wild_price = self._calculate_item_price(wild_card, card_data)
            wild_price["amount"] = max(1, int(wild_price["amount"] * 0.6))
            wild_name = wild_card.get_current_data().get("Name", "Unknown")
            shop.append({
                "card": wild_card, "price": wild_price,
                "display_name": f"{wild_name} (Wild)", "sell_state": 1
            })

            if len(shop) < shop_size:
                tamed_card = InventoryCard(item_data)
                tamed_card.current_state = 2
                tamed_price = self._calculate_item_price(tamed_card, card_data)
                tamed_price["amount"] = max(1, int(tamed_price["amount"] * 2.0))
                tamed_name = item_data["data"].get("2nd_State_Name", "Unknown")
                shop.append({
                    "card": tamed_card, "price": tamed_price,
                    "display_name": f"{tamed_name} (Tamed)", "sell_state": 2
                })
        else:
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
            "available_npcs": [],
            # Enemy spawn location fields
            "health": 0,
            "max_health": 0,
            "is_spawn_location": False,
            "spawn_enemy_deck": None,
            # NPC spawn location fields (churches)
            "npc_health": 0,
            "npc_max_health": 0,
            "is_npc_spawn_location": False,
            "npc_spawn_deck": None,
            # Defensive location fields
            "defenses": [],
            "garrison_npcs": []
        }

        # Initialize shop if defined in card
        self._initialize_shop(row, col)

        # Initialize spawn location data if applicable
        self._init_spawn_location_data((row, col), location_card.card_data, location_card.current_state)

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

    def get_random_spawn_position(self):
        """Get a random empty, accessible position anywhere on the map."""
        candidates = []
        for row in range(self.rows):
            for col in range(self.cols):
                if self._is_valid_spawn(row, col):
                    candidates.append((row, col))
        if candidates:
            return random.choice(candidates)
        return None

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

    def has_clear_line_of_sight(self, start_pos, target_pos, ignore_units=False):
        start_row, start_col = start_pos
        end_row, end_col = target_pos
        line = self.get_line_between(start_row, start_col, end_row, end_col)
        if not line:
            return False
        for row, col in line[1:-1]:
            if not self.grid[row][col]["accessible"]:
                return False
            if not ignore_units and self.grid[row][col]["unit"] is not None:
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

    def get_attack_range(self, start, range_limit, is_projectile=False, piercing=False):
        if is_projectile:
            attack_hexes = set()
            row, col = start
            for dir in DIRECTIONS:
                line = self.get_line(row, col, dir, range_limit)
                for hex_pos in line:
                    distance = self.hex_distance(start, hex_pos)
                    if 1 < distance <= range_limit and self.has_clear_line_of_sight(start, hex_pos, ignore_units=piercing):
                        attack_hexes.add(hex_pos)
            return attack_hexes
        else:
            # For melee, get all adjacent hexes (including those with units)
            return set(self.get_adjacent_hexes(*start))

    def calculate_range(self, pos, distance, pattern, include_pos=False, exclude_adj=False, piercing=False):
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
            piercing: If True, line of sight ignores units (for piercing shots)

        Returns:
            set: Set of (row, col) positions in range
        """
        if distance < 0:
            return set()

        # Support comma-separated multi-patterns (e.g. "line_of_sight,mist_shadow")
        if "," in pattern:
            combined = set()
            for sub_pattern in pattern.split(","):
                sub_pattern = sub_pattern.strip()
                if sub_pattern:
                    combined |= self.calculate_range(pos, distance, sub_pattern,
                                                     include_pos=False, exclude_adj=False, piercing=piercing)
            # Apply modifiers once on the combined set
            if include_pos:
                combined.add(pos)
            elif pos in combined:
                combined.remove(pos)
            if exclude_adj:
                adjacent = set(self.get_adjacent_hexes(*pos))
                combined -= adjacent
            return combined

        range_set = set()

        if pattern == "line_of_sight":
            range_set = self.get_attack_range(pos, distance, is_projectile=True, piercing=piercing)

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
        Supports any distance (no hardcoded limit).
        """
        range_set = set()
        row, col = pos

        # Diagonal direction definitions: (col_delta, row_delta_to_even_col, row_delta_to_odd_col)
        # Each step moves 1 column; row delta depends on parity of the NEW column.
        diag_dirs = {
            30:  (+1, -1, -2),   # ↗ up-right
            150: (+1, +2, +1),   # ↘ down-right
            210: (-1, +2, +1),   # ↙ down-left
            330: (-1, -1, -2),   # ↖ up-left
        }

        for angle in [30, 90, 150, 210, 270, 330]:
            line = []

            if angle in (90, 270):
                # Horizontal directions: step by 2 columns
                for step in range(1, distance + 1):
                    new_c = col + (2 * step if angle == 90 else -2 * step)
                    new_pos = (row, new_c)
                    if (0 <= new_c < self.cols and
                            self.hex_distance(pos, new_pos) <= distance):
                        if self.grid[row][new_c]["accessible"]:
                            line.append(new_pos)
                        else:
                            break
                    else:
                        break
            else:
                # Diagonal directions: compute offsets algorithmically
                col_d, dr_to_even, dr_to_odd = diag_dirs[angle]
                cur_r, cur_c = row, col
                for step in range(distance):
                    new_c = cur_c + col_d
                    # Row delta depends on parity of the NEW column
                    dr = dr_to_odd if new_c % 2 != 0 else dr_to_even
                    new_r = cur_r + dr
                    new_pos = (new_r, new_c)
                    if (0 <= new_r < self.rows and 0 <= new_c < self.cols and
                            self.hex_distance(pos, new_pos) <= distance):
                        if self.grid[new_r][new_c]["accessible"]:
                            line.append(new_pos)
                        else:
                            break
                    else:
                        break
                    cur_r, cur_c = new_r, new_c

            range_set.update(line)

        return range_set

    def is_in_range(self, attacker_pos, target_pos, distance, pattern, include_pos=False, exclude_adj=False, piercing=False):
        """
        Check if a target position is within attack range using specified pattern.

        Args:
            attacker_pos: Attacker's position (row, col)
            target_pos: Target's position (row, col)
            distance: Maximum range distance
            pattern: Pattern type string
            include_pos: Include caster's hex in range
            exclude_adj: Exclude adjacent hexes from range
            piercing: If True, line of sight ignores units

        Returns:
            bool: True if target is in range
        """
        range_set = self.calculate_range(attacker_pos, distance, pattern, include_pos, exclude_adj, piercing=piercing)
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

    def draw(self, surface, movement_range=None, attack_ranges=None, colors=None, targetable_units=None):
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
                # Subtle terrain texture patterns
                tc = terrain_color
                pat_alpha = 30
                pat_color = (max(0, tc[0] - 40), max(0, tc[1] - 40), max(0, tc[2] - 40), pat_alpha)
                pat_hi = (min(255, tc[0] + 30), min(255, tc[1] + 30), min(255, tc[2] + 30), pat_alpha)
                hs = self.hex_size
                ix, iy = int(x), int(y)
                if terrain_type == "water" or terrain_type == "deep_water":
                    # Wavy horizontal lines
                    wave_surf = pygame.Surface((hs * 2, hs * 2), pygame.SRCALPHA)
                    for wi in range(-2, 3):
                        wy = hs + wi * int(hs * 0.3)
                        wave_pts = [(int(hs * 0.3 + j * hs * 0.15), wy + int(math.sin(j * 0.8) * hs * 0.08)) for j in range(10)]
                        if len(wave_pts) > 1:
                            pygame.draw.lines(wave_surf, pat_hi, False, wave_pts, 1)
                    hex_surface.blit(wave_surf, (ix - hs, iy - hs))
                elif terrain_type == "sand":
                    # Scattered dots
                    dot_surf = pygame.Surface((hs * 2, hs * 2), pygame.SRCALPHA)
                    rng = random.Random(row * 100 + col)
                    for _ in range(8):
                        dx = rng.randint(int(hs * 0.4), int(hs * 1.6))
                        dy = rng.randint(int(hs * 0.4), int(hs * 1.6))
                        pygame.draw.circle(dot_surf, pat_color, (dx, dy), max(1, int(hs * 0.04)))
                    hex_surface.blit(dot_surf, (ix - hs, iy - hs))
                elif terrain_type == "forest":
                    # Small tree-like marks
                    tree_surf = pygame.Surface((hs * 2, hs * 2), pygame.SRCALPHA)
                    rng = random.Random(row * 100 + col)
                    for _ in range(5):
                        tx = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        ty = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        s = max(2, int(hs * 0.07))
                        pygame.draw.circle(tree_surf, pat_color, (tx, ty), s)
                        pygame.draw.line(tree_surf, pat_color, (tx, ty + s), (tx, ty + s * 2), 1)
                    hex_surface.blit(tree_surf, (ix - hs, iy - hs))
                elif terrain_type == "mountain" or terrain_type == "cliff":
                    # Small triangle peaks
                    mtn_surf = pygame.Surface((hs * 2, hs * 2), pygame.SRCALPHA)
                    rng = random.Random(row * 100 + col)
                    for _ in range(3):
                        mx = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        my = rng.randint(int(hs * 0.6), int(hs * 1.4))
                        s = max(3, int(hs * 0.1))
                        pygame.draw.polygon(mtn_surf, pat_hi, [(mx, my - s), (mx - s, my + s // 2), (mx + s, my + s // 2)])
                    hex_surface.blit(mtn_surf, (ix - hs, iy - hs))
                elif terrain_type == "stone":
                    # Crack lines
                    crack_surf = pygame.Surface((hs * 2, hs * 2), pygame.SRCALPHA)
                    rng = random.Random(row * 100 + col)
                    for _ in range(3):
                        cx1 = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        cy1 = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        cx2 = cx1 + rng.randint(-int(hs * 0.3), int(hs * 0.3))
                        cy2 = cy1 + rng.randint(-int(hs * 0.3), int(hs * 0.3))
                        pygame.draw.line(crack_surf, pat_color, (cx1, cy1), (cx2, cy2), 1)
                    hex_surface.blit(crack_surf, (ix - hs, iy - hs))
                elif terrain_type == "swamp":
                    # Scattered puddle circles
                    swamp_surf = pygame.Surface((hs * 2, hs * 2), pygame.SRCALPHA)
                    rng = random.Random(row * 100 + col)
                    for _ in range(4):
                        sx = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        sy = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        sr = max(2, int(hs * 0.06))
                        pygame.draw.circle(swamp_surf, pat_color, (sx, sy), sr, 1)
                    hex_surface.blit(swamp_surf, (ix - hs, iy - hs))
                elif terrain_type == "lava":
                    # Bright glow spots
                    lava_surf = pygame.Surface((hs * 2, hs * 2), pygame.SRCALPHA)
                    rng = random.Random(row * 100 + col)
                    for _ in range(4):
                        lx = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        ly = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        lr = max(2, int(hs * 0.06))
                        pygame.draw.circle(lava_surf, (255, 200, 50, 35), (lx, ly), lr)
                    hex_surface.blit(lava_surf, (ix - hs, iy - hs))
                elif terrain_type == "ice":
                    # Crystalline lines
                    ice_surf = pygame.Surface((hs * 2, hs * 2), pygame.SRCALPHA)
                    rng = random.Random(row * 100 + col)
                    for _ in range(4):
                        ix1 = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        iy1 = rng.randint(int(hs * 0.5), int(hs * 1.5))
                        ang = rng.uniform(0, math.pi)
                        length = int(hs * 0.15)
                        ix2 = ix1 + int(math.cos(ang) * length)
                        iy2 = iy1 + int(math.sin(ang) * length)
                        pygame.draw.line(ice_surf, (220, 240, 255, 40), (ix1, iy1), (ix2, iy2), 1)
                    hex_surface.blit(ice_surf, (ix - hs, iy - hs))
                # Subtle edge shading for terrain depth
                edge_color = (max(0, terrain_color[0] - 25), max(0, terrain_color[1] - 25), max(0, terrain_color[2] - 25))
                pygame.draw.polygon(hex_surface, edge_color, points, 2)

                # Draw overlay for inaccessible hexes (darker tint)
                if not self.grid[row][col]["accessible"]:
                    # Darken the terrain color for manually marked inaccessible
                    if is_terrain_accessible(terrain_type):
                        dark_overlay = pygame.Surface((self.hex_size * 2, self.hex_size * 2), pygame.SRCALPHA)
                        dark_points = [(self.hex_size + self.hex_size * math.cos(math.radians(60 * i)),
                                       self.hex_size + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]
                        pygame.draw.polygon(dark_overlay, (0, 0, 0, 80), dark_points, 0)
                        hex_surface.blit(dark_overlay, (x - self.hex_size, y - self.hex_size))

                # Hover highlight
                if self.hovered_hex == (row, col) and self.selected_hex != (row, col):
                    pygame.draw.polygon(hex_surface, (255, 255, 255, 25), points, 0)

                # Draw special hex indicators with pulsing glow
                for hex_data in self.card_drawing_hexes:
                    if hex_data["row"] == row and hex_data["column"] == col:
                        pulse = (math.sin(pygame.time.get_ticks() / 600.0) + 1) / 2  # 0.0 to 1.0
                        pulse_alpha = int(100 + pulse * 155)  # 100-255
                        if "linked_level" in hex_data and hex_data["linked_level"]:
                            glow_color = (180, 80, 255, int(pulse * 25))
                            border_color = (180, 80, 255, pulse_alpha)
                        elif "deck_file" in hex_data and hex_data["deck_file"] or "card_id" in hex_data and hex_data["card_id"]:
                            glow_color = (80, 255, 80, int(pulse * 20))
                            border_color = (80, 255, 80, pulse_alpha)
                        else:
                            break
                        # Subtle inner glow fill
                        pygame.draw.polygon(hex_surface, glow_color, points, 0)
                        # Pulsing border
                        pygame.draw.polygon(hex_surface, border_color, points, 3)
                        break
                # Draw location hex indicators
                if (row, col) in self.location_data:
                    loc_data = self.location_data[(row, col)]
                    is_spawn_location = loc_data.get("is_spawn_location", False)
                    has_health = loc_data.get("health", 0) > 0
                    is_npc_spawn = loc_data.get("is_npc_spawn_location", False)
                    has_npc_health = loc_data.get("npc_health", 0) > 0

                    # Determine border color: red for enemy spawns, blue for NPC spawns, orange for regular
                    if is_spawn_location and has_health:
                        border_color = colors['RED']
                    elif is_npc_spawn and has_npc_health:
                        border_color = colors['BLUE']
                    else:
                        border_color = colors['ORANGE']
                    pygame.draw.polygon(hex_surface, border_color, points, 3)
                if self.selected_hex == (row, col):
                    pygame.draw.polygon(hex_surface, (255, 215, 0, 60), points, 0)
                    pygame.draw.polygon(hex_surface, (255, 215, 0, 220), points, 3)
                # Thin border only where edge shading doesn't cover (selected hex)
                if self.selected_hex == (row, col):
                    pygame.draw.polygon(hex_surface, (80, 80, 100), points, 1)

        # Second pass: Draw range overlays on top of terrain and hex borders
        for row in range(self.rows):
            for col in range(self.cols):
                # Movement range: shade out-of-range hexes
                if movement_range and (row, col) not in movement_range:
                    x, y = self.get_hex_center(row, col)
                    dark_overlay = pygame.Surface((self.hex_size * 2, self.hex_size * 2), pygame.SRCALPHA)
                    dark_points = [(self.hex_size + self.hex_size * math.cos(math.radians(60 * i)),
                                   self.hex_size + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]
                    pygame.draw.polygon(dark_overlay, (0, 0, 0, 100), dark_points, 0)
                    hex_surface.blit(dark_overlay, (x - self.hex_size, y - self.hex_size))

        # Attack range hex fill with gentle breathing alpha
        ar_pulse = (math.sin(pygame.time.get_ticks() / 400.0) + 1) / 2  # 0.0–1.0
        for row in range(self.rows):
            for col in range(self.cols):
                if attack_ranges:
                    for ar in attack_ranges:
                        if (row, col) in ar["range"]:
                            x, y = self.get_hex_center(row, col)
                            color = ar["color"]
                            range_overlay = pygame.Surface((self.hex_size * 2, self.hex_size * 2), pygame.SRCALPHA)
                            range_points = [(self.hex_size + self.hex_size * math.cos(math.radians(60 * i)),
                                            self.hex_size + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]
                            # Breathing hex tint fill
                            fill_alpha = int(30 + ar_pulse * 25)
                            pygame.draw.polygon(range_overlay, (color[0], color[1], color[2], fill_alpha), range_points, 0)
                            # Subtle inner hex border
                            pygame.draw.polygon(range_overlay, (color[0], color[1], color[2], 100), range_points, 2)
                            hex_surface.blit(range_overlay, (x - self.hex_size, y - self.hex_size))

        # Third pass: Draw location icons and names on top of range rings
        for (row, col), loc_data in self.location_data.items():
            x, y = self.get_hex_center(row, col)
            is_spawn_location = loc_data.get("is_spawn_location", False)
            has_health = loc_data.get("health", 0) > 0
            is_npc_spawn = loc_data.get("is_npc_spawn_location", False)
            has_npc_health = loc_data.get("npc_health", 0) > 0

            if loc_data.get("card"):
                # Draw icons for assigned locations
                is_upgraded = loc_data.get("state", 1) == 2

                if is_spawn_location and has_health:
                    # Draw tower/fort icon for active enemy spawn locations (red)
                    icon_color = colors['RED']
                    outline_color = (10, 10, 20)
                    tower_size = self.hex_size * 0.3
                    tower_x, tower_y = x, y
                    base_rect = pygame.Rect(
                        tower_x - tower_size * 0.4,
                        tower_y - tower_size * 0.3,
                        tower_size * 0.8,
                        tower_size * 0.8
                    )
                    pygame.draw.rect(hex_surface, outline_color, base_rect.inflate(2, 2))
                    pygame.draw.rect(hex_surface, icon_color, base_rect)
                    cren_width = tower_size * 0.2
                    cren_height = tower_size * 0.25
                    for i in range(3):
                        cren_rect = pygame.Rect(
                            tower_x - tower_size * 0.4 + i * cren_width * 1.5,
                            tower_y - tower_size * 0.3 - cren_height,
                            cren_width,
                            cren_height
                        )
                        pygame.draw.rect(hex_surface, outline_color, cren_rect.inflate(2, 2))
                        pygame.draw.rect(hex_surface, icon_color, cren_rect)
                    # Health bar
                    max_health = loc_data.get("max_health", 1)
                    current_health = loc_data.get("health", 0)
                    if max_health > 0:
                        bar_width = self.hex_size * 0.6
                        bar_height = 4
                        bar_x = tower_x - bar_width / 2
                        bar_y = tower_y + tower_size * 0.6
                        pygame.draw.rect(hex_surface, colors['GRAY'],
                                       (bar_x, bar_y, bar_width, bar_height))
                        health_ratio = current_health / max_health
                        pygame.draw.rect(hex_surface, colors['RED'],
                                       (bar_x, bar_y, bar_width * health_ratio, bar_height))

                elif is_npc_spawn and has_npc_health:
                    # Draw church icon for active NPC spawn locations (blue)
                    icon_color = colors['BLUE']
                    outline_color = (10, 10, 20)
                    church_size = self.hex_size * 0.3
                    church_x, church_y = x, y
                    steeple_points = [
                        (church_x, church_y - church_size * 1.0),
                        (church_x - church_size * 0.2, church_y - church_size * 0.4),
                        (church_x + church_size * 0.2, church_y - church_size * 0.4)
                    ]
                    pygame.draw.polygon(hex_surface, outline_color, steeple_points)
                    pygame.draw.polygon(hex_surface, icon_color, steeple_points, 0)
                    body_rect = pygame.Rect(
                        church_x - church_size * 0.4,
                        church_y - church_size * 0.4,
                        church_size * 0.8,
                        church_size * 0.8
                    )
                    pygame.draw.rect(hex_surface, outline_color, body_rect.inflate(2, 2))
                    pygame.draw.rect(hex_surface, icon_color, body_rect)
                    cross_color = colors['WHITE']
                    cross_y = church_y - church_size * 0.85
                    pygame.draw.line(hex_surface, cross_color,
                                   (church_x, cross_y - church_size * 0.15),
                                   (church_x, cross_y + church_size * 0.1), 2)
                    pygame.draw.line(hex_surface, cross_color,
                                   (church_x - church_size * 0.1, cross_y),
                                   (church_x + church_size * 0.1, cross_y), 2)
                    # Health bar
                    max_npc_health = loc_data.get("npc_max_health", 1)
                    current_npc_health = loc_data.get("npc_health", 0)
                    if max_npc_health > 0:
                        bar_width = self.hex_size * 0.6
                        bar_height = 4
                        bar_x = church_x - bar_width / 2
                        bar_y = church_y + church_size * 0.6
                        pygame.draw.rect(hex_surface, colors['GRAY'],
                                       (bar_x, bar_y, bar_width, bar_height))
                        health_ratio = current_npc_health / max_npc_health
                        pygame.draw.rect(hex_surface, colors['BLUE'],
                                       (bar_x, bar_y, bar_width * health_ratio, bar_height))
                else:
                    # Draw house icon for regular assigned locations
                    icon_color = colors['GREEN'] if is_upgraded else colors['ORANGE']
                    outline_color = (10, 10, 20)
                    house_size = self.hex_size * 0.3
                    house_x, house_y = x, y
                    roof_points = [
                        (house_x, house_y - house_size * 0.8),
                        (house_x - house_size * 0.6, house_y - house_size * 0.2),
                        (house_x + house_size * 0.6, house_y - house_size * 0.2)
                    ]
                    base_rect = pygame.Rect(
                        house_x - house_size * 0.4,
                        house_y - house_size * 0.2,
                        house_size * 0.8,
                        house_size * 0.6
                    )
                    pygame.draw.polygon(hex_surface, outline_color, roof_points)
                    pygame.draw.polygon(hex_surface, icon_color, roof_points, 0)
                    pygame.draw.rect(hex_surface, outline_color, base_rect.inflate(2, 2))
                    pygame.draw.rect(hex_surface, icon_color, base_rect)

                # Draw location name with shadow
                loc_card = loc_data["card"]
                loc_name = loc_card.get_current_data().get("Name", "")
                if loc_name:
                    house_size = self.hex_size * 0.3
                    shadow_color = (10, 10, 20)
                    name_surface = self.font.render(loc_name, True, colors['WHITE'])
                    shadow_surface = self.font.render(loc_name, True, shadow_color)
                    name_rect = name_surface.get_rect(centerx=x, top=y + house_size * 0.5)
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        hex_surface.blit(shadow_surface, name_rect.move(dx, dy))
                    hex_surface.blit(name_surface, name_rect)

                # Draw garrison indicator (small green circle with count)
                garrison = loc_data.get("garrison_npcs", [])
                if garrison:
                    g_count = len(garrison)
                    g_radius = max(6, int(self.hex_size * 0.15))
                    g_x = int(x + self.hex_size * 0.45)
                    g_y = int(y - self.hex_size * 0.45)
                    pygame.draw.circle(hex_surface, (0, 180, 0), (g_x, g_y), g_radius)
                    pygame.draw.circle(hex_surface, colors['WHITE'], (g_x, g_y), g_radius, 1)
                    g_font = pygame.font.Font(None, max(10, g_radius * 2))
                    g_text = g_font.render(str(g_count), True, colors['WHITE'])
                    g_rect = g_text.get_rect(center=(g_x, g_y))
                    hex_surface.blit(g_text, g_rect)
            else:
                # Draw unknown building icon for unassigned locations
                unknown_color = (210, 180, 100)  # Muted gold/tan
                outline_color = (10, 10, 20)
                house_size = self.hex_size * 0.35  # Slightly larger than regular
                house_x, house_y = x, y
                # House silhouette (triangle roof + rectangle base)
                roof_points = [
                    (house_x, house_y - house_size * 0.9),
                    (house_x - house_size * 0.7, house_y - house_size * 0.2),
                    (house_x + house_size * 0.7, house_y - house_size * 0.2)
                ]
                base_rect = pygame.Rect(
                    house_x - house_size * 0.5,
                    house_y - house_size * 0.2,
                    house_size * 1.0,
                    house_size * 0.7
                )
                pygame.draw.polygon(hex_surface, outline_color, roof_points)
                pygame.draw.polygon(hex_surface, unknown_color, roof_points, 0)
                pygame.draw.rect(hex_surface, outline_color, base_rect.inflate(2, 2))
                pygame.draw.rect(hex_surface, unknown_color, base_rect)
                # Draw "?" in the center of the building
                q_font = pygame.font.Font(None, max(14, int(house_size * 1.8)))
                q_surface = q_font.render("?", True, (60, 40, 20))
                q_rect = q_surface.get_rect(center=(int(house_x), int(house_y + house_size * 0.05)))
                hex_surface.blit(q_surface, q_rect)

                # Draw "Unknown Location" label
                name_surface = self.font.render("Unknown Location", True, unknown_color)
                name_rect = name_surface.get_rect(centerx=x, top=y + house_size * 0.6)
                hex_surface.blit(name_surface, name_rect)

        # Update pulse time for targeting visuals
        self.pulse_time = pygame.time.get_ticks()

        # Fourth pass: Draw all units on top of hexes (for proper z-ordering)
        # This ensures animating units are visible and don't go under hexes
        # Collect all players (multiplayer mode or single player)
        all_players = self.players if self.players else ([self.player] if self.player else [])
        all_units = list(self.units) + all_players
        # Pre-calculate glow animation values
        ticks = pygame.time.get_ticks()
        glow_pulse = (math.sin(ticks / 300.0) + 1) / 2  # 0.0 to 1.0 pulsing
        for unit in all_units:
            if unit and unit.position:
                # Use render_pos for animating units, otherwise use hex center
                if unit.animating and unit.render_pos:
                    pos = unit.render_pos
                else:
                    pos = self.get_hex_center(*unit.position)

                # Draw active turn glow ring
                is_active = (self.active_turn_unit is not None and unit is self.active_turn_unit)
                if is_active:
                    # Determine glow color based on unit type
                    if isinstance(unit, Player):
                        glow_color = (255, 215, 0)  # Gold for players
                    elif hasattr(unit, 'allegiance'):
                        if unit.allegiance == "Hostile":
                            glow_color = (255, 60, 60)  # Red for enemies
                        elif unit.allegiance == "Allied":
                            glow_color = (60, 120, 255)  # Blue for allies
                        else:
                            glow_color = (0, 220, 200)  # Teal for neutral
                    else:
                        glow_color = (255, 215, 0)
                    glow_radius = max(14, int(self.hex_size / 2.2))
                    # Draw 3 concentric glow rings with pulsing alpha
                    for i in range(3):
                        ring_radius = glow_radius + (3 - i) * 3 + int(glow_pulse * 3)
                        alpha = int((0.25 + glow_pulse * 0.35) * 255 * (i + 1) / 3)
                        glow_surf = pygame.Surface((ring_radius * 2 + 4, ring_radius * 2 + 4), pygame.SRCALPHA)
                        pygame.draw.circle(glow_surf, (*glow_color, alpha),
                                           (ring_radius + 2, ring_radius + 2), ring_radius, 2)
                        hex_surface.blit(glow_surf, (int(pos[0]) - ring_radius - 2, int(pos[1]) - ring_radius - 2))

                # Check if this is a dead player (for grayed-out rendering)
                is_dead_player = isinstance(unit, Player) and unit.hp <= 0

                if isinstance(unit, Player) and unit.image:
                    scale_factor = (self.hex_size * 1.5 * unit.image_scale_factor) / unit.image.get_height()
                    scaled_image = pygame.transform.scale(unit.image,
                                                         (int(unit.image.get_width() * scale_factor),
                                                          int(unit.image.get_height() * scale_factor)))
                    if is_dead_player:
                        # Gray out the image for dead players
                        scaled_image = scaled_image.copy()
                        scaled_image.set_alpha(80)
                    image_rect = scaled_image.get_rect(center=(int(pos[0]), int(pos[1])))
                    hex_surface.blit(scaled_image, image_rect)
                    health_bar_y = image_rect.top - 5
                else:
                    # Use player's custom color if available (multiplayer), otherwise default colors
                    if isinstance(unit, Player):
                        if is_dead_player:
                            color = (100, 100, 100)  # Gray for dead players
                        else:
                            color = unit.player_color if hasattr(unit, 'player_color') else colors['GREEN']
                    elif unit.allegiance == "Hostile":
                        color = colors['RED']
                    elif unit.allegiance == "Allied":
                        color = colors['BLUE']
                    else:
                        color = (0, 190, 170)  # Teal for neutral NPCs
                    base_radius = max(10, int(self.hex_size / 3))
                    # Player tokens are slightly larger
                    radius = int(base_radius * 1.15) if isinstance(unit, Player) else base_radius
                    cx, cy = int(pos[0]), int(pos[1])
                    flash_elapsed = pygame.time.get_ticks() - unit.flash_start if unit.attack_flash else 0
                    draw_color = colors['WHITE'] if (unit.attack_flash and flash_elapsed >= 0) else color
                    # Dark outline
                    pygame.draw.circle(hex_surface, (10, 10, 20), (cx, cy), radius + 2)
                    # Player gets a thin gold ring around the token
                    if isinstance(unit, Player) and not is_dead_player:
                        pygame.draw.circle(hex_surface, (200, 170, 50), (cx, cy), radius + 1)
                    # Main token
                    pygame.draw.circle(hex_surface, draw_color, (cx, cy), radius)
                    # Inner highlight (lighter shade, upper-left offset for 3D effect)
                    if not unit.attack_flash:
                        hi_r = min(255, draw_color[0] + 60)
                        hi_g = min(255, draw_color[1] + 60)
                        hi_b = min(255, draw_color[2] + 60)
                        highlight_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
                        pygame.draw.circle(highlight_surf, (hi_r, hi_g, hi_b, 80),
                                           (radius - 2, radius - 2), radius // 2)
                        hex_surface.blit(highlight_surf, (cx - radius, cy - radius))
                    health_bar_y = pos[1] - radius - 5  # Position health bar just above the circle

                    # Draw P1/P2 badge for multiplayer mode
                    if isinstance(unit, Player) and hasattr(unit, 'player_number') and len(all_players) > 1:
                        badge_font = pygame.font.Font(None, 16)
                        badge_text = f"P{unit.player_number}"
                        badge_surface = badge_font.render(badge_text, True, colors['WHITE'])
                        badge_w = badge_surface.get_width() + 6
                        badge_h = badge_surface.get_height() + 4
                        badge_x = int(pos[0]) - radius - badge_w + 2
                        badge_y = int(pos[1]) - radius - badge_h + 2
                        # Draw badge background
                        badge_bg = pygame.Surface((badge_w, badge_h), pygame.SRCALPHA)
                        badge_color = unit.player_color if hasattr(unit, 'player_color') else (0, 200, 0)
                        pygame.draw.rect(badge_bg, (*badge_color, 200), (0, 0, badge_w, badge_h), border_radius=3)
                        hex_surface.blit(badge_bg, (badge_x, badge_y))
                        hex_surface.blit(badge_surface, (badge_x + 3, badge_y + 2))

                    # Draw unit name above health bar (with shadow for readability)
                    if isinstance(unit, Player):
                        name = unit.name if hasattr(unit, 'name') and unit.name else unit.class_name
                    else:
                        name = unit.name
                    shadow_surface = self.font.render(name, True, (0, 0, 0))
                    text_surface = self.font.render(name, True, colors['WHITE'])
                    name_y = health_bar_y - 12  # Name above health bar with gap
                    text_rect = text_surface.get_rect(centerx=pos[0], bottom=name_y)
                    # Draw shadow offset by 1px in each direction
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        hex_surface.blit(shadow_surface, text_rect.move(dx, dy))
                    hex_surface.blit(text_surface, text_rect)
                    # Draw damage text if present (above the name) with float-up and fade
                    # elapsed < 0 means the damage_time was set in the future (delayed by attack animation)
                    if unit.damage_text and (pygame.time.get_ticks() - unit.damage_time) >= 0:
                        elapsed = pygame.time.get_ticks() - unit.damage_time
                        duration = 1000  # matches DAMAGE_TEXT_DURATION
                        progress = min(1.0, elapsed / duration)
                        # Float upward by 20px over the duration
                        float_offset = int(progress * 20)
                        # Fade out: full opacity for first half, then fade
                        alpha = 255 if progress < 0.5 else int(255 * (1.0 - (progress - 0.5) * 2))
                        alpha = max(0, alpha)
                        # Use larger font for damage numbers
                        dmg_font_size = max(20, int(self.hex_size * 0.45))
                        dmg_font = pygame.font.Font(None, dmg_font_size)
                        # Green for heals (no minus sign), red for damage
                        is_heal = not unit.damage_text.startswith("-")
                        dmg_color = (80, 255, 80) if is_heal else (255, 60, 60)
                        dmg_text_surf = dmg_font.render(unit.damage_text, True, dmg_color)
                        dmg_shadow_surf = dmg_font.render(unit.damage_text, True, (0, 0, 0))
                        damage_rect = dmg_text_surf.get_rect(centerx=pos[0], bottom=text_rect.top - 2 - float_offset)
                        # Create alpha surface for fade
                        fade_surf = pygame.Surface((dmg_text_surf.get_width() + 4, dmg_text_surf.get_height() + 4), pygame.SRCALPHA)
                        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            fade_surf.blit(dmg_shadow_surf, (2 + dx, 2 + dy))
                        fade_surf.blit(dmg_text_surf, (2, 2))
                        fade_surf.set_alpha(alpha)
                        hex_surface.blit(fade_surf, (damage_rect.x - 2, damage_rect.y - 2))
                unit.draw_health_bar(hex_surface, (pos[0], health_bar_y))

                # Draw defeated X marker for dead players
                if is_dead_player:
                    x_radius = max(8, int(self.hex_size / 4))
                    cx, cy = int(pos[0]), int(pos[1])
                    x_surf = pygame.Surface((x_radius * 2 + 4, x_radius * 2 + 4), pygame.SRCALPHA)
                    xc = x_radius + 2
                    pygame.draw.line(x_surf, (255, 0, 0, 200), (xc - x_radius, xc - x_radius), (xc + x_radius, xc + x_radius), 3)
                    pygame.draw.line(x_surf, (255, 0, 0, 200), (xc - x_radius, xc + x_radius), (xc + x_radius, xc - x_radius), 3)
                    hex_surface.blit(x_surf, (cx - xc, cy - xc))

        # Movement range boundary: pulsing edge on border between reachable and unreachable
        # Drawn late so boundary lines appear above terrain, hex borders, and units
        if movement_range:
            pulse = (math.sin(pygame.time.get_ticks() / 500.0) + 1) / 2
            edge_alpha = int(140 + pulse * 115)
            edge_color = (180, 220, 255, edge_alpha)
            edge_surf = pygame.Surface((hex_surface.get_width(), hex_surface.get_height()), pygame.SRCALPHA)
            # Edge i faces direction (i+1)%6: edge 0→lower-right, 1→below, 2→lower-left, 3→upper-left, 4→above, 5→upper-right
            even_col_neighbors = [(0, 1), (1, 0), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
            odd_col_neighbors = [(1, 1), (1, 0), (1, -1), (0, -1), (-1, 0), (0, 1)]
            for (mr, mc) in movement_range:
                x, y = self.get_hex_center(mr, mc)
                verts = [(x + self.hex_size * math.cos(math.radians(60 * i)),
                          y + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]
                offsets = even_col_neighbors if mc % 2 == 0 else odd_col_neighbors
                for i, (dr, dc) in enumerate(offsets):
                    nr, nc = mr + dr, mc + dc
                    if (nr, nc) not in movement_range:
                        pygame.draw.line(edge_surf, edge_color, verts[i], verts[(i + 1) % 6], 2)
            hex_surface.blit(edge_surf, (0, 0))

        # Attack range boundary: pulsing inward-thickened edges on border of each attack range
        if attack_ranges:
            ar_edge_pulse = (math.sin(pygame.time.get_ticks() / 400.0) + 1) / 2
            even_col_nb = [(0, 1), (1, 0), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
            odd_col_nb = [(1, 1), (1, 0), (1, -1), (0, -1), (-1, 0), (0, 1)]
            inset_t = 0.12  # How far inward the thick edge extends (fraction of hex radius)
            for ar in attack_ranges:
                ar_set = ar["range"]
                color = ar["color"]
                glow_r = min(255, color[0] + 80)
                glow_g = min(255, color[1] + 80)
                glow_b = min(255, color[2] + 80)
                edge_alpha = int(160 + ar_edge_pulse * 95)
                glow_color = (glow_r, glow_g, glow_b, edge_alpha)
                ar_edge_surf = pygame.Surface((hex_surface.get_width(), hex_surface.get_height()), pygame.SRCALPHA)
                for (mr, mc) in ar_set:
                    x, y = self.get_hex_center(mr, mc)
                    verts = [(x + self.hex_size * math.cos(math.radians(60 * i)),
                              y + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]
                    # Inset vertices: each vertex lerped toward hex center
                    inset_verts = [(v[0] + (x - v[0]) * inset_t, v[1] + (y - v[1]) * inset_t) for v in verts]
                    offsets = even_col_nb if mc % 2 == 0 else odd_col_nb
                    for i, (dr, dc) in enumerate(offsets):
                        nr, nc = mr + dr, mc + dc
                        if (nr, nc) not in ar_set:
                            ni = (i + 1) % 6
                            # Quad from outer edge inward: outer_i, outer_i+1, inset_i+1, inset_i
                            quad = [verts[i], verts[ni], inset_verts[ni], inset_verts[i]]
                            pygame.draw.polygon(ar_edge_surf, glow_color, quad, 0)
                hex_surface.blit(ar_edge_surf, (0, 0))

        # Draw hover tooltip near the hovered hex
        if self.hovered_hex:
            h_row, h_col = self.hovered_hex
            if 0 <= h_row < self.rows and 0 <= h_col < self.cols:
                hx, hy = self.get_hex_center(h_row, h_col)
                cell = self.grid[h_row][h_col]
                h_terrain = cell.get("terrain", "grass").replace("_", " ").title()
                # Build tooltip lines
                tip_lines = [h_terrain]
                h_unit = cell.get("unit")
                if h_unit:
                    tip_lines.append(h_unit.name if hasattr(h_unit, 'name') else "Unit")
                # Check location
                if (h_row, h_col) in self.location_data:
                    loc = self.location_data[(h_row, h_col)]
                    if loc.get("card"):
                        loc_name = loc["card"].get_current_data().get("Name", "")
                        if loc_name:
                            tip_lines.append(loc_name)
                # Append extra lines (e.g. damage preview from game screen)
                for extra in self.hover_extra_lines:
                    tip_lines.append(extra)
                # Render tooltip
                tip_font = pygame.font.Font(None, 16)
                # Color extra lines differently (damage preview in red/yellow)
                tip_surfs = []
                for i, line in enumerate(tip_lines):
                    if line.startswith("~"):
                        # Colored line (damage preview)
                        tip_surfs.append(tip_font.render(line[1:], True, (255, 180, 80)))
                    else:
                        tip_surfs.append(tip_font.render(line, True, (220, 220, 230)))
                tip_w = max(s.get_width() for s in tip_surfs) + 12
                tip_h = sum(s.get_height() for s in tip_surfs) + 8 + (len(tip_surfs) - 1) * 2
                tip_x = int(hx + self.hex_size * 0.8)
                tip_y = int(hy - tip_h // 2)
                # Keep on screen
                sw, sh = surface.get_size()
                if tip_x + tip_w > sw:
                    tip_x = int(hx - self.hex_size * 0.8 - tip_w)
                if tip_y < 0:
                    tip_y = 0
                if tip_y + tip_h > sh:
                    tip_y = sh - tip_h
                tip_bg = pygame.Surface((tip_w, tip_h), pygame.SRCALPHA)
                tip_bg.fill((15, 15, 35, 200))
                pygame.draw.rect(tip_bg, (58, 58, 92, 180), (0, 0, tip_w, tip_h), 1)
                hex_surface.blit(tip_bg, (tip_x, tip_y))
                ty_offset = 4
                for ts in tip_surfs:
                    hex_surface.blit(ts, (tip_x + 6, tip_y + ty_offset))
                    ty_offset += ts.get_height() + 2

        # Update and draw attack animations
        self.attack_anims.update()
        self.attack_anims.draw(hex_surface)

        surface.blit(hex_surface, (0, 0))

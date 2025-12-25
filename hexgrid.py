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
        # Grid stores a dict with "unit" and "accessible" keys
        self.grid = [[{"unit": None, "accessible": True} for _ in range(cols)] for _ in range(rows)]
        self.player = None
        self.units = []
        self.selected_hex = None
        self.card_drawing_hexes = []
        self.deck_data = {}
        # Calculate initial offsets based on provided dimensions
        grid_width = self.cols * self.hex_size * 1.5
        grid_height = self.rows * self.hex_size * 1.732
        self.view_offset_x = (window_width - grid_width) / 2 if grid_width < window_width else 0
        self.view_offset_y = (window_height - grid_height) / 2 if grid_height < window_height else 0
        # Font for rendering unit names and damage text
        self.font = pygame.font.Font(None, 18)
        self.game_over = False  # Flag to indicate if the player is defeated

    def load_level(self, level_file, card_manager, player):
        try:
            with open(level_file, 'r') as f:
                level_data = json.load(f)
            # Set grid dimensions from the level file
            self.rows = level_data["grid"]["rows"]
            self.cols = level_data["grid"]["columns"]
            self.hex_size = level_data.get("hex_size", 30)  # Default to 30 if not specified
            # Rebuild the grid with the new dimensions
            self.grid = [[{"unit": None, "accessible": True} for _ in range(self.cols)] for _ in range(self.rows)]
            self.card_drawing_hexes = level_data.get("card_drawing_hexes", [])
            
            # Mark inaccessible hexes
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
            
            # Load and place units
            for unit_data in level_data.get("units", []):
                card_file = os.path.join("cards", f"{unit_data['card_id']}.json")
                with open(card_file, 'r') as cf:
                    card_data = json.load(cf)
                card_data["id"] = unit_data["card_id"]
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
                    deck_file = os.path.join("decks", hex_data["deck_file"])
                    if deck_file not in self.deck_data:
                        try:
                            with open(deck_file, 'r') as df:
                                self.deck_data[deck_file] = json.load(df)
                            print(f"Loaded deck: {deck_file}, contents: {self.deck_data[deck_file]}")
                        except Exception as e:
                            print(f"Error loading deck {deck_file}: {e}")
            
            # Recalculate view offsets based on new grid size
            grid_width = self.cols * self.hex_size * 1.5
            grid_height = self.rows * self.hex_size * 1.732
            self.view_offset_x = (pygame.display.Info().current_w - grid_width) / 2 if grid_width < pygame.display.Info().current_w else 0
            self.view_offset_y = (pygame.display.Info().current_h - grid_height) / 2 if grid_height < pygame.display.Info().current_h else 0

        except Exception as e:
            print(f"Error loading level: {e}")
            # Fallback to default setup only on error
            self.rows, self.cols, self.hex_size = 16, 24, 30
            self.grid = [[{"unit": None, "accessible": True} for _ in range(self.cols)] for _ in range(self.rows)]
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
                    deck_file = os.path.join("decks", hex_data["deck_file"])
                    deck = self.deck_data.get(deck_file)
                    if not deck or not deck["cards"]:
                        return None, "Deck is empty"
                    card_id = hex_data.get("card_id") or random.choice(deck["cards"])
                    card_file = os.path.join("cards", f"{card_id}.json")
                    try:
                        with open(card_file, 'r') as f:
                            card_data = json.load(f)
                        card_data["id"] = card_id
                        card = InventoryCard(card_data)
                        card_manager.track_card_usage(card_id, {"action": "drawn", "screen": "game", "position": (row, col)})
                        return card, f"Drew {card.get_current_data().get('Name', 'Unnamed')}"
                    except Exception as e:
                        return None, f"Error drawing card: {e}"
        return None, "No deck or linked level at this hex"

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
            return {(r, c) for r, c in self.get_neighbors(*start) if self.hex_distance(start, (r, c)) <= range_limit}

    def draw(self, surface, movement_range=None, attack_range=None, colors=None):
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
                'PURPLE': (128, 0, 128)
            }
        hex_surface = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
        for row in range(self.rows):
            for col in range(self.cols):
                x, y = self.get_hex_center(row, col)
                points = [(x + self.hex_size * math.cos(math.radians(60 * i)), 
                           y + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]
                # Draw hex background
                if not self.grid[row][col]["accessible"]:
                    pygame.draw.polygon(hex_surface, colors['GRAY'], points, 0)  # Gray for inaccessible
                elif movement_range and (row, col) in movement_range:
                    pygame.draw.polygon(hex_surface, colors['BLUE'], points, 0)
                elif attack_range and (row, col) in attack_range:
                    pygame.draw.polygon(hex_surface, colors['DARK_RED_ALPHA'], points, 0)
                # Draw special hex indicators
                for hex_data in self.card_drawing_hexes:
                    if hex_data["row"] == row and hex_data["column"] == col:
                        if "linked_level" in hex_data and hex_data["linked_level"]:
                            pygame.draw.polygon(hex_surface, colors['PURPLE'], points, 3)  # Purple for linked levels
                        elif "deck_file" in hex_data and hex_data["deck_file"] or "card_id" in hex_data and hex_data["card_id"]:
                            pygame.draw.polygon(hex_surface, colors['LIGHT_GREEN'], points, 3)  # Green for card-drawing
                        break
                if self.selected_hex == (row, col):
                    pygame.draw.polygon(hex_surface, colors['YELLOW'], points, 0)
                pygame.draw.polygon(hex_surface, colors['GOLDEN_YELLOW'], points, 1)
                # Draw unit if present
                if unit := self.grid[row][col]["unit"]:
                    pos = unit.render_pos if unit.animating and unit.render_pos else (x, y)
                    if isinstance(unit, Player) and unit.image:
                        scale_factor = (self.hex_size * 1.5 * unit.image_scale_factor) / unit.image.get_height()
                        scaled_image = pygame.transform.scale(unit.image, 
                                                             (int(unit.image.get_width() * scale_factor), 
                                                              int(unit.image.get_height() * scale_factor)))
                        image_rect = scaled_image.get_rect(center=(int(pos[0]), int(pos[1])))
                        hex_surface.blit(scaled_image, image_rect)
                        health_bar_y = image_rect.top - 5
                    else:
                        color = (colors['GREEN'] if isinstance(unit, Player) else 
                                 colors['RED'] if unit.allegiance == "Hostile" else 
                                 colors['BLUE'] if unit.allegiance == "Allied" else 
                                 colors['GRAY'])
                        radius = max(10, int(self.hex_size / 3))  # Same as old version
                        pygame.draw.circle(hex_surface, colors['WHITE'] if unit.attack_flash else color, 
                                           (int(pos[0]), int(pos[1])), radius)
                        health_bar_y = pos[1] - 15
                        # Draw unit name above health bar
                        name = unit.class_name if isinstance(unit, Player) else unit.name
                        text_surface = self.font.render(name, True, colors['WHITE'])
                        text_rect = text_surface.get_rect(centerx=pos[0], bottom=health_bar_y - 5)
                        hex_surface.blit(text_surface, text_rect)
                        # Draw damage text if present
                        if unit.damage_text:
                            damage_surface = self.font.render(unit.damage_text, True, colors['RED'])
                            damage_rect = damage_surface.get_rect(center=(pos[0], health_bar_y - 25))
                            hex_surface.blit(damage_surface, damage_rect)
                    unit.draw_health_bar(hex_surface, (pos[0], health_bar_y))
        surface.blit(hex_surface, (0, 0))

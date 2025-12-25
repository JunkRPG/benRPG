import pygame
import sys
import pygame_gui
from pygame_gui.elements import UIButton, UITextEntryLine, UISelectionList, UILabel, UIDropDownMenu
from pygame import display, event
import math
import os
import json
import tkinter as tk
from tkinter import filedialog

# Initialize Pygame
pygame.init()

# Get display info for fullscreen
display_info = pygame.display.Info()
WINDOW_WIDTH = display_info.current_w
WINDOW_HEIGHT = display_info.current_h

# Set up the display in fullscreen
screen = display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
display.set_caption("Level Maker")

# Colors synced with Card Maker
DARK_INDIGO = (25, 25, 112)      # Background
LIGHT_GOLDEN = (238, 221, 130)   # Text
LIGHT_TEAL = (127, 255, 212)     # UI elements background
DARK_BRONZE = (139, 69, 19)      # Text in UI
DARK_BRASS = (184, 134, 11)      # Button background
LIGHT_CREAM = (245, 245, 220)    # Button text
LIGHT_GREEN = (144, 238, 144)    # Card-drawing hex border
YELLOW = (255, 255, 0)           # Selected hex border
GRAY = (200, 200, 200)           # Default hex border

# Terrain types and their colors
TERRAIN_TYPES = ["grass", "water", "mountain"]
TERRAIN_COLORS = {
    "grass": (76, 153, 0),
    "water": (0, 0, 255),
    "mountain": (100, 100, 100)
}

# Initialize Pygame-GUI manager with Card Maker's theme
manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT), "theme.json")

class EditorHexGrid:
    """Manages the hexagonal grid's layout, drawing, and interaction."""
    def __init__(self, rows, cols, hex_size, window_width, window_height):
        self.rows = rows
        self.cols = cols
        self.base_hex_size = hex_size
        self.hex_size = hex_size
        self.min_hex_size = 10
        self.max_hex_size = 100
        grid_width = self.cols * self.hex_size * 1.5
        grid_height = self.rows * self.hex_size * 1.732
        self.view_offset_x = (window_width - grid_width) / 2 if grid_width < window_width else 0
        self.view_offset_y = (window_height - grid_height) / 2 if grid_height < window_height else 0
        self.window_width = window_width
        self.window_height = window_height

    def zoom(self, direction, mouse_x, mouse_y):
        old_hex_size = self.hex_size
        if direction > 0 and self.hex_size < self.max_hex_size:
            self.hex_size = min(self.hex_size + 5, self.max_hex_size)
        elif direction < 0 and self.hex_size > self.min_hex_size:
            self.hex_size = max(self.hex_size - 5, self.min_hex_size)
        if old_hex_size != self.hex_size:
            zoom_factor = self.hex_size / old_hex_size
            self.view_offset_x = mouse_x - (mouse_x - self.view_offset_x) * zoom_factor
            self.view_offset_y = mouse_y - (mouse_y - self.view_offset_y) * zoom_factor
            self.clamp_offsets()

    def pan(self, dx, dy):
        self.view_offset_x += dx
        self.view_offset_y += dy
        self.clamp_offsets()

    def clamp_offsets(self):
        grid_width = self.cols * self.hex_size * 1.5
        grid_height = self.rows * self.hex_size * 1.732
        self.view_offset_x = max(min(self.view_offset_x, self.window_width - grid_width / 2), -grid_width / 2)
        self.view_offset_y = max(min(self.view_offset_y, self.window_height - grid_height / 2), -grid_height / 2)

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
        if not (grid_left - padding <= x <= grid_right + padding and 
                grid_top - padding <= y <= grid_bottom + padding):
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

    def draw(self, surface, selected_hex, card_drawing_dict, player_start, terrain, units, level_editor):
        for row in range(self.rows):
            for col in range(self.cols):
                center = self.get_hex_center(row, col)
                points = [(center[0] + self.hex_size * math.cos(math.radians(60 * i)),
                           center[1] + self.hex_size * math.sin(math.radians(60 * i))) 
                          for i in range(6)]
                terrain_type = terrain[row][col]
                color = TERRAIN_COLORS.get(terrain_type, GRAY)
                pygame.draw.polygon(surface, color, points)
                pygame.draw.polygon(surface, GRAY, points, 1)
                if (row, col) in card_drawing_dict:
                    pygame.draw.polygon(surface, LIGHT_GREEN, points, 3)
                if (row, col) == selected_hex:
                    pygame.draw.polygon(surface, YELLOW, points, 3)
                if (row, col) == player_start:
                    pygame.draw.circle(surface, (0, 0, 255), (int(center[0]), int(center[1])), 5)
                if not level_editor.accessible[row][col]:
                    p1 = (center[0] - self.hex_size, center[1] - self.hex_size * 0.866)
                    p2 = (center[0] + self.hex_size, center[1] + self.hex_size * 0.866)
                    p3 = (center[0] - self.hex_size, center[1] + self.hex_size * 0.866)
                    p4 = (center[0] + self.hex_size, center[1] - self.hex_size * 0.866)
                    pygame.draw.line(surface, (255, 0, 0), p1, p2, 3)
                    pygame.draw.line(surface, (255, 0, 0), p3, p4, 3)
                for hex_data in level_editor.card_drawing_hexes:
                    if hex_data["row"] == row and hex_data["column"] == col and hex_data.get("linked_level"):
                        pygame.draw.polygon(surface, (128, 0, 128), 
                                            [(center[0], center[1] - self.hex_size * 0.5),
                                             (center[0] - self.hex_size * 0.5, center[1] + self.hex_size * 0.5),
                                             (center[0] + self.hex_size * 0.5, center[1] + self.hex_size * 0.5)], 0)
        for hex_data in level_editor.card_drawing_hexes:
            row, col = hex_data["row"], hex_data["column"]
            center = self.get_hex_center(row, col)
            if hex_data["card_id"]:
                try:
                    with open(os.path.join("cards", f"{hex_data['card_id']}.json"), 'r') as f:
                        card_data = json.load(f)
                    image_key = {
                        "Enemy Card": "Enemy Image File Path",
                        "Boss Card": "Boss Image File Path",
                        "NPC Card": "NPC Image File Path",
                        "Location Card": "Location Image File Path",
                        "Junk Card": "Junk Image File Path",
                        "Document Card": "Background Image"
                    }.get(card_data["card_type"], "Background Image File Path")
                    image_path = card_data["data"].get(image_key, "")
                    if image_path and os.path.exists(image_path):
                        image = pygame.image.load(image_path).convert_alpha()
                        image = pygame.transform.scale(image, (int(self.hex_size * 1.2), int(self.hex_size * 1.2)))
                        image_rect = image.get_rect(center=center)
                        surface.blit(image, image_rect)
                except Exception as e:
                    print(f"Error loading card image: {e}")
        for unit in units:
            row, col = unit["position"]
            center = self.get_hex_center(row, col)
            pygame.draw.circle(surface, (255, 0, 0), (int(center[0]), int(center[1])), 10)

class LevelEditor:
    def __init__(self):
        self.grid = EditorHexGrid(10, 10, 30, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.selected_hex = None
        self.card_drawing_hexes = []
        self.card_drawing_dict = {}
        self.deck_files = []
        self.level_files = []
        self.filename_to_deck_data = {}
        self.filename_to_level_data = {}
        self.player_start = None
        self.terrain = [["grass" for _ in range(self.grid.cols)] for _ in range(self.grid.rows)]
        self.accessible = [[True for _ in range(self.grid.cols)] for _ in range(self.grid.rows)]
        self.units = []
        self.unit_cards = {"Enemy": [], "Boss": [], "NPC": []}
        self.setup_ui()
        self.current_unit_type = self.unit_type_dropdown.selected_option[0]
        self.load_decks()
        self.load_levels()
        self.load_unit_cards()
        self.unit_card_list.set_item_list([name for _, name in self.unit_cards.get(self.current_unit_type, [])] or ["No cards available"])
        os.makedirs("levels", exist_ok=True)
        self.is_panning = False
        self.last_mouse_pos = None

    def load_decks(self):
        self.deck_files = []
        self.filename_to_deck_data = {}
        deck_dir = "decks"
        if not os.path.exists(deck_dir):
            os.makedirs(deck_dir)
            self.status_label.set_text("Created 'decks/' directory. Please add decks via Card Maker.")
        for filename in os.listdir(deck_dir):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(deck_dir, filename), 'r') as f:
                        deck_data = json.load(f)
                    display_name = deck_data["deck_name"]
                    self.deck_files.append((display_name, filename))
                    self.filename_to_deck_data[filename] = deck_data
                except Exception as e:
                    self.status_label.set_text(f"Error loading deck {filename}: {e}")
        self.deck_list.set_item_list([name for name, _ in self.deck_files] or ["No decks found"])

    def load_levels(self):
        self.level_files = []
        self.filename_to_level_data = {}
        level_dir = "levels"
        if not os.path.exists(level_dir):
            os.makedirs(level_dir)
            self.status_label.set_text("Created 'levels/' directory. Please add levels.")
        for filename in os.listdir(level_dir):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(level_dir, filename), 'r') as f:
                        level_data = json.load(f)
                    display_name = filename
                    self.level_files.append((display_name, filename))
                    self.filename_to_level_data[filename] = level_data
                except Exception as e:
                    self.status_label.set_text(f"Error loading level {filename}: {e}")
        self.level_list.set_item_list([name for name, _ in self.level_files] or ["No levels found"])

    def load_unit_cards(self):
        index_file = os.path.join("cards", "card_index.json")
        if not os.path.exists(index_file):
            self.status_label.set_text("Card index not found. Run Card Maker first.")
            return
        try:
            with open(index_file, 'r') as f:
                index = json.load(f)
            self.unit_cards = {
                "Enemy": [(card_id, info['name']) for card_id, info in index.items() if info['type'] == "Enemy Card"],
                "Boss": [(card_id, info['name']) for card_id, info in index.items() if info['type'] == "Boss Card"],
                "NPC": [(card_id, info['name']) for card_id, info in index.items() if info['type'] == "NPC Card"]
            }
        except json.JSONDecodeError:
            self.status_label.set_text("Corrupted card index file.")
        except Exception as e:
            self.status_label.set_text(f"Error loading card index: {e}")

    def setup_ui(self):
        self.rows_entry = UITextEntryLine(relative_rect=pygame.Rect(10, 10, 80, 30), manager=manager, initial_text="10")
        self.cols_entry = UITextEntryLine(relative_rect=pygame.Rect(100, 10, 80, 30), manager=manager, initial_text="10")
        self.apply_button = UIButton(relative_rect=pygame.Rect(190, 10, 80, 30), text="Apply", manager=manager)
        y_pos = 50
        self.unit_type_dropdown = UIDropDownMenu(options_list=["Enemy", "Boss", "NPC"], starting_option="Enemy", 
                                                 relative_rect=pygame.Rect(10, y_pos, 190, 30), manager=manager)
        y_pos += 40
        self.unit_card_list = UISelectionList(relative_rect=pygame.Rect(10, y_pos, 190, 100), 
                                              item_list=["No cards available"], manager=manager)
        y_pos += 110
        self.place_unit_button = UIButton(relative_rect=pygame.Rect(10, y_pos, 190, 30), 
                                          text="Place Unit", manager=manager)
        y_pos = 10
        self.deck_list = UISelectionList(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, y_pos, 190, 150), 
                                         item_list=["No decks found"], manager=manager)
        y_pos += 160
        self.assign_button = UIButton(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, y_pos, 90, 30), text="Assign Deck", manager=manager)
        self.remove_button = UIButton(relative_rect=pygame.Rect(WINDOW_WIDTH - 100, y_pos, 90, 30), text="Remove", manager=manager)
        y_pos += 40
        self.card_list = UISelectionList(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, y_pos, 190, 100), 
                                         item_list=["Select a deck first"], manager=manager)
        y_pos += 110
        self.assign_card_button = UIButton(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, y_pos, 190, 30), 
                                           text="Assign Card", manager=manager)
        y_pos += 40
        self.level_list = UISelectionList(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, y_pos, 190, 100), 
                                          item_list=["No levels found"], manager=manager)
        y_pos += 110
        self.assign_level_button = UIButton(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, y_pos, 190, 30), 
                                            text="Link Level", manager=manager)
        y_pos += 40
        self.set_player_start_button = UIButton(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, y_pos, 190, 30), 
                                                text="Set Player Start", manager=manager)
        y_pos += 40
        self.terrain_list = UISelectionList(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, y_pos, 190, 100), 
                                            item_list=TERRAIN_TYPES, manager=manager)
        y_pos += 110
        self.set_terrain_button = UIButton(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, y_pos, 190, 30), 
                                           text="Set Terrain", manager=manager)
        y_pos += 40
        self.toggle_inaccessible_button = UIButton(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, y_pos, 190, 30), 
                                                   text="Toggle Inaccessible", manager=manager)
        self.save_button = UIButton(relative_rect=pygame.Rect(10, WINDOW_HEIGHT - 40, 100, 30), 
                                    text="Save Level", manager=manager)
        self.load_button = UIButton(relative_rect=pygame.Rect(120, WINDOW_HEIGHT - 40, 100, 30), 
                                    text="Load Level", manager=manager)
        self.exit_button = UIButton(relative_rect=pygame.Rect(230, WINDOW_HEIGHT - 40, 100, 30), 
                                    text="Exit", manager=manager)
        self.info_label = UILabel(relative_rect=pygame.Rect(WINDOW_WIDTH - 200, 310, 190, 30), 
                                  text="No hex selected", manager=manager)
        self.status_label = UILabel(relative_rect=pygame.Rect(10, WINDOW_HEIGHT - 70, 300, 30), 
                                    text="", manager=manager)

    def update_info_label(self):
        if self.selected_hex:
            row, col = self.selected_hex
            text = f"Hex ({row}, {col}): Terrain={self.terrain[row][col]}"
            if not self.accessible[row][col]:
                text += " [Inaccessible]"
            for hex_data in self.card_drawing_hexes:
                if (hex_data["row"], hex_data["column"]) == self.selected_hex:
                    if hex_data.get("linked_level"):
                        level_name = os.path.basename(hex_data["linked_level"])
                        text += f", Linked Level={level_name}"
                    elif hex_data["deck_file"]:
                        deck_name = self.filename_to_deck_data.get(hex_data["deck_file"], {}).get("deck_name", "Unknown")
                        if hex_data["card_id"]:
                            with open(os.path.join("cards", "card_index.json"), 'r') as f:
                                index = json.load(f)
                            card_name = index.get(hex_data["card_id"], {}).get("name", "Unknown")
                            text += f", Card={card_name}"
                        else:
                            text += f", Deck={deck_name}"
                    break
            if any(u["position"] == self.selected_hex for u in self.units):
                text += " [Unit]"
            if self.selected_hex == self.player_start:
                text += " [Player Start]"
        else:
            text = "No hex selected"
        self.info_label.set_text(text)

    def update_card_list(self):
        selected_deck = self.deck_list.get_single_selection()
        if selected_deck:
            for display_name, filename in self.deck_files:
                if display_name == selected_deck:
                    deck_data = self.filename_to_deck_data[filename]
                    card_ids = deck_data["cards"]
                    card_names = []
                    with open(os.path.join("cards", "card_index.json"), 'r') as f:
                        index = json.load(f)
                    for card_id in card_ids:
                        card_names.append(index.get(card_id, {}).get("name", "Unknown"))
                    self.card_list.set_item_list(card_names or ["No cards in deck"])
                    return
        self.card_list.set_item_list(["Select a deck first"])

    def handle_event(self, event):
        # Process UI events first
        ui_consumed_event = manager.process_events(event)

        # Handle grid events only if the UI didn’t consume the event
        if event.type == pygame.MOUSEBUTTONDOWN and not ui_consumed_event:
            if event.button == 1:  # Left click to select hex
                pos = event.pos
                hex_pos = self.grid.get_hex_at_pixel(pos[0], pos[1])
                if hex_pos:
                    self.selected_hex = hex_pos
                    self.update_info_label()
            elif event.button == 2:  # Middle click to start panning
                self.is_panning = True
                self.last_mouse_pos = event.pos
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:  # Middle click release to stop panning
                self.is_panning = False
                self.last_mouse_pos = None
        elif event.type == pygame.MOUSEMOTION:
            if self.is_panning and self.last_mouse_pos:  # Pan the grid
                current_pos = event.pos
                dx = current_pos[0] - self.last_mouse_pos[0]
                dy = current_pos[1] - self.last_mouse_pos[1]
                self.grid.pan(dx, dy)
                self.last_mouse_pos = current_pos
        elif event.type == pygame.MOUSEWHEEL:  # Zoom in/out with scroll wheel
            pos = pygame.mouse.get_pos()
            self.grid.zoom(event.y, pos[0], pos[1])
            self.status_label.set_text(f"Zoom level: {self.grid.hex_size}")
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.apply_button:
                try:
                    rows = int(self.rows_entry.get_text())
                    cols = int(self.cols_entry.get_text())
                    if rows > 0 and cols > 0:
                        old_terrain = self.terrain
                        old_accessible = self.accessible
                        self.grid = EditorHexGrid(rows, cols, 30, WINDOW_WIDTH, WINDOW_HEIGHT)
                        self.terrain = [["grass" for _ in range(cols)] for _ in range(rows)]
                        self.accessible = [[True for _ in range(cols)] for _ in range(rows)]
                        for r in range(min(rows, len(old_terrain))):
                            for c in range(min(cols, len(old_terrain[0]))):
                                self.terrain[r][c] = old_terrain[r][c]
                                self.accessible[r][c] = old_accessible[r][c]
                        self.card_drawing_hexes = [hex for hex in self.card_drawing_hexes 
                                                 if 0 <= hex["row"] < rows and 0 <= hex["column"] < cols]
                        self.card_drawing_dict = {(hex["row"], hex["column"]): hex["deck_file"] 
                                                 for hex in self.card_drawing_hexes if hex["deck_file"]}
                        self.units = [u for u in self.units if 0 <= u["position"][0] < rows and 0 <= u["position"][1] < cols]
                        if self.player_start and (self.player_start[0] >= rows or self.player_start[1] >= cols):
                            self.player_start = None
                            self.status_label.set_text("Player start removed (out of bounds)")
                        self.selected_hex = None
                        self.update_info_label()
                        self.status_label.set_text(f"Grid set to {rows}x{cols}")
                    else:
                        self.status_label.set_text("Rows and columns must be positive")
                except ValueError:
                    self.status_label.set_text("Invalid grid size input")
            elif event.ui_element == self.assign_button and self.selected_hex:
                selected_deck = self.deck_list.get_single_selection()
                if selected_deck:
                    for _, filename in self.deck_files:
                        if self.filename_to_deck_data[filename]["deck_name"] == selected_deck:
                            self.card_drawing_dict[self.selected_hex] = filename
                            self.card_drawing_hexes = [hex for hex in self.card_drawing_hexes 
                                                      if (hex["row"], hex["column"]) != self.selected_hex]
                            self.card_drawing_hexes.append({"row": self.selected_hex[0], 
                                                           "column": self.selected_hex[1], 
                                                           "deck_file": filename,
                                                           "card_id": None,
                                                           "linked_level": None})
                            self.update_info_label()
                            self.status_label.set_text(f"Assigned deck {selected_deck}")
                            self.update_card_list()
                            break
            elif event.ui_element == self.assign_card_button and self.selected_hex:
                selected_deck = self.deck_list.get_single_selection()
                selected_card = self.card_list.get_single_selection()
                if selected_deck and selected_card:
                    for _, filename in self.deck_files:
                        if self.filename_to_deck_data[filename]["deck_name"] == selected_deck:
                            deck_data = self.filename_to_deck_data[filename]
                            with open(os.path.join("cards", "card_index.json"), 'r') as f:
                                index = json.load(f)
                            card_id = next((cid for cid in deck_data["cards"] 
                                          if index.get(cid, {}).get("name") == selected_card), None)
                            if card_id:
                                self.card_drawing_hexes = [hex for hex in self.card_drawing_hexes 
                                                          if (hex["row"], hex["column"]) != self.selected_hex]
                                self.card_drawing_hexes.append({"row": self.selected_hex[0], 
                                                               "column": self.selected_hex[1], 
                                                               "deck_file": filename,
                                                               "card_id": card_id,
                                                               "linked_level": None})
                                self.card_drawing_dict[self.selected_hex] = filename
                                self.update_info_label()
                                self.status_label.set_text(f"Assigned card {selected_card}")
                            break
            elif event.ui_element == self.assign_level_button and self.selected_hex:
                selected_level = self.level_list.get_single_selection()
                if selected_level:
                    for display_name, filename in self.level_files:
                        if display_name == selected_level:
                            self.card_drawing_hexes = [hex for hex in self.card_drawing_hexes 
                                                      if (hex["row"], hex["column"]) != self.selected_hex]
                            self.card_drawing_hexes.append({"row": self.selected_hex[0], 
                                                           "column": self.selected_hex[1], 
                                                           "deck_file": None,
                                                           "card_id": None,
                                                           "linked_level": filename})
                            if self.selected_hex in self.card_drawing_dict:
                                del self.card_drawing_dict[self.selected_hex]
                            self.update_info_label()
                            self.status_label.set_text(f"Linked level {selected_level}")
                            break
            elif event.ui_element == self.remove_button and self.selected_hex:
                if self.selected_hex in self.card_drawing_dict or any(h["row"] == self.selected_hex[0] and h["column"] == self.selected_hex[1] for h in self.card_drawing_hexes):
                    self.card_drawing_hexes = [hex for hex in self.card_drawing_hexes 
                                             if (hex["row"], hex["column"]) != self.selected_hex]
                    if self.selected_hex in self.card_drawing_dict:
                        deck_file = self.card_drawing_dict[self.selected_hex]
                        deck_name = self.filename_to_deck_data.get(deck_file, {}).get("deck_name", "Unknown")
                        del self.card_drawing_dict[self.selected_hex]
                        self.status_label.set_text(f"Removed {deck_name}")
                    else:
                        self.status_label.set_text("Removed level link")
                    self.update_info_label()
            elif event.ui_element == self.set_player_start_button and self.selected_hex:
                if not self.accessible[self.selected_hex[0]][self.selected_hex[1]]:
                    self.status_label.set_text("Cannot set player start on inaccessible hex")
                else:
                    self.player_start = self.selected_hex
                    self.update_info_label()
                    self.status_label.set_text(f"Player start set at {self.selected_hex}")
            elif event.ui_element == self.set_terrain_button and self.selected_hex:
                selected_terrain = self.terrain_list.get_single_selection()
                if selected_terrain:
                    self.terrain[self.selected_hex[0]][self.selected_hex[1]] = selected_terrain
                    self.update_info_label()
                    self.status_label.set_text(f"Set terrain to {selected_terrain}")
                else:
                    self.status_label.set_text("No terrain selected")
            elif event.ui_element == self.toggle_inaccessible_button and self.selected_hex:
                row, col = self.selected_hex
                if self.accessible[row][col]:
                    if self.player_start == self.selected_hex:
                        self.player_start = None
                        self.status_label.set_text("Player start removed from inaccessible hex")
                    self.units = [u for u in self.units if u["position"] != self.selected_hex]
                self.accessible[row][col] = not self.accessible[row][col]
                self.update_info_label()
                self.status_label.set_text(f"Toggled accessibility at {self.selected_hex}")
            elif event.ui_element == self.place_unit_button and self.selected_hex:
                if not self.accessible[self.selected_hex[0]][self.selected_hex[1]]:
                    self.status_label.set_text("Cannot place unit on inaccessible hex")
                else:
                    unit_type = self.current_unit_type
                    card_name = self.unit_card_list.get_single_selection()
                    if card_name and card_name != "No cards available":
                        cards = self.unit_cards.get(unit_type, [])
                        card_id = next((id for id, name in cards if name == card_name), None)
                        if card_id:
                            self.units = [u for u in self.units if u["position"] != self.selected_hex]
                            self.units.append({"card_id": card_id, "position": self.selected_hex})
                            self.status_label.set_text(f"Placed {card_name} at {self.selected_hex}")
                        else:
                            self.status_label.set_text("Card not found")
                    else:
                        self.status_label.set_text("No card selected")
            elif event.ui_element == self.save_button:
                self.save_level()
            elif event.ui_element == self.load_button:
                self.load_level()
            elif event.ui_element == self.exit_button:
                pygame.quit()
                sys.exit()
        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED and event.ui_element == self.unit_type_dropdown:
            self.current_unit_type = event.text
            cards = self.unit_cards.get(self.current_unit_type, [])
            self.unit_card_list.set_item_list([name for _, name in cards] or ["No cards available"])
        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION and event.ui_element == self.deck_list:
            self.update_card_list()

    def save_level(self):
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.asksaveasfilename(initialdir="levels", 
                                                defaultextension=".json", 
                                                filetypes=[("JSON files", "*.json")])
        root.destroy()
        if file_path:
            inaccessible_hexes = [{"row": r, "column": c} for r in range(self.grid.rows) 
                                  for c in range(self.grid.cols) if not self.accessible[r][c]]
            level_data = {
                "grid": {"rows": self.grid.rows, "columns": self.grid.cols},
                "player_start": {"row": self.player_start[0], "column": self.player_start[1]} if self.player_start else None,
                "terrain": self.terrain,
                "inaccessible_hexes": inaccessible_hexes,
                "units": [{"card_id": u["card_id"], "position": {"row": u["position"][0], "column": u["position"][1]}} 
                         for u in self.units],
                "card_drawing_hexes": self.card_drawing_hexes
            }
            try:
                with open(file_path, 'w') as f:
                    json.dump(level_data, f, indent=2)
                self.status_label.set_text(f"Level saved to {os.path.basename(file_path)}")
            except Exception as e:
                self.status_label.set_text(f"Error saving level: {e}")

    def load_level(self):
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(initialdir="levels", 
                                              filetypes=[("JSON files", "*.json")])
        root.destroy()
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    level_data = json.load(f)
                rows = level_data["grid"]["rows"]
                cols = level_data["grid"]["columns"]
                self.grid = EditorHexGrid(rows, cols, 30, WINDOW_WIDTH, WINDOW_HEIGHT)
                self.terrain = level_data["terrain"]
                self.accessible = [[True for _ in range(cols)] for _ in range(rows)]
                for hex in level_data.get("inaccessible_hexes", []):
                    row, col = hex["row"], hex["column"]
                    if 0 <= row < rows and 0 <= col < cols:
                        self.accessible[row][col] = False
                self.units = [{"card_id": u["card_id"], "position": (u["position"]["row"], u["position"]["column"])} 
                             for u in level_data["units"]]
                self.player_start = (level_data["player_start"]["row"], level_data["player_start"]["column"]) if level_data.get("player_start") else None
                self.card_drawing_hexes = level_data["card_drawing_hexes"]
                self.card_drawing_dict = {(hex["row"], hex["column"]): hex["deck_file"] 
                                         for hex in self.card_drawing_hexes if hex.get("deck_file")}
                self.selected_hex = None
                self.rows_entry.set_text(str(rows))
                self.cols_entry.set_text(str(cols))
                self.update_info_label()
                self.status_label.set_text(f"Loaded {os.path.basename(file_path)}")
                self.load_levels()
            except Exception as e:
                self.status_label.set_text(f"Error loading level: {e}")

    def draw(self):
        screen.fill(DARK_INDIGO)
        self.grid.draw(screen, self.selected_hex, self.card_drawing_dict, self.player_start, self.terrain, self.units, self)
        manager.draw_ui(screen)

# Main loop
editor = LevelEditor()
clock = pygame.time.Clock()
running = True
while running:
    time_delta = clock.tick(60) / 1000.0
    for e in event.get():
        if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
            running = False
        # Process UI events first, then pass to editor
        editor.handle_event(e)
    manager.update(time_delta)
    editor.draw()
    display.flip()

pygame.quit()
sys.exit()

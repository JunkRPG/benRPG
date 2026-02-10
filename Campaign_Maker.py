"""
Campaign Maker - Tool for creating and editing campaigns in JunkRPG

Campaigns link existing levels into a playable sequence with deck configuration
and completion conditions per stage.
"""

import pygame
import sys
import pygame_gui
from pygame_gui.elements import (
    UIButton, UITextEntryLine, UISelectionList, UILabel,
    UIDropDownMenu, UITextBox, UIPanel
)
from pygame import display, event
import math
import os
import json
import tkinter as tk
from tkinter import filedialog
import uuid
from terrain_config import TERRAIN_CONFIG, TERRAIN_COLORS
from deck_utils import resolve_deck_path

# Initialize Pygame
pygame.init()

# Get display info for fullscreen
display_info = pygame.display.Info()
WINDOW_WIDTH = display_info.current_w
WINDOW_HEIGHT = display_info.current_h

# Set up the display in fullscreen
screen = display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
display.set_caption("Campaign Maker")

# Colors
DARK_CHARCOAL = (35, 35, 40)
LIGHT_GOLDEN = (238, 221, 130)
LIGHT_GREEN = (144, 238, 144)
YELLOW = (255, 255, 0)
GRAY = (200, 200, 200)
ORANGE = (255, 165, 0)

# Completion condition types
COMPLETION_TYPES = [
    "defeat_all_enemies",
    "defeat_boss",
    "collect_item",
    "reach_location",
    "survive_turns"
]

# Initialize Pygame-GUI manager
manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT), "theme.json")


class PreviewHexGrid:
    """Read-only hex grid for level preview."""

    def __init__(self, preview_rect):
        self.preview_rect = preview_rect
        self.rows = 0
        self.cols = 0
        self.hex_size = 20
        self.terrain = []
        self.units = []
        self.player_start = None
        self.inaccessible = []
        self.card_drawing_hexes = []
        self.location_hexes = []
        self.view_offset_x = 0
        self.view_offset_y = 0
        self.level_data = None

    def load_level(self, level_file):
        """Load level data for preview."""
        try:
            with open(level_file, 'r') as f:
                self.level_data = json.load(f)

            self.rows = self.level_data["grid"]["rows"]
            self.cols = self.level_data["grid"]["columns"]
            self.terrain = self.level_data.get("terrain", [["grass"] * self.cols for _ in range(self.rows)])
            self.units = self.level_data.get("units", [])
            self.player_start = self.level_data.get("player_start")
            self.inaccessible = self.level_data.get("inaccessible_hexes", [])
            self.card_drawing_hexes = self.level_data.get("card_drawing_hexes", [])
            self.location_hexes = self.level_data.get("location_hexes", [])

            # Calculate hex size to fit preview area
            self._calculate_view()
            return True
        except Exception as e:
            print(f"Error loading level for preview: {e}")
            self.level_data = None
            return False

    def _calculate_view(self):
        """Calculate hex size and offsets to fit the preview area."""
        if self.rows == 0 or self.cols == 0:
            return

        # Calculate max hex size that fits
        available_width = self.preview_rect.width - 40
        available_height = self.preview_rect.height - 40

        # Hex grid dimensions
        grid_width_factor = self.cols * 1.5 + 0.5
        grid_height_factor = self.rows * 1.732 + 0.866

        # Calculate hex size
        size_by_width = available_width / grid_width_factor
        size_by_height = available_height / grid_height_factor
        self.hex_size = max(5, min(30, min(size_by_width, size_by_height)))

        # Center the grid
        actual_width = grid_width_factor * self.hex_size
        actual_height = grid_height_factor * self.hex_size
        self.view_offset_x = self.preview_rect.x + (self.preview_rect.width - actual_width) / 2
        self.view_offset_y = self.preview_rect.y + (self.preview_rect.height - actual_height) / 2 + 20

    def get_hex_center(self, row, col):
        x = self.view_offset_x + col * self.hex_size * 1.5
        y = self.view_offset_y + row * self.hex_size * 1.732 + (col % 2) * self.hex_size * 0.866
        return x, y

    def draw(self, surface):
        """Draw the level preview."""
        if not self.level_data:
            # Draw empty preview message
            font = pygame.font.SysFont(None, 24)
            text = font.render("Select a level to preview", True, LIGHT_GOLDEN)
            text_rect = text.get_rect(center=self.preview_rect.center)
            surface.blit(text, text_rect)
            return

        # Draw hexes
        for row in range(self.rows):
            for col in range(self.cols):
                center = self.get_hex_center(row, col)
                points = [
                    (center[0] + self.hex_size * math.cos(math.radians(60 * i)),
                     center[1] + self.hex_size * math.sin(math.radians(60 * i)))
                    for i in range(6)
                ]

                # Get terrain color
                terrain_type = self.terrain[row][col] if row < len(self.terrain) and col < len(self.terrain[row]) else "grass"
                color = TERRAIN_COLORS.get(terrain_type, GRAY)

                pygame.draw.polygon(surface, color, points)
                pygame.draw.polygon(surface, GRAY, points, 1)

                # Draw inaccessible marker
                for hex_data in self.inaccessible:
                    if hex_data["row"] == row and hex_data["column"] == col:
                        terrain_accessible = TERRAIN_CONFIG.get(terrain_type, {}).get("accessible", True)
                        if terrain_accessible:
                            # Only show X for manually blocked hexes
                            p1 = (center[0] - self.hex_size * 0.3, center[1] - self.hex_size * 0.3)
                            p2 = (center[0] + self.hex_size * 0.3, center[1] + self.hex_size * 0.3)
                            p3 = (center[0] - self.hex_size * 0.3, center[1] + self.hex_size * 0.3)
                            p4 = (center[0] + self.hex_size * 0.3, center[1] - self.hex_size * 0.3)
                            pygame.draw.line(surface, (255, 0, 0), p1, p2, 1)
                            pygame.draw.line(surface, (255, 0, 0), p3, p4, 1)
                        break

                # Draw location hex indicator
                for loc_hex in self.location_hexes:
                    if loc_hex["row"] == row and loc_hex["column"] == col:
                        pygame.draw.polygon(surface, ORANGE, points, 2)
                        break

                # Draw card drawing hex indicator
                for hex_data in self.card_drawing_hexes:
                    if hex_data["row"] == row and hex_data["column"] == col:
                        pygame.draw.polygon(surface, LIGHT_GREEN, points, 2)
                        break

        # Draw player start
        if self.player_start:
            row, col = self.player_start["row"], self.player_start["column"]
            center = self.get_hex_center(row, col)
            pygame.draw.circle(surface, (0, 0, 255), (int(center[0]), int(center[1])), max(3, int(self.hex_size * 0.3)))

        # Draw units
        for unit in self.units:
            pos = unit["position"]
            row, col = pos["row"], pos["column"]
            center = self.get_hex_center(row, col)
            pygame.draw.circle(surface, (255, 0, 0), (int(center[0]), int(center[1])), max(3, int(self.hex_size * 0.25)))


class CampaignMaker:
    """Main Campaign Maker application."""

    def __init__(self):
        self.campaign_data = {
            "campaign_id": str(uuid.uuid4())[:8],
            "name": "New Campaign",
            "description": "",
            "stages": []
        }
        self.current_stage_index = -1
        self.level_files = []
        self.deck_files = []
        self.filename_to_level_data = {}
        self.filename_to_deck_data = {}

        # Preview grid
        preview_x = 220
        preview_width = WINDOW_WIDTH - 440
        preview_height = WINDOW_HEIGHT - 150
        self.preview_rect = pygame.Rect(preview_x, 60, preview_width, preview_height)
        self.preview_grid = PreviewHexGrid(self.preview_rect)

        self.setup_ui()
        self.load_levels()
        self.load_decks()

        os.makedirs("campaigns", exist_ok=True)

    def load_levels(self):
        """Load available level files."""
        self.level_files = []
        self.filename_to_level_data = {}
        level_dir = "levels"

        if not os.path.exists(level_dir):
            os.makedirs(level_dir)
            return

        for filename in os.listdir(level_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(level_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        level_data = json.load(f)
                    self.level_files.append(filename)
                    self.filename_to_level_data[filename] = level_data
                except Exception as e:
                    print(f"Error loading level {filename}: {e}")

        # Update level dropdown if it exists
        if hasattr(self, 'level_dropdown'):
            options = ["-- Select Level --"] + self.level_files
            self.level_dropdown.kill()
            self.level_dropdown = UIDropDownMenu(
                options_list=options,
                starting_option="-- Select Level --",
                relative_rect=pygame.Rect(WINDOW_WIDTH - 210, 90, 200, 30),
                manager=manager
            )

    def load_decks(self):
        """Load available deck files."""
        self.deck_files = []
        self.filename_to_deck_data = {}
        deck_dir = "decks"

        if not os.path.exists(deck_dir):
            os.makedirs(deck_dir)
            return

        for filename in os.listdir(deck_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(deck_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        deck_data = json.load(f)
                    display_name = deck_data.get("deck_name", filename)
                    self.deck_files.append((display_name, filename))
                    self.filename_to_deck_data[filename] = deck_data
                except Exception as e:
                    print(f"Error loading deck {filename}: {e}")

    def setup_ui(self):
        """Set up the UI elements."""
        # === LEFT PANEL (Campaign Info & Stage List) ===
        left_panel_width = 210

        # Campaign Info Section
        self.campaign_info_label = UILabel(
            relative_rect=pygame.Rect(10, 10, left_panel_width - 20, 25),
            text="Campaign Info",
            manager=manager
        )

        UILabel(pygame.Rect(10, 40, 80, 20), "Name:", manager=manager)
        self.name_entry = UITextEntryLine(
            relative_rect=pygame.Rect(10, 60, left_panel_width - 20, 30),
            manager=manager,
            initial_text="New Campaign"
        )

        UILabel(pygame.Rect(10, 95, 100, 20), "Description:", manager=manager)
        self.desc_entry = UITextEntryLine(
            relative_rect=pygame.Rect(10, 115, left_panel_width - 20, 30),
            manager=manager,
            initial_text=""
        )

        # Stage List Section
        UILabel(pygame.Rect(10, 160, left_panel_width - 20, 25), "Stages:", manager=manager)
        self.stage_list = UISelectionList(
            relative_rect=pygame.Rect(10, 185, left_panel_width - 20, 200),
            item_list=["No stages"],
            manager=manager
        )

        # Stage management buttons
        self.add_stage_button = UIButton(
            relative_rect=pygame.Rect(10, 395, 90, 30),
            text="Add Stage",
            manager=manager
        )
        self.remove_stage_button = UIButton(
            relative_rect=pygame.Rect(110, 395, 90, 30),
            text="Remove",
            manager=manager
        )
        self.move_up_button = UIButton(
            relative_rect=pygame.Rect(10, 430, 90, 30),
            text="Move Up",
            manager=manager
        )
        self.move_down_button = UIButton(
            relative_rect=pygame.Rect(110, 430, 90, 30),
            text="Move Down",
            manager=manager
        )

        # Deck Configuration Section
        UILabel(pygame.Rect(10, 475, left_panel_width - 20, 25), "Deck Config:", manager=manager)

        deck_options = ["-- None --"] + [name for name, _ in self.deck_files]

        UILabel(pygame.Rect(10, 500, 100, 20), "Transition:", manager=manager)
        self.transition_deck_dropdown = UIDropDownMenu(
            options_list=deck_options,
            starting_option="-- None --",
            relative_rect=pygame.Rect(10, 520, left_panel_width - 20, 25),
            manager=manager
        )

        UILabel(pygame.Rect(10, 550, 100, 20), "Quest:", manager=manager)
        self.quest_deck_dropdown = UIDropDownMenu(
            options_list=deck_options,
            starting_option="-- None --",
            relative_rect=pygame.Rect(10, 570, left_panel_width - 20, 25),
            manager=manager
        )

        UILabel(pygame.Rect(10, 600, 100, 20), "Instance:", manager=manager)
        self.instance_deck_dropdown = UIDropDownMenu(
            options_list=deck_options,
            starting_option="-- None --",
            relative_rect=pygame.Rect(10, 620, left_panel_width - 20, 25),
            manager=manager
        )

        UILabel(pygame.Rect(10, 650, 100, 20), "Junk:", manager=manager)
        self.junk_deck_dropdown = UIDropDownMenu(
            options_list=deck_options,
            starting_option="-- None --",
            relative_rect=pygame.Rect(10, 670, left_panel_width - 20, 25),
            manager=manager
        )

        # === RIGHT PANEL (Stage Config) ===
        right_x = WINDOW_WIDTH - 210

        UILabel(pygame.Rect(right_x, 10, 200, 25), "Stage Config", manager=manager)

        UILabel(pygame.Rect(right_x, 40, 100, 20), "Stage Name:", manager=manager)
        self.stage_name_entry = UITextEntryLine(
            relative_rect=pygame.Rect(right_x, 60, 200, 30),
            manager=manager,
            initial_text=""
        )

        UILabel(pygame.Rect(right_x, 95, 100, 20), "Level File:", manager=manager)
        level_options = ["-- Select Level --"] + self.level_files
        self.level_dropdown = UIDropDownMenu(
            options_list=level_options,
            starting_option="-- Select Level --",
            relative_rect=pygame.Rect(right_x, 115, 200, 30),
            manager=manager
        )

        self.browse_level_button = UIButton(
            relative_rect=pygame.Rect(right_x, 150, 200, 30),
            text="Browse...",
            manager=manager
        )

        # Completion conditions
        UILabel(pygame.Rect(right_x, 195, 150, 20), "Completion:", manager=manager)
        self.completion_dropdown = UIDropDownMenu(
            options_list=COMPLETION_TYPES,
            starting_option="defeat_all_enemies",
            relative_rect=pygame.Rect(right_x, 215, 200, 30),
            manager=manager
        )

        UILabel(pygame.Rect(right_x, 250, 150, 20), "Target (Boss/Item):", manager=manager)
        self.target_entry = UITextEntryLine(
            relative_rect=pygame.Rect(right_x, 270, 200, 30),
            manager=manager,
            initial_text=""
        )

        UILabel(pygame.Rect(right_x, 305, 150, 20), "Turn Limit:", manager=manager)
        self.turn_limit_entry = UITextEntryLine(
            relative_rect=pygame.Rect(right_x, 325, 200, 30),
            manager=manager,
            initial_text=""
        )

        # Apply changes button
        self.apply_stage_button = UIButton(
            relative_rect=pygame.Rect(right_x, 370, 200, 35),
            text="Apply Stage Changes",
            manager=manager
        )

        # Level info display
        self.level_info_label = UILabel(
            relative_rect=pygame.Rect(right_x, 420, 200, 25),
            text="Level Info:",
            manager=manager
        )
        self.level_info_text = UITextBox(
            html_text="<font color='#FFFFFF'>Select a level to see info</font>",
            relative_rect=pygame.Rect(right_x, 445, 200, 150),
            manager=manager
        )

        # === BOTTOM TOOLBAR ===
        toolbar_y = WINDOW_HEIGHT - 50

        self.new_button = UIButton(
            relative_rect=pygame.Rect(10, toolbar_y, 100, 40),
            text="New",
            manager=manager
        )
        self.save_button = UIButton(
            relative_rect=pygame.Rect(120, toolbar_y, 100, 40),
            text="Save",
            manager=manager
        )
        self.load_button = UIButton(
            relative_rect=pygame.Rect(230, toolbar_y, 100, 40),
            text="Load",
            manager=manager
        )
        self.test_button = UIButton(
            relative_rect=pygame.Rect(340, toolbar_y, 150, 40),
            text="Test Campaign",
            manager=manager
        )
        self.exit_button = UIButton(
            relative_rect=pygame.Rect(WINDOW_WIDTH - 110, toolbar_y, 100, 40),
            text="Exit",
            manager=manager
        )

        # Status label
        self.status_label = UILabel(
            relative_rect=pygame.Rect(500, toolbar_y + 10, 400, 25),
            text="",
            manager=manager
        )

    def update_stage_list(self):
        """Update the stage list display."""
        if not self.campaign_data["stages"]:
            self.stage_list.set_item_list(["No stages"])
        else:
            stage_names = []
            for i, stage in enumerate(self.campaign_data["stages"]):
                name = stage.get("name", f"Stage {i+1}")
                level = stage.get("level_file", "No level")
                stage_names.append(f"{i+1}. {name}")
            self.stage_list.set_item_list(stage_names)

    def update_stage_config_ui(self):
        """Update the right panel with selected stage's configuration."""
        if self.current_stage_index < 0 or self.current_stage_index >= len(self.campaign_data["stages"]):
            self.stage_name_entry.set_text("")
            self.level_dropdown.selected_option = ("-- Select Level --", "-- Select Level --")
            self.completion_dropdown.selected_option = ("defeat_all_enemies", "defeat_all_enemies")
            self.target_entry.set_text("")
            self.turn_limit_entry.set_text("")
            self._clear_deck_dropdowns()
            self.preview_grid.level_data = None
            return

        stage = self.campaign_data["stages"][self.current_stage_index]

        # Update stage name
        self.stage_name_entry.set_text(stage.get("name", ""))

        # Update level dropdown
        level_file = stage.get("level_file", "")
        if level_file and level_file in self.level_files:
            self.level_dropdown.selected_option = (level_file, level_file)
            # Load preview
            self.preview_grid.load_level(os.path.join("levels", level_file))
            self._update_level_info(level_file)
        else:
            self.level_dropdown.selected_option = ("-- Select Level --", "-- Select Level --")
            self.preview_grid.level_data = None

        # Update completion condition
        completion = stage.get("completion_conditions", {})
        comp_type = completion.get("type", "defeat_all_enemies")
        self.completion_dropdown.selected_option = (comp_type, comp_type)
        self.target_entry.set_text(completion.get("target", ""))
        self.turn_limit_entry.set_text(str(completion.get("turn_limit", "")) if completion.get("turn_limit") else "")

        # Update deck config dropdowns
        deck_config = stage.get("deck_config", {})
        self._set_deck_dropdown(self.transition_deck_dropdown, deck_config.get("transition_deck", ""))
        self._set_deck_dropdown(self.quest_deck_dropdown, deck_config.get("quest_deck", ""))
        self._set_deck_dropdown(self.instance_deck_dropdown, deck_config.get("instance_deck", ""))
        self._set_deck_dropdown(self.junk_deck_dropdown, deck_config.get("junk_deck", ""))

    def _set_deck_dropdown(self, dropdown, deck_path):
        """Set a deck dropdown to the correct value."""
        if not deck_path:
            dropdown.selected_option = ("-- None --", "-- None --")
            return

        # Extract filename from path
        filename = os.path.basename(deck_path)

        # Find display name
        for display_name, fname in self.deck_files:
            if fname == filename:
                dropdown.selected_option = (display_name, display_name)
                return

        dropdown.selected_option = ("-- None --", "-- None --")

    def _clear_deck_dropdowns(self):
        """Clear all deck dropdowns."""
        self.transition_deck_dropdown.selected_option = ("-- None --", "-- None --")
        self.quest_deck_dropdown.selected_option = ("-- None --", "-- None --")
        self.instance_deck_dropdown.selected_option = ("-- None --", "-- None --")
        self.junk_deck_dropdown.selected_option = ("-- None --", "-- None --")

    def _update_level_info(self, level_file):
        """Update the level info display."""
        if level_file not in self.filename_to_level_data:
            self.level_info_text.set_text("<font color='#FFFFFF'>Level data not found</font>")
            return

        level_data = self.filename_to_level_data[level_file]
        rows = level_data.get("grid", {}).get("rows", 0)
        cols = level_data.get("grid", {}).get("columns", 0)
        units = len(level_data.get("units", []))
        locations = len(level_data.get("location_hexes", []))
        card_hexes = len(level_data.get("card_drawing_hexes", []))

        info = f"""<font color='#FFFFFF'>
Grid: {rows}x{cols}<br>
Units: {units}<br>
Locations: {locations}<br>
Card Hexes: {card_hexes}
</font>"""
        self.level_info_text.set_text(info)

    def _get_deck_path_from_dropdown(self, dropdown):
        """Get the deck file path from a dropdown selection."""
        selected = dropdown.selected_option[0] if dropdown.selected_option else "-- None --"
        if selected == "-- None --":
            return ""

        for display_name, filename in self.deck_files:
            if display_name == selected:
                return resolve_deck_path(filename)
        return ""

    def add_stage(self):
        """Add a new stage to the campaign."""
        stage_num = len(self.campaign_data["stages"]) + 1
        new_stage = {
            "stage_id": f"stage_{stage_num}",
            "name": f"Stage {stage_num}",
            "level_file": "",
            "deck_config": {
                "transition_deck": "",
                "quest_deck": "",
                "instance_deck": "",
                "junk_deck": ""
            },
            "completion_conditions": {
                "type": "defeat_all_enemies"
            },
            "next_stage": None
        }
        self.campaign_data["stages"].append(new_stage)

        # Update next_stage links
        for i, stage in enumerate(self.campaign_data["stages"][:-1]):
            stage["next_stage"] = self.campaign_data["stages"][i + 1]["stage_id"]

        self.update_stage_list()
        self.current_stage_index = len(self.campaign_data["stages"]) - 1
        self.update_stage_config_ui()
        self.status_label.set_text(f"Added Stage {stage_num}")

    def remove_stage(self):
        """Remove the selected stage."""
        if self.current_stage_index < 0 or self.current_stage_index >= len(self.campaign_data["stages"]):
            self.status_label.set_text("No stage selected")
            return

        removed_name = self.campaign_data["stages"][self.current_stage_index].get("name", "Stage")
        del self.campaign_data["stages"][self.current_stage_index]

        # Update next_stage links
        for i, stage in enumerate(self.campaign_data["stages"]):
            if i < len(self.campaign_data["stages"]) - 1:
                stage["next_stage"] = self.campaign_data["stages"][i + 1]["stage_id"]
            else:
                stage["next_stage"] = None

        self.update_stage_list()

        if self.current_stage_index >= len(self.campaign_data["stages"]):
            self.current_stage_index = len(self.campaign_data["stages"]) - 1

        self.update_stage_config_ui()
        self.status_label.set_text(f"Removed {removed_name}")

    def move_stage(self, direction):
        """Move the selected stage up or down."""
        if self.current_stage_index < 0:
            return

        new_index = self.current_stage_index + direction
        if new_index < 0 or new_index >= len(self.campaign_data["stages"]):
            return

        # Swap stages
        stages = self.campaign_data["stages"]
        stages[self.current_stage_index], stages[new_index] = stages[new_index], stages[self.current_stage_index]

        # Update next_stage links
        for i, stage in enumerate(stages):
            if i < len(stages) - 1:
                stage["next_stage"] = stages[i + 1]["stage_id"]
            else:
                stage["next_stage"] = None

        self.current_stage_index = new_index
        self.update_stage_list()
        self.status_label.set_text(f"Moved stage to position {new_index + 1}")

    def apply_stage_changes(self):
        """Apply changes from UI to the current stage."""
        if self.current_stage_index < 0 or self.current_stage_index >= len(self.campaign_data["stages"]):
            self.status_label.set_text("No stage selected")
            return

        stage = self.campaign_data["stages"][self.current_stage_index]

        # Update stage name
        stage["name"] = self.stage_name_entry.get_text() or f"Stage {self.current_stage_index + 1}"

        # Update level file
        level_selection = self.level_dropdown.selected_option[0] if self.level_dropdown.selected_option else ""
        if level_selection and level_selection != "-- Select Level --":
            stage["level_file"] = level_selection
        else:
            stage["level_file"] = ""

        # Update completion conditions
        comp_type = self.completion_dropdown.selected_option[0] if self.completion_dropdown.selected_option else "defeat_all_enemies"
        stage["completion_conditions"] = {"type": comp_type}

        target = self.target_entry.get_text().strip()
        if target:
            stage["completion_conditions"]["target"] = target

        turn_limit = self.turn_limit_entry.get_text().strip()
        if turn_limit:
            try:
                stage["completion_conditions"]["turn_limit"] = int(turn_limit)
            except ValueError:
                pass

        # Update deck config
        stage["deck_config"] = {
            "transition_deck": self._get_deck_path_from_dropdown(self.transition_deck_dropdown),
            "quest_deck": self._get_deck_path_from_dropdown(self.quest_deck_dropdown),
            "instance_deck": self._get_deck_path_from_dropdown(self.instance_deck_dropdown),
            "junk_deck": self._get_deck_path_from_dropdown(self.junk_deck_dropdown)
        }

        self.update_stage_list()
        self.status_label.set_text(f"Applied changes to {stage['name']}")

    def new_campaign(self):
        """Create a new empty campaign."""
        self.campaign_data = {
            "campaign_id": str(uuid.uuid4())[:8],
            "name": "New Campaign",
            "description": "",
            "stages": []
        }
        self.current_stage_index = -1
        self.name_entry.set_text("New Campaign")
        self.desc_entry.set_text("")
        self.update_stage_list()
        self.update_stage_config_ui()
        self.status_label.set_text("Created new campaign")

    def save_campaign(self):
        """Save the campaign to a file."""
        # Update campaign name and description from UI
        self.campaign_data["name"] = self.name_entry.get_text() or "Unnamed Campaign"
        self.campaign_data["description"] = self.desc_entry.get_text()

        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.asksaveasfilename(
            initialdir="campaigns",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=f"{self.campaign_data['name'].replace(' ', '_')}.json"
        )
        root.destroy()

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.campaign_data, f, indent=2)
                self.status_label.set_text(f"Saved: {os.path.basename(file_path)}")
            except Exception as e:
                self.status_label.set_text(f"Error saving: {e}")

    def load_campaign(self):
        """Load a campaign from a file."""
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            initialdir="campaigns",
            filetypes=[("JSON files", "*.json")]
        )
        root.destroy()

        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.campaign_data = json.load(f)

                # Handle old campaign format (convert if needed)
                if "levels" in self.campaign_data and "stages" not in self.campaign_data:
                    self._convert_old_format()

                self.name_entry.set_text(self.campaign_data.get("name", "Unnamed"))
                self.desc_entry.set_text(self.campaign_data.get("description", ""))
                self.current_stage_index = 0 if self.campaign_data.get("stages") else -1
                self.update_stage_list()
                self.update_stage_config_ui()
                self.status_label.set_text(f"Loaded: {os.path.basename(file_path)}")
            except Exception as e:
                self.status_label.set_text(f"Error loading: {e}")

    def _convert_old_format(self):
        """Convert old campaign format to new format."""
        old_levels = self.campaign_data.get("levels", [])
        new_stages = []

        for i, level in enumerate(old_levels):
            stage = {
                "stage_id": f"stage_{i+1}",
                "name": f"Stage {i+1}",
                "level_file": level.get("level_file", ""),
                "deck_config": {
                    "transition_deck": "",
                    "quest_deck": "",
                    "instance_deck": "",
                    "junk_deck": ""
                },
                "completion_conditions": {"type": "defeat_all_enemies"},
                "next_stage": f"stage_{i+2}" if i < len(old_levels) - 1 else None
            }

            # Parse old transition_to_next format
            transition = level.get("transition_to_next", "")
            if "Defeat Boss" in transition:
                stage["completion_conditions"]["type"] = "defeat_boss"
                if "'" in transition:
                    stage["completion_conditions"]["target"] = transition.split("'")[1]
            elif "Collect" in transition:
                stage["completion_conditions"]["type"] = "collect_item"
                if "'" in transition:
                    stage["completion_conditions"]["target"] = transition.split("'")[1]

            new_stages.append(stage)

        self.campaign_data["stages"] = new_stages
        if "levels" in self.campaign_data:
            del self.campaign_data["levels"]

    def test_campaign(self):
        """Launch the game with this campaign for testing."""
        # First save to a temp file
        temp_path = os.path.join("campaigns", "_test_campaign.json")

        # Update campaign data from UI
        self.campaign_data["name"] = self.name_entry.get_text() or "Test Campaign"
        self.campaign_data["description"] = self.desc_entry.get_text()

        if not self.campaign_data["stages"]:
            self.status_label.set_text("Add at least one stage before testing")
            return

        # Check all stages have level files
        for i, stage in enumerate(self.campaign_data["stages"]):
            if not stage.get("level_file"):
                self.status_label.set_text(f"Stage {i+1} has no level file")
                return

        try:
            with open(temp_path, 'w') as f:
                json.dump(self.campaign_data, f, indent=2)

            # Launch the game with this campaign
            import subprocess
            subprocess.Popen([sys.executable, "JunkRPG34.py", "--campaign", temp_path])
            self.status_label.set_text("Launched game for testing...")
        except Exception as e:
            self.status_label.set_text(f"Error launching test: {e}")

    def handle_event(self, e):
        """Handle pygame events."""
        manager.process_events(e)

        if e.type == pygame_gui.UI_BUTTON_PRESSED:
            if e.ui_element == self.add_stage_button:
                self.add_stage()
            elif e.ui_element == self.remove_stage_button:
                self.remove_stage()
            elif e.ui_element == self.move_up_button:
                self.move_stage(-1)
            elif e.ui_element == self.move_down_button:
                self.move_stage(1)
            elif e.ui_element == self.apply_stage_button:
                self.apply_stage_changes()
            elif e.ui_element == self.new_button:
                self.new_campaign()
            elif e.ui_element == self.save_button:
                self.save_campaign()
            elif e.ui_element == self.load_button:
                self.load_campaign()
            elif e.ui_element == self.test_button:
                self.test_campaign()
            elif e.ui_element == self.exit_button:
                pygame.quit()
                sys.exit()
            elif e.ui_element == self.browse_level_button:
                self._browse_level()

        elif e.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if e.ui_element == self.stage_list:
                # Parse stage index from selection
                selected = e.text
                if selected and selected != "No stages":
                    try:
                        self.current_stage_index = int(selected.split(".")[0]) - 1
                        self.update_stage_config_ui()
                    except (ValueError, IndexError):
                        pass

        elif e.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            if e.ui_element == self.level_dropdown:
                level_file = e.text
                if level_file and level_file != "-- Select Level --":
                    level_path = os.path.join("levels", level_file)
                    if os.path.exists(level_path):
                        self.preview_grid.load_level(level_path)
                        self._update_level_info(level_file)
                else:
                    self.preview_grid.level_data = None
                    self.level_info_text.set_text("<font color='#FFFFFF'>Select a level to see info</font>")

    def _browse_level(self):
        """Browse for a level file."""
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            initialdir="levels",
            filetypes=[("JSON files", "*.json")]
        )
        root.destroy()

        if file_path:
            filename = os.path.basename(file_path)
            # Add to level files if not already there
            if filename not in self.level_files:
                self.level_files.append(filename)
                try:
                    with open(file_path, 'r') as f:
                        self.filename_to_level_data[filename] = json.load(f)
                except Exception as e:
                    print(f"Error loading level: {e}")

            # Update dropdown and selection
            self.level_dropdown.kill()
            level_options = ["-- Select Level --"] + self.level_files
            self.level_dropdown = UIDropDownMenu(
                options_list=level_options,
                starting_option=filename,
                relative_rect=pygame.Rect(WINDOW_WIDTH - 210, 115, 200, 30),
                manager=manager
            )

            # Load preview
            self.preview_grid.load_level(file_path)
            self._update_level_info(filename)

    def draw(self):
        """Draw the application."""
        screen.fill(DARK_CHARCOAL)

        # Draw preview border
        pygame.draw.rect(screen, GRAY, self.preview_rect, 2)

        # Draw preview header
        font = pygame.font.SysFont(None, 20)
        header_text = font.render("Level Preview", True, LIGHT_GOLDEN)
        screen.blit(header_text, (self.preview_rect.x + 10, self.preview_rect.y + 5))

        # Draw hex grid preview
        self.preview_grid.draw(screen)

        # Draw UI
        manager.draw_ui(screen)


def main():
    """Main application loop."""
    app = CampaignMaker()
    clock = pygame.time.Clock()
    running = True

    while running:
        time_delta = clock.tick(60) / 1000.0

        for e in event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                running = False
            app.handle_event(e)

        manager.update(time_delta)
        app.draw()
        display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

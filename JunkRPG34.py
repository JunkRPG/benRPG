import pygame
import sys
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UIWindow, UISelectionList, UIDropDownMenu, UILabel, UIPanel, UITextEntryLine
from pygame import display, event
import math
from heapq import heappush, heappop
import os
import json
import datetime
import random
from collections import deque
import tkinter as tk
from tkinter import filedialog
from player import Player  # Import Player from player.py
from unit import Unit      # Import Unit from unit.py
from hexgrid import HexGrid  # Import HexGrid from hexgrid.py
from inventory_card import InventoryCard
from quest_system import QuestManager
from instance_system import InstanceManager
from transition_system import TransitionManager
from deck_utils import resolve_deck_path
from card_utils import load_card, load_card_index
from terrain_config import TERRAIN_CONFIG, get_terrain_color
from save_system import SaveManager

# Initialize Pygame and Pygame-GUI
pygame.init()

# Set up fullscreen display
display_info = pygame.display.Info()
WINDOW_WIDTH = display_info.current_w
WINDOW_HEIGHT = display_info.current_h
screen = display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
display.set_caption("Hex-Grid RPG")

# Initialize UIManager
manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT), "theme.json")

# Colors (synced with level maker where applicable)
DARK_CHARCOAL = (35, 35, 40)  # Background
GRAY = (200, 200, 200)
YELLOW = (255, 255, 0)
GOLDEN_YELLOW = (255, 215, 0)
BLUE = (0, 0, 255)
RED = (255, 0, 0)
DARK_RED_ALPHA = (100, 0, 0, 128)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
LIGHT_GREEN = (144, 238, 144)  # Card-drawing hex border
PURPLE = (128, 0, 128)  # Linked level hex border
ORANGE = (255, 165, 0)  # Location hex border

# Animation constants
MOVE_SPEED = 5
ATTACK_FLASH_DURATION = 500

# Directories
os.makedirs("cards", exist_ok=True)
os.makedirs("levels", exist_ok=True)
os.makedirs("campaigns", exist_ok=True)
os.makedirs("saves", exist_ok=True)
INDEX_FILE = "cards/card_index.json"
if not os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, 'w') as f:
        json.dump({}, f)

# Character classes
CHARACTER_CLASSES = {
    "Ranger": {"hp": 50, "movement": 5, "projectile_range": 5, "attacks": {"Sling": 8, "Punch": 4}, "special_attack": "Piercing Shot"},
    "Warrior": {"hp": 100, "movement": 4, "projectile_range": 4, "attacks": {"Throw Rock": 6, "Kick": 6}, "special_attack": "Double Attack"},
    "Tank": {"hp": 150, "movement": 3, "projectile_range": 3, "attacks": {"Spit": 4, "Head-butt": 8}, "special_attack": "Spin Punch"}
}


def add_card_to_player(card):
    """Add a card to inventory or party depending on type. Returns message about where it went."""
    card_type = card.card_data.get("card_type", "")
    if card_type == "NPC Card":
        allegiance = card.get_current_data().get("Allegiance (Hostile, Neutral, Allied)", "")
        if "Allied" in allegiance:
            game.current_party.append(card)
            name = card.get_current_data().get("Name", "Unknown")
            return f"{name} joined your party!"
    game.current_player.inventory.append(card)
    return None  # No special message


# CardManager class
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
        import random
        try:
            with open(deck_file, 'r') as f:
                deck_data = json.load(f)
        except Exception as e:
            print(f"Error loading deck {deck_file}: {e}")
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
            print(f"Error with usage log: {e}")

# InventoryScreen class
class InventoryScreen:
    def __init__(self):
        self.window = None
        self.header_label = None
        self.junk_list = None
        self.documents_list = None
        self.weapons_list = None
        self.equip_button = None
        self.consumables_list = None
        self.use_button = None
        self.use_junk_button = None
        self.tools_list = None
        self.equip_tool_button = None
        self.equip_accessory_button = None  # For tool belts and accessories
        self.browse_cards_button = None  # Creative mode: browse all cards
        self.read_guide_button = None  # For reading Guide documents
        self.info_text = None
        self.close_button = None
        self.selected_card = None
        self.selected_from_list = None  # Track which list the selection came from

    def initialize_screen(self):
        manager.clear_and_reset()
        window_rect = pygame.Rect((WINDOW_WIDTH - 1200) // 2, (WINDOW_HEIGHT - 800) // 2, 1200, 800)
        self.window = UIWindow(window_rect, manager, "Inventory")
        self.header_label = UILabel(pygame.Rect(0, 0, 1200, 50), "Inventory", manager, container=self.window)
        column_width = 280
        column_height = 500

        # Column labels
        UILabel(pygame.Rect(10, 35, column_width, 25), "Junk / Materials", manager, container=self.window)
        UILabel(pygame.Rect(column_width + 10, 35, column_width, 25), "Documents", manager, container=self.window)
        UILabel(pygame.Rect(2 * column_width + 10, 35, column_width, 25), "Weapons", manager, container=self.window)
        UILabel(pygame.Rect(3 * column_width + 10, 35, column_width, 25), "Consumables / Tools", manager, container=self.window)

        # Junk cards (column 1)
        junk_cards = [card for card in game.current_player.inventory if card.current_state == 1 and card.card_data["card_type"] == "Junk Card"]
        junk_names = []
        for card in junk_cards:
            name = card.get_current_data().get("Name", "Unnamed")
            # Mark consumable junk items
            if card.get_current_data().get("Use_HP") or card.card_data.get("subclass") == "Consumable":
                name += " [Usable]"
            junk_names.append(name)
        self.junk_list = UISelectionList(pygame.Rect(10, 60, column_width, column_height),
                                         junk_names if junk_names else ["No junk items"],
                                         manager, container=self.window)
        self.use_junk_button = UIButton(pygame.Rect(10, 565, column_width, 35), "Use Item", manager, container=self.window)

        # Documents (column 2) - include Guide cards in both states
        documents_cards = [card for card in game.current_player.inventory
                          if card.card_data["card_type"] == "Document Card"
                          and (card.current_state == 1 or card.card_data.get("subclass") == "Guide")]
        self.documents_list = UISelectionList(pygame.Rect(column_width + 10, 60, column_width, column_height - 45),
                                              [card.get_current_data().get("Name", "Unnamed") for card in documents_cards] or ["No documents"],
                                              manager, container=self.window)
        self.read_guide_button = UIButton(pygame.Rect(column_width + 10, column_height + 20, column_width, 35),
                                          "Read Guide", manager, container=self.window)

        # Weapons (column 3)
        weapons_cards = [card for card in game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") in ["Melee", "Projectile", "Both"]]
        self.weapons_list = UISelectionList(pygame.Rect(2 * column_width + 10, 60, column_width, column_height - 100),
                                            [card.get_current_data().get("Name", "Unnamed") for card in weapons_cards] or ["No weapons"],
                                            manager, container=self.window)
        self.equip_button = UIButton(pygame.Rect(2 * column_width + 10, column_height - 30, column_width, 35), "Equip Weapon", manager, container=self.window)

        # Consumables, Tools, and Ammunition (column 4)
        consumables_cards = [card for card in game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Consumable"]
        tools_cards = [card for card in game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Tool"]
        ammo_cards = [card for card in game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Ammunition"]
        accessory_cards = [card for card in game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") in ["Tool_Belt", "Accessory", "Belt", "Pouch"]]
        combined_items = consumables_cards + tools_cards + ammo_cards + accessory_cards

        # Mark item types in the list
        item_names = []
        for card in combined_items:
            name = card.get_current_data().get("Name", "Unnamed")
            card_type = card.get_current_data().get("Type", "")
            if card_type == "Ammunition":
                name += " [Ammo]"
            elif card_type in ["Tool_Belt", "Accessory", "Belt", "Pouch"]:
                name += " [Accessory]"
            item_names.append(name)

        self.consumables_list = UISelectionList(pygame.Rect(3 * column_width + 10, 60, column_width, column_height - 190),
                                                item_names if item_names else ["No consumables/tools"],
                                                manager, container=self.window)
        self.use_button = UIButton(pygame.Rect(3 * column_width + 10, column_height - 120, column_width, 35), "Use Consumable", manager, container=self.window)
        self.equip_tool_button = UIButton(pygame.Rect(3 * column_width + 10, column_height - 80, column_width, 35), "Equip as Tool/Ammo", manager, container=self.window)
        self.equip_accessory_button = UIButton(pygame.Rect(3 * column_width + 10, column_height - 40, column_width, 35), "Equip Accessory", manager, container=self.window)

        # Item details panel (bottom)
        UILabel(pygame.Rect(10, 610, 200, 25), "Item Details:", manager, container=self.window)
        self.info_text = UITextBox("<font color='#FFFFFF'>Select an item to view its stats and details</font>",
                                   pygame.Rect(10, 635, 870, 120), manager, container=self.window)

        # Creative mode button (browse all cards)
        if game.game_mode == "creative":
            self.browse_cards_button = UIButton(pygame.Rect(900, 635, 150, 35), "Browse Cards", manager, container=self.window)
            # Mode indicator
            UILabel(pygame.Rect(900, 680, 150, 25), "[Creative Mode]", manager, container=self.window)
        else:
            self.browse_cards_button = None

        # Close button
        self.close_button = UIButton(pygame.Rect(1050, 720, 120, 35), "Close", manager, container=self.window)
        self.selected_card = None
        self.selected_from_list = None

    def handle_event(self, event):
        # Handle window X button close
        if event.type == pygame_gui.UI_WINDOW_CLOSE:
            if event.ui_element == self.window:
                game.current_screen = "game"
                game_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                game.current_screen = "game"
                game_screen.initialize_screen()
            elif self.browse_cards_button and event.ui_element == self.browse_cards_button:
                game.current_screen = "card_browser"
                card_browser_screen.initialize_screen()
            elif event.ui_element == self.equip_button and self.selected_card and self.selected_from_list == "weapons":
                game.current_player.equip_weapon(self.selected_card)
                game_screen.player_info_label.set_text(game_screen.get_player_info())
                self.info_text.set_text("<font color='#00FF00'>Weapon equipped!</font>")
            elif event.ui_element == self.use_junk_button and self.selected_card and self.selected_from_list == "junk":
                # Use consumable junk item
                self._use_consumable_item()
            elif event.ui_element == self.use_button and self.selected_card and self.selected_from_list == "consumables":
                # Use crafted consumable
                self._use_consumable_item()
            elif event.ui_element == self.equip_tool_button and self.selected_card:
                # Equip item as tool (works for junk with Use_HP, consumables, tools, or ammunition)
                if self.selected_from_list in ["junk", "consumables"]:
                    card_type = self.selected_card.get_current_data().get("Type", "")
                    # Don't equip accessories via tool button
                    if card_type in ["Tool_Belt", "Accessory", "Belt", "Pouch"]:
                        self.info_text.set_text("<font color='#FF0000'>Use 'Equip Accessory' for tool belts</font>")
                    else:
                        msg = game.current_player.equip_tool(self.selected_card)
                        self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
                        self.initialize_screen()  # Refresh to remove from list
                else:
                    self.info_text.set_text("<font color='#FF0000'>Select a consumable, tool, or ammo to equip</font>")
            elif hasattr(self, 'equip_accessory_button') and event.ui_element == self.equip_accessory_button and self.selected_card:
                # Equip accessory (tool belt, pouch, etc.)
                if self.selected_from_list == "consumables":
                    card_type = self.selected_card.get_current_data().get("Type", "")
                    if card_type in ["Tool_Belt", "Accessory", "Belt", "Pouch"]:
                        msg = game.current_player.equip_accessory(self.selected_card)
                        self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
                        self.initialize_screen()  # Refresh to remove from list
                    else:
                        self.info_text.set_text("<font color='#FF0000'>Select a tool belt or accessory to equip</font>")
                else:
                    self.info_text.set_text("<font color='#FF0000'>Select a tool belt or accessory to equip</font>")
            elif self.read_guide_button and event.ui_element == self.read_guide_button:
                # Read Guide document to learn a blueprint
                if self.selected_card and self.selected_from_list == "documents" and self.selected_card.card_data.get("subclass") == "Guide":
                    message = game.current_player.read_guide(self.selected_card, game.card_manager)
                    self.info_text.set_text(f"<font color='#00FFFF'>{message}</font>")
                    game_screen.add_to_log(message)
                    self.initialize_screen()
                else:
                    self.info_text.set_text("<font color='#FF0000'>Select a Guide document to read</font>")

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            selected_name = event.text
            # Remove [Usable] suffix if present for matching
            clean_name = selected_name.replace(" [Usable]", "")

            if event.ui_element == self.junk_list:
                self.selected_from_list = "junk"
                self.selected_card = next((card for card in game.current_player.inventory
                                          if card.current_state == 1
                                          and card.card_data["card_type"] == "Junk Card"
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.documents_list:
                self.selected_from_list = "documents"
                self.selected_card = next((card for card in game.current_player.inventory
                                          if card.card_data["card_type"] == "Document Card"
                                          and (card.current_state == 1 or card.card_data.get("subclass") == "Guide")
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.weapons_list:
                self.selected_from_list = "weapons"
                self.selected_card = next((card for card in game.current_player.inventory
                                          if card.current_state == 2
                                          and card.get_current_data().get("Type") in ["Melee", "Projectile", "Both"]
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.consumables_list:
                self.selected_from_list = "consumables"
                # Remove type suffixes for matching
                match_name = clean_name.replace(" [Ammo]", "").replace(" [Accessory]", "")
                self.selected_card = next((card for card in game.current_player.inventory
                                          if card.current_state == 2
                                          and card.get_current_data().get("Type") in ["Consumable", "Tool", "Ammunition", "Tool_Belt", "Accessory", "Belt", "Pouch"]
                                          and card.get_current_data().get("Name") == match_name), None)

            if self.selected_card:
                # Build detailed info display
                card_data = self.selected_card.get_current_data()
                info_lines = []
                info_lines.append(f"<b>{card_data.get('Name', 'Unknown')}</b>")
                if card_data.get('Description'):
                    info_lines.append(f"<i>{card_data.get('Description')}</i>")
                info_lines.append("")
                for k, v in card_data.items():
                    if v and k not in ['Name', 'Description', 'id']:
                        info_lines.append(f"{k}: {v}")
                self.info_text.set_text(f"<font color='#FFFFFF'>{'<br>'.join(info_lines)}</font>")
            else:
                self.info_text.set_text("<font color='#FFFFFF'>Select an item to view its stats and details</font>")

    def _use_consumable_item(self):
        """Use a consumable item (junk or crafted)."""
        if not self.selected_card:
            self.info_text.set_text("<font color='#FF0000'>No item selected!</font>")
            return

        current_data = self.selected_card.get_current_data()
        hp_effect = current_data.get("Use_HP", "")

        if not hp_effect:
            self.info_text.set_text(f"<font color='#FF0000'>{current_data.get('Name', 'Item')} cannot be used!</font>")
            return

        try:
            # Handle case where hp_effect is a list
            if isinstance(hp_effect, list):
                hp_effect = next((effect for effect in hp_effect if effect and "HP" in effect), "+0HP")

            # Parse HP value (handles +15HP, -10HP, etc.)
            hp_str = hp_effect.replace("HP", "").replace("+", "")
            hp_change = int(hp_str)

            if hp_change > 0:
                old_hp = game.current_player.hp
                game.current_player.hp = min(game.current_player.max_hp, game.current_player.hp + hp_change)
                actual_heal = game.current_player.hp - old_hp
                game_screen.add_to_log(f"Used {current_data.get('Name', 'Item')}: +{actual_heal} HP ({old_hp} -> {game.current_player.hp})")
                game.current_player.inventory.remove(self.selected_card)
                self.selected_card = None
                self.initialize_screen()
                game_screen.player_info_label.set_text(game_screen.get_player_info())
            elif hp_change < 0:
                # Negative HP effect (poison, damage item, etc.)
                game.current_player.hp = max(0, game.current_player.hp + hp_change)
                game_screen.add_to_log(f"Used {current_data.get('Name', 'Item')}: {hp_change} HP")
                game.current_player.inventory.remove(self.selected_card)
                self.selected_card = None
                self.initialize_screen()
                game_screen.player_info_label.set_text(game_screen.get_player_info())
            else:
                self.info_text.set_text(f"<font color='#FF0000'>{current_data.get('Name', 'Item')} has no effect!</font>")
        except (ValueError, AttributeError) as e:
            self.info_text.set_text(f"<font color='#FF0000'>Cannot use {current_data.get('Name', 'Item')}: invalid effect</font>")

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# LocationScreen class for interacting with location hexes
class LocationScreen:
    def __init__(self):
        self.window = None
        self.location_card = None
        self.hex_pos = None
        self.choice_buttons = []
        self.shop_items_list = None
        self.buy_button = None
        self.sell_materials_list = None
        self.sell_button = None
        self.npc_list = None
        self.assign_npc_button = None
        self.close_button = None
        self.info_text = None
        self.selected_shop_item = None
        self.selected_materials = []
        self.material_name_to_card = {}
        self.shop_item_names = []
        # Quest viewing
        self.quest_panel_visible = False
        self.available_quests = []  # List of quest InventoryCards
        self.quest_list = None
        self.quest_details_text = None
        self.accept_quest_button = None
        self.selected_quest_index = None
        self.quest_deck_file = None
        # Garrison system
        self.garrison_panel_visible = False
        self.garrison_list = None
        self.garrison_npc_list = None
        self.garrison_button = None
        self.garrison_map_button = None

    def initialize_screen(self, location_card, hex_pos, hex_grid):
        self.location_card = location_card
        self.hex_pos = hex_pos
        self.hex_grid = hex_grid
        self.selected_shop_item = None
        self.selected_materials = []

        manager.clear_and_reset()

        window_rect = pygame.Rect((WINDOW_WIDTH - 1200) // 2, (WINDOW_HEIGHT - 800) // 2, 1200, 800)
        self.window = pygame_gui.elements.UIWindow(window_rect, manager, "Location")

        loc_data = location_card.get_current_data()
        loc_name = loc_data.get("Name", "Unknown Location")
        description = loc_data.get("Description", "")

        # Header with location name
        self.header_label = pygame_gui.elements.UILabel(
            pygame.Rect(10, 5, 1150, 40), loc_name, manager, container=self.window
        )

        # Description
        self.desc_text = pygame_gui.elements.UITextBox(
            f"<font color='#FFFFFF'>{description}</font>",
            pygame.Rect(10, 45, 380, 80), manager, container=self.window
        )

        # Choices panel (left side)
        self.choices_label = pygame_gui.elements.UILabel(
            pygame.Rect(10, 130, 380, 25), "Actions:", manager, container=self.window
        )

        choices = hex_grid.get_location_choices(hex_pos[0], hex_pos[1])
        self.choice_buttons = []
        y_pos = 160
        for choice in choices:
            choice_name = choice.get("name", "Unknown")
            costs_action = choice.get("costs_action", False)
            action = choice.get("action", "exit")
            btn_text = f"{choice_name} {'(Action)' if costs_action else '(Free)'}"
            btn = pygame_gui.elements.UIButton(
                pygame.Rect(10, y_pos, 380, 35), btn_text, manager, container=self.window
            )
            self.choice_buttons.append((btn, choice))
            y_pos += 40

        # Add Leave button if not in choices
        if not any(c.get("action") == "exit" for c in choices):
            leave_btn = pygame_gui.elements.UIButton(
                pygame.Rect(10, y_pos, 380, 35), "Leave (Free)", manager, container=self.window
            )
            self.choice_buttons.append((leave_btn, {"name": "Leave", "action": "exit", "costs_action": False}))

        # Check if quest panel should be shown (set before creating shop panel)
        self.quest_panel_visible = len(self.available_quests) > 0

        # Shop panel (middle) - only show if quest panel is not visible
        self.shop_label = None
        self.shop_items_list = None
        self.buy_button = None
        self.materials_label = None
        self.sell_materials_list = None
        self.shop_item_names = []

        if not self.quest_panel_visible:
            self.shop_label = pygame_gui.elements.UILabel(
                pygame.Rect(400, 130, 380, 25), "Shop:", manager, container=self.window
            )

            shop_inventory = hex_grid.get_shop_inventory(hex_pos[0], hex_pos[1])
            shop_items = []
            for item in shop_inventory:
                card = item.get("card")
                price = item.get("price", {})
                if card:
                    item_name = card.get_current_data().get("Name", "Unknown")
                    price_str = f"{price.get('amount', 0)} {price.get('type', 'metal')}"
                    shop_items.append(f"{item_name} - {price_str}")

            # Store shop item names for index lookup in handle_event
            self.shop_item_names = shop_items if shop_items else []

            self.shop_items_list = pygame_gui.elements.UISelectionList(
                pygame.Rect(400, 160, 380, 250),
                shop_items if shop_items else ["Shop is empty"],
                manager, container=self.window
            )

            self.buy_button = pygame_gui.elements.UIButton(
                pygame.Rect(400, 420, 185, 35), "Buy Item", manager, container=self.window
            )

            # Materials for payment (middle bottom)
            # Get the shop's currency type to show relevant material values
            shop_currency = loc_data.get("Shop_Currency", "metal")
            currency_to_value_field = {
                "metal": "Metal Value",
                "wood": "Wood Value",
                "raw_materials": "Raw Material Value",
                "refined_materials": "Refined Material Value"
            }
            value_field = currency_to_value_field.get(shop_currency, "Metal Value")

            self.materials_label = pygame_gui.elements.UILabel(
                pygame.Rect(400, 465, 380, 25), f"Materials for Payment ({shop_currency}):", manager, container=self.window
            )

            material_cards = [card for card in game.current_player.inventory
                            if card.card_data.get("card_type") == "Junk Card" and card.current_state == 1]

            # Build material names with their values
            material_names = []
            self.material_name_to_card = {}  # Map display name back to card for selection
            for card in material_cards:
                card_data = card.get_current_data()
                name = card_data.get("Name", "Unknown")
                value = int(card_data.get(value_field, 0))
                display_name = f"{name} ({value} {shop_currency})"
                material_names.append(display_name)
                self.material_name_to_card[display_name] = card

            self.sell_materials_list = pygame_gui.elements.UISelectionList(
                pygame.Rect(400, 495, 380, 200),
                material_names if material_names else ["No materials"],
                manager, container=self.window,
                allow_multi_select=True
            )

        # Upgrade panel (right side) - only if location can be upgraded
        self.upgrade_panel_visible = False
        if location_card.states == 2 and location_card.current_state == 1:
            upgrade_npc_type = loc_data.get("Upgrade_NPC_Type", "")
            if upgrade_npc_type:
                self.upgrade_panel_visible = True
                self.upgrade_label = pygame_gui.elements.UILabel(
                    pygame.Rect(790, 130, 380, 25), "Upgrade Location:", manager, container=self.window
                )

                upgrade_cost = loc_data.get("Upgrade_Material_Cost", "{}")
                self.upgrade_info = pygame_gui.elements.UITextBox(
                    f"<font color='#FFFFFF'>Requires {upgrade_npc_type} NPC<br>Materials: {upgrade_cost}</font>",
                    pygame.Rect(790, 160, 380, 80), manager, container=self.window
                )

                # Get allied NPCs from party
                allied_npcs = [card for card in game.current_party
                              if "Allied" in card.get_current_data().get("Allegiance (Hostile, Neutral, Allied)", "")]
                npc_names = [card.get_current_data().get("Name", "Unknown") for card in allied_npcs]

                self.npc_list = pygame_gui.elements.UISelectionList(
                    pygame.Rect(790, 250, 380, 150),
                    npc_names if npc_names else ["No allied NPCs"],
                    manager, container=self.window
                )

                self.assign_npc_button = pygame_gui.elements.UIButton(
                    pygame.Rect(790, 410, 380, 35), "Assign NPC (Upgrade)", manager, container=self.window
                )

        # Recruitable NPCs panel (right side, below upgrade or at upgrade position if no upgrade)
        self.recruit_panel_visible = False
        self.recruit_npc_list = None
        self.recruit_button = None
        self.selected_recruit_index = None

        available_npcs = hex_grid.get_available_npcs(hex_pos[0], hex_pos[1])
        if available_npcs:
            self.recruit_panel_visible = True
            recruit_y = 460 if self.upgrade_panel_visible else 130

            pygame_gui.elements.UILabel(
                pygame.Rect(790, recruit_y, 380, 25), "NPCs Available to Recruit:", manager, container=self.window
            )

            npc_names = [npc.get("name", "Unknown") for npc in available_npcs]
            self.recruit_npc_list = pygame_gui.elements.UISelectionList(
                pygame.Rect(790, recruit_y + 30, 380, 150),
                npc_names,
                manager, container=self.window
            )

            self.recruit_button = pygame_gui.elements.UIButton(
                pygame.Rect(790, recruit_y + 190, 380, 35), "Recruit to Party", manager, container=self.window
            )

        # Garrison panel (right side, for defensive locations in state 2)
        self.garrison_panel_visible = False
        self.garrison_list = None
        self.garrison_npc_list = None
        self.garrison_button = None
        self.garrison_map_button = None

        loc_data_dict = hex_grid.location_data.get(hex_pos)
        defenses = loc_data_dict.get("defenses", []) if loc_data_dict else []
        has_npc_defense = any(d.get("requires_npc") for d in defenses)
        if location_card.current_state == 2 and has_npc_defense:
            self.garrison_panel_visible = True
            garrison = loc_data_dict.get("garrison_npcs", [])
            garrison_y = 130
            # Position below upgrade/recruit panels if they exist
            if self.upgrade_panel_visible:
                garrison_y = 460
            if self.recruit_panel_visible:
                garrison_y = max(garrison_y, 460 if self.upgrade_panel_visible else 360)

            pygame_gui.elements.UILabel(
                pygame.Rect(790, garrison_y, 380, 25),
                f"Garrison ({len(garrison)}/3):", manager, container=self.window
            )

            # Current garrison members
            garrison_names = [f"{g.get('name', 'Unknown')} (HP: {g.get('hp', 0)}/{g.get('max_hp', 0)})" for g in garrison]

            # Party NPCs available to garrison
            party_npc_names = []
            self._garrison_party_npcs = []
            for card in game.current_party:
                card_data = card.get_current_data()
                allegiance = card_data.get("Allegiance (Hostile, Neutral, Allied)", "")
                if "Allied" in allegiance:
                    name = card_data.get("Name", "Unknown")
                    party_npc_names.append(f"[PARTY] {name}")
                    self._garrison_party_npcs.append(card)

            # On-map allied units available to garrison
            self._garrison_map_units = []
            for unit in hex_grid.units:
                if unit.allegiance == "Allied":
                    party_npc_names.append(f"[MAP] {unit.name}")
                    self._garrison_map_units.append(unit)

            all_items = garrison_names + (["---"] if garrison_names and party_npc_names else []) + party_npc_names
            if not all_items:
                all_items = ["No NPCs available"]

            self.garrison_npc_list = pygame_gui.elements.UISelectionList(
                pygame.Rect(790, garrison_y + 30, 380, 180),
                all_items,
                manager, container=self.window
            )

            if len(garrison) < 3 and party_npc_names:
                self.garrison_button = pygame_gui.elements.UIButton(
                    pygame.Rect(790, garrison_y + 220, 380, 35),
                    "Garrison NPC", manager, container=self.window
                )

        # Quest selection panel (shows when view_quests action is used)
        self.quest_list = None
        self.quest_details_text = None
        self.accept_quest_button = None
        self.back_to_shop_button = None

        if self.quest_panel_visible:
            # Quest panel in the middle area
            pygame_gui.elements.UILabel(
                pygame.Rect(400, 130, 380, 25), "Available Quests:", manager, container=self.window
            )

            quest_names = [q.get_current_data().get("Name", "Unknown Quest") for q in self.available_quests]
            self.quest_list = pygame_gui.elements.UISelectionList(
                pygame.Rect(400, 160, 380, 150),
                quest_names,
                manager, container=self.window
            )

            pygame_gui.elements.UILabel(
                pygame.Rect(400, 320, 380, 25), "Quest Details:", manager, container=self.window
            )

            self.quest_details_text = pygame_gui.elements.UITextBox(
                "<font color='#FFFFFF'>Select a quest to view details</font>",
                pygame.Rect(400, 350, 380, 200), manager, container=self.window
            )

            self.accept_quest_button = pygame_gui.elements.UIButton(
                pygame.Rect(400, 560, 185, 35), "Accept Quest", manager, container=self.window
            )

            self.back_to_shop_button = pygame_gui.elements.UIButton(
                pygame.Rect(595, 560, 185, 35), "Back to Shop", manager, container=self.window
            )

        # Info panel (bottom)
        self.info_text = pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select an action or shop item</font>",
            pygame.Rect(10, 700, 1150, 60), manager, container=self.window
        )

        # Close button
        self.close_button = pygame_gui.elements.UIButton(
            pygame.Rect(1050, 5, 100, 30), "Close", manager, container=self.window
        )

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            # Handle close button
            if event.ui_element == self.close_button:
                game.current_screen = "game"
                game_screen.initialize_screen()
                return

            # Handle choice buttons
            for btn, choice in self.choice_buttons:
                if event.ui_element == btn:
                    self.execute_choice(choice)
                    return

            # Handle buy button
            if event.ui_element == self.buy_button:
                self.purchase_item()
                return

            # Handle NPC assignment for upgrade
            if self.upgrade_panel_visible and event.ui_element == self.assign_npc_button:
                self.upgrade_location()
                return

            # Handle NPC recruitment
            if self.recruit_panel_visible and event.ui_element == self.recruit_button:
                self.recruit_npc()
                return

            # Handle garrison NPC button
            if self.garrison_panel_visible and self.garrison_button and event.ui_element == self.garrison_button:
                self.garrison_npc()
                return

            # Handle quest acceptance
            if self.quest_panel_visible and self.accept_quest_button and event.ui_element == self.accept_quest_button:
                self.accept_selected_quest()
                return

            # Handle back to shop button
            if self.quest_panel_visible and self.back_to_shop_button and event.ui_element == self.back_to_shop_button:
                self.available_quests = []
                self.selected_quest_index = None
                self.initialize_screen(self.location_card, self.hex_pos, self.hex_grid)
                return

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            # Handle quest selection
            if self.quest_panel_visible and self.quest_list and event.ui_element == self.quest_list:
                selection = self.quest_list.get_single_selection()
                if selection:
                    for i, quest in enumerate(self.available_quests):
                        if quest.get_current_data().get("Name") == selection:
                            self.selected_quest_index = i
                            # Show quest details
                            quest_data = quest.get_current_data()
                            info = f"<b>{quest_data.get('Name', 'Unknown')}</b><br><br>"
                            info += f"<i>{quest_data.get('Description', '')}</i><br><br>"
                            template = quest_data.get('Template_Text', '')
                            info += f"{template}<br><br>"
                            # Show rewards info
                            rewards_json = quest_data.get('Rewards', '{}')
                            try:
                                import json
                                rewards = json.loads(rewards_json) if isinstance(rewards_json, str) else rewards_json
                                if rewards.get('cards'):
                                    info += f"<b>Rewards:</b> {len(rewards['cards'])} item(s)"
                            except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
                                pass  # Invalid rewards format, skip display
                            if self.quest_details_text:
                                self.quest_details_text.set_text(f"<font color='#FFFFFF'>{info}</font>")
                            break
            # Handle recruit NPC selection
            if self.recruit_panel_visible and self.recruit_npc_list and event.ui_element == self.recruit_npc_list:
                available_npcs = self.hex_grid.get_available_npcs(self.hex_pos[0], self.hex_pos[1])
                selection = self.recruit_npc_list.get_single_selection()
                if selection:
                    for i, npc in enumerate(available_npcs):
                        if npc.get("name") == selection:
                            self.selected_recruit_index = i
                            # Show NPC stats
                            info = f"<b>{npc.get('name', 'Unknown')}</b><br>"
                            info += f"HP: {npc.get('hp', 0)}/{npc.get('max_hp', 0)}<br>"
                            info += f"Movement: {npc.get('movement', 0)}<br>"
                            info += f"Melee Damage: {npc.get('melee_damage', 0)}<br>"
                            if npc.get('projectile_damage', 0) > 0:
                                info += f"Projectile: {npc.get('projectile_damage', 0)} (Range: {npc.get('projectile_range', 0)})<br>"
                            info += f"Allegiance: {npc.get('allegiance', 'Unknown')}"
                            self.info_text.set_text(f"<font color='#FFFFFF'>{info}</font>")
                            break
            if self.shop_items_list and event.ui_element == self.shop_items_list:
                selection = self.shop_items_list.get_single_selection()
                if selection and selection != "Shop is empty" and selection in self.shop_item_names:
                    idx = self.shop_item_names.index(selection)
                    self.selected_shop_item = idx
                    shop_inv = self.hex_grid.get_shop_inventory(self.hex_pos[0], self.hex_pos[1])
                    if idx < len(shop_inv):
                        item = shop_inv[idx]
                        card = item.get("card")
                        if card:
                            item_data = card.get_current_data()
                            info = "<br>".join(f"{k}: {v}" for k, v in item_data.items() if v and k != "id")
                            self.info_text.set_text(f"<font color='#FFFFFF'>{info}</font>")

    def execute_choice(self, choice):
        action = choice.get("action", "exit")
        costs_action = choice.get("costs_action", False)
        params = choice.get("params", {})

        if costs_action and game.current_player.action_used:
            self.info_text.set_text("<font color='#FF0000'>Action already used this turn!</font>")
            return

        if action == "exit":
            game.current_screen = "game"
            game_screen.initialize_screen()
        elif action == "draw_card":
            outcome_card, msg = self.hex_grid.trigger_location_outcome(self.hex_pos[0], self.hex_pos[1], game_screen.card_manager)
            if outcome_card:
                party_msg = add_card_to_player(outcome_card)
                if party_msg:
                    game_screen.add_to_log(party_msg)
            game_screen.add_to_log(msg)
            if costs_action:
                game.current_player.action_used = True
            self.hex_grid.mark_location_visited(self.hex_pos[0], self.hex_pos[1])
            self.info_text.set_text(f"<font color='#FFFFFF'>{msg}</font>")
        elif action == "heal":
            hp_amount = int(params.get("amount", 10))
            old_hp = game.current_player.hp
            game.current_player.hp = min(game.current_player.max_hp, game.current_player.hp + hp_amount)
            msg = f"Healed for {game.current_player.hp - old_hp} HP"
            game_screen.add_to_log(msg)
            if costs_action:
                game.current_player.action_used = True
            self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
        elif action == "shop":
            self.info_text.set_text("<font color='#FFFFFF'>Select items from the shop above</font>")
        elif action == "trade":
            self.info_text.set_text("<font color='#FFFFFF'>Select materials to trade</font>")
        elif action == "accept_quest":
            # Accept a quest from this location
            deck_file = params.get("deck", "decks/test_quest_deck.json")

            # Check if player can accept more quests
            if not game.current_quest_manager.can_accept_quest():
                self.info_text.set_text("<font color='#FF0000'>Quest log full! Complete or abandon a quest first.</font>")
                return

            # Draw a quest card from the specified deck
            quest_card = game.card_manager.draw_from_deck(deck_file)
            if not quest_card:
                self.info_text.set_text("<font color='#FF0000'>No quests available at this location.</font>")
                return

            # Check if player already has this quest active
            quest_name = quest_card.get_current_data().get("Name", "Unknown")
            for active in game.current_quest_manager.active_quests:
                if active.quest_card.get_current_data().get("Name") == quest_name:
                    self.info_text.set_text(f"<font color='#FF0000'>Already have quest: {quest_name}</font>")
                    return

            # Activate the quest
            success, msg = game.current_quest_manager.activate_quest(quest_card, self.hex_grid, game.current_player)

            if success:
                if costs_action:
                    game.current_player.action_used = True
                game_screen.add_to_log(f"New quest accepted: {quest_name}")
                self.info_text.set_text(f"<font color='#00FF00'>Quest accepted: {quest_name}</font>")
                # Update quest button count
                game_screen.update_quest_button()
            else:
                self.info_text.set_text(f"<font color='#FF0000'>{msg}</font>")
        elif action == "view_quests":
            # Show available quests from the deck
            deck_file = params.get("deck", "decks/test_quest_deck.json")
            self.quest_deck_file = deck_file
            self.load_available_quests(deck_file)
        elif action == "repair_location":
            # Repair an NPC spawn location (church) using a hammer and materials
            heal_amount = int(params.get("amount", 20))
            can_rebuild = params.get("can_rebuild", True)
            required_materials = params.get("materials", {})  # e.g., {"Metal": 2, "Wood": 3}

            # Check for building tool (hammer)
            if not game.current_player.has_building_tool():
                self.info_text.set_text("<font color='#FF0000'>You need a hammer equipped to repair!</font>")
                return

            # Calculate player's available materials
            totals = {"Metal": 0, "Wood": 0, "Raw": 0, "Refined": 0}
            for card in game.current_player.inventory:
                card_data = card.get_current_data()
                totals["Metal"] += int(card_data.get("Metal Value", 0) or 0)
                totals["Wood"] += int(card_data.get("Wood Value", 0) or 0)
                totals["Raw"] += int(card_data.get("Raw Material Value", 0) or 0)
                totals["Refined"] += int(card_data.get("Refined Material Value", 0) or 0)

            # Check material requirements
            missing = []
            for material, required in required_materials.items():
                required = int(required or 0)
                if required <= 0:
                    continue
                available = totals.get(material, 0)
                if available < required:
                    missing.append(f"{material}: need {required}, have {available}")

            if missing:
                self.info_text.set_text(f"<font color='#FF0000'>Missing materials: {', '.join(missing)}</font>")
                return

            # Consume materials from inventory (consume cards until requirements met)
            materials_to_consume = dict(required_materials)
            cards_to_remove = []
            for card in game.current_player.inventory[:]:  # Copy list to avoid modification during iteration
                if all(v <= 0 for v in materials_to_consume.values()):
                    break
                card_data = card.get_current_data()
                card_contributes = False
                for mat_type in ["Metal", "Wood", "Raw", "Refined"]:
                    if materials_to_consume.get(mat_type, 0) > 0:
                        card_value = int(card_data.get(f"{mat_type} Value" if mat_type in ["Metal", "Wood"] else f"{mat_type} Material Value", 0) or 0)
                        if card_value > 0:
                            card_contributes = True
                            materials_to_consume[mat_type] = max(0, materials_to_consume.get(mat_type, 0) - card_value)
                if card_contributes:
                    cards_to_remove.append(card)

            # Remove consumed cards
            for card in cards_to_remove:
                if card in game.current_player.inventory:
                    game.current_player.inventory.remove(card)

            # Perform the repair
            success, healed, rebuilt, msg = self.hex_grid.repair_npc_location(
                self.hex_pos[0], self.hex_pos[1], heal_amount, can_rebuild
            )

            if success:
                game_screen.add_to_log(msg)
                if costs_action:
                    game.current_player.action_used = True
                color = "#00FF00"
                # Refresh location card display
                self.location_card = self.hex_grid.get_location_card(self.hex_pos[0], self.hex_pos[1])
                self.initialize_screen(self.location_card, self.hex_pos, self.hex_grid)
            else:
                color = "#FF0000"

            self.info_text.set_text(f"<font color='{color}'>{msg}</font>")

    def load_available_quests(self, deck_file):
        """Load all quests from a deck and display them for selection."""
        import json
        import os

        self.available_quests = []
        self.selected_quest_index = None

        try:
            with open(deck_file, 'r') as f:
                deck_data = json.load(f)
            quest_ids = deck_data.get("cards", [])

            for quest_id in quest_ids:
                card_file = os.path.join("cards", f"{quest_id}.json")
                try:
                    with open(card_file, 'r') as f:
                        card_data = json.load(f)
                    card_data["id"] = quest_id
                    quest_card = InventoryCard(card_data)
                    self.available_quests.append(quest_card)
                except Exception as e:
                    print(f"Error loading quest {quest_id}: {e}")
        except Exception as e:
            print(f"Error loading quest deck {deck_file}: {e}")

        # Refresh the screen to show quest panel
        self.initialize_screen(self.location_card, self.hex_pos, self.hex_grid)

    def accept_selected_quest(self):
        """Accept the currently selected quest."""
        if self.selected_quest_index is None:
            self.info_text.set_text("<font color='#FF0000'>Select a quest first!</font>")
            return

        if not game.current_quest_manager.can_accept_quest():
            self.info_text.set_text("<font color='#FF0000'>Quest log full! Complete or abandon a quest first.</font>")
            return

        quest_card = self.available_quests[self.selected_quest_index]
        quest_name = quest_card.get_current_data().get("Name", "Unknown")

        # Check if player already has this quest active
        for active in game.current_quest_manager.active_quests:
            if active.quest_card.get_current_data().get("Name") == quest_name:
                self.info_text.set_text(f"<font color='#FF0000'>Already have quest: {quest_name}</font>")
                return

        # Activate the quest
        success, msg = game.current_quest_manager.activate_quest(quest_card, self.hex_grid, game.current_player)

        if success:
            game_screen.add_to_log(f"New quest accepted: {quest_name}")
            self.info_text.set_text(f"<font color='#00FF00'>Quest accepted: {quest_name}</font>")
            game_screen.update_quest_button()
            # Clear the quest panel
            self.available_quests = []
            self.selected_quest_index = None
            self.initialize_screen(self.location_card, self.hex_pos, self.hex_grid)
        else:
            self.info_text.set_text(f"<font color='#FF0000'>{msg}</font>")

    def purchase_item(self):
        if self.selected_shop_item is None:
            self.info_text.set_text("<font color='#FF0000'>Select a shop item first!</font>")
            return

        # Get selected materials using the display name to card mapping
        selected_material_names = self.sell_materials_list.get_multi_selection() if self.sell_materials_list else []
        material_cards = [self.material_name_to_card[name] for name in selected_material_names
                         if name in self.material_name_to_card]

        purchased_card, msg = self.hex_grid.purchase_from_shop(
            self.hex_pos[0], self.hex_pos[1], self.selected_shop_item, game.current_player.inventory, material_cards
        )

        if purchased_card:
            # Remove used materials
            for mat in material_cards:
                if mat in game.current_player.inventory:
                    game.current_player.inventory.remove(mat)
            # Add purchased card
            party_msg = add_card_to_player(purchased_card)
            if party_msg:
                game_screen.add_to_log(party_msg)
            game_screen.add_to_log(msg)
            self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
            # Refresh the screen
            self.initialize_screen(self.location_card, self.hex_pos, self.hex_grid)
        else:
            self.info_text.set_text(f"<font color='#FF0000'>{msg}</font>")

    def upgrade_location(self):
        if not self.npc_list:
            return

        selected_npc_name = self.npc_list.get_single_selection()
        if not selected_npc_name or selected_npc_name == "No allied NPCs":
            self.info_text.set_text("<font color='#FF0000'>Select an NPC to assign!</font>")
            return

        # Find the NPC card in party
        npc_card = None
        for card in game.current_party:
            if card.get_current_data().get("Name") == selected_npc_name:
                npc_card = card
                break

        if not npc_card:
            self.info_text.set_text("<font color='#FF0000'>NPC not found!</font>")
            return

        success, msg = self.hex_grid.upgrade_location(self.hex_pos[0], self.hex_pos[1], npc_card)
        if success:
            # Remove NPC from party (they're now at the location)
            game.current_party.remove(npc_card)
            game_screen.add_to_log(msg)
            self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
            # Refresh with upgraded location
            new_card = self.hex_grid.get_location_card(self.hex_pos[0], self.hex_pos[1])
            self.initialize_screen(new_card, self.hex_pos, self.hex_grid)
        else:
            self.info_text.set_text(f"<font color='#FF0000'>{msg}</font>")

    def garrison_npc(self):
        """Garrison a party or map NPC at this defensive location."""
        if not self.garrison_npc_list:
            return

        selection = self.garrison_npc_list.get_single_selection()
        if not selection or selection in ("No NPCs available", "---"):
            self.info_text.set_text("<font color='#FF0000'>Select an NPC to garrison!</font>")
            return

        if selection.startswith("[PARTY] "):
            npc_name = selection[8:]  # Strip "[PARTY] "
            npc_card = None
            for card in self._garrison_party_npcs:
                if card.get_current_data().get("Name") == npc_name:
                    npc_card = card
                    break
            if not npc_card:
                self.info_text.set_text("<font color='#FF0000'>NPC not found in party!</font>")
                return
            # Create garrison data from party card
            card_data = npc_card.get_current_data()
            garrison_entry = {
                "id": npc_card.card_data.get("id", ""),
                "name": card_data.get("Name", "Unknown"),
                "hp": int(card_data.get("Health", 10)),
                "max_hp": int(card_data.get("Health", 10)),
                "melee_damage": int(card_data.get("Melee Damage", 0)),
                "projectile_damage": int(card_data.get("Projectile Damage", 0)),
                "allegiance": card_data.get("Allegiance (Hostile, Neutral, Allied)", "Allied")
            }
            success, msg = self.hex_grid.garrison_npc_to_location(garrison_entry, self.hex_pos)
            if success:
                game.current_party.remove(npc_card)
                game_screen.add_to_log(msg)
                self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
                new_card = self.hex_grid.get_location_card(self.hex_pos[0], self.hex_pos[1])
                self.initialize_screen(new_card, self.hex_pos, self.hex_grid)
            else:
                self.info_text.set_text(f"<font color='#FF0000'>{msg}</font>")

        elif selection.startswith("[MAP] "):
            unit_name = selection[6:]  # Strip "[MAP] "
            target_unit = None
            for unit in self._garrison_map_units:
                if unit.name == unit_name:
                    target_unit = unit
                    break
            if not target_unit:
                self.info_text.set_text("<font color='#FF0000'>Unit not found on map!</font>")
                return
            # Set garrison target so unit pathfinds there on its turn
            target_unit.garrison_target_location = self.hex_pos
            self.info_text.set_text(f"<font color='#00FF00'>{unit_name} will move to garrison this location</font>")
            game_screen.add_to_log(f"{unit_name} ordered to garrison location")

    def recruit_npc(self):
        """Recruit an NPC from the location to the player's party."""
        if self.selected_recruit_index is None:
            self.info_text.set_text("<font color='#FF0000'>Select an NPC to recruit!</font>")
            return

        # Check party size limit
        if len(game.current_party) >= 5:
            self.info_text.set_text("<font color='#FF0000'>Party is full (max 5 members)!</font>")
            return

        # Get NPC data and remove from location
        npc_data, msg = self.hex_grid.recruit_npc_from_location(
            self.hex_pos[0], self.hex_pos[1], self.selected_recruit_index
        )

        if npc_data:
            # Create an InventoryCard for the NPC
            card_data = {
                "id": npc_data.get("id", "recruited_npc"),
                "card_type": npc_data.get("card_type", "NPC Card"),
                "states": 1,
                "data": {
                    "Name": npc_data.get("name", "Unknown"),
                    "Health": str(npc_data.get("max_hp", 10)),
                    "Movement": str(npc_data.get("movement", 3)),
                    "Melee Damage": str(npc_data.get("melee_damage", 5)),
                    "Projectile Damage": str(npc_data.get("projectile_damage", 0)),
                    "Projectile Range": str(npc_data.get("projectile_range", 0)),
                    "Allegiance (Hostile, Neutral, Allied)": npc_data.get("allegiance", "Allied")
                }
            }
            from inventory_card import InventoryCard
            npc_card = InventoryCard(card_data)
            game.current_party.append(npc_card)

            game_screen.add_to_log(msg)
            self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
            self.selected_recruit_index = None

            # Refresh the screen to update available NPCs list
            self.initialize_screen(self.location_card, self.hex_pos, self.hex_grid)
        else:
            self.info_text.set_text(f"<font color='#FF0000'>{msg}</font>")

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# RecruitmentScreen class for recruiting neutral NPCs
class RecruitmentScreen:
    def __init__(self):
        self.window = None
        self.target_unit = None
        self.junk_list = None
        self.selected_junk = []  # List of selected junk cards
        self.junk_name_to_card = {}  # Maps list names to cards
        self.info_text = None
        self.recruit_button = None
        self.cancel_button = None
        self.cost_label = None
        self.offered_label = None

    def initialize_screen(self, target_unit):
        """Initialize the recruitment screen for a specific neutral NPC."""
        self.target_unit = target_unit
        self.selected_junk = []
        self.junk_name_to_card = {}

        manager.clear_and_reset()

        window_rect = pygame.Rect((WINDOW_WIDTH - 800) // 2, (WINDOW_HEIGHT - 600) // 2, 800, 600)
        self.window = pygame_gui.elements.UIWindow(window_rect, manager, "Recruit NPC")

        # NPC info header
        npc_name = target_unit.name if target_unit else "Unknown"
        pygame_gui.elements.UILabel(
            pygame.Rect(10, 5, 780, 30), f"Recruit: {npc_name}", manager, container=self.window
        )

        # Calculate recruitment cost
        recruitment_cost = self._calculate_recruitment_cost(target_unit)

        # NPC stats panel (left side)
        stats_text = self._get_npc_stats_text(target_unit)
        self.npc_info_text = pygame_gui.elements.UITextBox(
            f"<font color='#FFFFFF'>{stats_text}</font>",
            pygame.Rect(10, 40, 300, 200), manager, container=self.window
        )

        # Cost label
        self.cost_label = pygame_gui.elements.UILabel(
            pygame.Rect(10, 250, 300, 30), f"Recruitment Cost: {recruitment_cost} material value",
            manager, container=self.window
        )

        # Junk selection (right side)
        pygame_gui.elements.UILabel(
            pygame.Rect(320, 40, 460, 25), "Select junk to offer (multi-select):",
            manager, container=self.window
        )

        # Build junk list with material values
        junk_items = []
        for card in game.current_player.inventory:
            if card.card_data.get("card_type") == "Junk Card":
                card_data = card.get_current_data()
                name = card_data.get("Name", "Unnamed")
                value = self._get_material_value(card)
                display_name = f"{name} (Value: {value})"
                junk_items.append(display_name)
                self.junk_name_to_card[display_name] = card

        self.junk_list = pygame_gui.elements.UISelectionList(
            pygame.Rect(320, 70, 460, 300),
            junk_items if junk_items else ["No junk items available"],
            manager, container=self.window,
            allow_multi_select=True
        )

        # Offered value label
        self.offered_label = pygame_gui.elements.UILabel(
            pygame.Rect(320, 380, 460, 30), "Total offered: 0 / " + str(recruitment_cost),
            manager, container=self.window
        )

        # Info text at bottom
        self.info_text = pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select junk items with enough total value to meet the recruitment cost.</font>",
            pygame.Rect(10, 420, 780, 80), manager, container=self.window
        )

        # Buttons
        self.recruit_button = pygame_gui.elements.UIButton(
            pygame.Rect(200, 510, 180, 40), "Recruit", manager, container=self.window
        )
        self.cancel_button = pygame_gui.elements.UIButton(
            pygame.Rect(420, 510, 180, 40), "Cancel", manager, container=self.window
        )

    def _calculate_recruitment_cost(self, unit):
        """Calculate recruitment cost based on NPC stats: HP/10 + melee + ranged + movement + 5"""
        if not unit:
            return 10
        hp_component = unit.max_hp // 10
        melee = unit.melee_damage if hasattr(unit, 'melee_damage') else 0
        ranged = unit.projectile_damage if hasattr(unit, 'projectile_damage') else 0
        movement = unit.movement if hasattr(unit, 'movement') else 3
        return hp_component + melee + ranged + movement + 5

    def _get_material_value(self, card):
        """Get total material value of a junk card."""
        card_data = card.get_current_data()
        total = 0
        value_fields = ["Raw Material Value", "Refined Material Value", "Metal Value", "Wood Value"]
        for field in value_fields:
            try:
                total += int(card_data.get(field, 0) or 0)
            except (ValueError, TypeError):
                pass
        return max(1, total)  # Minimum value of 1

    def _get_npc_stats_text(self, unit):
        """Get formatted stats text for the NPC."""
        if not unit:
            return "No NPC selected"
        lines = [
            f"<b>{unit.name}</b>",
            f"HP: {unit.hp}/{unit.max_hp}",
            f"Movement: {unit.movement}",
            f"Melee Damage: {unit.melee_damage}",
        ]
        if unit.projectile_damage > 0:
            lines.append(f"Projectile Damage: {unit.projectile_damage}")
            lines.append(f"Projectile Range: {unit.projectile_range}")
        lines.append(f"Allegiance: {unit.allegiance}")
        return "<br>".join(lines)

    def _get_total_offered_value(self):
        """Calculate total material value of selected junk."""
        total = 0
        for card in self.selected_junk:
            total += self._get_material_value(card)
        return total

    def _update_offered_label(self):
        """Update the offered value label."""
        total = self._get_total_offered_value()
        cost = self._calculate_recruitment_cost(self.target_unit)
        color = "#00FF00" if total >= cost else "#FFFFFF"
        self.offered_label.set_text(f"Total offered: {total} / {cost}")

    def handle_event(self, event):
        # Handle window X button close
        if event.type == pygame_gui.UI_WINDOW_CLOSE:
            if event.ui_element == self.window:
                game.current_screen = "game"
                game_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.cancel_button:
                game.current_screen = "game"
                game_screen.initialize_screen()
            elif event.ui_element == self.recruit_button:
                self._attempt_recruitment()

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.junk_list:
                # Add to selected
                selected_name = event.text
                if selected_name in self.junk_name_to_card:
                    card = self.junk_name_to_card[selected_name]
                    if card not in self.selected_junk:
                        self.selected_junk.append(card)
                        self._update_offered_label()

        elif event.type == pygame_gui.UI_SELECTION_LIST_DROPPED_SELECTION:
            if event.ui_element == self.junk_list:
                # Remove from selected
                selected_name = event.text
                if selected_name in self.junk_name_to_card:
                    card = self.junk_name_to_card[selected_name]
                    if card in self.selected_junk:
                        self.selected_junk.remove(card)
                        self._update_offered_label()

    def _attempt_recruitment(self):
        """Attempt to recruit the NPC with selected junk."""
        if not self.target_unit:
            self.info_text.set_text("<font color='#FF0000'>No NPC to recruit!</font>")
            return

        cost = self._calculate_recruitment_cost(self.target_unit)
        offered = self._get_total_offered_value()

        if offered < cost:
            self.info_text.set_text(f"<font color='#FF0000'>Not enough value! Need {cost}, offered {offered}</font>")
            return

        # Check party limit (max 5)
        if len(game.current_party) >= 5:
            self.info_text.set_text("<font color='#FF0000'>Party is full! (Max 5 members)</font>")
            return

        # Success! Remove junk from inventory
        for card in self.selected_junk:
            if card in game.current_player.inventory:
                game.current_player.inventory.remove(card)

        # Change NPC allegiance to Allied
        self.target_unit.allegiance = "Allied"

        # Create party card for the NPC
        npc_card_data = {
            "id": self.target_unit.card_id,
            "card_type": "NPC Card",
            "data": {
                "Name": self.target_unit.name,
                "Health": str(self.target_unit.max_hp),
                "Movement": str(self.target_unit.movement),
                "Melee Damage": str(self.target_unit.melee_damage),
                "Projectile Damage": str(self.target_unit.projectile_damage),
                "Projectile Range": str(self.target_unit.projectile_range),
                "Allegiance (Hostile, Neutral, Allied)": "Allied"
            }
        }
        npc_card = InventoryCard(npc_card_data)
        game.current_party.append(npc_card)

        # Log the recruitment
        game_screen.add_to_log(f"{self.target_unit.name} joined your party!")

        # Return to game
        game.current_screen = "game"
        game_screen.initialize_screen()

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# PartyScreen class for viewing and managing party members (allied NPCs)
class PartyScreen:
    def __init__(self):
        self.window = None
        self.party_list = None
        self.info_text = None
        self.close_button = None
        self.selected_member = None
        self.dismiss_button = None
        self.deploy_button = None
        self.recall_button = None

    def initialize_screen(self):
        manager.clear_and_reset()
        self.selected_member = None

        window_rect = pygame.Rect((WINDOW_WIDTH - 900) // 2, (WINDOW_HEIGHT - 600) // 2, 900, 600)
        self.window = pygame_gui.elements.UIWindow(window_rect, manager, "Party")

        # Header
        pygame_gui.elements.UILabel(
            pygame.Rect(10, 5, 880, 30), "Your Party Members", manager, container=self.window
        )

        # Party members list (left side)
        pygame_gui.elements.UILabel(
            pygame.Rect(10, 40, 300, 25), "Party Members:", manager, container=self.window
        )

        party_names = []
        for card in game.current_party:
            card_data = card.get_current_data()
            name = card_data.get("Name", "Unknown")
            # Check if deployed on map
            deployed = any(u.card_id == card.card_data.get("id") for u in game_screen.hex_grid.units if u.allegiance == "Allied")
            status = " [Deployed]" if deployed else ""
            party_names.append(f"{name}{status}")

        self.party_list = pygame_gui.elements.UISelectionList(
            pygame.Rect(10, 70, 300, 400),
            party_names if party_names else ["No party members"],
            manager, container=self.window
        )
        self.party_member_names = party_names if party_names else []

        # Info panel (right side)
        pygame_gui.elements.UILabel(
            pygame.Rect(320, 40, 560, 25), "Member Details:", manager, container=self.window
        )

        self.info_text = pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select a party member to view details</font>",
            pygame.Rect(320, 70, 560, 350), manager, container=self.window
        )

        # Action buttons
        self.deploy_button = pygame_gui.elements.UIButton(
            pygame.Rect(320, 430, 170, 35), "Deploy to Map", manager, container=self.window
        )

        self.recall_button = pygame_gui.elements.UIButton(
            pygame.Rect(500, 430, 170, 35), "Recall to Party", manager, container=self.window
        )

        self.dismiss_button = pygame_gui.elements.UIButton(
            pygame.Rect(320, 475, 350, 35), "Dismiss from Party", manager, container=self.window
        )

        # Close button
        self.close_button = pygame_gui.elements.UIButton(
            pygame.Rect(780, 5, 100, 30), "Close", manager, container=self.window
        )

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                game.current_screen = "game"
                game_screen.initialize_screen()
                return

            if event.ui_element == self.deploy_button:
                self.deploy_member()
                return

            if event.ui_element == self.recall_button:
                self.recall_member()
                return

            if event.ui_element == self.dismiss_button:
                self.dismiss_member()
                return

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.party_list:
                selection = self.party_list.get_single_selection()
                if selection and selection != "No party members" and selection in self.party_member_names:
                    idx = self.party_member_names.index(selection)
                    if idx < len(game.current_party):
                        self.selected_member = idx
                        card = game.current_party[idx]
                        card_data = card.get_current_data()

                        # Build info display
                        info_lines = []
                        info_lines.append(f"<b>{card_data.get('Name', 'Unknown')}</b>")
                        info_lines.append(f"")
                        info_lines.append(f"Health: {card_data.get('Health', '?')}")
                        info_lines.append(f"Movement: {card_data.get('Movement', '?')}")
                        info_lines.append(f"Melee Damage: {card_data.get('Melee Damage', '0')}")
                        if card_data.get('Projectile Damage'):
                            info_lines.append(f"Projectile Damage: {card_data.get('Projectile Damage')}")
                            info_lines.append(f"Projectile Range: {card_data.get('Projectile Range', '0')}")
                        if card_data.get('Special Skill'):
                            info_lines.append(f"Special Skill: {card_data.get('Special Skill')}")
                        if card_data.get('Description'):
                            info_lines.append(f"")
                            info_lines.append(f"{card_data.get('Description')}")

                        self.info_text.set_text(f"<font color='#FFFFFF'>{'<br>'.join(info_lines)}</font>")

    def deploy_member(self):
        if self.selected_member is None:
            self.info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = game.current_party[self.selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        # Check if already deployed
        already_deployed = any(u.card_id == card.card_data.get("id") for u in game_screen.hex_grid.units if u.allegiance == "Allied")
        if already_deployed:
            self.info_text.set_text(f"<font color='#FF0000'>{name} is already deployed!</font>")
            return

        # Find a spot near the player to deploy
        player_pos = game.current_player.position
        neighbors = game_screen.hex_grid.get_neighbors(*player_pos)
        deploy_pos = None
        for n in neighbors:
            row, col = n
            if 0 <= row < game_screen.hex_grid.rows and 0 <= col < game_screen.hex_grid.cols:
                cell = game_screen.hex_grid.grid[row][col]
                if cell["unit"] is None and cell.get("accessible", True):
                    deploy_pos = n
                    break

        if not deploy_pos:
            self.info_text.set_text(f"<font color='#FF0000'>No space near player to deploy {name}!</font>")
            return

        # Create unit from card and place on map
        from unit import Unit
        unit_data = {
            "id": card.card_data.get("id"),
            "card_type": "NPC Card",
            "states": card.states,
            "data": card_data
        }
        unit = Unit(unit_data)
        unit.allegiance = "Allied"  # Ensure allied
        game_screen.hex_grid.place_unit(unit, deploy_pos[0], deploy_pos[1])

        game_screen.add_to_log(f"{name} deployed to the battlefield!")
        self.info_text.set_text(f"<font color='#00FF00'>{name} deployed!</font>")
        self.initialize_screen()  # Refresh to show [Deployed] status

    def recall_member(self):
        """Recall a deployed NPC from the map back to the party (stays in party). Must be adjacent to player."""
        if self.selected_member is None:
            self.info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = game.current_party[self.selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        # Check if deployed on map
        deployed_unit = None
        for unit in game_screen.hex_grid.units:
            if unit.card_id == card.card_data.get("id") and unit.allegiance == "Allied":
                deployed_unit = unit
                break

        if not deployed_unit:
            self.info_text.set_text(f"<font color='#FF0000'>{name} is not deployed!</font>")
            return

        # Check if adjacent to player
        player_pos = game.current_player.position
        unit_pos = deployed_unit.position
        distance = game_screen.hex_grid.hex_distance(player_pos, unit_pos)
        if distance > 1:
            self.info_text.set_text(f"<font color='#FF0000'>{name} must be adjacent to recall!</font>")
            return

        # Remove from map but keep in party
        game_screen.hex_grid.grid[deployed_unit.position[0]][deployed_unit.position[1]]["unit"] = None
        game_screen.hex_grid.units.remove(deployed_unit)

        game_screen.add_to_log(f"{name} recalled to party.")
        self.info_text.set_text(f"<font color='#00FF00'>{name} recalled!</font>")
        self.initialize_screen()  # Refresh to update [Deployed] status

    def dismiss_member(self):
        if self.selected_member is None:
            self.info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = game.current_party[self.selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        # Remove from map if deployed
        for unit in game_screen.hex_grid.units[:]:
            if unit.card_id == card.card_data.get("id") and unit.allegiance == "Allied":
                game_screen.hex_grid.grid[unit.position[0]][unit.position[1]]["unit"] = None
                game_screen.hex_grid.units.remove(unit)
                break

        # Remove from party
        game.current_party.remove(card)
        game_screen.add_to_log(f"{name} dismissed from party.")
        self.selected_member = None
        self.initialize_screen()  # Refresh

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# QuestScreen class for viewing and managing quests
class QuestScreen:
    def __init__(self):
        self.window = None
        self.tab_buttons = []
        self.quest_list = None
        self.quest_details = None
        self.abandon_button = None
        self.close_button = None
        self.current_tab = "active"  # "active", "completed", "failed"
        self.selected_quest = None
        self.quest_names = []

    def initialize_screen(self):
        manager.clear_and_reset()
        self.selected_quest = None

        window_rect = pygame.Rect((WINDOW_WIDTH - 1000) // 2, (WINDOW_HEIGHT - 700) // 2, 1000, 700)
        self.window = pygame_gui.elements.UIWindow(window_rect, manager, "Quest Journal")

        # Tab buttons
        tab_y = 5
        tab_width = 150
        self.tab_buttons = []

        active_count = len(game.current_quest_manager.active_quests)
        completed_count = len(game.current_quest_manager.completed_quests)
        failed_count = len(game.current_quest_manager.failed_quests)

        active_btn = pygame_gui.elements.UIButton(
            pygame.Rect(10, tab_y, tab_width, 30),
            f"Active ({active_count})",
            manager, container=self.window
        )
        self.tab_buttons.append(("active", active_btn))

        completed_btn = pygame_gui.elements.UIButton(
            pygame.Rect(170, tab_y, tab_width, 30),
            f"Completed ({completed_count})",
            manager, container=self.window
        )
        self.tab_buttons.append(("completed", completed_btn))

        failed_btn = pygame_gui.elements.UIButton(
            pygame.Rect(330, tab_y, tab_width, 30),
            f"Failed ({failed_count})",
            manager, container=self.window
        )
        self.tab_buttons.append(("failed", failed_btn))

        # Quest list (left panel)
        pygame_gui.elements.UILabel(
            pygame.Rect(10, 45, 350, 25), "Quests:", manager, container=self.window
        )

        quest_names = self._get_quest_names_for_tab()
        self.quest_names = quest_names
        self.quest_list = pygame_gui.elements.UISelectionList(
            pygame.Rect(10, 75, 350, 500),
            quest_names if quest_names else ["No quests"],
            manager, container=self.window
        )

        # Quest details (right panel)
        pygame_gui.elements.UILabel(
            pygame.Rect(370, 45, 600, 25), "Quest Details:", manager, container=self.window
        )

        self.quest_details = pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select a quest to view details</font>",
            pygame.Rect(370, 75, 600, 500), manager, container=self.window
        )

        # Abandon button (only for active tab)
        if self.current_tab == "active":
            self.abandon_button = pygame_gui.elements.UIButton(
                pygame.Rect(370, 585, 150, 35), "Abandon Quest", manager, container=self.window
            )
        else:
            self.abandon_button = None

        # Close button
        self.close_button = pygame_gui.elements.UIButton(
            pygame.Rect(870, 5, 100, 30), "Close", manager, container=self.window
        )

    def _get_quest_names_for_tab(self):
        """Get quest names for the current tab."""
        if self.current_tab == "active":
            return [q.get_display_name() for q in game.current_quest_manager.active_quests]
        elif self.current_tab == "completed":
            return [q.get_display_name() for q in game.current_quest_manager.completed_quests]
        elif self.current_tab == "failed":
            return [q.get_display_name() for q in game.current_quest_manager.failed_quests]
        return []

    def _get_quests_for_tab(self):
        """Get quest list for the current tab."""
        if self.current_tab == "active":
            return game.current_quest_manager.active_quests
        elif self.current_tab == "completed":
            return game.current_quest_manager.completed_quests
        elif self.current_tab == "failed":
            return game.current_quest_manager.failed_quests
        return []

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                game.current_screen = "game"
                game_screen.initialize_screen()
                return

            # Tab buttons
            for tab_name, btn in self.tab_buttons:
                if event.ui_element == btn:
                    self.current_tab = tab_name
                    self.selected_quest = None
                    self.initialize_screen()
                    return

            # Abandon button
            if self.abandon_button and event.ui_element == self.abandon_button:
                if self.selected_quest:
                    success, msg = game.current_quest_manager.abandon_quest(self.selected_quest)
                    game_screen.add_to_log(msg)
                    self.selected_quest = None
                    self.initialize_screen()
                return

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.quest_list:
                selection = self.quest_list.get_single_selection()
                if selection and selection != "No quests" and selection in self.quest_names:
                    idx = self.quest_names.index(selection)
                    quests = self._get_quests_for_tab()
                    if idx < len(quests):
                        self.selected_quest = quests[idx]
                        self._update_quest_details()

    def _update_quest_details(self):
        """Update the quest details panel."""
        if not self.selected_quest:
            self.quest_details.set_text("<font color='#FFFFFF'>Select a quest to view details</font>")
            return

        quest = self.selected_quest
        lines = []

        # Quest name
        lines.append(f"<b>{quest.get_display_name()}</b>")
        lines.append("")

        # Status
        if quest.is_complete:
            lines.append("<font color='#00FF00'>Status: COMPLETED</font>")
        elif quest.is_failed:
            lines.append("<font color='#FF0000'>Status: FAILED</font>")
        else:
            lines.append("<font color='#FFFF00'>Status: IN PROGRESS</font>")
        lines.append("")

        # Description
        lines.append("<b>Description:</b>")
        lines.append(quest.get_filled_description())
        lines.append("")

        # Tracked units
        if quest.tracked_units:
            lines.append("<b>Tracked Characters:</b>")
            for pid, unit in quest.tracked_units.items():
                status = "Active" if unit.hp > 0 else "Defeated"
                lines.append(f"- {pid}: {unit.name} ({status})")
            lines.append("")

        # Tracked locations
        if quest.tracked_locations:
            lines.append("<b>Tracked Locations:</b>")
            for pid, pos in quest.tracked_locations.items():
                lines.append(f"- {pid}: Position {pos}")
            lines.append("")

        # Turn count
        lines.append(f"Turns elapsed: {quest.turn_count}")

        self.quest_details.set_text(f"<font color='#FFFFFF'>{'<br>'.join(lines)}</font>")

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# SkillsScreen class for managing learned and equipped skills
class SkillsScreen:
    def __init__(self):
        self.ui_elements = []
        self.learned_skills_list = None
        self.equipped_skills_list = None
        self.learnable_cards_list = None
        self.learn_button = None
        self.equip_button = None
        self.unequip_button = None
        self.back_button = None
        self.selected_learnable = None
        self.selected_learned = None
        self.selected_equipped = None
        # Flip animation tracking
        self.animating_card = None

    def initialize_screen(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.selected_learnable = None
        self.selected_learned = None
        self.selected_equipped = None

        # Title
        title = UILabel(
            pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            "Skills Management",
            manager,
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(title)

        # Back button
        self.back_button = UIButton(
            pygame.Rect(20, 20, 100, 40),
            "Back",
            manager
        )
        self.ui_elements.append(self.back_button)

        # Three columns layout
        column_width = (WINDOW_WIDTH - 80) // 3
        list_height = WINDOW_HEIGHT - 250
        y_start = 80

        # Column 1: Learnable Cards (Document cards that can become skills)
        col1_x = 20
        learnable_label = UILabel(
            pygame.Rect(col1_x, y_start, column_width, 30),
            "Learnable Documents",
            manager
        )
        self.ui_elements.append(learnable_label)

        learnable_items = self._get_learnable_cards()
        self.learnable_cards_list = UISelectionList(
            pygame.Rect(col1_x, y_start + 35, column_width, list_height),
            learnable_items,
            manager,
            allow_multi_select=False
        )
        self.ui_elements.append(self.learnable_cards_list)

        self.learn_button = UIButton(
            pygame.Rect(col1_x, y_start + list_height + 45, column_width, 40),
            "Learn Skill",
            manager
        )
        self.ui_elements.append(self.learn_button)

        # Column 2: Learned Skills
        col2_x = col1_x + column_width + 20
        learned_label = UILabel(
            pygame.Rect(col2_x, y_start, column_width, 30),
            "Learned Skills",
            manager
        )
        self.ui_elements.append(learned_label)

        learned_items = self._get_learned_skills()
        self.learned_skills_list = UISelectionList(
            pygame.Rect(col2_x, y_start + 35, column_width, list_height),
            learned_items,
            manager,
            allow_multi_select=False
        )
        self.ui_elements.append(self.learned_skills_list)

        self.equip_button = UIButton(
            pygame.Rect(col2_x, y_start + list_height + 45, column_width, 40),
            "Equip Skill",
            manager
        )
        self.ui_elements.append(self.equip_button)

        # Column 3: Equipped Skills
        col3_x = col2_x + column_width + 20
        equipped_label = UILabel(
            pygame.Rect(col3_x, y_start, column_width, 30),
            f"Equipped Skills ({len(game.current_player.equipped_skills)}/{game.current_player.active_skill_slots})",
            manager
        )
        self.ui_elements.append(equipped_label)

        equipped_items = self._get_equipped_skills()
        self.equipped_skills_list = UISelectionList(
            pygame.Rect(col3_x, y_start + 35, column_width, list_height),
            equipped_items,
            manager,
            allow_multi_select=False
        )
        self.ui_elements.append(self.equipped_skills_list)

        self.unequip_button = UIButton(
            pygame.Rect(col3_x, y_start + list_height + 45, column_width, 40),
            "Unequip Skill",
            manager
        )
        self.ui_elements.append(self.unequip_button)

    def _get_learnable_cards(self):
        """Get Document cards from inventory that can be transformed into skills."""
        learnable = []
        for card in game.current_player.inventory:
            card_type = card.card_data.get("card_type", "")
            # Check for Document/Skill compound type or Skill_Tome subclass
            if "Document/Skill" in card_type or card.card_data.get("subclass") == "Skill_Tome":
                if card.current_state == 1:  # Still in Document state
                    name = card.get_current_data().get("Name", "Unknown")
                    learnable.append(name)
        return learnable

    def _get_learned_skills(self):
        """Get all learned skills."""
        skills = []
        for card in game.current_player.skills:
            skill_data = card.get_current_data()
            name = skill_data.get("Name", "Unknown")
            skill_type = skill_data.get("Skill_Type", "Unknown")
            skills.append(f"{name} ({skill_type})")
        return skills

    def _get_equipped_skills(self):
        """Get equipped active skills."""
        equipped = []
        for card in game.current_player.equipped_skills:
            skill_data = card.get_current_data()
            name = skill_data.get("Name", "Unknown")
            cooldown = game.current_player.skill_cooldowns.get(name, 0)
            if cooldown > 0:
                equipped.append(f"{name} (CD:{cooldown})")
            else:
                equipped.append(name)
        return equipped

    def _find_card_by_name(self, name, card_list):
        """Find a card in a list by its name."""
        for card in card_list:
            card_name = card.get_current_data().get("Name", "")
            if card_name == name:
                return card
        return None

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                game.current_screen = "game"
                game_screen.initialize_screen()

            elif event.ui_element == self.learn_button:
                selections = self.learnable_cards_list.get_single_selection()
                if selections:
                    # Find the card in inventory
                    for card in game.current_player.inventory:
                        card_type = card.card_data.get("card_type", "")
                        if ("Document/Skill" in card_type or card.card_data.get("subclass") == "Skill_Tome"):
                            if card.current_state == 1:
                                name = card.get_current_data().get("Name", "")
                                if name == selections:
                                    msg = game.current_player.learn_skill(card)
                                    print(msg)
                                    self.initialize_screen()  # Refresh lists
                                    break

            elif event.ui_element == self.equip_button:
                selections = self.learned_skills_list.get_single_selection()
                if selections:
                    # Parse skill name from "Name (Type)" format
                    skill_name = selections.split(" (")[0]
                    for card in game.current_player.skills:
                        if card.get_current_data().get("Name") == skill_name:
                            msg = game.current_player.equip_skill(card)
                            print(msg)
                            self.initialize_screen()
                            break

            elif event.ui_element == self.unequip_button:
                selections = self.equipped_skills_list.get_single_selection()
                if selections:
                    # Parse skill name (may have cooldown suffix)
                    skill_name = selections.split(" (")[0]
                    for card in game.current_player.equipped_skills:
                        if card.get_current_data().get("Name") == skill_name:
                            msg = game.current_player.unequip_skill(card)
                            print(msg)
                            self.initialize_screen()
                            break

    def update(self):
        # Update flip animations
        if self.animating_card:
            if self.animating_card.update_flip_animation():
                self.animating_card = None
                self.initialize_screen()  # Refresh after animation complete

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# CraftingScreen class
class CraftingScreen:
    def __init__(self):
        self.window = None
        self.junk_list = None
        self.blueprint_list = None
        self.materials_list = None
        self.to_craft_info = None
        self.selected_material_info = None
        self.state2_info = None
        self.requirements_info = None
        self.craft_button = None
        self.success_label = None
        self.close_button = None
        self.selected_to_craft = None
        self.selected_materials = set()
        self.REQUIREMENT_TO_VALUE = {
            "Requirements: Raw Materials": "Raw Material Value",
            "Requirements: Refined Materials": "Refined Material Value",
            "Requirements: Wood": "Wood Value",
            "Requirements: Metal": "Metal Value"
        }

    def initialize_screen(self):
        manager.clear_and_reset()
        self.window = UIWindow(pygame.Rect((WINDOW_WIDTH - 1380) // 2, (WINDOW_HEIGHT - 900) // 2, 1380, 900), manager, "Crafting")
        junk_cards = [card for card in game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.is_two_state() and card.current_state == 1]
        self.junk_list = UISelectionList(pygame.Rect(15, 75, 330, 300), 
                                         [card.get_current_data().get("Name", "Unnamed") for card in junk_cards], 
                                         manager, container=self.window)
        blueprint_cards = [card for card in game.current_player.inventory if card.card_data["card_type"] == "Document Card" and card.card_data.get("subclass", "") == "Blueprint" and card.is_two_state() and card.current_state == 1]
        self.blueprint_list = UISelectionList(pygame.Rect(15, 390, 330, 300), 
                                              [card.get_current_data().get("Name", "Unnamed") for card in blueprint_cards], 
                                              manager, container=self.window)
        self.materials_list = UISelectionList(pygame.Rect(360, 75, 330, 750), 
                                              [], manager, container=self.window, allow_multi_select=True)
        self.update_materials_list()
        self.to_craft_info = UITextBox("<font color='#FFFFFF' size=4>To Craft</font>", pygame.Rect(705, 75, 330, 250), manager, container=self.window)
        self.selected_material_info = UITextBox("<font color='#FFFFFF' size=4>Selected Material</font>", pygame.Rect(705, 335, 330, 250), manager, container=self.window)
        self.state2_info = UITextBox("<font color='#FFFFFF' size=4>State 2 Info</font>", pygame.Rect(705, 595, 330, 250), manager, container=self.window)
        self.requirements_info = UITextBox("<font color='#FFFFFF' size=4>Requirements</font>", pygame.Rect(1050, 75, 330, 300), manager, container=self.window)
        self.craft_button = UIButton(pygame.Rect(1060, 390, 100, 30), "Craft", manager, container=self.window)
        self.close_button = UIButton(pygame.Rect(1170, 390, 100, 30), "Close", manager, container=self.window)
        self.success_label = UILabel(pygame.Rect(1060, 430, 310, 30), "", manager, container=self.window)
        self.update_requirements_display()

    def update_materials_list(self):
        materials_cards = [card for card in game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.current_state == 1]
        if self.selected_to_craft and self.selected_to_craft.card_data["card_type"] == "Junk Card":
            materials_cards = [card for card in materials_cards if card != self.selected_to_craft]
        self.materials_list.set_item_list([card.get_current_data().get("Name", "Unnamed") for card in materials_cards])

    def update_requirements_display(self):
        if not self.selected_to_craft:
            self.requirements_info.set_text("<font color='#FFFFFF' size=4>Requirements</font>")
            return
        state1_data = self.selected_to_craft.get_state_data(1)

        # Calculate provided totals from selected materials
        provided_totals = {val_key: 0 for val_key in self.REQUIREMENT_TO_VALUE.values()}
        for material in self.selected_materials:
            material_data = material.get_current_data()
            for val_key in provided_totals:
                provided_totals[val_key] += int(material_data.get(val_key, 0) or 0)

        # Build table header
        requirements_text = "<font color='#FFFFFF' size=4>"
        requirements_text += "<b>Requirements:</b><br><br>"
        requirements_text += "<font color='#AAAAAA'>Material</font>           "
        requirements_text += "<font color='#00FF00'>Have</font>  "
        requirements_text += "<font color='#FFAA00'>Need</font><br>"
        requirements_text += "─────────────────────<br>"

        all_met = True
        for req_key, val_key in self.REQUIREMENT_TO_VALUE.items():
            required = int(state1_data.get(req_key, 0) or 0)
            provided = provided_totals[val_key]
            material_type = req_key.split(": ")[1]

            # Color code: green if met, red if not
            if provided >= required:
                have_color = "#00FF00"  # Green - requirement met
            else:
                have_color = "#FF4444"  # Red - requirement not met
                all_met = False

            # Pad material type for alignment (max ~15 chars)
            padded_type = material_type.ljust(18)
            requirements_text += f"{padded_type}<font color='{have_color}'>{provided:>3}</font>   <font color='#FFAA00'>{required:>3}</font><br>"

        # Handle specific card requirements
        specific_cards = state1_data.get("Requirements: Specific Cards", "")
        if specific_cards:
            required_cards = [card.strip() for card in specific_cards.split(",") if card.strip()]
            provided_cards = [material.get_current_data().get("Name", "Unnamed") for material in self.selected_materials]
            cards_have = len([card for card in required_cards if card in provided_cards])
            cards_need = len(required_cards)

            if cards_have >= cards_need:
                have_color = "#00FF00"
            else:
                have_color = "#FF4444"
                all_met = False

            requirements_text += f"{'Specific Cards'.ljust(18)}<font color='{have_color}'>{cards_have:>3}</font>   <font color='#FFAA00'>{cards_need:>3}</font><br>"

        requirements_text += "─────────────────────<br>"

        if all_met:
            requirements_text += "<font color='#00FF00'><b>✓ Ready to Craft!</b></font>"
        else:
            requirements_text += "<font color='#FF4444'>✗ Missing materials</font>"

        requirements_text += "</font>"
        self.requirements_info.set_text(requirements_text)

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                game.current_screen = "game"
                game_screen.initialize_screen()
            elif event.ui_element == self.craft_button:
                if self.selected_to_craft and self.check_requirements():
                    for material in self.selected_materials:
                        game.current_player.inventory.remove(material)
                    self.selected_to_craft.toggle_state()
                    crafted_name = self.selected_to_craft.get_state_data(2).get("2nd_state_Name", "Unnamed Item")
                    self.success_label.set_text(f"Crafted {crafted_name}")
                    self.selected_to_craft = None
                    self.selected_materials.clear()
                    self.initialize_screen()
                else:
                    self.success_label.set_text("Requirements not met or no item selected")
        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element in [self.junk_list, self.blueprint_list]:
                selected_name = event.text
                cards = (
                    [card for card in game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.is_two_state() and card.current_state == 1]
                    if event.ui_element == self.junk_list else
                    [card for card in game.current_player.inventory if card.card_data["card_type"] == "Document Card" and card.card_data.get("subclass", "") == "Blueprint" and card.is_two_state() and card.current_state == 1]
                )
                self.selected_to_craft = next((card for card in cards if card.get_state_data(1).get("Name") == selected_name), None)
                self.update_materials_list()
                if self.selected_to_craft:
                    state1_data = self.selected_to_craft.get_state_data(1)
                    info_text = f"<font color='#FFFFFF' size=4>To Craft: {state1_data.get('Name', 'Unnamed')}<br>" + "<br>".join(f"{k}: {v}" for k, v in state1_data.items() if k != "Name" and v) + "</font>"
                    self.to_craft_info.set_text(info_text)
                    state2_data = self.selected_to_craft.get_state_data(2)
                    state2_text = f"<font color='#FFFFFF' size=4>State 2: {state2_data.get('2nd_state_Name', 'Unnamed')}<br>" + "<br>".join(f"{k}: {v}" for k, v in state2_data.items() if k != '2nd_state_Name' and v) + "</font>"
                    self.state2_info.set_text(state2_text)
                    self.update_requirements_display()
            elif event.ui_element == self.materials_list:
                selected_names = self.materials_list.get_multi_selection()
                materials_cards = [card for card in game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.current_state == 1]
                if self.selected_to_craft and self.selected_to_craft.card_data["card_type"] == "Junk Card":
                    materials_cards = [card for card in materials_cards if card != self.selected_to_craft]
                self.selected_materials = {card for card in materials_cards if card.get_current_data().get("Name") in selected_names}
                if selected_names:
                    last_material = next((card for card in materials_cards if card.get_current_data().get("Name") == selected_names[-1]), None)
                    if last_material:
                        data = last_material.get_current_data()
                        info_text = f"<font color='#FFFFFF' size=4>Selected Material: {data.get('Name', 'Unnamed')}<br>" + "<br>".join(f"{k}: {v}" for k, v in data.items() if k != "Name" and v) + "</font>"
                        self.selected_material_info.set_text(info_text)
                self.update_requirements_display()

    def check_requirements(self):
        if not self.selected_to_craft:
            return False
        state1_data = self.selected_to_craft.get_state_data(1)
        for req_key, val_key in self.REQUIREMENT_TO_VALUE.items():
            required_amount = int(state1_data.get(req_key, 0) or 0)  # Handle empty or None values
            provided_amount = sum(int(material.get_current_data().get(val_key, 0) or 0) for material in self.selected_materials)
            if provided_amount < required_amount:
                return False
        specific_cards = state1_data.get("Requirements: Specific Cards", "")
        if specific_cards:
            required_cards = [card.strip() for card in specific_cards.split(",") if card.strip()]
            provided_cards = [material.get_current_data().get("Name", "Unnamed") for material in self.selected_materials]
            if not all(req_card in provided_cards for req_card in required_cards):
                return False
        return True

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


class TabbedMenuScreen:
    """Single tabbed screen combining Inventory, Crafting, Skills, Party, and Quests."""
    TAB_NAMES = ["Inventory", "Crafting", "Skills", "Party", "Quests"]
    TAB_WIDTH = 200
    TAB_HEIGHT = 40
    CONTENT_Y = 60  # Where content starts below the tab bar

    def __init__(self):
        self.active_tab = "Inventory"
        self.tab_buttons = {}  # {name: UIButton}
        self.close_button = None
        self.content_elements = []  # All UI elements in content area (killed on tab switch)

        # Inventory tab state
        self.inv_junk_list = None
        self.inv_documents_list = None
        self.inv_weapons_list = None
        self.inv_consumables_list = None
        self.inv_equip_button = None
        self.inv_use_button = None
        self.inv_use_junk_button = None
        self.inv_equip_tool_button = None
        self.inv_equip_accessory_button = None
        self.inv_browse_cards_button = None
        self.inv_read_guide_button = None
        self.inv_info_text = None
        self.inv_selected_card = None
        self.inv_selected_from_list = None

        # Crafting tab state
        self.craft_junk_list = None
        self.craft_blueprint_list = None
        self.craft_materials_list = None
        self.craft_to_craft_info = None
        self.craft_selected_material_info = None
        self.craft_state2_info = None
        self.craft_requirements_info = None
        self.craft_button = None
        self.craft_success_label = None
        self.craft_selected_to_craft = None
        self.craft_selected_materials = set()
        self.REQUIREMENT_TO_VALUE = {
            "Requirements: Raw Materials": "Raw Material Value",
            "Requirements: Refined Materials": "Refined Material Value",
            "Requirements: Wood": "Wood Value",
            "Requirements: Metal": "Metal Value"
        }

        # Skills tab state
        self.skill_learnable_list = None
        self.skill_learned_list = None
        self.skill_equipped_list = None
        self.skill_learn_button = None
        self.skill_equip_button = None
        self.skill_unequip_button = None

        # Party tab state
        self.party_list = None
        self.party_info_text = None
        self.party_deploy_button = None
        self.party_recall_button = None
        self.party_dismiss_button = None
        self.party_browse_npcs_button = None
        self.party_selected_member = None
        self.party_member_names = []

        # Quest tab state
        self.quest_tab_buttons = []
        self.quest_current_tab = "active"
        self.quest_list = None
        self.quest_details = None
        self.quest_abandon_button = None
        self.quest_selected_quest = None
        self.quest_names = []

    def initialize_screen(self):
        manager.clear_and_reset()
        self.content_elements = []
        self._build_tab_bar()
        self._build_active_content()

    def _build_tab_bar(self):
        """Build the persistent tab bar at the top."""
        total_width = len(self.TAB_NAMES) * self.TAB_WIDTH + (len(self.TAB_NAMES) - 1) * 10
        start_x = (WINDOW_WIDTH - total_width) // 2
        self.tab_buttons = {}
        for i, name in enumerate(self.TAB_NAMES):
            x = start_x + i * (self.TAB_WIDTH + 10)
            btn = UIButton(pygame.Rect(x, 10, self.TAB_WIDTH, self.TAB_HEIGHT), name, manager)
            self.tab_buttons[name] = btn
        # Close button at far right
        self.close_button = UIButton(pygame.Rect(WINDOW_WIDTH - 120, 10, 100, self.TAB_HEIGHT), "Close", manager)

    def switch_tab(self, name):
        """Switch to a different tab, killing content and rebuilding."""
        self.active_tab = name
        self._kill_content()
        self._build_active_content()

    def _kill_content(self):
        """Kill all content elements (preserving tab bar)."""
        for elem in self.content_elements:
            elem.kill()
        self.content_elements = []

    def _build_active_content(self):
        """Build content for the currently active tab."""
        if self.active_tab == "Inventory":
            self._build_inventory_content()
        elif self.active_tab == "Crafting":
            self._build_crafting_content()
        elif self.active_tab == "Skills":
            self._build_skills_content()
        elif self.active_tab == "Party":
            self._build_party_content()
        elif self.active_tab == "Quests":
            self._build_quests_content()

    def _refresh_current_tab(self):
        """Refresh the current tab content (after equip, craft, etc.)."""
        self._kill_content()
        self._build_active_content()

    def _add(self, element):
        """Helper to track content elements."""
        self.content_elements.append(element)
        return element

    # ========================
    # INVENTORY TAB
    # ========================
    def _build_inventory_content(self):
        self.inv_selected_card = None
        self.inv_selected_from_list = None
        y = self.CONTENT_Y
        column_width = 280
        column_height = 500

        # Column labels
        self._add(UILabel(pygame.Rect(10, y, column_width, 25), "Junk / Materials", manager))
        self._add(UILabel(pygame.Rect(column_width + 20, y, column_width, 25), "Documents", manager))
        self._add(UILabel(pygame.Rect(2 * column_width + 30, y, column_width, 25), "Weapons", manager))
        self._add(UILabel(pygame.Rect(3 * column_width + 40, y, column_width, 25), "Consumables / Tools", manager))

        list_y = y + 30

        # Junk cards (column 1)
        junk_cards = [card for card in game.current_player.inventory if card.current_state == 1 and card.card_data["card_type"] == "Junk Card"]
        junk_names = []
        for card in junk_cards:
            name = card.get_current_data().get("Name", "Unnamed")
            if card.get_current_data().get("Use_HP") or card.card_data.get("subclass") == "Consumable":
                name += " [Usable]"
            junk_names.append(name)
        self.inv_junk_list = self._add(UISelectionList(pygame.Rect(10, list_y, column_width, column_height),
                                         junk_names if junk_names else ["No junk items"], manager))
        self.inv_use_junk_button = self._add(UIButton(pygame.Rect(10, list_y + column_height + 10, column_width, 35), "Use Item", manager))

        # Documents (column 2)
        documents_cards = [card for card in game.current_player.inventory
                          if card.card_data["card_type"] == "Document Card"
                          and (card.current_state == 1 or card.card_data.get("subclass") == "Guide")]
        self.inv_documents_list = self._add(UISelectionList(pygame.Rect(column_width + 20, list_y, column_width, column_height - 45),
                                              [card.get_current_data().get("Name", "Unnamed") for card in documents_cards] or ["No documents"], manager))
        self.inv_read_guide_button = self._add(UIButton(pygame.Rect(column_width + 20, list_y + column_height - 40, column_width, 35),
                                          "Read Guide", manager))

        # Weapons (column 3)
        weapons_cards = [card for card in game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") in ["Melee", "Projectile", "Both"]]
        self.inv_weapons_list = self._add(UISelectionList(pygame.Rect(2 * column_width + 30, list_y, column_width, column_height - 100),
                                            [card.get_current_data().get("Name", "Unnamed") for card in weapons_cards] or ["No weapons"], manager))
        self.inv_equip_button = self._add(UIButton(pygame.Rect(2 * column_width + 30, list_y + column_height - 90, column_width, 35), "Equip Weapon", manager))

        # Consumables, Tools, Ammunition (column 4)
        consumables_cards = [card for card in game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Consumable"]
        tools_cards = [card for card in game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Tool"]
        ammo_cards = [card for card in game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Ammunition"]
        accessory_cards = [card for card in game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") in ["Tool_Belt", "Accessory", "Belt", "Pouch"]]
        combined_items = consumables_cards + tools_cards + ammo_cards + accessory_cards

        item_names = []
        for card in combined_items:
            name = card.get_current_data().get("Name", "Unnamed")
            card_type = card.get_current_data().get("Type", "")
            if card_type == "Ammunition":
                name += " [Ammo]"
            elif card_type in ["Tool_Belt", "Accessory", "Belt", "Pouch"]:
                name += " [Accessory]"
            item_names.append(name)

        self.inv_consumables_list = self._add(UISelectionList(pygame.Rect(3 * column_width + 40, list_y, column_width, column_height - 190),
                                                item_names if item_names else ["No consumables/tools"], manager))
        self.inv_use_button = self._add(UIButton(pygame.Rect(3 * column_width + 40, list_y + column_height - 180, column_width, 35), "Use Consumable", manager))
        self.inv_equip_tool_button = self._add(UIButton(pygame.Rect(3 * column_width + 40, list_y + column_height - 140, column_width, 35), "Equip as Tool/Ammo", manager))
        self.inv_equip_accessory_button = self._add(UIButton(pygame.Rect(3 * column_width + 40, list_y + column_height - 100, column_width, 35), "Equip Accessory", manager))

        # Item details panel (bottom)
        detail_y = list_y + column_height + 55
        self._add(UILabel(pygame.Rect(10, detail_y, 200, 25), "Item Details:", manager))
        self.inv_info_text = self._add(UITextBox("<font color='#FFFFFF'>Select an item to view its stats and details</font>",
                                   pygame.Rect(10, detail_y + 25, 870, 120), manager))

        # Creative mode button
        if game.game_mode == "creative":
            self.inv_browse_cards_button = self._add(UIButton(pygame.Rect(900, detail_y + 25, 150, 35), "Browse Cards", manager))
            self._add(UILabel(pygame.Rect(900, detail_y + 70, 150, 25), "[Creative Mode]", manager))
        else:
            self.inv_browse_cards_button = None

    def _handle_inventory_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if self.inv_browse_cards_button and event.ui_element == self.inv_browse_cards_button:
                game.current_screen = "card_browser"
                card_browser_screen.initialize_screen()
                return
            elif event.ui_element == self.inv_equip_button and self.inv_selected_card and self.inv_selected_from_list == "weapons":
                game.current_player.equip_weapon(self.inv_selected_card)
                game_screen.player_info_label.set_text(game_screen.get_player_info())
                self.inv_info_text.set_text("<font color='#00FF00'>Weapon equipped!</font>")
            elif event.ui_element == self.inv_use_junk_button and self.inv_selected_card and self.inv_selected_from_list == "junk":
                self._inv_use_consumable_item()
            elif event.ui_element == self.inv_use_button and self.inv_selected_card and self.inv_selected_from_list == "consumables":
                self._inv_use_consumable_item()
            elif event.ui_element == self.inv_equip_tool_button and self.inv_selected_card:
                if self.inv_selected_from_list in ["junk", "consumables"]:
                    card_type = self.inv_selected_card.get_current_data().get("Type", "")
                    if card_type in ["Tool_Belt", "Accessory", "Belt", "Pouch"]:
                        self.inv_info_text.set_text("<font color='#FF0000'>Use 'Equip Accessory' for tool belts</font>")
                    else:
                        msg = game.current_player.equip_tool(self.inv_selected_card)
                        self.inv_info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
                        self._refresh_current_tab()
                else:
                    self.inv_info_text.set_text("<font color='#FF0000'>Select a consumable, tool, or ammo to equip</font>")
            elif event.ui_element == self.inv_equip_accessory_button and self.inv_selected_card:
                if self.inv_selected_from_list == "consumables":
                    card_type = self.inv_selected_card.get_current_data().get("Type", "")
                    if card_type in ["Tool_Belt", "Accessory", "Belt", "Pouch"]:
                        msg = game.current_player.equip_accessory(self.inv_selected_card)
                        self.inv_info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
                        self._refresh_current_tab()
                    else:
                        self.inv_info_text.set_text("<font color='#FF0000'>Select a tool belt or accessory to equip</font>")
                else:
                    self.inv_info_text.set_text("<font color='#FF0000'>Select a tool belt or accessory to equip</font>")
            elif self.inv_read_guide_button and event.ui_element == self.inv_read_guide_button:
                if self.inv_selected_card and self.inv_selected_from_list == "documents" and self.inv_selected_card.card_data.get("subclass") == "Guide":
                    message = game.current_player.read_guide(self.inv_selected_card, game.card_manager)
                    self.inv_info_text.set_text(f"<font color='#00FFFF'>{message}</font>")
                    game_screen.add_to_log(message)
                    self._refresh_current_tab()
                else:
                    self.inv_info_text.set_text("<font color='#FF0000'>Select a Guide document to read</font>")

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            selected_name = event.text
            clean_name = selected_name.replace(" [Usable]", "")

            if event.ui_element == self.inv_junk_list:
                self.inv_selected_from_list = "junk"
                self.inv_selected_card = next((card for card in game.current_player.inventory
                                          if card.current_state == 1
                                          and card.card_data["card_type"] == "Junk Card"
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.inv_documents_list:
                self.inv_selected_from_list = "documents"
                self.inv_selected_card = next((card for card in game.current_player.inventory
                                          if card.card_data["card_type"] == "Document Card"
                                          and (card.current_state == 1 or card.card_data.get("subclass") == "Guide")
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.inv_weapons_list:
                self.inv_selected_from_list = "weapons"
                self.inv_selected_card = next((card for card in game.current_player.inventory
                                          if card.current_state == 2
                                          and card.get_current_data().get("Type") in ["Melee", "Projectile", "Both"]
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.inv_consumables_list:
                self.inv_selected_from_list = "consumables"
                match_name = clean_name.replace(" [Ammo]", "").replace(" [Accessory]", "")
                self.inv_selected_card = next((card for card in game.current_player.inventory
                                          if card.current_state == 2
                                          and card.get_current_data().get("Type") in ["Consumable", "Tool", "Ammunition", "Tool_Belt", "Accessory", "Belt", "Pouch"]
                                          and card.get_current_data().get("Name") == match_name), None)

            if self.inv_selected_card:
                card_data = self.inv_selected_card.get_current_data()
                info_lines = []
                info_lines.append(f"<b>{card_data.get('Name', 'Unknown')}</b>")
                if card_data.get('Description'):
                    info_lines.append(f"<i>{card_data.get('Description')}</i>")
                info_lines.append("")
                for k, v in card_data.items():
                    if v and k not in ['Name', 'Description', 'id']:
                        info_lines.append(f"{k}: {v}")
                self.inv_info_text.set_text(f"<font color='#FFFFFF'>{'<br>'.join(info_lines)}</font>")
            else:
                self.inv_info_text.set_text("<font color='#FFFFFF'>Select an item to view its stats and details</font>")

    def _inv_use_consumable_item(self):
        """Use a consumable item (junk or crafted) from inventory tab."""
        if not self.inv_selected_card:
            self.inv_info_text.set_text("<font color='#FF0000'>No item selected!</font>")
            return

        current_data = self.inv_selected_card.get_current_data()
        hp_effect = current_data.get("Use_HP", "")

        if not hp_effect:
            self.inv_info_text.set_text(f"<font color='#FF0000'>{current_data.get('Name', 'Item')} cannot be used!</font>")
            return

        try:
            if isinstance(hp_effect, list):
                hp_effect = next((effect for effect in hp_effect if effect and "HP" in effect), "+0HP")
            hp_str = hp_effect.replace("HP", "").replace("+", "")
            hp_change = int(hp_str)

            if hp_change > 0:
                old_hp = game.current_player.hp
                game.current_player.hp = min(game.current_player.max_hp, game.current_player.hp + hp_change)
                actual_heal = game.current_player.hp - old_hp
                game_screen.add_to_log(f"Used {current_data.get('Name', 'Item')}: +{actual_heal} HP ({old_hp} -> {game.current_player.hp})")
                game.current_player.inventory.remove(self.inv_selected_card)
                self.inv_selected_card = None
                self._refresh_current_tab()
                game_screen.player_info_label.set_text(game_screen.get_player_info())
            elif hp_change < 0:
                game.current_player.hp = max(0, game.current_player.hp + hp_change)
                game_screen.add_to_log(f"Used {current_data.get('Name', 'Item')}: {hp_change} HP")
                game.current_player.inventory.remove(self.inv_selected_card)
                self.inv_selected_card = None
                self._refresh_current_tab()
                game_screen.player_info_label.set_text(game_screen.get_player_info())
            else:
                self.inv_info_text.set_text(f"<font color='#FF0000'>{current_data.get('Name', 'Item')} has no effect!</font>")
        except (ValueError, AttributeError):
            self.inv_info_text.set_text(f"<font color='#FF0000'>Cannot use {current_data.get('Name', 'Item')}: invalid effect</font>")

    # ========================
    # CRAFTING TAB
    # ========================
    def _build_crafting_content(self):
        self.craft_selected_to_craft = None
        self.craft_selected_materials = set()
        y = self.CONTENT_Y

        # Layout: 4 columns spread across full screen
        col_w = 330
        gap = 15
        col1_x = 10
        col2_x = col1_x + col_w + gap
        col3_x = col2_x + col_w + gap
        col4_x = col3_x + col_w + gap
        list_h = 300

        # Column 1: Junk cards to craft
        self._add(UILabel(pygame.Rect(col1_x, y, col_w, 25), "Junk Items (Craftable)", manager))
        junk_cards = [card for card in game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.is_two_state() and card.current_state == 1]
        self.craft_junk_list = self._add(UISelectionList(pygame.Rect(col1_x, y + 30, col_w, list_h),
                                         [card.get_current_data().get("Name", "Unnamed") for card in junk_cards], manager))

        # Blueprints below junk
        self._add(UILabel(pygame.Rect(col1_x, y + list_h + 40, col_w, 25), "Blueprints", manager))
        blueprint_cards = [card for card in game.current_player.inventory if card.card_data["card_type"] == "Document Card" and card.card_data.get("subclass", "") == "Blueprint" and card.is_two_state() and card.current_state == 1]
        self.craft_blueprint_list = self._add(UISelectionList(pygame.Rect(col1_x, y + list_h + 70, col_w, list_h),
                                              [card.get_current_data().get("Name", "Unnamed") for card in blueprint_cards], manager))

        # Column 2: Materials (multi-select)
        self._add(UILabel(pygame.Rect(col2_x, y, col_w, 25), "Materials", manager))
        self.craft_materials_list = self._add(UISelectionList(pygame.Rect(col2_x, y + 30, col_w, list_h * 2 + 40),
                                              [], manager, allow_multi_select=True))
        self._craft_update_materials_list()

        # Column 3: Info panels
        self.craft_to_craft_info = self._add(UITextBox("<font color='#FFFFFF' size=4>To Craft</font>",
                                              pygame.Rect(col3_x, y + 30, col_w, 220), manager))
        self.craft_selected_material_info = self._add(UITextBox("<font color='#FFFFFF' size=4>Selected Material</font>",
                                              pygame.Rect(col3_x, y + 260, col_w, 220), manager))
        self.craft_state2_info = self._add(UITextBox("<font color='#FFFFFF' size=4>State 2 Info</font>",
                                              pygame.Rect(col3_x, y + 490, col_w, 220), manager))

        # Column 4: Requirements + craft button
        self.craft_requirements_info = self._add(UITextBox("<font color='#FFFFFF' size=4>Requirements</font>",
                                              pygame.Rect(col4_x, y + 30, col_w, 300), manager))
        self.craft_button = self._add(UIButton(pygame.Rect(col4_x, y + 340, 150, 30), "Craft", manager))
        self.craft_success_label = self._add(UILabel(pygame.Rect(col4_x, y + 380, col_w, 30), "", manager))
        self._craft_update_requirements_display()

    def _craft_update_materials_list(self):
        materials_cards = [card for card in game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.current_state == 1]
        if self.craft_selected_to_craft and self.craft_selected_to_craft.card_data["card_type"] == "Junk Card":
            materials_cards = [card for card in materials_cards if card != self.craft_selected_to_craft]
        self.craft_materials_list.set_item_list([card.get_current_data().get("Name", "Unnamed") for card in materials_cards])

    def _craft_update_requirements_display(self):
        if not self.craft_selected_to_craft:
            self.craft_requirements_info.set_text("<font color='#FFFFFF' size=4>Requirements</font>")
            return
        state1_data = self.craft_selected_to_craft.get_state_data(1)

        provided_totals = {val_key: 0 for val_key in self.REQUIREMENT_TO_VALUE.values()}
        for material in self.craft_selected_materials:
            material_data = material.get_current_data()
            for val_key in provided_totals:
                provided_totals[val_key] += int(material_data.get(val_key, 0) or 0)

        requirements_text = "<font color='#FFFFFF' size=4>"
        requirements_text += "<b>Requirements:</b><br><br>"
        requirements_text += "<font color='#AAAAAA'>Material</font>           "
        requirements_text += "<font color='#00FF00'>Have</font>  "
        requirements_text += "<font color='#FFAA00'>Need</font><br>"
        requirements_text += "─────────────────────<br>"

        all_met = True
        for req_key, val_key in self.REQUIREMENT_TO_VALUE.items():
            required = int(state1_data.get(req_key, 0) or 0)
            provided = provided_totals[val_key]
            material_type = req_key.split(": ")[1]

            if provided >= required:
                have_color = "#00FF00"
            else:
                have_color = "#FF4444"
                all_met = False

            padded_type = material_type.ljust(18)
            requirements_text += f"{padded_type}<font color='{have_color}'>{provided:>3}</font>   <font color='#FFAA00'>{required:>3}</font><br>"

        specific_cards = state1_data.get("Requirements: Specific Cards", "")
        if specific_cards:
            required_cards = [card.strip() for card in specific_cards.split(",") if card.strip()]
            provided_cards = [material.get_current_data().get("Name", "Unnamed") for material in self.craft_selected_materials]
            cards_have = len([card for card in required_cards if card in provided_cards])
            cards_need = len(required_cards)

            if cards_have >= cards_need:
                have_color = "#00FF00"
            else:
                have_color = "#FF4444"
                all_met = False

            requirements_text += f"{'Specific Cards'.ljust(18)}<font color='{have_color}'>{cards_have:>3}</font>   <font color='#FFAA00'>{cards_need:>3}</font><br>"

        requirements_text += "─────────────────────<br>"

        if all_met:
            requirements_text += "<font color='#00FF00'><b>✓ Ready to Craft!</b></font>"
        else:
            requirements_text += "<font color='#FF4444'>✗ Missing materials</font>"

        requirements_text += "</font>"
        self.craft_requirements_info.set_text(requirements_text)

    def _craft_check_requirements(self):
        if not self.craft_selected_to_craft:
            return False
        state1_data = self.craft_selected_to_craft.get_state_data(1)
        for req_key, val_key in self.REQUIREMENT_TO_VALUE.items():
            required_amount = int(state1_data.get(req_key, 0) or 0)
            provided_amount = sum(int(material.get_current_data().get(val_key, 0) or 0) for material in self.craft_selected_materials)
            if provided_amount < required_amount:
                return False
        specific_cards = state1_data.get("Requirements: Specific Cards", "")
        if specific_cards:
            required_cards = [card.strip() for card in specific_cards.split(",") if card.strip()]
            provided_cards = [material.get_current_data().get("Name", "Unnamed") for material in self.craft_selected_materials]
            if not all(req_card in provided_cards for req_card in required_cards):
                return False
        return True

    def _handle_crafting_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.craft_button:
                if self.craft_selected_to_craft and self._craft_check_requirements():
                    for material in self.craft_selected_materials:
                        game.current_player.inventory.remove(material)
                    self.craft_selected_to_craft.toggle_state()
                    crafted_name = self.craft_selected_to_craft.get_state_data(2).get("2nd_state_Name", "Unnamed Item")
                    self.craft_selected_to_craft = None
                    self.craft_selected_materials.clear()
                    self._refresh_current_tab()
                    self.craft_success_label.set_text(f"Crafted {crafted_name}")
                else:
                    self.craft_success_label.set_text("Requirements not met or no item selected")
        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element in [self.craft_junk_list, self.craft_blueprint_list]:
                selected_name = event.text
                cards = (
                    [card for card in game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.is_two_state() and card.current_state == 1]
                    if event.ui_element == self.craft_junk_list else
                    [card for card in game.current_player.inventory if card.card_data["card_type"] == "Document Card" and card.card_data.get("subclass", "") == "Blueprint" and card.is_two_state() and card.current_state == 1]
                )
                self.craft_selected_to_craft = next((card for card in cards if card.get_state_data(1).get("Name") == selected_name), None)
                self._craft_update_materials_list()
                if self.craft_selected_to_craft:
                    state1_data = self.craft_selected_to_craft.get_state_data(1)
                    info_text = f"<font color='#FFFFFF' size=4>To Craft: {state1_data.get('Name', 'Unnamed')}<br>" + "<br>".join(f"{k}: {v}" for k, v in state1_data.items() if k != "Name" and v) + "</font>"
                    self.craft_to_craft_info.set_text(info_text)
                    state2_data = self.craft_selected_to_craft.get_state_data(2)
                    state2_text = f"<font color='#FFFFFF' size=4>State 2: {state2_data.get('2nd_state_Name', 'Unnamed')}<br>" + "<br>".join(f"{k}: {v}" for k, v in state2_data.items() if k != '2nd_state_Name' and v) + "</font>"
                    self.craft_state2_info.set_text(state2_text)
                    self._craft_update_requirements_display()
            elif event.ui_element == self.craft_materials_list:
                selected_names = self.craft_materials_list.get_multi_selection()
                materials_cards = [card for card in game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.current_state == 1]
                if self.craft_selected_to_craft and self.craft_selected_to_craft.card_data["card_type"] == "Junk Card":
                    materials_cards = [card for card in materials_cards if card != self.craft_selected_to_craft]
                self.craft_selected_materials = {card for card in materials_cards if card.get_current_data().get("Name") in selected_names}
                if selected_names:
                    last_material = next((card for card in materials_cards if card.get_current_data().get("Name") == selected_names[-1]), None)
                    if last_material:
                        data = last_material.get_current_data()
                        info_text = f"<font color='#FFFFFF' size=4>Selected Material: {data.get('Name', 'Unnamed')}<br>" + "<br>".join(f"{k}: {v}" for k, v in data.items() if k != "Name" and v) + "</font>"
                        self.craft_selected_material_info.set_text(info_text)
                self._craft_update_requirements_display()

    # ========================
    # SKILLS TAB
    # ========================
    def _build_skills_content(self):
        self.skill_selected_learnable = None
        self.skill_selected_learned = None
        self.skill_selected_equipped = None
        y = self.CONTENT_Y

        column_width = (WINDOW_WIDTH - 80) // 3
        list_height = WINDOW_HEIGHT - 250

        # Column 1: Learnable Documents
        col1_x = 20
        self._add(UILabel(pygame.Rect(col1_x, y, column_width, 30), "Learnable Documents", manager))
        learnable_items = self._skill_get_learnable_cards()
        self.skill_learnable_list = self._add(UISelectionList(
            pygame.Rect(col1_x, y + 35, column_width, list_height),
            learnable_items, manager, allow_multi_select=False))
        self.skill_learn_button = self._add(UIButton(
            pygame.Rect(col1_x, y + list_height + 45, column_width, 40), "Learn Skill", manager))

        # Column 2: Learned Skills
        col2_x = col1_x + column_width + 20
        self._add(UILabel(pygame.Rect(col2_x, y, column_width, 30), "Learned Skills", manager))
        learned_items = self._skill_get_learned_skills()
        self.skill_learned_list = self._add(UISelectionList(
            pygame.Rect(col2_x, y + 35, column_width, list_height),
            learned_items, manager, allow_multi_select=False))
        self.skill_equip_button = self._add(UIButton(
            pygame.Rect(col2_x, y + list_height + 45, column_width, 40), "Equip Skill", manager))

        # Column 3: Equipped Skills
        col3_x = col2_x + column_width + 20
        self._add(UILabel(pygame.Rect(col3_x, y, column_width, 30),
            f"Equipped Skills ({len(game.current_player.equipped_skills)}/{game.current_player.active_skill_slots})", manager))
        equipped_items = self._skill_get_equipped_skills()
        self.skill_equipped_list = self._add(UISelectionList(
            pygame.Rect(col3_x, y + 35, column_width, list_height),
            equipped_items, manager, allow_multi_select=False))
        self.skill_unequip_button = self._add(UIButton(
            pygame.Rect(col3_x, y + list_height + 45, column_width, 40), "Unequip Skill", manager))

    def _skill_get_learnable_cards(self):
        learnable = []
        for card in game.current_player.inventory:
            card_type = card.card_data.get("card_type", "")
            if "Document/Skill" in card_type or card.card_data.get("subclass") == "Skill_Tome":
                if card.current_state == 1:
                    name = card.get_current_data().get("Name", "Unknown")
                    learnable.append(name)
        return learnable

    def _skill_get_learned_skills(self):
        skills = []
        for card in game.current_player.skills:
            skill_data = card.get_current_data()
            name = skill_data.get("Name", "Unknown")
            skill_type = skill_data.get("Skill_Type", "Unknown")
            skills.append(f"{name} ({skill_type})")
        return skills

    def _skill_get_equipped_skills(self):
        equipped = []
        for card in game.current_player.equipped_skills:
            skill_data = card.get_current_data()
            name = skill_data.get("Name", "Unknown")
            cooldown = game.current_player.skill_cooldowns.get(name, 0)
            if cooldown > 0:
                equipped.append(f"{name} (CD:{cooldown})")
            else:
                equipped.append(name)
        return equipped

    def _handle_skills_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.skill_learn_button:
                selections = self.skill_learnable_list.get_single_selection()
                if selections:
                    for card in game.current_player.inventory:
                        card_type = card.card_data.get("card_type", "")
                        if ("Document/Skill" in card_type or card.card_data.get("subclass") == "Skill_Tome"):
                            if card.current_state == 1:
                                name = card.get_current_data().get("Name", "")
                                if name == selections:
                                    game.current_player.learn_skill(card)
                                    self._refresh_current_tab()
                                    break

            elif event.ui_element == self.skill_equip_button:
                selections = self.skill_learned_list.get_single_selection()
                if selections:
                    skill_name = selections.split(" (")[0]
                    for card in game.current_player.skills:
                        if card.get_current_data().get("Name") == skill_name:
                            game.current_player.equip_skill(card)
                            self._refresh_current_tab()
                            break

            elif event.ui_element == self.skill_unequip_button:
                selections = self.skill_equipped_list.get_single_selection()
                if selections:
                    skill_name = selections.split(" (")[0]
                    for card in game.current_player.equipped_skills:
                        if card.get_current_data().get("Name") == skill_name:
                            game.current_player.unequip_skill(card)
                            self._refresh_current_tab()
                            break

    # ========================
    # PARTY TAB
    # ========================
    def _build_party_content(self):
        self.party_selected_member = None
        y = self.CONTENT_Y

        # Header
        self._add(UILabel(pygame.Rect(10, y, 880, 30), "Your Party Members", manager))

        # Party members list (left side)
        self._add(UILabel(pygame.Rect(10, y + 40, 300, 25), "Party Members:", manager))

        party_names = []
        for card in game.current_party:
            card_data = card.get_current_data()
            name = card_data.get("Name", "Unknown")
            deployed = any(u.card_id == card.card_data.get("id") for u in game_screen.hex_grid.units if u.allegiance == "Allied")
            status = " [Deployed]" if deployed else ""
            party_names.append(f"{name}{status}")

        self.party_list = self._add(pygame_gui.elements.UISelectionList(
            pygame.Rect(10, y + 70, 300, 400),
            party_names if party_names else ["No party members"],
            manager))
        self.party_member_names = party_names if party_names else []

        # Info panel (right side)
        self._add(UILabel(pygame.Rect(320, y + 40, 560, 25), "Member Details:", manager))
        self.party_info_text = self._add(pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select a party member to view details</font>",
            pygame.Rect(320, y + 70, 560, 350), manager))

        # Action buttons
        self.party_deploy_button = self._add(UIButton(pygame.Rect(320, y + 430, 170, 35), "Deploy to Map", manager))
        self.party_recall_button = self._add(UIButton(pygame.Rect(500, y + 430, 170, 35), "Recall to Party", manager))
        self.party_dismiss_button = self._add(UIButton(pygame.Rect(320, y + 475, 350, 35), "Dismiss from Party", manager))

        # Creative mode button (browse all NPCs)
        if game.game_mode == "creative":
            self.party_browse_npcs_button = self._add(UIButton(pygame.Rect(320, y + 520, 170, 35), "Browse NPCs", manager))
            self._add(UILabel(pygame.Rect(500, y + 520, 150, 35), "[Creative Mode]", manager))
        else:
            self.party_browse_npcs_button = None

    def _handle_party_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if self.party_browse_npcs_button and event.ui_element == self.party_browse_npcs_button:
                game.current_screen = "npc_browser"
                npc_browser_screen.initialize_screen()
                return
            if event.ui_element == self.party_deploy_button:
                self._party_deploy_member()
                return
            if event.ui_element == self.party_recall_button:
                self._party_recall_member()
                return
            if event.ui_element == self.party_dismiss_button:
                self._party_dismiss_member()
                return

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.party_list:
                selection = self.party_list.get_single_selection()
                if selection and selection != "No party members" and selection in self.party_member_names:
                    idx = self.party_member_names.index(selection)
                    if idx < len(game.current_party):
                        self.party_selected_member = idx
                        card = game.current_party[idx]
                        card_data = card.get_current_data()

                        info_lines = []
                        info_lines.append(f"<b>{card_data.get('Name', 'Unknown')}</b>")
                        info_lines.append(f"")
                        info_lines.append(f"Health: {card_data.get('Health', '?')}")
                        info_lines.append(f"Movement: {card_data.get('Movement', '?')}")
                        info_lines.append(f"Melee Damage: {card_data.get('Melee Damage', '0')}")
                        if card_data.get('Projectile Damage'):
                            info_lines.append(f"Projectile Damage: {card_data.get('Projectile Damage')}")
                            info_lines.append(f"Projectile Range: {card_data.get('Projectile Range', '0')}")
                        if card_data.get('Special Skill'):
                            info_lines.append(f"Special Skill: {card_data.get('Special Skill')}")
                        if card_data.get('Description'):
                            info_lines.append(f"")
                            info_lines.append(f"{card_data.get('Description')}")

                        self.party_info_text.set_text(f"<font color='#FFFFFF'>{'<br>'.join(info_lines)}</font>")

    def _party_deploy_member(self):
        if self.party_selected_member is None:
            self.party_info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = game.current_party[self.party_selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        already_deployed = any(u.card_id == card.card_data.get("id") for u in game_screen.hex_grid.units if u.allegiance == "Allied")
        if already_deployed:
            self.party_info_text.set_text(f"<font color='#FF0000'>{name} is already deployed!</font>")
            return

        player_pos = game.current_player.position
        neighbors = game_screen.hex_grid.get_neighbors(*player_pos)
        deploy_pos = None
        for n in neighbors:
            row, col = n
            if 0 <= row < game_screen.hex_grid.rows and 0 <= col < game_screen.hex_grid.cols:
                cell = game_screen.hex_grid.grid[row][col]
                if cell["unit"] is None and cell.get("accessible", True):
                    deploy_pos = n
                    break

        if not deploy_pos:
            self.party_info_text.set_text(f"<font color='#FF0000'>No space near player to deploy {name}!</font>")
            return

        from unit import Unit
        unit_data = {
            "id": card.card_data.get("id"),
            "card_type": "NPC Card",
            "states": card.states,
            "data": card_data
        }
        unit = Unit(unit_data)
        unit.allegiance = "Allied"
        game_screen.hex_grid.place_unit(unit, deploy_pos[0], deploy_pos[1])

        game_screen.add_to_log(f"{name} deployed to the battlefield!")
        self.party_info_text.set_text(f"<font color='#00FF00'>{name} deployed!</font>")
        self._refresh_current_tab()

    def _party_recall_member(self):
        if self.party_selected_member is None:
            self.party_info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = game.current_party[self.party_selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        deployed_unit = None
        for unit in game_screen.hex_grid.units:
            if unit.card_id == card.card_data.get("id") and unit.allegiance == "Allied":
                deployed_unit = unit
                break

        if not deployed_unit:
            self.party_info_text.set_text(f"<font color='#FF0000'>{name} is not deployed!</font>")
            return

        player_pos = game.current_player.position
        unit_pos = deployed_unit.position
        distance = game_screen.hex_grid.hex_distance(player_pos, unit_pos)
        if distance > 1:
            self.party_info_text.set_text(f"<font color='#FF0000'>{name} must be adjacent to recall!</font>")
            return

        game_screen.hex_grid.grid[deployed_unit.position[0]][deployed_unit.position[1]]["unit"] = None
        game_screen.hex_grid.units.remove(deployed_unit)

        game_screen.add_to_log(f"{name} recalled to party.")
        self.party_info_text.set_text(f"<font color='#00FF00'>{name} recalled!</font>")
        self._refresh_current_tab()

    def _party_dismiss_member(self):
        if self.party_selected_member is None:
            self.party_info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = game.current_party[self.party_selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        for unit in game_screen.hex_grid.units[:]:
            if unit.card_id == card.card_data.get("id") and unit.allegiance == "Allied":
                game_screen.hex_grid.grid[unit.position[0]][unit.position[1]]["unit"] = None
                game_screen.hex_grid.units.remove(unit)
                break

        game.current_party.remove(card)
        game_screen.add_to_log(f"{name} dismissed from party.")
        self.party_selected_member = None
        self._refresh_current_tab()

    # ========================
    # QUESTS TAB
    # ========================
    def _build_quests_content(self):
        self.quest_selected_quest = None
        y = self.CONTENT_Y

        # Sub-tab buttons for active/completed/failed
        tab_y = y
        tab_width = 150
        self.quest_tab_buttons = []

        active_count = len(game.current_quest_manager.active_quests)
        completed_count = len(game.current_quest_manager.completed_quests)
        failed_count = len(game.current_quest_manager.failed_quests)

        active_btn = self._add(UIButton(pygame.Rect(10, tab_y, tab_width, 30), f"Active ({active_count})", manager))
        self.quest_tab_buttons.append(("active", active_btn))

        completed_btn = self._add(UIButton(pygame.Rect(170, tab_y, tab_width, 30), f"Completed ({completed_count})", manager))
        self.quest_tab_buttons.append(("completed", completed_btn))

        failed_btn = self._add(UIButton(pygame.Rect(330, tab_y, tab_width, 30), f"Failed ({failed_count})", manager))
        self.quest_tab_buttons.append(("failed", failed_btn))

        # Quest list (left panel)
        self._add(UILabel(pygame.Rect(10, tab_y + 40, 350, 25), "Quests:", manager))

        quest_names = self._quest_get_names_for_tab()
        self.quest_names = quest_names
        self.quest_list = self._add(pygame_gui.elements.UISelectionList(
            pygame.Rect(10, tab_y + 70, 350, 500),
            quest_names if quest_names else ["No quests"],
            manager))

        # Quest details (right panel)
        self._add(UILabel(pygame.Rect(370, tab_y + 40, 600, 25), "Quest Details:", manager))
        self.quest_details = self._add(pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select a quest to view details</font>",
            pygame.Rect(370, tab_y + 70, 600, 500), manager))

        # Abandon button (only for active tab)
        if self.quest_current_tab == "active":
            self.quest_abandon_button = self._add(UIButton(
                pygame.Rect(370, tab_y + 580, 150, 35), "Abandon Quest", manager))
        else:
            self.quest_abandon_button = None

    def _quest_get_names_for_tab(self):
        if self.quest_current_tab == "active":
            return [q.get_display_name() for q in game.current_quest_manager.active_quests]
        elif self.quest_current_tab == "completed":
            return [q.get_display_name() for q in game.current_quest_manager.completed_quests]
        elif self.quest_current_tab == "failed":
            return [q.get_display_name() for q in game.current_quest_manager.failed_quests]
        return []

    def _quest_get_quests_for_tab(self):
        if self.quest_current_tab == "active":
            return game.current_quest_manager.active_quests
        elif self.quest_current_tab == "completed":
            return game.current_quest_manager.completed_quests
        elif self.quest_current_tab == "failed":
            return game.current_quest_manager.failed_quests
        return []

    def _quest_update_details(self):
        if not self.quest_selected_quest:
            self.quest_details.set_text("<font color='#FFFFFF'>Select a quest to view details</font>")
            return

        quest = self.quest_selected_quest
        lines = []
        lines.append(f"<b>{quest.get_display_name()}</b>")
        lines.append("")

        if quest.is_complete:
            lines.append("<font color='#00FF00'>Status: COMPLETED</font>")
        elif quest.is_failed:
            lines.append("<font color='#FF0000'>Status: FAILED</font>")
        else:
            lines.append("<font color='#FFFF00'>Status: IN PROGRESS</font>")
        lines.append("")

        lines.append("<b>Description:</b>")
        lines.append(quest.get_filled_description())
        lines.append("")

        if quest.tracked_units:
            lines.append("<b>Tracked Characters:</b>")
            for pid, unit in quest.tracked_units.items():
                status = "Active" if unit.hp > 0 else "Defeated"
                lines.append(f"- {pid}: {unit.name} ({status})")
            lines.append("")

        if quest.tracked_locations:
            lines.append("<b>Tracked Locations:</b>")
            for pid, pos in quest.tracked_locations.items():
                lines.append(f"- {pid}: Position {pos}")
            lines.append("")

        lines.append(f"Turns elapsed: {quest.turn_count}")
        self.quest_details.set_text(f"<font color='#FFFFFF'>{'<br>'.join(lines)}</font>")

    def _handle_quests_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            # Quest sub-tab buttons
            for tab_name, btn in self.quest_tab_buttons:
                if event.ui_element == btn:
                    self.quest_current_tab = tab_name
                    self.quest_selected_quest = None
                    self._refresh_current_tab()
                    return

            # Abandon button
            if self.quest_abandon_button and event.ui_element == self.quest_abandon_button:
                if self.quest_selected_quest:
                    success, msg = game.current_quest_manager.abandon_quest(self.quest_selected_quest)
                    game_screen.add_to_log(msg)
                    self.quest_selected_quest = None
                    self._refresh_current_tab()
                return

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.quest_list:
                selection = self.quest_list.get_single_selection()
                if selection and selection != "No quests" and selection in self.quest_names:
                    idx = self.quest_names.index(selection)
                    quests = self._quest_get_quests_for_tab()
                    if idx < len(quests):
                        self.quest_selected_quest = quests[idx]
                        self._quest_update_details()

    # ========================
    # MAIN EVENT HANDLER & DRAW
    # ========================
    def handle_event(self, event):
        # ESC to close
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            game.current_screen = "game"
            game_screen.initialize_screen()
            return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            # Close button
            if event.ui_element == self.close_button:
                game.current_screen = "game"
                game_screen.initialize_screen()
                return

            # Tab buttons
            for name, btn in self.tab_buttons.items():
                if event.ui_element == btn and name != self.active_tab:
                    self.switch_tab(name)
                    return

        # Delegate to active tab handler
        if self.active_tab == "Inventory":
            self._handle_inventory_event(event)
        elif self.active_tab == "Crafting":
            self._handle_crafting_event(event)
        elif self.active_tab == "Skills":
            self._handle_skills_event(event)
        elif self.active_tab == "Party":
            self._handle_party_event(event)
        elif self.active_tab == "Quests":
            self._handle_quests_event(event)

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        # Draw active tab highlight (underline bar)
        if self.active_tab in self.tab_buttons:
            btn = self.tab_buttons[self.active_tab]
            rect = btn.relative_rect
            pygame.draw.rect(screen, GOLDEN_YELLOW, (rect.x, rect.y + rect.height, rect.width, 3))
        manager.draw_ui(screen)


# Player Count Selection Screen (shown after selecting a level file)
class PlayerCountScreen:
    def __init__(self):
        self.ui_elements = []
        self.level_file = None
        self.mode_buttons = []
        self.selected_mode = "survival"

    def initialize_screen(self, level_file=None):
        self.level_file = level_file
        self.selected_mode = "survival"  # Reset to default
        manager.clear_and_reset()
        level_name = os.path.basename(level_file) if level_file else "Unknown"

        # Mode selection
        mode_label = UILabel(pygame.Rect(0, 50, WINDOW_WIDTH, 30), "Select Game Mode", manager, anchors={'centerx': 'centerx'})
        survival_btn = UIButton(pygame.Rect((WINDOW_WIDTH - 420) // 2, 90, 200, 40), "Survival Mode", manager)
        creative_btn = UIButton(pygame.Rect((WINDOW_WIDTH - 420) // 2 + 220, 90, 200, 40), "Creative Mode", manager)
        mode_desc = UILabel(pygame.Rect(0, 140, WINDOW_WIDTH, 25), "Survival: Normal gameplay | Creative: Test with card browser", manager, anchors={'centerx': 'centerx'})

        # Player count selection
        self.ui_elements = [
            UILabel(pygame.Rect(0, 190, WINDOW_WIDTH, 50), "Select Number of Players", manager, anchors={'centerx': 'centerx'}),
            UILabel(pygame.Rect(0, 240, WINDOW_WIDTH, 30), f"Level: {level_name}", manager, anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, 290, 200, 50), "1 Player", manager),
            UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, 360, 200, 50), "2 Players", manager),
            UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, 460, 200, 50), "Back", manager)
        ]
        self.mode_buttons = [survival_btn, creative_btn]
        self.mode_label = mode_label
        self.mode_desc = mode_desc
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        """Update button appearance based on selected mode."""
        # Visual feedback - we'll just update the text to show selection
        if self.selected_mode == "survival":
            self.mode_buttons[0].set_text(">> Survival <<")
            self.mode_buttons[1].set_text("Creative Mode")
        else:
            self.mode_buttons[0].set_text("Survival Mode")
            self.mode_buttons[1].set_text(">> Creative <<")

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.mode_buttons[0]:  # Survival
                self.selected_mode = "survival"
                self._update_mode_buttons()
            elif event.ui_element == self.mode_buttons[1]:  # Creative
                self.selected_mode = "creative"
                self._update_mode_buttons()
            elif event.ui_element == self.ui_elements[2]:  # 1 Player
                game.game_mode = self.selected_mode
                game.current_screen = "character_creation"
                character_creation_screen.initialize_screen(level_file=self.level_file)
            elif event.ui_element == self.ui_elements[3]:  # 2 Players
                game.game_mode = self.selected_mode
                game.current_screen = "multiplayer_character_creation"
                multiplayer_character_creation_screen.initialize_screen(level_file=self.level_file)
            elif event.ui_element == self.ui_elements[4]:  # Back
                game.current_screen = "main_menu"
                main_menu.initialize_buttons()

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# Main Menu screen (updated to include Load Campaign)
class MainMenu:
    def __init__(self):
        self.ui_elements = []
        self.initialize_buttons()

    def initialize_buttons(self):
        manager.clear_and_reset()
        btn_x = (WINDOW_WIDTH - 200) // 2
        self.ui_elements = [
            UILabel(pygame.Rect(0, 50, WINDOW_WIDTH, 50), "Hex-Grid RPG", manager, object_id="#title_label", anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect(btn_x, 200, 200, 50), "New Campaign", manager),
            UIButton(pygame.Rect(btn_x, 270, 200, 50), "Load Campaign", manager),
            UIButton(pygame.Rect(btn_x, 340, 200, 50), "Load Level", manager),
            UIButton(pygame.Rect(btn_x, 410, 200, 50), "Load Game", manager),
            UIButton(pygame.Rect(btn_x, 480, 200, 50), "2-Player Local", manager),
            UIButton(pygame.Rect(btn_x, 550, 200, 50), "Settings", manager),
            UIButton(pygame.Rect(btn_x, 620, 200, 50), "Quit", manager)
        ]

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            text = event.ui_element.text
            if text == "New Campaign":
                game.current_screen = "character_creation"
                character_creation_screen.initialize_screen()
            elif text == "Load Campaign":
                root = tk.Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(initialdir="campaigns", filetypes=[("JSON files", "*.json")])
                root.destroy()
                if file_path:
                    game.current_screen = "character_creation"
                    character_creation_screen.initialize_screen(campaign_file=file_path)
                else:
                    print("No campaign file selected")
            elif text == "Load Level":
                root = tk.Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(initialdir="levels", filetypes=[("JSON files", "*.json")])
                root.destroy()
                if file_path:
                    game.current_screen = "player_count"
                    player_count_screen.initialize_screen(level_file=file_path)
                else:
                    print("No level file selected")
            elif text == "Load Game":
                game.current_screen = "save_load"
                save_load_screen.initialize_screen(mode="load")
            elif text == "2-Player Local":
                game.current_screen = "multiplayer_character_creation"
                multiplayer_character_creation_screen.initialize_screen()
            elif text == "Settings":
                game.current_screen = "settings"
                settings_screen.initialize_screen()
            elif text == "Quit":
                pygame.quit()
                sys.exit()

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        # Decorative background hex pattern
        hex_s = 40
        pat_color = (30, 30, 70)
        for pr in range(0, WINDOW_HEIGHT + hex_s * 2, int(hex_s * 1.732)):
            for pc in range(0, WINDOW_WIDTH + hex_s * 2, int(hex_s * 1.5)):
                offset = hex_s * 0.866 if (pc // int(hex_s * 1.5)) % 2 else 0
                pts = [(pc + hex_s * math.cos(math.radians(60 * i)),
                        pr + offset + hex_s * math.sin(math.radians(60 * i))) for i in range(6)]
                pygame.draw.polygon(screen, pat_color, pts, 1)
        # Styled title
        title_font = pygame.font.Font(None, 80)
        subtitle_font = pygame.font.Font(None, 28)
        title_text = "Hex-Grid RPG"
        shadow = title_font.render(title_text, True, (10, 10, 30))
        title = title_font.render(title_text, True, (200, 180, 120))
        tr = title.get_rect(centerx=WINDOW_WIDTH // 2, y=50)
        screen.blit(shadow, tr.move(3, 3))
        screen.blit(title, tr)
        # Decorative line under title
        line_y = tr.bottom + 10
        pygame.draw.line(screen, (120, 100, 60), (WINDOW_WIDTH // 2 - 140, line_y), (WINDOW_WIDTH // 2 + 140, line_y), 1)
        # Subtitle
        sub = subtitle_font.render("A Card-Based Tactical Adventure", True, (120, 120, 160))
        sr = sub.get_rect(centerx=WINDOW_WIDTH // 2, y=line_y + 8)
        screen.blit(sub, sr)
        # Version text
        ver_font = pygame.font.Font(None, 18)
        ver = ver_font.render("v0.34", True, (80, 80, 110))
        screen.blit(ver, (WINDOW_WIDTH - 60, WINDOW_HEIGHT - 30))
        manager.draw_ui(screen)

# Character Creation screen (updated to accept campaign_file)
class CharacterCreationScreen:
    def __init__(self):
        self.ui_elements = []
        self.class_buttons = []
        self.level_file = None
        self.campaign_file = None
        self.name_entry = None

    def initialize_screen(self, level_file=None, campaign_file=None):
        self.level_file = level_file
        self.campaign_file = campaign_file
        manager.clear_and_reset()
        self.ui_elements = [
            UILabel(pygame.Rect(0, 30, WINDOW_WIDTH, 40), "Enter Your Name", manager, anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect(20, 20, 100, 50), "Back", manager)
        ]
        self.name_entry = UITextEntryLine(pygame.Rect((WINDOW_WIDTH - 250) // 2, 70, 250, 40), manager, placeholder_text="Player Name")
        self.ui_elements.append(self.name_entry)
        self.ui_elements.append(UILabel(pygame.Rect(0, 120, WINDOW_WIDTH, 40), "Choose Your Class", manager, anchors={'centerx': 'centerx'}))
        self.class_buttons = []
        for i, (class_name, stats) in enumerate(CHARACTER_CLASSES.items()):
            y_pos = 170 + i * 100
            button = UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 50), class_name, manager)
            self.class_buttons.append((button, class_name))
            self.ui_elements.append(button)
            desc = f"{stats['hp']} HP, {stats['movement']} Movement, {stats['projectile_range']} Range, " \
                   f"{list(stats['attacks'].keys())[0]} ({list(stats['attacks'].values())[0]} dmg), " \
                   f"{list(stats['attacks'].keys())[1]} ({list(stats['attacks'].values())[1]} dmg), {stats['special_attack']}"
            self.ui_elements.append(UILabel(pygame.Rect((WINDOW_WIDTH - 600) // 2, y_pos + 60, 600, 30), desc, manager))

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.ui_elements[1]:
                game.current_screen = "main_menu"
                main_menu.initialize_buttons()
            else:
                for button, class_name in self.class_buttons:
                    if event.ui_element == button:
                        game.player = Player(class_name)
                        entered_name = self.name_entry.get_text().strip() if self.name_entry else ""
                        game.player.name = entered_name if entered_name else class_name
                        game.current_screen = "game"
                        game_screen.start_new_game(level_file=self.level_file, campaign_file=self.campaign_file)
                        break

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# Multiplayer Character Creation Screen (2-player local)
class MultiplayerCharacterCreationScreen:
    def __init__(self):
        self.ui_elements = []
        self.class_buttons = []
        self.current_player_selecting = 1  # 1 or 2
        self.player1_class = None
        self.player1_name = ""
        self.level_file = None
        self.name_entry = None

    def initialize_screen(self, level_file=None):
        self.level_file = level_file
        self.current_player_selecting = 1
        self.player1_class = None
        self.player1_name = ""
        manager.clear_and_reset()
        self._build_selection_ui()

    def _build_selection_ui(self):
        """Build the class selection UI for the current player."""
        manager.clear_and_reset()
        player_label = f"Player {self.current_player_selecting}: Enter Name & Choose Class"
        color_hint = "(Green)" if self.current_player_selecting == 1 else "(Blue)"
        self.ui_elements = [
            UILabel(pygame.Rect(0, 30, WINDOW_WIDTH, 40), player_label, manager, anchors={'centerx': 'centerx'}),
            UILabel(pygame.Rect(0, 70, WINDOW_WIDTH, 30), color_hint, manager, anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect(20, 20, 100, 50), "Back", manager)
        ]
        placeholder = f"Player {self.current_player_selecting} Name"
        self.name_entry = UITextEntryLine(pygame.Rect((WINDOW_WIDTH - 250) // 2, 105, 250, 40), manager, placeholder_text=placeholder)
        self.ui_elements.append(self.name_entry)
        self.class_buttons = []
        for i, (class_name, stats) in enumerate(CHARACTER_CLASSES.items()):
            y_pos = 170 + i * 100
            button = UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 50), class_name, manager)
            self.class_buttons.append((button, class_name))
            self.ui_elements.append(button)
            desc = f"{stats['hp']} HP, {stats['movement']} Movement, {stats['projectile_range']} Range, " \
                   f"{list(stats['attacks'].keys())[0]} ({list(stats['attacks'].values())[0]} dmg), " \
                   f"{list(stats['attacks'].keys())[1]} ({list(stats['attacks'].values())[1]} dmg), {stats['special_attack']}"
            self.ui_elements.append(UILabel(pygame.Rect((WINDOW_WIDTH - 600) // 2, y_pos + 60, 600, 30), desc, manager))

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.ui_elements[2]:  # Back button
                if self.current_player_selecting == 2:
                    # Go back to player 1 selection
                    self.current_player_selecting = 1
                    self.player1_class = None
                    self.player1_name = ""
                    self._build_selection_ui()
                else:
                    game.current_screen = "main_menu"
                    main_menu.initialize_buttons()
            else:
                for button, class_name in self.class_buttons:
                    if event.ui_element == button:
                        entered_name = self.name_entry.get_text().strip() if self.name_entry else ""
                        if self.current_player_selecting == 1:
                            # Store Player 1's name and class, move to Player 2 selection
                            self.player1_class = class_name
                            self.player1_name = entered_name if entered_name else "Player 1"
                            self.current_player_selecting = 2
                            self._build_selection_ui()
                        else:
                            # Both players selected - start the game
                            player2_name = entered_name if entered_name else "Player 2"
                            self._start_multiplayer_game(self.player1_class, class_name, self.player1_name, player2_name)
                        break

    def _start_multiplayer_game(self, player1_class, player2_class, player1_name, player2_name):
        """Create both players and start the multiplayer game."""
        # Create Player 1
        player1 = Player(player1_class)
        player1.name = player1_name
        player1.player_number = 1
        player1.player_color = (0, 200, 0)  # Green
        player1.party = []

        # Create Player 2
        player2 = Player(player2_class)
        player2.name = player2_name
        player2.player_number = 2
        player2.player_color = (100, 150, 255)  # Blue
        player2.party = []

        # Set up multiplayer mode
        game.multiplayer_mode = True
        game.players = [player1, player2]
        game.current_player_index = 0
        game.player = player1  # For backwards compatibility

        # Create per-player quest managers
        game.quest_managers = [
            QuestManager(game.card_manager),
            QuestManager(game.card_manager)
        ]

        # Start the game
        game.current_screen = "game"
        game_screen.start_new_game_multiplayer(level_file=self.level_file)

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# Settings screen
class SettingsScreen:
    def __init__(self):
        self.ui_elements = []

    def initialize_screen(self):
        manager.clear_and_reset()
        self.ui_elements = [
            UILabel(pygame.Rect(0, 50, WINDOW_WIDTH, 50), "Settings", manager, anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect(20, 20, 150, 50), "Back to Main Menu", manager)
        ]

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED and event.ui_element == self.ui_elements[1]:
            game.current_screen = "main_menu"
            main_menu.initialize_buttons()

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)

# GameScreen class
class GameScreen:
    def __init__(self):
        self.hex_grid = None
        self.ui_elements = []
        self.left_panel_buttons = []
        self.selected_unit = None
        self.card_manager = None
        self.log = []
        self.log_minimized = True  # Log starts minimized
        self.log_toggle_button = None
        self.log_mini_label = None  # Single-line minimized log
        self.is_player_turn = True
        self.selected_attack = None
        self.turn_phase = "player"
        self.animating = False
        self.dragging = False
        self.drag_button = None  # Track which button started the drag (2=middle, 3=right)
        self.drag_start_x = self.drag_start_y = self.start_view_offset_x = self.start_view_offset_y = 0
        self.player_mode = "movement"
        self.selected_skill = None  # Currently selected skill for use
        self.skill_buttons = []     # List of (button, skill_card) tuples
        self.skills_button = None   # Skills menu button
        self.special_attack_button = None  # Special attack button
        self.attack_button = None  # Main "Attack" button that opens submenu
        self.attack_submenu_open = False
        self.attack_submenu_buttons = []  # List of (button, action_type, data)
        # Recruitment mode
        self.recruit_button = None
        self.recruit_info_panel = None  # Panel showing adjacent NPC costs
        self.player_info_label = None
        self.game_started = False
        self.campaign = None
        self.campaign_file = None
        self.current_level_idx = 0
        self.current_level_file = None
        self.initial_inventory = []
        self.initial_melee_weapon = None
        self.initial_projectile_weapon = None
        self.player_class = None  # Store player's class for reset
        # Turn queue for consecutive unit animations
        self.turn_queue = []  # Queue of (unit, allegiance) tuples waiting to act
        self.current_acting_unit = None  # Unit currently taking its turn
        self.turn_action_delay = 500  # Delay in ms between unit actions
        self.last_action_time = 0  # Time of last unit action
        self.waiting_for_animation = False  # Whether we're waiting for animation to finish
        # Pending location screen (show after movement animation completes)
        self.pending_location = None  # {"card": loc_card, "pos": hex_pos, "hex_grid": hex_grid}
        # Pending defeat screen (show after death animation completes)
        self.pending_defeat = False
        self.defeat_notifications = []  # [(name, timestamp), ...]
        self.current_location_hex = None  # (row, col) if player is on a location
        # Building/placement mode
        self.placement_mode = False
        self.placement_card = None  # The location card being placed
        # Multiplayer transition target cycle: 0=P1, 1=P2, 2=Both
        self.transition_target_cycle = 0
        # Turn cycle counter for autosave timing
        self.turn_cycle_count = 0
        # Save manager
        self.save_manager = SaveManager()
        # Equipment toolbar (bottom of screen)
        self.equip_toolbar_buttons = []    # 6 UIButtons for Melee/Proj/Acc/Tool/Action/Items slots
        self.equip_action_tool = None      # Reference to the equipped tool providing the current action
        self.equip_popup_open = False      # Whether a popup is showing
        self.equip_popup_slot = None       # "melee"/"projectile"/"tool"/"accessory"
        self.equip_popup_buttons = []      # List of (UIButton, slot_type, data) tuples
        # Items button / consumable targeting mode
        self.selected_item = None          # Consumable card selected for use
        self.item_targeting_mode = False   # Whether in item targeting mode
        # Action choice popup (shown when multiple actions available on a unit)
        self.action_choice_open = False
        self.action_choice_buttons = []    # List of (button, action_type, data) tuples
        self.action_choice_target = None   # The unit being targeted
        # Right panel layout (computed in initialize_screen)
        self.rp_width = 234
        self.rp_pad = 10
        self.rp_x = 0
        self.rp_inner_w = 0
        self.rp_pi_y = 0
        self.rp_stats_y = 0
        self.rp_menu_y = 0
        self.rp_height = 0
        self.rp_header_font = pygame.font.SysFont("Arial", 13, bold=True)
        self.colors = {
            'BLUE': BLUE,
            'DARK_RED_ALPHA': DARK_RED_ALPHA,
            'LIGHT_GREEN': LIGHT_GREEN,
            'YELLOW': YELLOW,
            'GOLDEN_YELLOW': GOLDEN_YELLOW,
            'GREEN': GREEN,
            'RED': RED,
            'GRAY': (128, 128, 128),
            'WHITE': WHITE,
            'PURPLE': PURPLE,  # Added for linked level hexes
            'ORANGE': ORANGE   # Added for location hexes
        }

    def add_defeat_notification(self, name):
        self.defeat_notifications.append((name, pygame.time.get_ticks()))

    def draw_defeat_notifications(self):
        now = pygame.time.get_ticks()
        self.defeat_notifications = [(n, t) for n, t in self.defeat_notifications if now - t < 3000]
        if not self.defeat_notifications:
            return
        font = pygame.font.SysFont("Arial", 36, bold=True)
        shadow_font = pygame.font.SysFont("Arial", 36, bold=True)
        cx = WINDOW_WIDTH // 2
        start_y = WINDOW_HEIGHT // 3
        for i, (name, timestamp) in enumerate(self.defeat_notifications):
            elapsed = now - timestamp
            alpha = 255 if elapsed < 2000 else max(0, 255 - int(255 * (elapsed - 2000) / 1000))
            # Upward drift: float up 30px over the full duration
            drift_y = int(30 * elapsed / 3000)
            text = f"{name} defeated!"
            text_surf = font.render(text, True, (255, 215, 0))
            shadow_surf = shadow_font.render(text, True, (0, 0, 0))
            tw, th = text_surf.get_size()
            bw, bh = tw + 40, th + 20
            by = start_y + i * (bh + 10) - drift_y
            banner = pygame.Surface((bw, bh), pygame.SRCALPHA)
            # Dark background with subtle border
            banner.fill((10, 10, 30, min(alpha, 200)))
            pygame.draw.rect(banner, (58, 58, 92, min(alpha, 160)), (0, 0, bw, bh), 1)
            # Text shadow then gold text
            banner.blit(shadow_surf, (22, 12))
            banner.blit(text_surf, (20, 10))
            banner.set_alpha(alpha)
            screen.blit(banner, (cx - bw // 2, by))

    def set_card_manager(self, card_manager):
        self.card_manager = card_manager

    def start_new_game(self, level_file=None, campaign_file=None):
        # Reset game state
        self.hex_grid = HexGrid(16, 24, 30, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.current_level_file = level_file
        self.campaign_file = campaign_file
        self.log.clear()
        self.turn_phase = "player"
        self.is_player_turn = True
        self.hex_grid.game_over = False
        # Reset turn queue
        self.turn_queue = []
        self.current_acting_unit = None
        self.waiting_for_animation = False
        self.pending_location = None
        self.pending_defeat = False
        self.defeat_notifications = []
        self.current_location_hex = None
        self.transition_target_cycle = 0
        self.selected_item = None
        self.item_targeting_mode = False
        self.action_choice_open = False
        self.action_choice_buttons = []
        self.action_choice_target = None
        # Reset party
        game.party = []
        # Reset quest manager
        game.quest_manager = QuestManager(self.card_manager)
        # Reset instance manager and try to load test deck
        game.instance_manager = InstanceManager(self.card_manager, self.hex_grid)
        game.instance_manager.load_instance_deck("test_instance_deck.json")
        # Reset transition manager and try to load test transition card
        game.transition_manager = TransitionManager(self.card_manager, game.instance_manager)
        game.transition_manager.load_transition_card("test_transition_forest")

        # Store the current player's class for future reference
        # (CharacterCreationScreen already created the player with the correct class)
        if game.player:
            self.player_class = game.player.class_name
        
        # Load campaign or level
        if campaign_file:
            try:
                with open(campaign_file, 'r') as f:
                    self.campaign = json.load(f)
                self.load_campaign_level()
                self.log.append(f"Loaded campaign: {campaign_file}")
            except Exception as e:
                print(f"Error loading campaign file '{campaign_file}': {e}")
                self.hex_grid.place_unit(game.player, self.hex_grid.rows // 2, self.hex_grid.cols // 2)
                self.log.append("Failed to load campaign. Starting default level.")
        elif level_file:
            try:
                self.hex_grid.load_level(level_file, self.card_manager, game.player)
                self.log.append(f"Loaded level: {level_file}")
            except Exception as e:
                print(f"Error loading level '{level_file}': {e}")
                self.hex_grid.place_unit(game.player, self.hex_grid.rows // 2, self.hex_grid.cols // 2)
                self.log.append("Failed to load level. Starting default level.")
        else:
            self.hex_grid.place_unit(game.player, self.hex_grid.rows // 2, self.hex_grid.cols // 2)
            self.log.append("Started default level.")

        # Load class-specific starter kit
        from player import CHARACTER_CLASSES
        starter_kit = CHARACTER_CLASSES.get(game.player.class_name, {}).get("starting_kit", [])
        for item in starter_kit:
            card_id = item.get("card_id")
            card_data = load_card(card_id)
            if card_data:
                inv_card = InventoryCard(card_data)
                if item.get("state", 1) == 2:
                    inv_card.current_state = 2
                game.player.inventory.append(inv_card)
                print(f"Added starter kit item: {inv_card.get_current_data().get('Name', card_id)}")
            else:
                print(f"Warning: Starter kit card '{card_id}' not found")

        # Store initial state after loading
        self.initial_inventory = game.player.inventory.copy()
        self.initial_melee_weapon = game.player.melee_weapon
        self.initial_projectile_weapon = game.player.projectile_weapon
        
        # Ensure player's HP is reset
        game.player.hp = game.player.max_hp
        
        # Reset equipped weapons
        game.player.melee_weapon = None
        game.player.projectile_weapon = None
        if self.initial_melee_weapon:
            game.player.equip_weapon(self.initial_melee_weapon)
        if self.initial_projectile_weapon:
            game.player.equip_weapon(self.initial_projectile_weapon)
        
        # Reset movement and action flags
        game.player.movement_used = False
        game.player.action_used = False
        game.player.reset_double_attack()

        # Ensure all units are reset and active
        for unit in self.hex_grid.units:
            unit.hp = unit.max_hp
            unit.current_state = 1  # Reset to initial state if applicable
        
        self.hex_grid.active_turn_unit = game.player
        self.game_started = True
        self.turn_cycle_count = 0
        self.initialize_screen()
        # Autosave at level start
        self.save_manager.save_game(game, self, save_type="autosave", save_label="Level Start")

    def start_new_game_multiplayer(self, level_file=None):
        """Start a new multiplayer game with two players."""
        # Reset game state
        self.hex_grid = HexGrid(16, 24, 30, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.hex_grid.players = game.players  # Set players list on hex_grid
        self.current_level_file = level_file
        self.campaign_file = None
        self.log.clear()
        self.turn_phase = "player1"  # Start with player 1's turn
        self.is_player_turn = True
        self.hex_grid.game_over = False
        # Reset turn queue
        self.turn_queue = []
        self.current_acting_unit = None
        self.waiting_for_animation = False
        self.pending_location = None
        self.pending_defeat = False
        self.current_location_hex = None
        self.transition_target_cycle = 0

        # Reset instance manager and try to load test deck
        game.instance_manager = InstanceManager(self.card_manager, self.hex_grid)
        game.instance_manager.load_instance_deck("test_instance_deck.json")
        # Reset transition manager and try to load test transition card
        game.transition_manager = TransitionManager(self.card_manager, game.instance_manager)
        game.transition_manager.load_transition_card("test_transition_forest")

        # Load level or use default placement
        player1 = game.players[0]
        player2 = game.players[1]

        if level_file:
            try:
                # Load level with player 1 first
                self.hex_grid.load_level(level_file, self.card_manager, player1)
                self.log.append(f"Loaded level: {level_file}")
                # Find adjacent position for player 2
                p1_pos = player1.position
                neighbors = self.hex_grid.get_neighbors(p1_pos[0], p1_pos[1])
                p2_placed = False
                for n_row, n_col in neighbors:
                    if (0 <= n_row < self.hex_grid.rows and 0 <= n_col < self.hex_grid.cols and
                        self.hex_grid.grid[n_row][n_col]["unit"] is None and
                        self.hex_grid.grid[n_row][n_col]["accessible"]):
                        self.hex_grid.place_unit(player2, n_row, n_col)
                        p2_placed = True
                        break
                if not p2_placed:
                    # Fallback: place near center
                    self.hex_grid.place_unit(player2, self.hex_grid.rows // 2 + 1, self.hex_grid.cols // 2)
            except Exception as e:
                print(f"Error loading level '{level_file}': {e}")
                # Place both players in default positions
                self.hex_grid.place_unit(player1, self.hex_grid.rows // 2, self.hex_grid.cols // 2)
                self.hex_grid.place_unit(player2, self.hex_grid.rows // 2 + 1, self.hex_grid.cols // 2)
                self.log.append("Failed to load level. Starting default level.")
        else:
            # Default placement
            self.hex_grid.place_unit(player1, self.hex_grid.rows // 2, self.hex_grid.cols // 2)
            self.hex_grid.place_unit(player2, self.hex_grid.rows // 2 + 1, self.hex_grid.cols // 2)
            self.log.append("Started default level (2-Player).")

        # Load class-specific starter kits for both players
        from player import CHARACTER_CLASSES
        for player in game.players:
            starter_kit = CHARACTER_CLASSES.get(player.class_name, {}).get("starting_kit", [])
            for item in starter_kit:
                card_id = item.get("card_id")
                card_data = load_card(card_id)
                if card_data:
                    inv_card = InventoryCard(card_data)
                    if item.get("state", 1) == 2:
                        inv_card.current_state = 2
                    player.inventory.append(inv_card)
                    print(f"Added starter kit item for {player.name}: {inv_card.get_current_data().get('Name', card_id)}")
                else:
                    print(f"Warning: Starter kit card '{card_id}' not found")

        # Reset both players
        for player in game.players:
            player.hp = player.max_hp
            player.melee_weapon = None
            player.projectile_weapon = None
            player.movement_used = False
            player.action_used = False
            player.reset_double_attack()
            player.party = []  # Clear each player's party

        # Ensure all units are reset and active
        for unit in self.hex_grid.units:
            unit.hp = unit.max_hp
            unit.current_state = 1

        self.hex_grid.active_turn_unit = game.players[0]
        self.game_started = True
        self.turn_cycle_count = 0
        self.initialize_screen()
        # Autosave at level start
        self.save_manager.save_game(game, self, save_type="autosave", save_label="Level Start")

    def load_campaign_level(self):
        """Load the current campaign level and configure decks based on stage settings."""
        # Support both old format (campaign["levels"]) and new format (campaign["stages"])
        stages = self.campaign.get("stages") or self.campaign.get("levels", [])
        if not stages or self.current_level_idx >= len(stages):
            return

        stage_data = stages[self.current_level_idx]
        level_file = stage_data.get("level_file", "")

        # Handle level_file path - it may or may not include "levels/" prefix
        if level_file:
            if not level_file.startswith("levels"):
                level_file = os.path.join("levels", level_file)
        else:
            self.log.append(f"Stage {self.current_level_idx + 1} has no level file configured.")
            return

        try:
            self.hex_grid.load_level(level_file, self.card_manager, game.player)
            stage_name = stage_data.get("name", f"Stage {self.current_level_idx + 1}")
            self.log.append(f"Loaded {stage_name}: {os.path.basename(level_file)}")
        except Exception as e:
            print(f"Error loading level '{level_file}': {e}")
            self.hex_grid.place_unit(game.player, self.hex_grid.rows // 2, self.hex_grid.cols // 2)
            self.log.append(f"Failed to load level {self.current_level_idx + 1}. Starting default level.")
            return

        # Load stage-specific decks if configured (new format)
        deck_config = stage_data.get("deck_config", {})
        self._load_stage_decks(deck_config)

    def _load_stage_decks(self, deck_config):
        """Load decks configured for the current stage."""
        # Load transition deck
        transition_deck = deck_config.get("transition_deck", "")
        if transition_deck:
            # Transition system loads individual cards, so we need to pick one from the deck
            try:
                deck_path = resolve_deck_path(transition_deck)
                if os.path.exists(deck_path):
                    with open(deck_path, 'r') as f:
                        deck_data = json.load(f)
                    card_ids = deck_data.get("cards", [])
                    if card_ids:
                        # Load the first transition card from the deck
                        card_id = card_ids[0]
                        if game.transition_manager.load_transition_card(card_id):
                            self.log.append(f"Loaded transition card: {game.transition_manager.active_transition.name}")
            except Exception as e:
                print(f"Error loading transition deck: {e}")

        # Load instance deck
        instance_deck = deck_config.get("instance_deck", "")
        if instance_deck:
            deck_path = resolve_deck_path(instance_deck)
            if os.path.exists(deck_path):
                if game.instance_manager.load_instance_deck(deck_path):
                    self.log.append(f"Loaded instance deck: {os.path.basename(deck_path)}")

        # Load quest deck - store path for quest manager to use
        quest_deck = deck_config.get("quest_deck", "")
        if quest_deck:
            deck_path = resolve_deck_path(quest_deck)
            if os.path.exists(deck_path):
                game.current_quest_manager.quest_deck_path = deck_path
                self.log.append(f"Loaded quest deck: {os.path.basename(deck_path)}")

        # Load junk deck - store path for card drawing hexes
        junk_deck = deck_config.get("junk_deck", "")
        if junk_deck:
            deck_path = resolve_deck_path(junk_deck)
            if os.path.exists(deck_path):
                self.current_junk_deck = deck_path
                self.log.append(f"Loaded junk deck: {os.path.basename(deck_path)}")

    def _handle_delete_prev_saves(self, choice):
        """Callback for the level transition save deletion confirmation."""
        prev_level = getattr(self, '_pending_delete_level_saves', None)
        if choice == "Yes" and prev_level:
            deleted = self.save_manager.delete_saves_for_level(prev_level)
            self.add_to_log(f"Deleted {deleted} save(s) from previous level.")
        self._pending_delete_level_saves = None
        game.current_screen = "game"
        self.initialize_screen()

    def _handle_restart_confirm(self, choice):
        """Callback for 'Are you sure you want to restart?' confirmation."""
        if choice == "Yes":
            game.current_screen = "confirmation"
            confirmation_screen.initialize_screen(
                "Where would you like to restart from?",
                options=["Beginning of Level", "Choose a Save", "Cancel"],
                callback=self._handle_restart_choice
            )
        else:
            game.current_screen = "game"
            self.initialize_screen()

    def _handle_restart_choice(self, choice):
        """Callback for restart options."""
        if choice == "Beginning of Level":
            # Find the most recent "Level Start" autosave for current level
            save_info = self.save_manager.get_latest_level_start_save(self.current_level_file)
            if save_info:
                save_data = self.save_manager.load_save_file(save_info["filepath"])
                if save_data:
                    game.current_screen = "game"
                    self.load_from_save(save_data)
                    return
            # Fallback: full restart via character creation
            game.current_screen = "character_creation"
            character_creation_screen.initialize_screen(
                level_file=self.current_level_file,
                campaign_file=self.campaign_file if self.campaign else None
            )
        elif choice == "Choose a Save":
            game.current_screen = "save_load"
            save_load_screen.initialize_screen(mode="load")
        else:
            # Cancel
            game.current_screen = "game"
            self.initialize_screen()

    def load_from_save(self, save_data):
        """Rebuild the entire game state from a save data dict. Parallel to start_new_game()."""
        from quest_system import QuestManager
        from instance_system import InstanceManager
        from transition_system import TransitionManager

        # Rebuild player(s)
        multiplayer = save_data.get("multiplayer_mode", False)
        game.multiplayer_mode = multiplayer
        game.game_mode = save_data.get("game_mode", "survival")

        if multiplayer and "players" in save_data:
            game.players = [self.save_manager.rebuild_player(pd) for pd in save_data["players"]]
            game.current_player_index = save_data.get("current_player_index", 0)
            game.player = game.players[0]
        else:
            game.player = self.save_manager.rebuild_player(save_data["player"])
            game.players = []
            game.current_player_index = 0

        # Restore party
        game.party = []
        for card_ref in save_data.get("party", []):
            card = self.save_manager._rebuild_inventory_card(card_ref)
            if card:
                game.party.append(card)

        # Set up level/campaign info
        self.current_level_file = save_data.get("level_file")
        self.campaign_file = save_data.get("campaign_file")
        self.current_level_idx = save_data.get("current_level_idx", 0)
        self.campaign = save_data.get("campaign")

        # Restore game screen state
        gs = save_data.get("game_screen", {})
        self.turn_phase = gs.get("turn_phase", "player")
        self.log = gs.get("log", [])
        self.transition_target_cycle = gs.get("transition_target_cycle", 0)
        self.turn_cycle_count = gs.get("turn_cycle_count", 0)
        self.player_class = gs.get("player_class")

        # Create hex grid and load level terrain
        self.hex_grid = HexGrid(16, 24, 30, WINDOW_WIDTH, WINDOW_HEIGHT)
        if multiplayer:
            self.hex_grid.players = game.players

        # Load level file to get terrain, but we'll clear the auto-loaded units
        if self.current_level_file:
            try:
                self.hex_grid.load_level(self.current_level_file, self.card_manager, game.player)
            except Exception as e:
                print(f"Error loading level for save restore: {e}")
        elif self.campaign_file and self.campaign:
            try:
                self.load_campaign_level()
            except Exception as e:
                print(f"Error loading campaign level for save restore: {e}")

        # Clear auto-loaded units and player placement from level load
        for unit in list(self.hex_grid.units):
            if unit.position:
                self.hex_grid.grid[unit.position[0]][unit.position[1]]["unit"] = None
        self.hex_grid.units.clear()
        # Clear player from grid (will re-place from save data)
        if game.player and game.player.position:
            r, c = game.player.position
            if 0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols:
                self.hex_grid.grid[r][c]["unit"] = None

        # Place player(s) from save
        if multiplayer:
            for p in game.players:
                pos = save_data["players"][game.players.index(p)].get("position")
                if pos:
                    self.hex_grid.place_unit(p, pos[0], pos[1])
            self.hex_grid.player = game.players[0]
        else:
            pos = save_data["player"].get("position")
            if pos:
                self.hex_grid.place_unit(game.player, pos[0], pos[1])

        # Rebuild saved units
        self.save_manager.rebuild_units(save_data.get("units", []), self.hex_grid)

        # Overlay saved location data
        if save_data.get("location_data"):
            self.save_manager.rebuild_location_data(save_data["location_data"], self.hex_grid)

        # Restore card_drawing_hexes state
        if "card_drawing_hexes" in save_data:
            self.hex_grid.card_drawing_hexes = save_data["card_drawing_hexes"]

        # Reset managers
        game.quest_manager = QuestManager(self.card_manager)
        game.instance_manager = InstanceManager(self.card_manager, self.hex_grid)
        game.transition_manager = TransitionManager(self.card_manager, game.instance_manager)

        # Rebuild managers from save
        if save_data.get("quest_manager"):
            self.save_manager.rebuild_quest_manager(
                save_data["quest_manager"], game.quest_manager,
                self.hex_grid, game.player, self.card_manager
            )
        if save_data.get("instance_manager"):
            self.save_manager.rebuild_instance_manager(
                save_data["instance_manager"], game.instance_manager
            )
        if save_data.get("transition_manager"):
            self.save_manager.rebuild_transition_manager(
                save_data["transition_manager"], game.transition_manager
            )

        # Reset transient state
        self.turn_queue = []
        self.current_acting_unit = None
        self.waiting_for_animation = False
        self.pending_location = None
        self.pending_defeat = False
        self.current_location_hex = None
        self.is_player_turn = self.turn_phase in ("player", "player1", "player2")
        self.hex_grid.game_over = False

        # Set active turn unit
        if multiplayer:
            idx = game.current_player_index
            self.hex_grid.active_turn_unit = game.players[idx] if idx < len(game.players) else game.players[0]
        else:
            self.hex_grid.active_turn_unit = game.player

        self.game_started = True
        self.initialize_screen()
        self.add_to_log("Game loaded from save.")

    def check_level_completion(self):
        """Check if the current level's completion conditions are met."""
        # Support both old format (campaign["levels"]) and new format (campaign["stages"])
        stages = self.campaign.get("stages") or self.campaign.get("levels", []) if self.campaign else []
        if not stages or self.current_level_idx >= len(stages):
            return False

        stage_data = stages[self.current_level_idx]

        # New format: completion_conditions object
        completion = stage_data.get("completion_conditions", {})
        if completion:
            comp_type = completion.get("type", "defeat_all_enemies")
            target = completion.get("target", "")
            turn_limit = completion.get("turn_limit")

            if comp_type == "none" or comp_type == "sandbox":
                # Sandbox mode - never auto-complete
                return False

            if comp_type == "defeat_all_enemies":
                return len([u for u in self.hex_grid.units if u.allegiance == "Hostile"]) == 0

            elif comp_type == "defeat_boss":
                if target:
                    return not any(u.name == target and u.allegiance == "Hostile" for u in self.hex_grid.units)
                # If no target specified, check for any boss-type units
                return len([u for u in self.hex_grid.units if u.allegiance == "Hostile"]) == 0

            elif comp_type == "collect_item":
                if target:
                    return any(card.get_current_data().get("Name") == target for card in game.current_player.inventory)
                return False

            elif comp_type == "reach_location":
                if target:
                    # Check if player is at a location hex with the target name
                    player_pos = game.current_player.position if game.current_player else (0, 0)
                    for loc_hex in self.hex_grid.location_hexes:
                        if (loc_hex["row"], loc_hex["column"]) == player_pos:
                            loc_card = loc_hex.get("assigned_location_card")
                            if loc_card and loc_card.get_current_data().get("Name") == target:
                                return True
                return False

            elif comp_type == "survive_turns":
                if turn_limit:
                    # This would need turn tracking - for now, default to defeat all
                    pass
                return len([u for u in self.hex_grid.units if u.allegiance == "Hostile"]) == 0

        # Old format: transition_to_next string
        transition = stage_data.get("transition_to_next")
        if transition:
            if "Defeat Boss" in transition:
                boss_name = transition.split("'")[1] if "'" in transition else None
                if boss_name:
                    return not any(u.name == boss_name and u.allegiance == "Hostile" for u in self.hex_grid.units)
            elif "Collect" in transition:
                item_name = transition.split("'")[1] if "'" in transition else None
                if item_name:
                    return any(card.get_current_data().get("Name") == item_name for card in game.current_player.inventory)

        # Default: defeat all enemies
        return len([u for u in self.hex_grid.units if u.allegiance == "Hostile"]) == 0

    def _setup_multiplayer_player_phase(self):
        """Set up the correct player phase, skipping dead players."""
        if game.players[0].hp > 0:
            self.turn_phase = "player1"
            game.current_player_index = 0
            self.hex_grid.active_turn_unit = game.players[0]
        elif game.players[1].hp > 0:
            self.turn_phase = "player2"
            game.current_player_index = 1
            self.hex_grid.active_turn_unit = game.players[1]
        else:
            # Both dead - fallback
            self.turn_phase = "player1"
            game.current_player_index = 0
            self.hex_grid.active_turn_unit = game.players[0]
        self.rebuild_left_panel()

    def _start_player_turn(self):
        """Reset UI state and center camera on the current active player."""
        self.player_mode = "movement"
        self.selected_attack = None
        self._close_attack_submenu()
        # Center camera on the active player
        current_player = game.current_player
        if current_player and current_player.position:
            row, col = current_player.position
            pixel_x = col * self.hex_grid.hex_size * 1.5
            pixel_y = row * self.hex_grid.hex_size * 1.732 + (col % 2) * self.hex_grid.hex_size * 0.866
            self.hex_grid.view_offset_x = WINDOW_WIDTH / 2 - pixel_x
            self.hex_grid.view_offset_y = WINDOW_HEIGHT / 2 - pixel_y

    def advance_turn(self):
        self._close_action_choice_popup()
        if self.turn_phase == "player":
            # Single-player mode: Apply Turn_End passives before ending player turn
            for msg in game.player.apply_passive_skills(self.hex_grid, "Turn_End"):
                self.add_to_log(msg)
            game.player.tick_cooldowns()
            game.player.movement_used = game.player.action_used = False
            game.player.reset_double_attack()
            self.turn_phase = "allied"
            self.execute_turn("Allied")
        elif self.turn_phase == "player1":
            # Multiplayer: End Player 1's turn
            player1 = game.players[0]
            for msg in player1.apply_passive_skills(self.hex_grid, "Turn_End"):
                self.add_to_log(msg)
            player1.tick_cooldowns()
            player1.movement_used = player1.action_used = False
            player1.reset_double_attack()
            # Switch to Player 2's turn
            player2 = game.players[1]
            if player2.hp <= 0:
                # Player 2 is dead, skip to allied phase
                self.turn_phase = "allied"
                self.execute_turn("Allied")
            else:
                game.current_player_index = 1
                self.turn_phase = "player2"
                self.is_player_turn = True
                self.hex_grid.active_turn_unit = player2
                self.rebuild_left_panel()
                self._start_player_turn()
                # Apply Turn_Start passives for player 2
                for msg in player2.apply_passive_skills(self.hex_grid, "Turn_Start"):
                    self.add_to_log(msg)
        elif self.turn_phase == "player2":
            # Multiplayer: End Player 2's turn
            player2 = game.players[1]
            for msg in player2.apply_passive_skills(self.hex_grid, "Turn_End"):
                self.add_to_log(msg)
            player2.tick_cooldowns()
            player2.movement_used = player2.action_used = False
            player2.reset_double_attack()
            # Move to allied phase
            self.turn_phase = "allied"
            self.execute_turn("Allied")
        elif self.turn_phase == "allied":
            self.turn_phase = "neutral"
            self.execute_turn("Neutral")
        elif self.turn_phase == "neutral":
            self.turn_phase = "hostile"
            self.execute_turn("Hostile")
        elif self.turn_phase == "hostile":
            # Clear passthrough defense cache and move to location defense phase
            self._clear_defense_range_cache()
            self.turn_phase = "location_defense"
            self.hex_grid.active_turn_unit = None
            self.update_turn_label()
            self.process_location_defense_turn()
        elif self.turn_phase == "location_defense":
            # Move to transition phase
            self.turn_phase = "transition"
            self.update_turn_label()  # Show "World Events" immediately
            self.process_transition_turn()
        elif self.turn_phase == "transition":
            # End of turn cycle - process location shop cycles
            self.hex_grid.on_turn_end()
            # Increment turn cycle counter
            self.turn_cycle_count += 1
            # Notify quest system of turn end
            quest_results = game.current_quest_manager.update("turn_end", {}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)
            self._handle_quest_chain()

            if self.check_level_completion():
                # Autosave before level transition
                self.save_manager.save_game(game, self, save_type="autosave", save_label="Level Complete")
                self.current_level_idx += 1
                stages = self.campaign.get("stages") or self.campaign.get("levels", []) if self.campaign else []
                if self.campaign and self.current_level_idx < len(stages):
                    prev_level_file = self.current_level_file
                    self.load_campaign_level()
                    if game.multiplayer_mode:
                        self.turn_phase = "player1"
                        game.current_player_index = 0
                        self.hex_grid.active_turn_unit = game.players[0]
                        self.rebuild_left_panel()
                    else:
                        self.turn_phase = "player"
                        self.hex_grid.active_turn_unit = game.player
                    self.is_player_turn = True
                    self._start_player_turn()
                    # Autosave at new level start
                    self.turn_cycle_count = 0
                    self.save_manager.save_game(game, self, save_type="autosave", save_label="Level Start")
                    # Show confirmation about deleting previous level saves
                    self._pending_delete_level_saves = prev_level_file
                    game.current_screen = "confirmation"
                    confirmation_screen.initialize_screen(
                        "New autosave created for this level.\nDelete save data from the previous level?",
                        options=["Yes", "No"],
                        callback=self._handle_delete_prev_saves
                    )
                else:
                    self.add_to_log("Campaign Completed!")
                    game.current_screen = "main_menu"
                    main_menu.initialize_buttons()
            else:
                # Start new turn cycle
                if game.multiplayer_mode:
                    self._setup_multiplayer_player_phase()
                else:
                    self.turn_phase = "player"
                    self.hex_grid.active_turn_unit = game.player
                self.is_player_turn = True
                self._start_player_turn()
                # Reset location visits for new turn
                self.hex_grid.reset_location_visits()

                # Apply Turn_Start passives at start of player turn
                current_player = game.current_player
                for msg in current_player.apply_passive_skills(self.hex_grid, "Turn_Start"):
                    self.add_to_log(msg)

                # Periodic autosave every 5 turn cycles
                if self.turn_cycle_count > 0 and self.turn_cycle_count % 5 == 0:
                    self.save_manager.save_game(game, self, save_type="autosave", save_label=f"Turn {self.turn_cycle_count}")
        self.update_turn_label()
        self.animating = self.check_animations()

    def _cache_defense_ranges(self):
        """Pre-cache defense ranges for passthrough checks during hostile movement."""
        for pos, loc_data in self.hex_grid.location_data.items():
            if loc_data.get("state", 1) != 2:
                continue
            garrison = loc_data.get("garrison_npcs", [])
            if not garrison:
                continue
            for defense in loc_data.get("defenses", []):
                if not defense.get("requires_npc") or defense.get("passthrough_chance", 0) <= 0:
                    continue
                defense["_cached_range"] = self.hex_grid.calculate_range(
                    pos, defense["range_distance"], defense["range_type"],
                    defense.get("include_position", False), defense.get("exclude_adjacent", False)
                )

    def _clear_defense_range_cache(self):
        """Clear cached defense ranges after hostile turn."""
        for pos, loc_data in self.hex_grid.location_data.items():
            for defense in loc_data.get("defenses", []):
                defense.pop("_cached_range", None)

    def execute_turn(self, allegiance):
        """Queue units of the given allegiance to take their turns consecutively."""
        # Cache defense ranges at start of hostile turn for passthrough performance
        if allegiance == "Hostile":
            self._cache_defense_ranges()

        units_to_process = [unit for unit in self.hex_grid.units if unit.allegiance == allegiance]
        if not units_to_process:
            # No units of this allegiance - immediately advance to next phase
            if allegiance == "Hostile":
                self._clear_defense_range_cache()
            self.advance_turn()
            return
        for unit in units_to_process:
            self.turn_queue.append((unit, allegiance))
        # Start processing the queue
        if not self.current_acting_unit:
            self.process_next_unit()

    def process_next_unit(self):
        """Process the next unit in the turn queue."""
        if not self.turn_queue:
            # Queue empty, advance to next phase
            self.current_acting_unit = None
            self.waiting_for_animation = False
            self.advance_turn()
            return

        unit, allegiance = self.turn_queue.pop(0)

        # Check if unit is still valid (alive and on the grid)
        if unit not in self.hex_grid.units or unit.hp <= 0:
            self.process_next_unit()  # Skip to next unit
            return

        self.current_acting_unit = unit
        self.hex_grid.active_turn_unit = unit
        self.last_action_time = pygame.time.get_ticks()

        # Track position before turn for quest movement detection
        position_before = unit.position

        # Execute the unit's turn
        for entry in unit.take_turn(self.hex_grid):
            self.add_to_log(entry)

        # Process immediate attack results (attacks without movement)
        if self._post_attack_processing(unit):
            return

        # Notify quest system if unit moved
        if unit.position != position_before:
            quest_results = game.current_quest_manager.update(
                "unit_moved", {"unit": unit, "position": unit.position},
                self.hex_grid, game.current_player
            )
            for quest, result, qmsg in quest_results:
                self.add_to_log(qmsg)
            self._handle_quest_chain()

        self.player_info_label.set_text(self.get_player_info())
        self.waiting_for_animation = True
        self.animating = self.check_animations()

    def _post_attack_processing(self, unit):
        """Handle post-attack cleanup: dead units, game over, state switch.
        Returns True if game over was triggered (caller should return early)."""
        # Check for any units killed
        dead_units = [u for u in self.hex_grid.units if u.hp <= 0]
        for dead_unit in dead_units:
            if dead_unit.position:
                self.hex_grid.grid[dead_unit.position[0]][dead_unit.position[1]]["unit"] = None
            self.hex_grid.units.remove(dead_unit)
            self.add_to_log(f"{dead_unit.name} defeated")
            self.add_defeat_notification(dead_unit.name)
            self.card_manager.track_card_usage(dead_unit.card_id, {"action": "defeated", "screen": "game"})
            quest_results = game.current_quest_manager.update("unit_death", {"unit": dead_unit}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)
            self._handle_quest_chain()

        # Check for game over
        if game.multiplayer_mode:
            # Log player deaths only once (when HP first reaches 0)
            for i, p in enumerate(game.players):
                if p.hp <= 0 and not getattr(p, '_death_logged', False):
                    self.add_to_log(f"Player {i+1} ({p.class_name}) has fallen!")
                    self.add_defeat_notification(f"Player {i+1} ({p.class_name})")
                    p._death_logged = True
            # Only defeat if ALL players are dead
            all_dead = all(p.hp <= 0 for p in game.players)
            if all_dead:
                quest_results = game.current_quest_manager.update("player_death", {}, self.hex_grid, game.current_player)
                for quest, result, msg in quest_results:
                    self.add_to_log(msg)
                self._handle_quest_chain()
                self.turn_queue.clear()
                self.pending_defeat = True
                return True
        elif isinstance(self.hex_grid.player, Player) and self.hex_grid.player.hp <= 0:
            self.add_to_log("Player defeated!")
            self.add_defeat_notification("Player")
            quest_results = game.current_quest_manager.update("player_death", {}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)
            self._handle_quest_chain()
            self.turn_queue.clear()
            self.pending_defeat = True
            return True

        # Check for state switch (only if unit is still alive)
        if unit in self.hex_grid.units and unit.hp > 0:
            if unit.states == 2 and unit.hp < unit.max_hp * 0.3:
                switch_msg = unit.switch_state()
                if switch_msg:
                    self.add_to_log(switch_msg)

        return False

    def update_turn_queue(self):
        """Update the turn queue - called each frame to process consecutive unit turns."""
        if not self.waiting_for_animation:
            return

        # Check if animation is still playing
        # Also check if the unit is still on the grid (it might have been removed by quest completion)
        if self.current_acting_unit:
            if self.current_acting_unit not in self.hex_grid.units:
                # Unit was removed (e.g., moved to location after quest), skip animation wait
                self.current_acting_unit = None
            elif self.current_acting_unit.animating:
                return  # Wait for animation to finish

        # After movement animation completes, execute any deferred attack
        if self.current_acting_unit and getattr(self.current_acting_unit, 'pending_attack', None):
            attack_log = self.current_acting_unit.execute_pending_attack(self.hex_grid)
            for entry in attack_log:
                self.add_to_log(entry)

            # Process deaths and game over from the deferred attack
            if self._post_attack_processing(self.current_acting_unit):
                return

            self.player_info_label.set_text(self.get_player_info())
            # Reset timer so there's a brief pause after the attack before next unit
            self.last_action_time = pygame.time.get_ticks()
            return

        # Check if allied unit reached garrison target after movement
        if self.current_acting_unit and getattr(self.current_acting_unit, 'garrison_target_location', None):
            unit = self.current_acting_unit
            garrison_pos = unit.garrison_target_location
            if unit.position and self.hex_grid.hex_distance(unit.position, garrison_pos) <= 1:
                success, msg = self.hex_grid.garrison_map_npc_to_location(unit, garrison_pos)
                if success:
                    self.add_to_log(msg)
                    self.current_acting_unit = None

        # Log any passthrough defense messages from hostile movement
        if self.current_acting_unit and getattr(self.current_acting_unit, 'passthrough_messages', None):
            for msg in self.current_acting_unit.passthrough_messages:
                self.add_to_log(msg)
            self.current_acting_unit.passthrough_messages.clear()
            # Check if passthrough killed the unit
            if self.current_acting_unit and self.current_acting_unit.hp <= 0:
                if self._post_attack_processing(self.current_acting_unit):
                    return
                self.player_info_label.set_text(self.get_player_info())

        # Check if enough time has passed since last action
        current_time = pygame.time.get_ticks()
        if current_time - self.last_action_time < self.turn_action_delay:
            return  # Wait for delay

        # Process next unit
        self.waiting_for_animation = False
        self.process_next_unit()

    def _open_attack_submenu(self):
        """Open the attack submenu to the right of the Attack button."""
        self._close_attack_submenu()
        current_player = game.current_player
        left_panel_width = WINDOW_WIDTH // 4
        button_width = (left_panel_width - 20) // 2

        # Position submenu to the right of the Attack button
        x = 10 + button_width + 5
        y = self.attack_button_y

        # Melee first (orange-red outline), then projectile (neon purple outline)
        attack_order = [
            ("melee", (255, 69, 0)),      # Orange-red
            ("projectile", (191, 0, 255))  # Neon purple
        ]
        for attack_key, outline_color in attack_order:
            attack = current_player.attacks.get(attack_key)
            if attack:
                btn = UIButton(pygame.Rect(x, y, button_width, 30),
                               f"{attack['name']} ({attack['damage']} dmg)", manager)
                btn._outline_color = outline_color
                self.attack_submenu_buttons.append((btn, "attack", attack))
                y += 34

        # Special attack (Warrior's Dual Strike and Ranger's Piercing Shot are passive - no button needed)
        if current_player.special_attack not in ("Dual Strike", "Piercing Shot"):
            btn = UIButton(pygame.Rect(x, y, button_width, 30),
                           f"[Special] {current_player.special_attack}", manager)
            self.attack_submenu_buttons.append((btn, "special", None))
            self.special_attack_button = btn

        self.attack_submenu_open = True

    def _close_attack_submenu(self):
        """Close the attack submenu."""
        for btn, _, _ in self.attack_submenu_buttons:
            btn.kill()
        self.attack_submenu_buttons = []
        self.attack_submenu_open = False
        self.special_attack_button = None

    def initialize_screen(self):
        manager.clear_and_reset()
        # Compute right panel geometry
        rp_w = self.rp_width  # 234
        rp_pad = self.rp_pad  # 10
        rp_x = WINDOW_WIDTH - rp_w
        rp_inner_w = rp_w - 2 * rp_pad  # 214
        toolbar_clearance = 60
        section_header_h = 20
        player_info_h = 155
        stats_h = 175

        pi_y = section_header_h + 4  # Below "Player" label
        stats_y = pi_y + player_info_h + rp_pad + section_header_h + 4
        menu_y = stats_y + stats_h + rp_pad

        # Store for draw()
        self.rp_x = rp_x
        self.rp_inner_w = rp_inner_w
        self.rp_pi_y = pi_y
        self.rp_stats_y = stats_y
        self.rp_menu_y = menu_y
        self.rp_height = WINDOW_HEIGHT - toolbar_clearance

        self.ui_elements = [
            UITextBox("<font color='#FFFFFF' size=4>Game Log</font>",
                      pygame.Rect((WINDOW_WIDTH - 600) // 2, 45, 600, 140),
                      manager, object_id="#log_textbox"),
            UITextBox("<font color='#FFFFFF' size=4>Stats</font>",
                      pygame.Rect(rp_x + rp_pad, stats_y, rp_inner_w, stats_h),
                      manager, object_id="#stats_panel", visible=False),
            UITextBox("<font color='#FFFFFF' size=4>Player's Turn</font>",
                      pygame.Rect((WINDOW_WIDTH - 200) // 2, 10, 200, 30),
                      manager, object_id="#turn_label")
        ]
        # Minimized log: toggle button on left + single line at bottom
        log_x = (WINDOW_WIDTH - 600) // 2
        self.log_toggle_button = UIButton(
            pygame.Rect(log_x, 45, 30, 28),
            "^", manager
        )
        self.log_mini_label = UITextBox(
            "<font color='#CCCCCC' size=3></font>",
            pygame.Rect(log_x + 32, 45, 568, 28),
            manager
        )
        # Start minimized
        self.log_minimized = True
        self.ui_elements[0].hide()

        left_panel_width = WINDOW_WIDTH // 4
        button_width = (left_panel_width - 20) // 2
        self.player_info_label = UITextBox(
            self.get_player_info(),
            pygame.Rect(rp_x + rp_pad, pi_y, rp_inner_w, player_info_h),
            manager, object_id="#right_panel_info"
        )
        self.ui_elements.append(self.player_info_label)
        
        # Menu button inside the right panel
        self.menu_button = UIButton(
            pygame.Rect(rp_x + rp_pad, menu_y, rp_inner_w, 30), "Menu", manager)
        self.ui_elements.append(self.menu_button)

        y_pos = 200
        self.left_panel_buttons = []
        self.attack_submenu_open = False
        self.attack_submenu_buttons = []
        self.special_attack_button = None
        self.selected_item = None
        self.item_targeting_mode = False
        self.action_choice_open = False
        self.action_choice_buttons = []
        self.action_choice_target = None

        # Tool buttons no longer needed on left panel (handled by bottom toolbar)
        self.tool_buttons = []
        self.tool_button = None

        # Add equipped skill buttons
        self.skill_buttons = []
        y_pos = 200
        for skill_card in game.current_player.equipped_skills:
            skill_data = skill_card.get_current_data()
            skill_name = skill_data.get("Name", "Unknown")
            cooldown = game.current_player.skill_cooldowns.get(skill_name, 0)
            text = f"{skill_name} (CD:{cooldown})" if cooldown else skill_name
            btn = UIButton(pygame.Rect(10, y_pos, button_width, 30), text, manager)
            self.skill_buttons.append((btn, skill_card))
            self.left_panel_buttons.append(btn)
            y_pos += 40

        self.ui_elements.extend(self.left_panel_buttons)

        self.ui_elements[0].set_text("<font color='#FFFFFF' size=4>" + "<br>".join(reversed(self.log)) + "</font>")
        self.update_turn_label()
        self.show_stats(None)
        self._create_equipment_toolbar()

    def get_player_info(self):
        p = game.current_player
        pos = p.position
        # Color-coded HP based on health percentage
        hp_ratio = p.hp / p.max_hp if p.max_hp > 0 else 0
        if hp_ratio > 0.6:
            hp_color = "#66DD66"  # Green
        elif hp_ratio > 0.3:
            hp_color = "#DDDD44"  # Yellow
        else:
            hp_color = "#DD4444"  # Red
        # Build HTML formatted info
        lines = []
        if game.multiplayer_mode:
            lines.append(f"<font color='#AAAAFF'>Player {p.player_number}</font>")
        lines.append(f"<font color='#FFD700'>{p.class_name}</font>")
        lines.append(f"<font color='#999999'>HP:</font> <font color='{hp_color}'>{p.hp}/{p.max_hp}</font>")
        mv_color = "#888888" if p.movement_used else "#CCCCDD"
        lines.append(f"<font color='#999999'>Move:</font> <font color='{mv_color}'>{p.movement}</font>")
        lines.append(f"<font color='#999999'>Range:</font> <font color='#CCCCDD'>{p.projectile_range}</font>")
        act_color = "#888888" if p.action_used else "#CCCCDD"
        lines.append(f"<font color='#999999'>Action:</font> <font color='{act_color}'>{'Used' if p.action_used else 'Ready'}</font>")
        if p.class_name == "Warrior":
            lines.append(f"<font color='#999999'>Attacks:</font> <font color='#CCCCDD'>{p.warrior_attacks_remaining}/2</font>")
        return "<br>".join(lines)

    def _handle_quest_chain(self):
        """Check for pending quest chain and handle by mode (auto_activate or offer)."""
        chain = game.current_quest_manager.get_pending_chain()
        if not chain:
            return

        quest_card = chain["quest_card"]
        mode = chain["mode"]
        message = chain.get("message", "")
        inherited_context = chain.get("inherited_context", {})

        if mode == "auto_activate":
            success, msg = game.current_quest_manager.activate_chain_quest(
                quest_card, self.hex_grid, game.current_player, inherited_context
            )
            if message:
                self.add_to_log(message)
            self.add_to_log(msg)
        elif mode == "offer":
            # Store chain data for the callback
            self._pending_chain_offer = {
                "quest_card": quest_card,
                "inherited_context": inherited_context,
                "message": message
            }
            offer_text = message if message else "A new quest awaits. Accept?"
            confirmation_screen.initialize_screen(
                offer_text, ["Accept", "Decline"],
                self._handle_chain_offer_response
            )
            self.active_screen = "confirmation"

    def _handle_chain_offer_response(self, choice):
        """Callback for quest chain offer confirmation."""
        self.active_screen = "game"
        if choice == "Accept" and hasattr(self, '_pending_chain_offer'):
            offer = self._pending_chain_offer
            success, msg = game.current_quest_manager.activate_chain_quest(
                offer["quest_card"], self.hex_grid, game.current_player,
                offer.get("inherited_context", {})
            )
            self.add_to_log(msg)
        else:
            self.add_to_log("Quest chain declined.")
        if hasattr(self, '_pending_chain_offer'):
            del self._pending_chain_offer

    def _get_log_color(self, message):
        """Return an HTML color based on message content."""
        msg = message.lower()
        if "defeated" in msg or "damage" in msg or "hit" in msg or "attack" in msg:
            return "#FF7766"  # Red for combat
        if "quest" in msg or "reward" in msg or "chain" in msg:
            return "#FFD700"  # Gold for quests
        if "[recruit]" in msg or "recruit" in msg:
            return "#44DDBB"  # Teal for recruitment
        if "moved" in msg or "path" in msg:
            return "#88BBFF"  # Blue for movement
        if "drew" in msg or "found" in msg or "item" in msg or "card" in msg:
            return "#88DD88"  # Green for loot/items
        if "skill" in msg or "cooldown" in msg or "heal" in msg:
            return "#CC99FF"  # Purple for skills
        if "spawn" in msg or "weather" in msg or "event" in msg:
            return "#FFAA55"  # Orange for world events
        return "#CCCCDD"  # Default light gray

    def add_to_log(self, message):
        if message:
            self.log.append(message)
            if len(self.log) > 10:
                self.log.pop(0)
            colored_lines = []
            for msg in reversed(self.log):
                color = self._get_log_color(msg)
                colored_lines.append(f"<font color='{color}'>{msg}</font>")
            self.ui_elements[0].set_text("<font size=4>" + "<br>".join(colored_lines) + "</font>")
            # Update minimized label with latest entry
            if self.log_mini_label:
                color = self._get_log_color(message)
                self.log_mini_label.set_text(f"<font color='{color}' size=3>{message}</font>")

    def _get_terrain_info(self, hex_pos):
        """Build terrain info string for the given hex position."""
        row, col = hex_pos
        cell = self.hex_grid.grid[row][col]
        terrain_type = cell.get("terrain", "grass")
        terrain_name = terrain_type.replace("_", " ").title()
        config = TERRAIN_CONFIG.get(terrain_type, TERRAIN_CONFIG["grass"])
        walkable = "Yes" if config["accessible"] else "No"
        blocks_los = "Yes" if config["blocks_los"] else "No"
        lines = [
            "--- Terrain ---",
            f"Type: {terrain_name}",
            f"Walkable: {walkable}",
            f"Blocks LOS: {blocks_los}",
        ]
        loc_data = self.hex_grid.location_data.get(hex_pos)
        if loc_data and loc_data.get("card"):
            loc_name = loc_data["card"].card_data.get("Name", "Unknown")
            lines.append(f"Location: {loc_name}")
        return "\n".join(lines)

    def show_stats(self, unit, hex_pos=None):
        html_parts = []
        if unit:
            html_parts.append(self._format_unit_stats_html(unit))
        if hex_pos:
            html_parts.append(self._format_terrain_html(hex_pos))
        if html_parts:
            self.ui_elements[1].set_text("<br>".join(html_parts))
            self.ui_elements[1].show()
        else:
            self.ui_elements[1].hide()

    def _format_unit_stats_html(self, unit):
        """Format unit stats as color-coded HTML."""
        lines = []
        # Name colored by allegiance
        if hasattr(unit, 'allegiance'):
            name_colors = {"Hostile": "#FF6644", "Allied": "#4488FF", "Neutral": "#44DDBB"}
            nc = name_colors.get(unit.allegiance, "#FFFFFF")
        else:
            nc = "#66DD66"
        name = unit.name if hasattr(unit, 'name') else "Unknown"
        lines.append(f"<font color='{nc}'><b>{name}</b></font>")
        # HP with color
        hp_ratio = unit.hp / unit.max_hp if unit.max_hp > 0 else 0
        if hp_ratio > 0.6:
            hc = "#66DD66"
        elif hp_ratio > 0.3:
            hc = "#DDDD44"
        else:
            hc = "#DD4444"
        lines.append(f"<font color='#999999'>HP:</font> <font color='{hc}'>{unit.hp}/{unit.max_hp}</font>")
        lines.append(f"<font color='#999999'>Move:</font> <font color='#CCCCDD'>{unit.movement}</font>")
        # Handle Player (attacks dict) vs Unit (melee_damage attribute)
        if hasattr(unit, 'attacks') and isinstance(unit.attacks, dict):
            melee_dmg = unit.attacks.get("melee", {}).get("damage", 0)
            proj_info = unit.attacks.get("projectile", {})
            proj_dmg = proj_info.get("damage", 0)
            proj_rng = proj_info.get("range", 0)
        else:
            melee_dmg = getattr(unit, 'melee_damage', 0)
            proj_dmg = getattr(unit, 'projectile_damage', 0)
            proj_rng = getattr(unit, 'projectile_range', 0)
        lines.append(f"<font color='#999999'>Melee:</font> <font color='#FF9966'>{melee_dmg}</font>")
        if proj_dmg > 0:
            lines.append(f"<font color='#999999'>Proj:</font> <font color='#BB88FF'>{proj_dmg}</font>  <font color='#999999'>Rng:</font> <font color='#CCCCDD'>{proj_rng}</font>")
        if hasattr(unit, 'allegiance'):
            lines.append(f"<font color='#999999'>Allegiance:</font> <font color='{nc}'>{unit.allegiance}</font>")
        if hasattr(unit, 'special_skill') and unit.special_skill:
            lines.append(f"<font color='#CC99FF'>{unit.special_skill}</font>")
        return "<br>".join(lines)

    def _format_terrain_html(self, hex_pos):
        """Format terrain info as color-coded HTML."""
        row, col = hex_pos
        cell = self.hex_grid.grid[row][col]
        terrain_type = cell.get("terrain", "grass")
        terrain_name = terrain_type.replace("_", " ").title()
        config = TERRAIN_CONFIG.get(terrain_type, TERRAIN_CONFIG["grass"])
        walkable = config["accessible"]
        blocks_los = config["blocks_los"]
        lines = [f"<font color='#777799'>--- Terrain ---</font>"]
        lines.append(f"<font color='#999999'>Type:</font> <font color='#CCCCDD'>{terrain_name}</font>")
        wc = "#66DD66" if walkable else "#DD4444"
        lines.append(f"<font color='#999999'>Walkable:</font> <font color='{wc}'>{'Yes' if walkable else 'No'}</font>")
        lc = "#DD4444" if blocks_los else "#66DD66"
        lines.append(f"<font color='#999999'>Blocks LOS:</font> <font color='{lc}'>{'Yes' if blocks_los else 'No'}</font>")
        loc_data = self.hex_grid.location_data.get(hex_pos)
        if loc_data and loc_data.get("card"):
            loc_name = loc_data["card"].card_data.get("Name", "Unknown")
            lines.append(f"<font color='#FFAA33'>{loc_name}</font>")
        return "<br>".join(lines)

    def update_turn_label(self):
        if self.turn_phase == "player" and game.player:
            player_name = game.player.name if hasattr(game.player, 'name') and game.player.name else "Player"
            label = f"{player_name}'s Turn"
            color = "#66DD66"  # Green for player
        elif self.turn_phase == "player1" and game.multiplayer_mode and len(game.players) > 0:
            player_name = game.players[0].name if hasattr(game.players[0], 'name') and game.players[0].name else "Player 1"
            label = f"{player_name}'s Turn"
            color = "#66DD66"
        elif self.turn_phase == "player2" and game.multiplayer_mode and len(game.players) > 1:
            player_name = game.players[1].name if hasattr(game.players[1], 'name') and game.players[1].name else "Player 2"
            label = f"{player_name}'s Turn"
            color = "#6688FF"  # Blue for player 2
        else:
            phases = {
                "allied": ("Allied Turn", "#44AAFF"),
                "neutral": ("Neutral Turn", "#00CCAA"),
                "hostile": ("Enemies' Turn", "#FF6644"),
                "location_defense": ("Location Defense", "#FFAA33"),
                "transition": ("World Events", "#CC88FF")
            }
            label, color = phases.get(self.turn_phase, ("Unknown", "#FFFFFF"))
        turn_num = self.turn_cycle_count + 1
        self.ui_elements[2].set_text(f"<font color='{color}' size=4>{label}</font> <font color='#8888AA' size=3>Turn {turn_num}</font>")

    def rebuild_left_panel(self):
        """Rebuild the left panel UI for the current player (used in multiplayer when turn changes)."""
        # Close attack submenu if open
        self._close_attack_submenu()
        # Kill all existing left panel buttons and remove from ui_elements
        for btn in self.left_panel_buttons:
            btn.kill()
            if btn in self.ui_elements:
                self.ui_elements.remove(btn)
        self.left_panel_buttons.clear()

        # Get current player's data
        current_player = game.current_player
        left_panel_width = WINDOW_WIDTH // 4
        button_width = (left_panel_width - 20) // 2

        # Update player info label
        self.player_info_label.set_text(
            self.get_player_info()
        )

        # Rebuild menu button in right panel
        if self.menu_button:
            self.menu_button.kill()
            if self.menu_button in self.ui_elements:
                self.ui_elements.remove(self.menu_button)
        self.menu_button = UIButton(
            pygame.Rect(self.rp_x + self.rp_pad, self.rp_menu_y, self.rp_inner_w, 30),
            "Menu", manager)
        self.ui_elements.append(self.menu_button)

        y_pos = 200
        self.attack_submenu_open = False
        self.attack_submenu_buttons = []
        self.special_attack_button = None

        # Tool buttons no longer needed on left panel (handled by bottom toolbar)
        self.tool_buttons = []
        self.tool_button = None

        # Add equipped skill buttons
        self.skill_buttons = []
        y_pos = 200
        for skill_card in current_player.equipped_skills:
            skill_data = skill_card.get_current_data()
            skill_name = skill_data.get("Name", "Unknown")
            cooldown = current_player.skill_cooldowns.get(skill_name, 0)
            text = f"{skill_name} (CD:{cooldown})" if cooldown else skill_name
            btn = UIButton(pygame.Rect(10, y_pos, button_width, 30), text, manager)
            self.skill_buttons.append((btn, skill_card))
            self.left_panel_buttons.append(btn)
            y_pos += 40

        self.ui_elements.extend(self.left_panel_buttons)
        self.update_turn_label()
        self._create_equipment_toolbar()

    def _create_equipment_toolbar(self):
        """Create 7 bottom toolbar buttons (6 equipment + End Turn)."""
        self._close_equip_popup()
        # Kill existing toolbar buttons
        for btn in self.equip_toolbar_buttons:
            btn.kill()
            if btn in self.ui_elements:
                self.ui_elements.remove(btn)
        self.equip_toolbar_buttons = []
        # Kill existing end turn button if it exists
        if hasattr(self, 'end_turn_button') and self.end_turn_button:
            self.end_turn_button.kill()
            if self.end_turn_button in self.ui_elements:
                self.ui_elements.remove(self.end_turn_button)
            if self.end_turn_button in self.left_panel_buttons:
                self.left_panel_buttons.remove(self.end_turn_button)

        p = game.current_player
        btn_w, btn_h = 180, 40
        gap = 8
        total_w = btn_w * 7 + gap * 6
        start_x = (WINDOW_WIDTH - total_w) // 2
        y = WINDOW_HEIGHT - 50

        # Melee slot label
        if p.melee_weapon:
            melee_name = p.melee_weapon.get_current_data().get("Name", "???")
        else:
            melee_name = "---"
        # Projectile slot label
        if p.projectile_weapon:
            if p.melee_weapon and p.projectile_weapon is p.melee_weapon:
                proj_name = "(Both)"
            else:
                proj_name = p.projectile_weapon.get_current_data().get("Name", "???")
        else:
            proj_name = "---"
        # Tool slot label
        tool_names = []
        if p.equipped_tools:
            for t in p.equipped_tools:
                if t:
                    tool_names.append(t.get_current_data().get("Name", "?"))
        elif p.equipped_tool:
            tool_names.append(p.equipped_tool.get_current_data().get("Name", "?"))
        tool_label = ", ".join(tool_names) if tool_names else "---"
        if len(tool_label) > 20:
            tool_label = tool_label[:17] + "..."
        # Action button label - shows Tool_Action from first equipped tool that has one
        action_label = "---"
        self.equip_action_tool = None
        action_name, action_tool = p.get_tool_action()
        if action_name:
            action_label = action_name
            self.equip_action_tool = action_tool
        # Accessory slot label
        if p.equipped_accessory:
            acc_name = p.equipped_accessory.get_current_data().get("Name", "???")
        else:
            acc_name = "---"

        labels = [f"Melee: {melee_name}", f"Proj: {proj_name}", f"Acc: {acc_name}", f"Tool: {tool_label}", f"Action: {action_label}", "Items"]
        for i, label in enumerate(labels):
            bx = start_x + i * (btn_w + gap)
            btn = UIButton(pygame.Rect(bx, y, btn_w, btn_h), label, manager)
            self.equip_toolbar_buttons.append(btn)
            self.ui_elements.append(btn)

        # End Turn as 7th button in the same row
        end_x = start_x + 6 * (btn_w + gap)
        self.end_turn_button = UIButton(pygame.Rect(end_x, y, btn_w, btn_h), "End Turn", manager)
        self.ui_elements.append(self.end_turn_button)

    # ===== TOOL ACTION SYSTEM =====

    def _handle_tool_action_click(self):
        """Handle click on the Action toolbar button. Dispatches based on Tool_Action value."""
        current_player = game.current_player
        action_name, action_tool = current_player.get_tool_action()

        if not action_name:
            self.add_to_log("No tool action available - equip a tool with an action")
            return

        if action_name == "Build":
            self._handle_build_action(current_player)
        elif action_name == "Read":
            self._handle_read_action(current_player, action_tool)
        elif action_name == "Search":
            self._handle_search_action(current_player)
        else:
            self._handle_generic_tool_action(current_player, action_name)

    def _handle_build_action(self, current_player):
        """Handle the Build tool action (moved from left panel Build button)."""
        if self.placement_mode:
            self.placement_mode = False
            self.placement_card = None
            self.add_to_log("Cancelled building placement")
        else:
            plans = current_player.get_location_plans()
            if not plans:
                self.add_to_log("No Location Plans in inventory")
            elif not current_player.has_building_tool():
                self.add_to_log("Need a hammer/building tool equipped")
            else:
                plan = plans[0]
                can, missing = current_player.can_build(plan)
                if can:
                    material_cards = [c for c in current_player.inventory
                                     if c.get_current_data().get("Metal Value") or
                                        c.get_current_data().get("Wood Value") or
                                        c.get_current_data().get("Raw Material Value")]
                    success, msg, built_card = current_player.build(plan, material_cards[:5])
                    if success:
                        self.add_to_log(msg + " Click on an empty hex to place it.")
                        self.placement_mode = True
                        self.placement_card = built_card
                        self.player_mode = "placement"
                    else:
                        self.add_to_log(msg)
                else:
                    for m in missing:
                        self.add_to_log(f"Missing: {m}")

    def _handle_read_action(self, current_player, action_tool):
        """Handle the Read tool action for Guide documents."""
        message = current_player.read_guide(action_tool, game.card_manager)
        self.add_to_log(message)
        self.player_info_label.set_text(self.get_player_info())
        self._create_equipment_toolbar()

    def _handle_search_action(self, current_player):
        """Handle the Search tool action for Scavenger's Kit."""
        if current_player.action_used:
            self.add_to_log("Action already used this turn")
            return
        player_pos = current_player.position
        terrain = self.hex_grid.grid[player_pos[0]][player_pos[1]].get("terrain", "grass")
        location_name = None
        loc_data = self.hex_grid.location_data.get(player_pos)
        if loc_data and loc_data.get("card"):
            location_name = loc_data["card"].get_current_data().get("Name", "")
        success, message, flipped_card = current_player.search(terrain, location_name)
        self.add_to_log(message)
        if success:
            self.player_info_label.set_text(self.get_player_info())
            self.initialize_screen()

    def _handle_generic_tool_action(self, current_player, action_name):
        """Handle generic tool actions (Dig, Prune, etc.) that flip Searchable cards."""
        if current_player.action_used:
            self.add_to_log("Action already used this turn")
            return

        player_pos = current_player.position
        terrain = self.hex_grid.grid[player_pos[0]][player_pos[1]].get("terrain", "grass")

        # Search inventory for state 1 cards with matching Required_Tool_Action
        matching_cards = []
        for card in current_player.inventory:
            if card.current_state != 1:
                continue
            cdata = card.get_current_data()
            required_action = cdata.get("Required_Tool_Action", "")
            if required_action and required_action.lower() == action_name.lower():
                # Check terrain match
                search_terrain = cdata.get("Search_Terrain", "")
                if search_terrain:
                    valid_terrains = [t.strip().lower() for t in search_terrain.split(",")]
                    if terrain.lower() not in valid_terrains:
                        continue
                matching_cards.append(card)

        if not matching_cards:
            self.add_to_log(f"No items respond to {action_name} here")
            return

        # Filter by hex tracking
        for card in matching_cards:
            cdata = card.get_current_data()
            track_hex = cdata.get("Track_Hex_Attempts", "false").lower() == "true"
            if track_hex:
                attempted = self._load_hex_attempts(card)
                if tuple(player_pos) in attempted:
                    continue  # Already tried this hex

            # Roll for success
            success_chance = int(cdata.get("Search_Success_Chance", "50") or "50")
            roll = random.randint(1, 100)

            if roll <= success_chance:
                card.current_state = 2
                self.add_to_log(f"Success! {cdata.get('Name', 'Item')} revealed something!")
                # Clear hex tracking for this card
                if track_hex:
                    self._clear_hex_attempts(card)
            else:
                self.add_to_log(f"Nothing found with {action_name} here...")
                if track_hex:
                    self._save_hex_attempt(card, player_pos)

            current_player.action_used = True
            self.player_info_label.set_text(self.get_player_info())
            self.initialize_screen()
            return

        self.add_to_log(f"Already tried {action_name} on all available items at this hex")

    def _get_card_id(self, card):
        """Get a stable ID for a card for hex tracking purposes."""
        return card.card_data.get("card_id", card.card_data.get("data", {}).get("Name", "unknown"))

    def _load_hex_attempts(self, card):
        """Load set of attempted hex positions for a card from temp file."""
        card_id = self._get_card_id(card)
        safe_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in card_id)
        filepath = os.path.join("temp", f"hex_attempts_{safe_id}.json")
        if not os.path.exists(filepath):
            return set()
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return {tuple(h) for h in data.get("attempted_hexes", [])}
        except Exception:
            return set()

    def _save_hex_attempt(self, card, hex_pos):
        """Record a hex as attempted for a card."""
        card_id = self._get_card_id(card)
        safe_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in card_id)
        os.makedirs("temp", exist_ok=True)
        filepath = os.path.join("temp", f"hex_attempts_{safe_id}.json")
        attempted = self._load_hex_attempts(card)
        attempted.add(tuple(hex_pos))
        data = {"card_id": card_id, "attempted_hexes": [list(h) for h in attempted]}
        with open(filepath, 'w') as f:
            json.dump(data, f)

    def _clear_hex_attempts(self, card):
        """Delete the temp hex tracking file for a card."""
        card_id = self._get_card_id(card)
        safe_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in card_id)
        filepath = os.path.join("temp", f"hex_attempts_{safe_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)

    # ===== ITEMS BUTTON SYSTEM =====

    def _handle_items_click(self):
        """Handle click on the Items toolbar button. Opens popup of usable consumables from inventory."""
        # If already in item targeting mode, cancel it
        if self.item_targeting_mode:
            self.selected_item = None
            self.item_targeting_mode = False
            self.player_mode = "movement"
            self.add_to_log("Item use cancelled")
            self._close_equip_popup()
            return

        # If a popup is already open for items, close it
        if self.equip_popup_open and self.equip_popup_slot == "items":
            self._close_equip_popup()
            return

        self._close_equip_popup()
        p = game.current_player

        if p.action_used:
            self.add_to_log("Action already used this turn")
            return

        # Get the Items button (index 5)
        if len(self.equip_toolbar_buttons) < 6:
            return
        slot_btn = self.equip_toolbar_buttons[5]

        items = []
        # Gather equipped cards to exclude
        equipped_cards = set()
        if p.melee_weapon:
            equipped_cards.add(id(p.melee_weapon))
        if p.projectile_weapon:
            equipped_cards.add(id(p.projectile_weapon))
        if p.equipped_accessory:
            equipped_cards.add(id(p.equipped_accessory))
        for t in p.equipped_tools:
            if t:
                equipped_cards.add(id(t))
        if p.equipped_tool:
            equipped_cards.add(id(p.equipped_tool))

        for card in p.inventory:
            if id(card) in equipped_cards:
                continue
            if card.current_state != 2:
                continue
            cdata = card.get_current_data()
            ctype = cdata.get("Type", "")
            hp_effect = cdata.get("Use_HP", "")
            # Include consumables and any card with Use_HP, but exclude ammunition
            if ctype == "Ammunition":
                continue
            if ctype == "Consumable" or hp_effect:
                name = cdata.get("Name", "???")
                label = f"{name} ({hp_effect})" if hp_effect else name
                items.append((label, card))

        if not items:
            items.append(("(No consumables)", None))

        # Cap at 10 items
        items = items[:10]

        # Build popup buttons stacking upward from just above the slot button
        popup_y = slot_btn.rect.y - 5
        btn_w = slot_btn.rect.width
        self.equip_popup_buttons = []
        for label, data in reversed(items):
            popup_y -= 34
            btn = UIButton(pygame.Rect(slot_btn.rect.x, popup_y, btn_w, 30), label, manager)
            self.equip_popup_buttons.append((btn, "items", data))
            self.ui_elements.append(btn)

        self.equip_popup_open = True
        self.equip_popup_slot = "items"

    # ===== EQUIPMENT POPUP SYSTEM =====

    def _open_equip_popup(self, slot_type):
        """Open a popup menu above the clicked equipment slot."""
        self._close_equip_popup()
        self._close_action_choice_popup()
        # Cancel item targeting mode when opening other popups
        if self.item_targeting_mode:
            self.selected_item = None
            self.item_targeting_mode = False
            self.player_mode = "movement"
        p = game.current_player
        slot_idx_map = {"melee": 0, "projectile": 1, "accessory": 2, "tool": 3}
        btn_idx = slot_idx_map[slot_type]
        if btn_idx >= len(self.equip_toolbar_buttons):
            return
        slot_btn = self.equip_toolbar_buttons[btn_idx]

        items = []  # List of (label, data) — data is card or special string

        if slot_type == "melee":
            for card in p.inventory:
                if card.current_state == 2 and card is not p.melee_weapon:
                    cdata = card.get_current_data()
                    ctype = cdata.get("Type", "")
                    if ctype in ("Melee", "Both"):
                        items.append((cdata.get("Name", "???"), card))
            if p.melee_weapon:
                items.append(("-- Unequip --", "unequip"))

        elif slot_type == "projectile":
            for card in p.inventory:
                if card.current_state == 2 and card is not p.projectile_weapon:
                    cdata = card.get_current_data()
                    ctype = cdata.get("Type", "")
                    if ctype in ("Projectile", "Both"):
                        items.append((cdata.get("Name", "???"), card))
            if p.projectile_weapon:
                items.append(("-- Unequip --", "unequip"))

        elif slot_type == "tool":
            for card in p.inventory:
                cdata = card.get_current_data()
                ctype = cdata.get("Type", "")
                # Allow state 1 cards with Tool_Action (e.g., Guide documents), otherwise require state 2
                if card.current_state != 2 and not cdata.get("Tool_Action"):
                    continue
                # Check if already equipped in a tool slot
                already_equipped = False
                if p.equipped_tools:
                    for t in p.equipped_tools:
                        if t is card:
                            already_equipped = True
                            break
                elif p.equipped_tool is card:
                    already_equipped = True
                if already_equipped:
                    continue
                if ctype in ("Ammunition", "Consumable"):
                    continue
                if ctype == "Tool" or cdata.get("Tool_Action"):
                    items.append((cdata.get("Name", "???"), card))
            # Unequip entries per slot
            if p.equipped_tools:
                for si, t in enumerate(p.equipped_tools):
                    if t:
                        tname = t.get_current_data().get("Name", "?")
                        items.append((f"-- Unequip [{si+1}] {tname} --", ("unequip_tool", si)))
            elif p.equipped_tool:
                items.append(("-- Unequip --", ("unequip_tool", 0)))

        elif slot_type == "accessory":
            for card in p.inventory:
                if card.current_state == 2 and card is not p.equipped_accessory:
                    cdata = card.get_current_data()
                    ctype = cdata.get("Type", "")
                    if ctype in ("Tool_Belt", "Accessory", "Belt", "Pouch", "Ammunition"):
                        items.append((cdata.get("Name", "???"), card))
            if p.equipped_accessory:
                items.append(("-- Unequip --", "unequip"))

        if not items:
            items.append(("(Nothing available)", None))

        # Cap at 10 items
        items = items[:10]

        # Build popup buttons stacking upward from just above the slot button
        popup_y = slot_btn.rect.y - 5
        btn_w = slot_btn.rect.width
        self.equip_popup_buttons = []
        for label, data in reversed(items):
            popup_y -= 34
            btn = UIButton(pygame.Rect(slot_btn.rect.x, popup_y, btn_w, 30), label, manager)
            self.equip_popup_buttons.append((btn, slot_type, data))
            self.ui_elements.append(btn)

        self.equip_popup_open = True
        self.equip_popup_slot = slot_type

    def _close_equip_popup(self):
        """Close the equipment popup menu."""
        for btn, _, _ in self.equip_popup_buttons:
            btn.kill()
            if btn in self.ui_elements:
                self.ui_elements.remove(btn)
        self.equip_popup_buttons = []
        self.equip_popup_open = False
        self.equip_popup_slot = None

    def _open_action_choice_popup(self, unit, hex_pos, actions):
        """Open a popup near the clicked unit showing available actions (melee, projectile, recruit)."""
        self._close_action_choice_popup()
        # Convert hex position to screen pixel
        cx, cy = self.hex_grid.get_hex_center(hex_pos[0], hex_pos[1])
        btn_w = 200
        btn_h = 30
        # Position popup to the right of the hex, offset slightly
        start_x = int(cx + self.hex_grid.hex_size * 0.8)
        start_y = int(cy - (len(actions) * (btn_h + 4)) // 2)
        # Clamp to screen bounds
        if start_x + btn_w > WINDOW_WIDTH:
            start_x = int(cx - self.hex_grid.hex_size * 0.8 - btn_w)
        if start_y < 0:
            start_y = 5
        if start_y + len(actions) * (btn_h + 4) > WINDOW_HEIGHT:
            start_y = WINDOW_HEIGHT - len(actions) * (btn_h + 4) - 5
        for i, (label, action_type, data) in enumerate(actions):
            y = start_y + i * (btn_h + 4)
            btn = UIButton(pygame.Rect(start_x, y, btn_w, btn_h), label, manager)
            self.action_choice_buttons.append((btn, action_type, data))
            self.ui_elements.append(btn)
        self.action_choice_open = True
        self.action_choice_target = unit

    def _close_action_choice_popup(self):
        """Close the action choice popup."""
        for btn, _, _ in self.action_choice_buttons:
            btn.kill()
            if btn in self.ui_elements:
                self.ui_elements.remove(btn)
        self.action_choice_buttons = []
        self.action_choice_open = False
        self.action_choice_target = None

    def _handle_action_choice(self, action_type, data):
        """Dispatch the chosen action from the action choice popup."""
        target = self.action_choice_target
        self._close_action_choice_popup()
        if not target:
            return
        current_player = game.current_player
        if action_type == "melee":
            self.selected_attack = current_player.attacks["melee"]["name"]
            self.player_mode = "attack"
            # Execute the attack on the target
            hex_pos = target.position
            if hex_pos:
                message, result = current_player.attack(target, self.selected_attack, self.hex_grid, game.current_party)
                self.add_to_log(message)
                if message:
                    if isinstance(result, list):
                        for hit_unit, hit_dmg, hit_defeated in result:
                            hit_unit.attack_flash = True
                            hit_unit.flash_start = pygame.time.get_ticks()
                            if hit_defeated:
                                hit_pos = hit_unit.position
                                if hit_pos:
                                    self.hex_grid.grid[hit_pos[0]][hit_pos[1]]["unit"] = None
                                if hit_unit in self.hex_grid.units:
                                    self.hex_grid.units.remove(hit_unit)
                                self.add_to_log(f"{hit_unit.name} defeated")
                                self.add_defeat_notification(hit_unit.name)
                                self.card_manager.track_card_usage(hit_unit.card_id, {"action": "defeated", "screen": "game"})
                                quest_results = game.current_quest_manager.update("unit_death", {"unit": hit_unit}, self.hex_grid, current_player)
                                for quest, qresult, msg in quest_results:
                                    self.add_to_log(msg)
                                self._handle_quest_chain()
                        self.update_quest_button()
                        self.show_stats(None)
                    else:
                        target.attack_flash = True
                        target.flash_start = pygame.time.get_ticks()
                        if result:
                            self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] = None
                            if target in self.hex_grid.units:
                                self.hex_grid.units.remove(target)
                            self.add_to_log(f"{target.name} defeated")
                            self.add_defeat_notification(target.name)
                            self.card_manager.track_card_usage(target.card_id, {"action": "defeated", "screen": "game"})
                            quest_results = game.current_quest_manager.update("unit_death", {"unit": target}, self.hex_grid, current_player)
                            for quest, qresult, msg in quest_results:
                                self.add_to_log(msg)
                            self._handle_quest_chain()
                            self.update_quest_button()
                            self.show_stats(None)
                self.player_info_label.set_text(self.get_player_info())
                self.selected_attack = None
                if current_player.action_used and not current_player.movement_used:
                    self.player_mode = "movement"
        elif action_type == "projectile":
            self.selected_attack = current_player.attacks["projectile"]["name"]
            self.player_mode = "attack"
            hex_pos = target.position
            if hex_pos:
                message, result = current_player.attack(target, self.selected_attack, self.hex_grid, game.current_party)
                self.add_to_log(message)
                if message:
                    if isinstance(result, list):
                        for hit_unit, hit_dmg, hit_defeated in result:
                            hit_unit.attack_flash = True
                            hit_unit.flash_start = pygame.time.get_ticks()
                            if hit_defeated:
                                hit_pos = hit_unit.position
                                if hit_pos:
                                    self.hex_grid.grid[hit_pos[0]][hit_pos[1]]["unit"] = None
                                if hit_unit in self.hex_grid.units:
                                    self.hex_grid.units.remove(hit_unit)
                                self.add_to_log(f"{hit_unit.name} defeated")
                                self.add_defeat_notification(hit_unit.name)
                                self.card_manager.track_card_usage(hit_unit.card_id, {"action": "defeated", "screen": "game"})
                                quest_results = game.current_quest_manager.update("unit_death", {"unit": hit_unit}, self.hex_grid, current_player)
                                for quest, qresult, msg in quest_results:
                                    self.add_to_log(msg)
                                self._handle_quest_chain()
                        self.update_quest_button()
                        self.show_stats(None)
                    else:
                        target.attack_flash = True
                        target.flash_start = pygame.time.get_ticks()
                        if result:
                            self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] = None
                            if target in self.hex_grid.units:
                                self.hex_grid.units.remove(target)
                            self.add_to_log(f"{target.name} defeated")
                            self.add_defeat_notification(target.name)
                            self.card_manager.track_card_usage(target.card_id, {"action": "defeated", "screen": "game"})
                            quest_results = game.current_quest_manager.update("unit_death", {"unit": target}, self.hex_grid, current_player)
                            for quest, qresult, msg in quest_results:
                                self.add_to_log(msg)
                            self._handle_quest_chain()
                            self.update_quest_button()
                            self.show_stats(None)
                self.player_info_label.set_text(self.get_player_info())
                self.selected_attack = None
                if current_player.action_used and not current_player.movement_used:
                    self.player_mode = "movement"
        elif action_type == "recruit":
            game.current_screen = "recruitment"
            recruitment_screen.initialize_screen(target)

    def _handle_equip_popup_selection(self, slot_type, data):
        """Handle equip/unequip from the popup menu."""
        if data is None:
            self._close_equip_popup()
            return

        p = game.current_player

        if slot_type == "melee":
            if data == "unequip":
                from player import CHARACTER_CLASSES
                defaults = CHARACTER_CLASSES[p.class_name]
                default_attacks = list(defaults["attacks"].items())
                old_melee = p.melee_weapon
                p.melee_weapon = None
                p.attacks["melee"]["name"] = default_attacks[1][0]
                p.attacks["melee"]["damage"] = default_attacks[1][1]
                # If both-type weapon was in projectile slot too, clear it
                if p.projectile_weapon and p.projectile_weapon is old_melee:
                    p.projectile_weapon = None
                    p.attacks["projectile"]["name"] = default_attacks[0][0]
                    p.attacks["projectile"]["damage"] = default_attacks[0][1]
                    p.projectile_range = defaults["projectile_range"]
                self.add_to_log("Unequipped melee weapon")
            else:
                p.equip_weapon(data)
                name = data.get_current_data().get("Name", "???")
                self.add_to_log(f"Equipped {name}")

        elif slot_type == "projectile":
            if data == "unequip":
                from player import CHARACTER_CLASSES
                defaults = CHARACTER_CLASSES[p.class_name]
                default_attacks = list(defaults["attacks"].items())
                # If both-type weapon, clear melee too
                if p.melee_weapon and p.projectile_weapon is p.melee_weapon:
                    p.melee_weapon = None
                    p.attacks["melee"]["name"] = default_attacks[1][0]
                    p.attacks["melee"]["damage"] = default_attacks[1][1]
                p.projectile_weapon = None
                p.attacks["projectile"]["name"] = default_attacks[0][0]
                p.attacks["projectile"]["damage"] = default_attacks[0][1]
                p.projectile_range = defaults["projectile_range"]
                p.projectile_range_type = "line_of_sight"
                p.projectile_include_pos = False
                p.projectile_exclude_adj = False
                self.add_to_log("Unequipped projectile weapon")
            else:
                p.equip_weapon(data)
                name = data.get_current_data().get("Name", "???")
                self.add_to_log(f"Equipped {name}")

        elif slot_type == "tool":
            if isinstance(data, tuple) and data[0] == "unequip_tool":
                slot_index = data[1]
                p.unequip_tool(slot_index)
                self.add_to_log(f"Unequipped tool from slot {slot_index + 1}")
            else:
                p.equip_tool(data)
                name = data.get_current_data().get("Name", "???")
                self.add_to_log(f"Equipped {name}")

        elif slot_type == "accessory":
            if data == "unequip":
                p.unequip_accessory()
                self.add_to_log("Unequipped accessory")
            else:
                p.equip_accessory(data)
                name = data.get_current_data().get("Name", "???")
                self.add_to_log(f"Equipped {name}")

        elif slot_type == "items":
            # Selected a consumable item from the Items popup
            item_name = data.get_current_data().get("Name", "???")
            self.selected_item = data
            self.item_targeting_mode = True
            self.player_mode = "item"
            self.add_to_log(f"Selected {item_name} - Click adjacent entity or self to use")
            self._close_equip_popup()
            return

        self._close_equip_popup()
        self.player_info_label.set_text(
            self.get_player_info()
        )
        self._create_equipment_toolbar()
        self.rebuild_left_panel()

    def _execute_special_attack(self, target):
        """Execute the player's special attack and handle results."""
        message, defeated_units = game.current_player.use_special_attack(target, self.hex_grid)
        self.add_to_log(message)

        # Handle defeated units
        for defeated_unit in defeated_units:
            if defeated_unit.position:
                row, col = defeated_unit.position
                self.hex_grid.grid[row][col]["unit"] = None
            if defeated_unit in self.hex_grid.units:
                self.hex_grid.units.remove(defeated_unit)
            self.add_to_log(f"{defeated_unit.name} defeated")
            self.add_defeat_notification(defeated_unit.name)
            self.card_manager.track_card_usage(defeated_unit.card_id, {"action": "defeated", "screen": "game"})
            # Notify quest system of unit death
            quest_results = game.current_quest_manager.update("unit_death", {"unit": defeated_unit}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)
            self._handle_quest_chain()

        if defeated_units:
            self.update_quest_button()
            self.show_stats(None)

        self.player_info_label.set_text(self.get_player_info())
        self.player_mode = "movement"

    def _attack_location(self, hex_pos, player):
        """Attack a spawn location and return (message, action_used)."""
        if not self.hex_grid.is_attackable_location(hex_pos[0], hex_pos[1]):
            return "This location cannot be attacked", False

        # Check if action has already been used
        if player.action_used:
            return "You've already used your action this turn", False

        # Determine attack type and damage
        is_projectile = self.selected_attack == player.attacks["projectile"]["name"]
        is_melee = self.selected_attack == player.attacks["melee"]["name"]

        ammo_card = None
        runout_check = False

        if is_melee:
            # Melee attack - must be adjacent
            distance = self.hex_grid.hex_distance(player.position, hex_pos)
            if distance != 1:
                return "Target not in melee range", False
            damage = player.attacks["melee"]["damage"]
        elif is_projectile:
            # Projectile attack - check range
            if not player._is_valid_projectile_target(hex_pos, self.hex_grid):
                distance = self.hex_grid.hex_distance(player.position, hex_pos)
                if player.projectile_exclude_adj and distance == 1:
                    return "Target too close for this weapon", False
                elif distance > player.projectile_range:
                    return "Target out of range", False
                else:
                    return "Target not in valid range pattern", False

            # Get damage (handle ammunition if required)
            attack_info = player.attacks.get("projectile", {})
            requires_ammo = attack_info.get("requires_ammo", False)

            if requires_ammo:
                ammo_card = player._get_equipped_ammunition()
                if not ammo_card:
                    return "No ammunition equipped - cannot fire!", False
                ammo_data = ammo_card.get_current_data()
                damage = int(ammo_data.get("Ammo_Damage", 0))
                # Check ammo runout after attack
                runout_check = True
            else:
                damage = attack_info.get("damage", 0)
                ammo_card = None
                runout_check = False
        else:
            return "Invalid attack type", False

        # Apply damage to the location
        damage_dealt, destroyed, message = self.hex_grid.damage_location(hex_pos[0], hex_pos[1], damage)

        if damage_dealt > 0:
            # Mark action as used
            player.action_used = True
            player.attack_flash = True
            player.flash_start = pygame.time.get_ticks()

            # Handle ammunition runout for projectile attacks
            if is_projectile and runout_check and ammo_card:
                ammo_data = ammo_card.get_current_data()
                runout_msg = player._check_ammo_runout(ammo_card, ammo_data)
                if runout_msg:
                    message += f" {runout_msg}"

            return message, True
        else:
            return message, False

    def update_quest_button(self):
        """Update the quest button text to reflect current quest count."""
        if hasattr(self, 'quest_button') and self.quest_button:
            quest_count = len(game.current_quest_manager.active_quests)
            self.quest_button.set_text(f"Quests ({quest_count}/5)")

    def _get_adjacent_neutral_npcs(self):
        """Get list of neutral NPCs adjacent to the player."""
        if not game.current_player or not game.current_player.position:
            return []

        adjacent_hexes = self.hex_grid.get_adjacent_hexes(*game.current_player.position)
        neutral_npcs = []

        for row, col in adjacent_hexes:
            if 0 <= row < self.hex_grid.rows and 0 <= col < self.hex_grid.cols:
                unit = self.hex_grid.grid[row][col].get("unit")
                if unit and hasattr(unit, 'allegiance') and unit.allegiance == "Neutral":
                    neutral_npcs.append(unit)

        return neutral_npcs

    def _calculate_recruitment_cost(self, unit):
        """Calculate recruitment cost based on NPC stats: HP/10 + melee + ranged + movement + 5"""
        if not unit:
            return 10
        hp_component = unit.max_hp // 10
        melee = unit.melee_damage if hasattr(unit, 'melee_damage') else 0
        ranged = unit.projectile_damage if hasattr(unit, 'projectile_damage') else 0
        movement = unit.movement if hasattr(unit, 'movement') else 3
        return hp_component + melee + ranged + movement + 5

    def show_instance_event(self, instance_card, target_player=None):
        """Show an instance event and switch to instance event screen."""
        import sys
        print(f"[DEBUG] show_instance_event START for {instance_card.name}", flush=True)

        # Use provided target player, or fall back to stored pending player, then current player
        if target_player is None:
            target_player = game.instance_manager.pending_instance_player or game.current_player
        print(f"[DEBUG] show_instance_event: target_player={target_player.name if target_player else 'None'}", flush=True)

        # Update hex_grid reference in instance manager
        game.instance_manager.set_hex_grid(self.hex_grid)
        print("[DEBUG] show_instance_event: set hex_grid", flush=True)

        # Resolve the instance and get outcome using the correct target player
        print("[DEBUG] show_instance_event: calling resolve_instance...", flush=True)
        try:
            outcome_text, needs_choice = game.instance_manager.resolve_instance(
                instance_card, self.hex_grid, target_player
            )
            print(f"[DEBUG] show_instance_event: resolve_instance returned, needs_choice={needs_choice}", flush=True)
        except Exception as e:
            import traceback
            print(f"[DEBUG] EXCEPTION in resolve_instance: {e}", flush=True)
            traceback.print_exc()
            sys.stdout.flush()
            outcome_text, needs_choice = "Error occurred.", False

        # Switch to instance event screen
        print(f"[DEBUG] show_instance_event: setting current_screen to instance_event (was {game._current_screen})", flush=True)
        game.current_screen = "instance_event"
        print(f"[DEBUG] show_instance_event: current_screen is now {game._current_screen}", flush=True)

        print("[DEBUG] show_instance_event: calling instance_event_screen.initialize_screen...", flush=True)
        # Determine target player name for display
        target_name = target_player.name if target_player and target_player.name else "Player"
        instance_event_screen.initialize_screen(instance_card, outcome_text, needs_choice, target_name, target_player)
        print("[DEBUG] show_instance_event: initialize_screen completed", flush=True)

        # Log the event
        self.add_to_log(f"EVENT: {instance_card.name}")
        print("[DEBUG] show_instance_event END", flush=True)

    def resume_after_instance(self):
        """Called after an instance event is resolved to continue the turn."""
        print(f"[DEBUG] resume_after_instance: turn_phase={self.turn_phase}, campaign={bool(self.campaign)}")
        # Show defeat notifications for any units killed by the instance event
        for name in game.instance_manager.defeated_units:
            self.add_defeat_notification(name)
        game.instance_manager.defeated_units.clear()
        # If we're still in transition phase (instance was triggered by transition card),
        # complete the transition and move to player phase
        if self.turn_phase == "transition":
            print("[DEBUG] In transition phase, completing transition...")
            # Complete transition phase processing
            self.hex_grid.on_turn_end()
            quest_results = game.current_quest_manager.update("turn_end", {}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)
            self._handle_quest_chain()

            # Check level completion (only matters for campaigns)
            level_complete = self.check_level_completion()
            print(f"[DEBUG] check_level_completion() returned {level_complete}")
            if level_complete:
                self.current_level_idx += 1
                stages = self.campaign.get("stages") or self.campaign.get("levels", []) if self.campaign else []
                print(f"[DEBUG] Incremented level_idx to {self.current_level_idx}, campaign stages={len(stages)}")
                if self.campaign and self.current_level_idx < len(stages):
                    self.load_campaign_level()
                    if game.multiplayer_mode:
                        self.turn_phase = "player1"
                        game.current_player_index = 0
                        self.hex_grid.active_turn_unit = game.players[0]
                        self.rebuild_left_panel()
                else:
                    self.add_to_log("Campaign Completed!")
                    print("[DEBUG] Campaign completed - going to main_menu!")
                    game.current_screen = "main_menu"
                    main_menu.initialize_buttons()
                    return

            # Move to player phase (or first living player in multiplayer)
            if game.multiplayer_mode:
                self._setup_multiplayer_player_phase()
            else:
                self.turn_phase = "player"
                self.hex_grid.active_turn_unit = game.player
            self.is_player_turn = True
            self.hex_grid.reset_location_visits()
            self._start_player_turn()
            print("[DEBUG] Moved to player phase")

        # Apply Turn_Start passives
        for msg in game.current_player.apply_passive_skills(self.hex_grid, "Turn_Start"):
            self.add_to_log(msg)
        self.update_turn_label()
        self.animating = self.check_animations()
        print(f"[DEBUG] resume_after_instance complete, current_screen={game._current_screen}")

    def resume_after_transition(self):
        """Called after transition event screen is dismissed to continue the turn."""
        # Check if transition triggered an instance event that needs to show
        if game.instance_manager.pending_instance:
            instance_card = game.instance_manager.pending_instance
            self.show_instance_event(instance_card)
            return

        # Complete the transition phase processing
        self.hex_grid.on_turn_end()

        # Notify quest system of turn end
        quest_results = game.current_quest_manager.update("turn_end", {}, self.hex_grid, game.current_player)
        for quest, result, msg in quest_results:
            self.add_to_log(msg)
        self._handle_quest_chain()

        # Check level completion (only matters for campaigns)
        if self.check_level_completion():
            self.current_level_idx += 1
            stages = self.campaign.get("stages") or self.campaign.get("levels", []) if self.campaign else []
            if self.campaign and self.current_level_idx < len(stages):
                self.load_campaign_level()
                if game.multiplayer_mode:
                    self.turn_phase = "player1"
                    game.current_player_index = 0
                    self.hex_grid.active_turn_unit = game.players[0]
                    self.rebuild_left_panel()
                else:
                    self.turn_phase = "player"
                    self.hex_grid.active_turn_unit = game.player
                self.is_player_turn = True
                self._start_player_turn()
            else:
                self.add_to_log("Campaign Completed!")
                game.current_screen = "main_menu"
                main_menu.initialize_buttons()
                return

        # Advance to player phase (or first living player in multiplayer)
        if game.multiplayer_mode:
            self._setup_multiplayer_player_phase()
        else:
            self.turn_phase = "player"
            self.hex_grid.active_turn_unit = game.player
        self.is_player_turn = True
        self.hex_grid.reset_location_visits()
        self._start_player_turn()

        # Apply Turn_Start passives at start of player turn
        for msg in game.current_player.apply_passive_skills(self.hex_grid, "Turn_Start"):
            self.add_to_log(msg)

        self.update_turn_label()
        self.animating = self.check_animations()

    def process_location_defense_turn(self):
        """Process defensive location attacks against hostile units."""
        active_locations = self.hex_grid.get_active_defensive_locations()
        if not active_locations:
            self.advance_turn()
            return

        attacks_fired = False
        for pos, loc_data in active_locations:
            garrison = loc_data.get("garrison_npcs", [])
            num_garrison = len(garrison)
            if num_garrison == 0:
                continue

            for defense in loc_data.get("defenses", []):
                if not defense.get("requires_npc"):
                    continue
                damage = defense.get("damage", 0)
                if damage <= 0:
                    continue

                # Calculate range for this defense
                d_range = self.hex_grid.calculate_range(
                    pos, defense["range_distance"], defense["range_type"],
                    defense.get("include_position", False), defense.get("exclude_adjacent", False)
                )

                # Find hostile units in range
                hostiles_in_range = []
                for hex_pos in d_range:
                    r, c = hex_pos
                    if 0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols:
                        unit = self.hex_grid.grid[r][c].get("unit")
                        if unit and hasattr(unit, 'allegiance') and unit.allegiance == "Hostile" and unit.hp > 0:
                            hostiles_in_range.append(unit)

                if not hostiles_in_range:
                    continue

                # Fire N attacks (N = garrison count), each at a random hostile
                loc_name = loc_data.get("card").get_current_data().get("Name", "Defense") if loc_data.get("card") else "Defense"
                for _ in range(num_garrison):
                    # Re-filter alive hostiles each shot
                    alive = [u for u in hostiles_in_range if u.hp > 0]
                    if not alive:
                        break
                    target = random.choice(alive)
                    target.hp -= damage
                    target.set_damage_text(damage)
                    self.add_to_log(f"{loc_name} defense hits {target.name} for {damage} damage")
                    attacks_fired = True

        # Process deaths from defense attacks
        if attacks_fired:
            dead_units = [u for u in self.hex_grid.units if u.hp <= 0]
            for dead_unit in dead_units:
                if dead_unit.position:
                    self.hex_grid.grid[dead_unit.position[0]][dead_unit.position[1]]["unit"] = None
                self.hex_grid.units.remove(dead_unit)
                self.add_to_log(f"{dead_unit.name} defeated")
                self.add_defeat_notification(dead_unit.name)
                self.card_manager.track_card_usage(dead_unit.card_id, {"action": "defeated", "screen": "game"})
                quest_results = game.current_quest_manager.update("unit_death", {"unit": dead_unit}, self.hex_grid, game.current_player)
                for quest, result, msg in quest_results:
                    self.add_to_log(msg)
                self._handle_quest_chain()
            self.player_info_label.set_text(self.get_player_info())

        self.advance_turn()

    def process_transition_turn(self):
        """Process the transition card's turn in the cycle."""
        if not game.transition_manager.has_active_transition():
            # No active transition card, skip to next phase
            self.advance_turn()
            return

        try:
            # Get the transition card and its outcomes
            transition_card = game.transition_manager.active_transition
            all_outcomes = transition_card.get_current_outcomes()

            # Determine target player(s) for multiplayer cycling
            if game.multiplayer_mode and len(game.players) >= 2:
                cycle = self.transition_target_cycle
                p1, p2 = game.players[0], game.players[1]

                if cycle == 0:
                    target_player = p1
                    target_label = p1.name or "Player 1"
                elif cycle == 1:
                    target_player = p2
                    target_label = p2.name or "Player 2"
                else:
                    target_player = p1  # Will also apply to p2
                    target_label = "Both Players"

                # Roll and apply to primary target
                selected_index, result_text, log_messages = game.transition_manager.process_transition_turn_with_index(
                    self.hex_grid, target_player
                )

                # For "Both" cycle, also apply same outcome to player 2
                if cycle == 2 and 0 <= selected_index < len(all_outcomes):
                    outcome = all_outcomes[selected_index]
                    outcome_type = outcome.get("type", "none")
                    params = outcome.get("params", {})
                    extra_result = game.transition_manager.apply_outcome(outcome_type, params, self.hex_grid, p2)
                    if extra_result:
                        result_text += f"\n{extra_result}"
                        log_messages.append(extra_result)

                self.transition_target_cycle = (self.transition_target_cycle + 1) % 3
            else:
                target_label = ""
                selected_index, result_text, log_messages = game.transition_manager.process_transition_turn_with_index(
                    self.hex_grid, game.current_player
                )

            # Log the transition events
            for msg in log_messages:
                self.add_to_log(msg)

            # Update UI in case stats changed
            self.player_info_label.set_text(self.get_player_info())

            # Show the transition event screen
            game.current_screen = "transition_event"
            transition_event_screen.initialize_screen(
                transition_card, all_outcomes, selected_index, result_text, target_label
            )
            return  # Wait for user to click OK

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            print(f"Error in transition turn: {e}")
            print(f"Full traceback:\n{tb_str}")
            self.add_to_log(f"[Transition Error]")
            # Skip to player phase on error (don't call advance_turn which would re-process transition)
            if game.multiplayer_mode:
                self.turn_phase = "player1"
                game.current_player_index = 0
                self.hex_grid.active_turn_unit = game.players[0]
                self.rebuild_left_panel()
            else:
                self.turn_phase = "player"
                self.hex_grid.active_turn_unit = game.player
            self.is_player_turn = True
            self.update_turn_label()

    def check_animations(self):
        animating = False
        # Update animations for all players (multiplayer or single player)
        all_players = self.hex_grid.players if self.hex_grid.players else ([self.hex_grid.player] if self.hex_grid.player else [])
        for player in all_players:
            if player and player.animating:
                player.update_animation(self.hex_grid)
                animating = True
        for unit in self.hex_grid.units:
            if unit.animating:
                unit.update_animation(self.hex_grid)  # Pass grid
                animating = True
            elif unit.damage_text:
                unit.update_animation(self.hex_grid)  # Update damage text fade only

        # Check for active attack animations
        if self.hex_grid.attack_anims.is_animating():
            animating = True

        # Check for pending NPC arrivals (quest NPCs moving to locations)
        if game.current_quest_manager.has_pending_arrivals():
            messages = game.current_quest_manager.update_pending_arrivals()
            for msg in messages:
                self.add_to_log(msg)
            animating = True  # Keep animating while there are pending arrivals

        return animating

    def _is_click_on_ui(self, pos):
        """Check if a screen position overlaps any visible UI element."""
        # Right panel covers the entire right side
        rp_rect = pygame.Rect(self.rp_x, 0, self.rp_width, self.rp_height)
        if rp_rect.collidepoint(pos):
            return True
        if self.equip_popup_open:
            for btn, _, _ in self.equip_popup_buttons:
                if btn.rect.collidepoint(pos):
                    return True
        for el in self.ui_elements:
            if hasattr(el, 'rect') and el.rect.collidepoint(pos):
                if hasattr(el, 'visible') and not el.visible:
                    continue
                return True
        return False

    def handle_event(self, event):
        # ESC opens pause menu
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            game.current_screen = "pause_menu"
            pause_menu_screen.initialize_screen()
            return
        if self.animating:
            return
        elif event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            # Dismiss equipment popup if clicking outside it
            if self.equip_popup_open and event.button == 1:
                on_popup = False
                for btn, _, _ in self.equip_popup_buttons:
                    if btn.rect.collidepoint(pos):
                        on_popup = True
                        break
                if not on_popup:
                    for btn in self.equip_toolbar_buttons:
                        if btn.rect.collidepoint(pos):
                            on_popup = True
                            break
                if not on_popup:
                    self._close_equip_popup()
            # Dismiss action choice popup if clicking outside it
            if self.action_choice_open and event.button == 1:
                on_action_popup = False
                for btn, _, _ in self.action_choice_buttons:
                    if btn.rect.collidepoint(pos):
                        on_action_popup = True
                        break
                if not on_action_popup:
                    self._close_action_choice_popup()
            # Skip hex grid processing if click is on a UI element
            if self._is_click_on_ui(pos):
                return
            hex_pos = self.hex_grid.get_hex_at_pixel(pos[0], pos[1])
            # Check if it's the current player's turn (single-player: "player", multiplayer: "player1" or "player2")
            is_player_turn = self.turn_phase in ("player", "player1", "player2")
            if event.button == 1 and hex_pos and is_player_turn:
                self.hex_grid.selected_hex = hex_pos
                unit = self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"]
                self.show_stats(unit, hex_pos)
                current_player = game.current_player
                # Auto-detect available actions when clicking on a unit (skip in recruit/skill modes)
                if not self.selected_attack and unit and isinstance(unit, Unit) and self.player_mode not in ("recruit", "skill", "item"):
                    available_actions = []
                    # Attack options only available if action not yet used
                    if not current_player.action_used:
                        melee_range = current_player.get_melee_attack_range(self.hex_grid)
                        proj_range = current_player.get_projectile_attack_range(self.hex_grid, game.current_party)
                        if melee_range and hex_pos in melee_range:
                            melee_name = current_player.attacks["melee"]["name"]
                            melee_dmg = current_player.attacks["melee"]["damage"]
                            available_actions.append((f"Melee: {melee_name} ({melee_dmg} dmg)", "melee", None))
                        if proj_range and hex_pos in proj_range:
                            proj_name = current_player.attacks["projectile"]["name"]
                            proj_dmg = current_player.attacks["projectile"]["damage"]
                            available_actions.append((f"Proj: {proj_name} ({proj_dmg} dmg)", "projectile", None))
                    # Recruit option available regardless of action_used
                    if unit.allegiance == "Neutral" and self.hex_grid.hex_distance(current_player.position, hex_pos) == 1:
                        cost = self._calculate_recruitment_cost(unit)
                        available_actions.append((f"Recruit {unit.name} (Cost: {cost})", "recruit", unit))
                    if len(available_actions) == 1:
                        action_type = available_actions[0][1]
                        if action_type == "melee":
                            self.selected_attack = current_player.attacks["melee"]["name"]
                            self.player_mode = "attack"
                        elif action_type == "projectile":
                            self.selected_attack = current_player.attacks["projectile"]["name"]
                            self.player_mode = "attack"
                        elif action_type == "recruit":
                            game.current_screen = "recruitment"
                            recruitment_screen.initialize_screen(unit)
                            return
                    elif len(available_actions) >= 2:
                        self._open_action_choice_popup(unit, hex_pos, available_actions)
                        return
                if self.player_mode == "attack" and self.selected_attack and unit and isinstance(unit, Unit):
                    message, result = current_player.attack(unit, self.selected_attack, self.hex_grid, game.current_party)
                    self.add_to_log(message)
                    if message:
                        # Handle piercing attack (returns list of hit units)
                        if isinstance(result, list):
                            for hit_unit, hit_dmg, hit_defeated in result:
                                hit_unit.attack_flash = True
                                hit_unit.flash_start = pygame.time.get_ticks()
                                if hit_defeated:
                                    hit_pos = hit_unit.position
                                    if hit_pos:
                                        self.hex_grid.grid[hit_pos[0]][hit_pos[1]]["unit"] = None
                                    if hit_unit in self.hex_grid.units:
                                        self.hex_grid.units.remove(hit_unit)
                                    self.add_to_log(f"{hit_unit.name} defeated")
                                    self.add_defeat_notification(hit_unit.name)
                                    self.card_manager.track_card_usage(hit_unit.card_id, {"action": "defeated", "screen": "game"})
                                    quest_results = game.current_quest_manager.update("unit_death", {"unit": hit_unit}, self.hex_grid, current_player)
                                    for quest, qresult, msg in quest_results:
                                        self.add_to_log(msg)
                                    self._handle_quest_chain()
                            self.update_quest_button()
                            self.show_stats(None)
                        else:
                            # Standard single-target attack
                            unit.attack_flash = True
                            unit.flash_start = pygame.time.get_ticks()
                            if result:
                                self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] = None
                                self.hex_grid.units.remove(unit)
                                self.add_to_log(f"{unit.name} defeated")
                                self.add_defeat_notification(unit.name)
                                self.card_manager.track_card_usage(unit.card_id, {"action": "defeated", "screen": "game"})
                                quest_results = game.current_quest_manager.update("unit_death", {"unit": unit}, self.hex_grid, current_player)
                                for quest, qresult, msg in quest_results:
                                    self.add_to_log(msg)
                                self._handle_quest_chain()
                                self.update_quest_button()
                                self.show_stats(None)
                        self.player_info_label.set_text(self.get_player_info())
                        self.selected_attack = None
                        # Auto-switch to movement mode after action is fully used
                        if current_player.action_used and not current_player.movement_used:
                            self.player_mode = "movement"
                elif not unit and not current_player.action_used and self.hex_grid.is_attackable_location(hex_pos[0], hex_pos[1]) and not self.selected_attack:
                    # Auto-detect attack type for spawn location
                    melee_range = current_player.get_melee_attack_range(self.hex_grid)
                    proj_range = current_player.get_projectile_attack_range(self.hex_grid, game.current_party)
                    if melee_range and hex_pos in melee_range:
                        self.selected_attack = current_player.attacks["melee"]["name"]
                        self.player_mode = "attack"
                    elif proj_range and hex_pos in proj_range:
                        self.selected_attack = current_player.attacks["projectile"]["name"]
                        self.player_mode = "attack"
                if self.player_mode == "attack" and self.selected_attack and not unit and self.hex_grid.is_attackable_location(hex_pos[0], hex_pos[1]):
                    # Attack a spawn location
                    message, action_used = self._attack_location(hex_pos, current_player)
                    if message:
                        self.add_to_log(message)
                    if action_used:
                        self.player_info_label.set_text(self.get_player_info())
                        self.selected_attack = None
                        if not current_player.movement_used:
                            self.player_mode = "movement"
                elif self.player_mode == "skill" and self.selected_skill:
                    # Use skill on target
                    target = unit if unit and isinstance(unit, Unit) else current_player
                    message, defeated = current_player.use_skill(self.selected_skill, target, self.hex_grid)
                    self.add_to_log(message)
                    if message and unit and isinstance(unit, Unit):
                        unit.attack_flash = True
                        unit.flash_start = pygame.time.get_ticks()
                        if defeated:
                            self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] = None
                            self.hex_grid.units.remove(unit)
                            self.add_to_log(f"{unit.name} defeated")
                            self.add_defeat_notification(unit.name)
                            self.card_manager.track_card_usage(unit.card_id, {"action": "defeated", "screen": "game"})
                            # Notify quest system of unit death
                            quest_results = game.current_quest_manager.update("unit_death", {"unit": unit}, self.hex_grid, current_player)
                            for quest, result, msg in quest_results:
                                self.add_to_log(msg)
                            self._handle_quest_chain()
                            self.update_quest_button()
                            self.show_stats(None)
                    self.player_info_label.set_text(self.get_player_info())
                    self.selected_skill = None
                    self.player_mode = "movement"
                    self.initialize_screen()  # Refresh to update cooldown display
                elif self.player_mode == "item" and self.selected_item:
                    # Use consumable item on target
                    target = None
                    if hex_pos == current_player.position:
                        target = current_player
                    elif self.hex_grid.hex_distance(current_player.position, hex_pos) == 1:
                        if unit and isinstance(unit, Unit):
                            target = unit
                        elif unit and hasattr(unit, 'class_name'):
                            # Another player in multiplayer
                            target = unit
                    if target is None:
                        self.add_to_log("No valid target - click self or adjacent entity")
                    else:
                        success, msg = current_player.use_item(self.selected_item, target, self.hex_grid)
                        self.add_to_log(msg)
                        if success:
                            self.player_info_label.set_text(self.get_player_info())
                            self._create_equipment_toolbar()
                        # Exit item mode after attempt
                        self.selected_item = None
                        self.item_targeting_mode = False
                        self.player_mode = "movement"
                elif self.player_mode == "recruit" and unit and isinstance(unit, Unit):
                    # Check if clicked unit is adjacent and neutral
                    distance = self.hex_grid.hex_distance(current_player.position, hex_pos)
                    if distance == 1 and unit.allegiance == "Neutral":
                        # Open recruitment screen
                        game.current_screen = "recruitment"
                        recruitment_screen.initialize_screen(unit)
                    elif unit.allegiance != "Neutral":
                        self.add_to_log(f"{unit.name} is not a neutral NPC")
                    else:
                        self.add_to_log("NPC is not adjacent to you")
                elif self.player_mode == "special_attack" and unit and isinstance(unit, Unit):
                    # Execute special attack on target
                    self._execute_special_attack(unit)
                elif hex_pos == current_player.position and self.hex_grid.is_location_hex(hex_pos[0], hex_pos[1]):
                    # Clicked on current position which is a location - reopen location screen
                    loc_data = self.hex_grid.location_data.get(hex_pos)
                    if loc_data and loc_data.get("card"):
                        game.current_screen = "location"
                        location_screen.initialize_screen(loc_data["card"], hex_pos, self.hex_grid)
                elif self.player_mode == "placement" and self.placement_mode and self.placement_card:
                    # Place the built location on the clicked hex
                    if unit:
                        self.add_to_log("Cannot place location on an occupied hex")
                    else:
                        success, msg = self.hex_grid.create_location_hex(hex_pos[0], hex_pos[1], self.placement_card)
                        self.add_to_log(msg)
                        if success:
                            # Remove from inventory if it's still there
                            if self.placement_card in current_player.inventory:
                                current_player.inventory.remove(self.placement_card)
                            # Exit placement mode
                            self.placement_mode = False
                            self.placement_card = None
                            self.player_mode = "movement"
                            self.initialize_screen()  # Refresh UI
                elif not current_player.movement_used and not unit:
                    path = self.hex_grid.find_path(current_player.position, hex_pos)
                    effective_movement = current_player.get_effective_movement(game.current_party)
                    if path and len(path) - 1 <= effective_movement:
                        success, msg = self.hex_grid.move_unit(current_player, *hex_pos)
                        if success:
                            self.add_to_log(msg)
                            current_player.movement_used = True
                            # Notify quest system of player movement
                            quest_results = game.current_quest_manager.update(
                                "unit_moved", {"unit": current_player, "position": hex_pos},
                                self.hex_grid, current_player
                            )
                            for quest, result, qmsg in quest_results:
                                self.add_to_log(qmsg)
                            self._handle_quest_chain()
                            # Draw card if applicable
                            card, card_msg = self.hex_grid.draw_card(hex_pos[0], hex_pos[1], self.card_manager)
                            if card:
                                party_msg = add_card_to_player(card)
                                if party_msg:
                                    self.add_to_log(party_msg)
                                self.add_to_log(card_msg)
                            # Check for linked level only if explicitly set
                            for hex_data in self.hex_grid.card_drawing_hexes:
                                if hex_data["row"] == hex_pos[0] and hex_data["column"] == hex_pos[1]:
                                    if hex_data.get("linked_level") and isinstance(hex_data["linked_level"], str):
                                        linked_level_file = os.path.join("levels", hex_data["linked_level"])
                                        if os.path.exists(linked_level_file):
                                            self.add_to_log(f"Entering {hex_data['linked_level']}")
                                            self.hex_grid.load_level(linked_level_file, self.card_manager, current_player)
                                            # Teleport player to new start position
                                            player_start = self.hex_grid.player.position
                                            current_player.teleport(self.hex_grid, *player_start)
                                            # Teleport allied NPCs
                                            allied_units = [u for u in self.hex_grid.units if u.allegiance == "Allied"]
                                            for i, ally in enumerate(allied_units):
                                                neighbors = self.hex_grid.get_neighbors(*player_start)
                                                if i < len(neighbors):
                                                    ally.teleport(self.hex_grid, *neighbors[i])
                                            self.initialize_screen()
                                            current_player.movement_used = False
                                            current_player.action_used = False
                                            current_player.reset_double_attack()
                                            break
                                        else:
                                            self.add_to_log(f"Linked level file not found: {hex_data['linked_level']}")
                                    break  # Exit loop after handling this hex
                            # Check for location hex
                            if self.hex_grid.is_location_hex(hex_pos[0], hex_pos[1]):
                                loc_data = self.hex_grid.location_data.get((hex_pos[0], hex_pos[1]))
                                loc_card = loc_data.get("card") if loc_data else None

                                # Draw location card if unassigned
                                if not loc_card:
                                    loc_card, draw_msg = self.hex_grid.draw_location_card(
                                        hex_pos[0], hex_pos[1], self.card_manager
                                    )
                                    self.add_to_log(draw_msg)

                                if loc_card:
                                    # Queue location UI to show after movement animation completes
                                    self.pending_location = {
                                        "card": loc_card,
                                        "pos": hex_pos,
                                        "hex_grid": self.hex_grid
                                    }
                                    # Don't show immediately - will show after animation in draw()

                            self.player_info_label.set_text(self.get_player_info())
                    else:
                        self.add_to_log("No valid path within movement range")
            elif event.button in (2, 3) and hex_pos:  # Middle mouse (2) or right-click (3) to pan
                self.dragging = True
                self.drag_button = event.button
                self.drag_start_x, self.drag_start_y = pos
                self.start_view_offset_x, self.start_view_offset_y = self.hex_grid.view_offset_x, self.hex_grid.view_offset_y
        elif event.type == pygame.MOUSEBUTTONUP and event.button in (2, 3):
            if hasattr(self, 'drag_button') and event.button == self.drag_button:
                self.dragging = False
        elif event.type == pygame.MOUSEMOTION:
            # Update hover hex tracking (always, even when not dragging)
            if not self._is_click_on_ui(event.pos):
                self.hex_grid.hovered_hex = self.hex_grid.get_hex_at_pixel(event.pos[0], event.pos[1])
                # Build damage preview for hover tooltip
                self.hex_grid.hover_extra_lines = []
                hover_pos = self.hex_grid.hovered_hex
                if hover_pos and not game.current_player.action_used:
                    hcell = self.hex_grid.grid[hover_pos[0]][hover_pos[1]] if (0 <= hover_pos[0] < self.hex_grid.rows and 0 <= hover_pos[1] < self.hex_grid.cols) else None
                    h_unit = hcell.get("unit") if hcell else None
                    if h_unit and isinstance(h_unit, Unit) and hasattr(h_unit, 'allegiance') and h_unit.allegiance == "Hostile":
                        cp = game.current_player
                        melee_r = cp.get_melee_attack_range(self.hex_grid)
                        proj_r = cp.get_projectile_attack_range(self.hex_grid, game.current_party)
                        if melee_r and hover_pos in melee_r:
                            m_dmg = cp.attacks["melee"]["damage"]
                            self.hex_grid.hover_extra_lines.append(f"~Melee: {m_dmg} dmg")
                        if proj_r and hover_pos in proj_r:
                            p_dmg = cp.attacks["projectile"]["damage"]
                            self.hex_grid.hover_extra_lines.append(f"~Proj: {p_dmg} dmg")
            else:
                self.hex_grid.hovered_hex = None
                self.hex_grid.hover_extra_lines = []
            if self.dragging:
                dx = event.pos[0] - self.drag_start_x
                dy = event.pos[1] - self.drag_start_y
                self.hex_grid.view_offset_x = self.start_view_offset_x + dx
                self.hex_grid.view_offset_y = self.start_view_offset_y + dy
                grid_width = self.hex_grid.cols * self.hex_grid.hex_size * 1.5
                grid_height = self.hex_grid.rows * self.hex_grid.hex_size * 1.732
                # Allow scrolling with padding so edges can be seen when zoomed in
                padding_x = WINDOW_WIDTH * 0.4  # 40% of window as padding
                padding_y = WINDOW_HEIGHT * 0.4
                min_offset_x = WINDOW_WIDTH - grid_width - padding_x
                max_offset_x = padding_x
                min_offset_y = WINDOW_HEIGHT - grid_height - padding_y
                max_offset_y = padding_y
                self.hex_grid.view_offset_x = max(min(self.hex_grid.view_offset_x, max_offset_x), min_offset_x)
                self.hex_grid.view_offset_y = max(min(self.hex_grid.view_offset_y, max_offset_y), min_offset_y)
        elif event.type == pygame.MOUSEWHEEL:
            # Skip zoom if mouse is over a UI element
            mx, my = pygame.mouse.get_pos()
            if self._is_click_on_ui((mx, my)):
                return
            if event.y > 0:
                zoom_factor = 1.1
            elif event.y < 0:
                zoom_factor = 0.9
            else:
                zoom_factor = 1.0
            if zoom_factor != 1.0:
                ox, oy = self.hex_grid.view_offset_x, self.hex_grid.view_offset_y
                s = self.hex_grid.hex_size
                new_s = s * zoom_factor
                if new_s < 10:
                    new_s = 10
                    zoom_factor = 10 / s
                elif new_s > 100:
                    new_s = 100
                    zoom_factor = 100 / s
                self.hex_grid.hex_size = new_s
                self.hex_grid.view_offset_x = mx - zoom_factor * (mx - ox)
                self.hex_grid.view_offset_y = my - zoom_factor * (my - oy)
                grid_width = self.hex_grid.cols * self.hex_grid.hex_size * 1.5
                grid_height = self.hex_grid.rows * self.hex_grid.hex_size * 1.732
                # Allow scrolling with padding so edges can be seen when zoomed in
                padding_x = WINDOW_WIDTH * 0.4  # 40% of window as padding
                padding_y = WINDOW_HEIGHT * 0.4
                min_offset_x = WINDOW_WIDTH - grid_width - padding_x
                max_offset_x = padding_x
                min_offset_y = WINDOW_HEIGHT - grid_height - padding_y
                max_offset_y = padding_y
                self.hex_grid.view_offset_x = max(min(self.hex_grid.view_offset_x, max_offset_x), min_offset_x)
                self.hex_grid.view_offset_y = max(min(self.hex_grid.view_offset_y, max_offset_y), min_offset_y)
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            # Handle log toggle
            if event.ui_element == self.log_toggle_button:
                self.log_minimized = not self.log_minimized
                log_x = (WINDOW_WIDTH - 600) // 2
                if self.log_minimized:
                    self.ui_elements[0].hide()
                    self.log_mini_label.show()
                    self.log_toggle_button.set_text("^")
                    self.log_toggle_button.set_relative_position((log_x, 45))
                else:
                    self.ui_elements[0].show()
                    self.log_mini_label.hide()
                    self.log_toggle_button.set_text("v")
                    self.log_toggle_button.set_relative_position((log_x, 45))
                return

            is_player_turn = self.turn_phase in ("player", "player1", "player2")

            # Action choice popup button clicks
            if self.action_choice_open:
                for btn, action_type, data in self.action_choice_buttons:
                    if event.ui_element == btn:
                        self._handle_action_choice(action_type, data)
                        return

            # Equipment popup button clicks
            if self.equip_popup_open:
                for popup_btn, slot_type, data in self.equip_popup_buttons:
                    if event.ui_element == popup_btn:
                        self._handle_equip_popup_selection(slot_type, data)
                        return

            # Equipment toolbar slot clicks (player turn only)
            if is_player_turn:
                slot_types = ["melee", "projectile", "accessory", "tool", "action", "items"]
                for i, btn in enumerate(self.equip_toolbar_buttons):
                    if event.ui_element == btn:
                        if slot_types[i] == "action":
                            self._handle_tool_action_click()
                            return
                        if slot_types[i] == "items":
                            self._handle_items_click()
                            return
                        if self.equip_popup_open and self.equip_popup_slot == slot_types[i]:
                            self._close_equip_popup()
                        else:
                            self._open_equip_popup(slot_types[i])
                        return

            # Handle attack submenu button clicks
            if self.attack_submenu_open:
                for btn, action_type, data in self.attack_submenu_buttons:
                    if event.ui_element == btn:
                        current_player = game.current_player
                        if action_type == "attack" and is_player_turn:
                            attack_name = data['name']
                            self.selected_attack = attack_name
                            self.player_mode = "attack"
                            self.selected_skill = None
                            self.hex_grid.selected_hex = None
                            self.add_to_log(f"Selected attack: {attack_name}")
                        elif action_type == "special" and is_player_turn:
                            if current_player.action_used:
                                self.add_to_log("Action already used this turn")
                            else:
                                self.player_mode = "special_attack"
                                self.selected_attack = None
                                self.selected_skill = None
                                self.hex_grid.selected_hex = None
                                if current_player.special_attack == "Spin Punch":
                                    self._execute_special_attack(None)
                                else:
                                    self.add_to_log(f"Select target for {current_player.special_attack}")
                        self._close_attack_submenu()
                        return

            # End Turn button (in toolbar, not left panel)
            if hasattr(self, 'end_turn_button') and event.ui_element == self.end_turn_button and is_player_turn:
                self.advance_turn()
                return

            # Menu button (in right panel)
            if event.ui_element == self.menu_button and is_player_turn:
                if self.attack_submenu_open:
                    self._close_attack_submenu()
                if self.action_choice_open:
                    self._close_action_choice_popup()
                game.current_screen = "tabbed_menu"
                tabbed_menu_screen.initialize_screen()
                return

            if event.ui_element in self.left_panel_buttons:
                text = event.ui_element.text
                # Close popups when clicking any left panel button
                if self.attack_submenu_open:
                    self._close_attack_submenu()
                if self.action_choice_open:
                    self._close_action_choice_popup()
                if text == "Search" and is_player_turn:
                    # Search for items using Searchable documents in inventory
                    current_player = game.current_player
                    if current_player.action_used:
                        self.add_to_log("Action already used this turn")
                    else:
                        # Get terrain at current position
                        player_pos = current_player.position
                        terrain = self.hex_grid.grid[player_pos[0]][player_pos[1]].get("terrain", "grass")
                        # Get location name if on a location hex
                        location_name = None
                        loc_data = self.hex_grid.location_data.get(player_pos)
                        if loc_data and loc_data.get("card"):
                            location_name = loc_data["card"].get_current_data().get("Name", "")
                        # Perform search
                        success, message, flipped_card = current_player.search(terrain, location_name)
                        self.add_to_log(message)
                        if success:
                            self.player_info_label.set_text(self.get_player_info())
                            self.initialize_screen()  # Refresh UI
                elif text == "End Turn" and is_player_turn:
                    self.advance_turn()
                elif is_player_turn:
                    # Check if it's a skill button
                    skill_button_clicked = False
                    for btn, skill_card in self.skill_buttons:
                        if event.ui_element == btn:
                            skill_name = skill_card.get_current_data().get("Name", "Unknown")
                            cooldown = game.current_player.skill_cooldowns.get(skill_name, 0)
                            if cooldown > 0:
                                self.add_to_log(f"{skill_name} is on cooldown ({cooldown} turns)")
                            else:
                                self.selected_skill = skill_card
                                self.player_mode = "skill"
                                self.hex_grid.selected_hex = None
                                self.add_to_log(f"Selected skill: {skill_name}")
                            skill_button_clicked = True
                            break

                    # Check if tool button was clicked (multi-slot support)
                    tool_button_clicked = False
                    if not skill_button_clicked:
                        # Check multi-slot tool buttons
                        for btn, slot_idx in self.tool_buttons:
                            if event.ui_element == btn:
                                current_player = game.current_player
                                # Check if this is a revival tool - auto-target dead ally
                                tool = current_player.get_tool_in_slot(slot_idx)
                                target = None
                                if tool:
                                    tool_data = tool.get_current_data()
                                    is_revival = str(tool_data.get("Revival", "false")).lower() == "true"
                                    if is_revival and game.multiplayer_mode:
                                        # Find dead player to revive
                                        for p in game.players:
                                            if p is not current_player and p.hp <= 0 and p.position:
                                                target = p
                                                break
                                        if not target:
                                            self.add_to_log("No fallen ally to revive")
                                            tool_button_clicked = True
                                            break
                                success, message = current_player.use_tool(slot_idx, target=target, grid=self.hex_grid)
                                self.add_to_log(message)
                                if success:
                                    self.player_info_label.set_text(self.get_player_info())
                                    self.rebuild_left_panel()  # Refresh to update tool buttons
                                tool_button_clicked = True
                                break

                        # Fallback to legacy single tool button
                        if not tool_button_clicked and self.tool_button and event.ui_element == self.tool_button:
                            current_player = game.current_player
                            target = None
                            tool = current_player.get_tool_in_slot(0)
                            if tool:
                                tool_data = tool.get_current_data()
                                is_revival = str(tool_data.get("Revival", "false")).lower() == "true"
                                if is_revival and game.multiplayer_mode:
                                    for p in game.players:
                                        if p is not current_player and p.hp <= 0 and p.position:
                                            target = p
                                            break
                            success, message = current_player.use_tool(0, target=target, grid=self.hex_grid)
                            self.add_to_log(message)
                            if success:
                                self.player_info_label.set_text(self.get_player_info())
                            tool_button_clicked = True

                    skill_button_clicked = skill_button_clicked or tool_button_clicked  # Prevent further processing

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        current_player = game.current_player
        is_player_turn = self.turn_phase in ("player", "player1", "player2")
        # Check animation state early so range displays are accurate this frame
        self.animating = self.check_animations()
        player_alive = current_player.hp > 0
        effective_movement = current_player.get_effective_movement(game.current_party)
        movement_range = self.hex_grid.get_valid_moves(current_player.position, effective_movement) if is_player_turn and player_alive and not current_player.movement_used and not self.animating else None

        # Build list of all available attack ranges to display simultaneously
        attack_ranges = []

        # Always-visible defense range rings for defensive locations
        for def_pos, def_loc in self.hex_grid.get_all_defensive_locations():
            garrison = def_loc.get("garrison_npcs", [])
            is_manned = len(garrison) > 0 and def_loc.get("state", 1) == 2
            for defense in def_loc.get("defenses", []):
                if not defense.get("requires_npc"):
                    continue
                d_range = self.hex_grid.calculate_range(
                    def_pos, defense["range_distance"], defense["range_type"],
                    defense.get("include_position", False), defense.get("exclude_adjacent", False)
                )
                if d_range:
                    r, g, b = defense.get("color", (255, 165, 0))
                    alpha = 140 if is_manned else 60
                    attack_ranges.append({
                        "range": d_range,
                        "color": (r, g, b, alpha),
                        "outline": (max(0, r - 60), max(0, g - 60), max(0, b - 60), alpha),
                        "inset": 0.40
                    })

        if is_player_turn and player_alive and not current_player.action_used and not self.animating and self.player_mode not in ("recruit", "item"):
            melee_range = current_player.get_melee_attack_range(self.hex_grid)
            if melee_range:
                attack_ranges.append({"range": melee_range, "color": (255, 69, 0, 220), "outline": (139, 0, 0, 220), "inset": 0.75})
            proj_range = current_player.get_projectile_attack_range(self.hex_grid, game.current_party)
            if proj_range:
                attack_ranges.append({"range": proj_range, "color": (191, 0, 255, 220), "outline": (75, 0, 130, 220), "inset": 0.55})

        # Show white rings around recruitable adjacent NPCs (always visible on player turn)
        if is_player_turn:
            adjacent_neutrals = self._get_adjacent_neutral_npcs()
            recruit_hexes = {npc_unit.position for npc_unit in adjacent_neutrals if npc_unit.position}
            if recruit_hexes:
                attack_ranges.append({"range": recruit_hexes, "color": (255, 255, 255, 220), "outline": (180, 180, 180, 220), "inset": 0.75})

        # In item targeting mode, show green rings on adjacent hexes + self
        if is_player_turn and self.player_mode == "item" and self.selected_item:
            item_hexes = set(self.hex_grid.get_adjacent_hexes(*current_player.position))
            item_hexes.add(current_player.position)
            attack_ranges.append({"range": item_hexes, "color": (0, 200, 100, 200), "outline": (0, 140, 70, 200), "inset": 0.75})

        # Get targetable units for visual highlighting from all attack ranges
        targetable_units = None
        all_attack_hexes = set()
        for ar in attack_ranges:
            all_attack_hexes |= ar["range"]
        if all_attack_hexes:
            targetable_units = self.hex_grid.get_targetable_units(all_attack_hexes, "player")

        self.hex_grid.draw(screen, movement_range, attack_ranges, self.colors, targetable_units)
        # Draw dark semi-transparent backgrounds behind UI panels
        panel_border_color = (58, 58, 92)  # Subtle indigo-gray border

        # --- Unified right panel background ---
        rp_rect = pygame.Rect(self.rp_x, 0, self.rp_width, self.rp_height)
        rp_bg = pygame.Surface((rp_rect.width, rp_rect.height), pygame.SRCALPHA)
        rp_bg.fill((10, 10, 30, 180))
        screen.blit(rp_bg, rp_rect.topleft)
        pygame.draw.rect(screen, panel_border_color, rp_rect, 1)

        # Section headers (muted gold text)
        header_font = self.rp_header_font
        header_color = (180, 160, 100)
        # "Player" header
        player_hdr = header_font.render("Player", True, header_color)
        screen.blit(player_hdr, (self.rp_x + self.rp_pad, 4))
        # "Selected" header
        selected_hdr = header_font.render("Selected", True, header_color)
        screen.blit(selected_hdr, (self.rp_x + self.rp_pad, self.rp_stats_y - 20))

        # Section divider lines
        # Divider between Player and Selected
        div1_y = self.rp_stats_y - 24
        pygame.draw.line(screen, panel_border_color,
                         (self.rp_x + self.rp_pad, div1_y),
                         (self.rp_x + self.rp_width - self.rp_pad, div1_y), 1)
        # Divider above Menu button
        div2_y = self.rp_menu_y - 6
        pygame.draw.line(screen, panel_border_color,
                         (self.rp_x + self.rp_pad, div2_y),
                         (self.rp_x + self.rp_width - self.rp_pad, div2_y), 1)

        # --- Other panel backgrounds (log, turn label) ---
        panel_rects = []
        if not self.log_minimized:
            panel_rects.append(self.ui_elements[0].rect)
        else:
            # Background behind minimized log (toggle + label)
            if self.log_toggle_button and self.log_mini_label:
                mini_rect = pygame.Rect(self.log_toggle_button.rect.x, self.log_toggle_button.rect.y,
                                        self.log_mini_label.rect.right - self.log_toggle_button.rect.x,
                                        self.log_toggle_button.rect.height)
                panel_rects.append(mini_rect)
        panel_rects.append(self.ui_elements[2].rect)  # Turn label
        for rect in panel_rects:
            padded = rect.inflate(6, 6)
            bg_surf = pygame.Surface((padded.width, padded.height), pygame.SRCALPHA)
            bg_surf.fill((10, 10, 30, 180))
            screen.blit(bg_surf, padded.topleft)
            pygame.draw.rect(screen, panel_border_color, padded, 1)
        # Left panel buttons background
        if self.left_panel_buttons:
            first_btn = self.left_panel_buttons[0]
            last_btn = self.left_panel_buttons[-1]
            lp_rect = pygame.Rect(first_btn.rect.x - 4, first_btn.rect.y - 4,
                                  first_btn.rect.width + 8, last_btn.rect.bottom - first_btn.rect.y + 8)
            bg_surf = pygame.Surface((lp_rect.width, lp_rect.height), pygame.SRCALPHA)
            bg_surf.fill((10, 10, 30, 140))
            screen.blit(bg_surf, lp_rect.topleft)
            pygame.draw.rect(screen, panel_border_color, lp_rect, 1)
        # Equipment toolbar background (includes end turn button)
        if self.equip_toolbar_buttons:
            first = self.equip_toolbar_buttons[0]
            last_btn = self.end_turn_button if hasattr(self, 'end_turn_button') and self.end_turn_button else self.equip_toolbar_buttons[-1]
            bg = pygame.Rect(first.rect.x - 6, first.rect.y - 6,
                             last_btn.rect.right - first.rect.x + 12, first.rect.height + 12)
            bg_surf = pygame.Surface((bg.width, bg.height), pygame.SRCALPHA)
            bg_surf.fill((10, 10, 30, 180))
            screen.blit(bg_surf, bg.topleft)
            pygame.draw.rect(screen, panel_border_color, bg, 1)
        manager.draw_ui(screen)
        # Draw colored borders on equipment toolbar buttons
        if self.equip_toolbar_buttons and len(self.equip_toolbar_buttons) >= 2:
            # Melee button: red-orange border (matches melee range color)
            pygame.draw.rect(screen, (255, 69, 0), self.equip_toolbar_buttons[0].rect, 2)
            # Projectile button: purple border (matches projectile range color)
            pygame.draw.rect(screen, (191, 0, 255), self.equip_toolbar_buttons[1].rect, 2)
        # Dim empty toolbar slots with a dark overlay
        if self.equip_toolbar_buttons and len(self.equip_toolbar_buttons) >= 6:
            empty_labels = ("---",)
            for i, btn in enumerate(self.equip_toolbar_buttons):
                label_text = btn.text if hasattr(btn, 'text') else ""
                if label_text.endswith("---"):
                    dim_surf = pygame.Surface((btn.rect.width, btn.rect.height), pygame.SRCALPHA)
                    dim_surf.fill((0, 0, 0, 80))
                    screen.blit(dim_surf, btn.rect.topleft)
        # End Turn button: gold border
        if hasattr(self, 'end_turn_button') and self.end_turn_button:
            pygame.draw.rect(screen, (180, 160, 60), self.end_turn_button.rect, 2)
        # Items button: green border when in item targeting mode
        if self.item_targeting_mode and len(self.equip_toolbar_buttons) >= 6:
            pygame.draw.rect(screen, (0, 200, 100), self.equip_toolbar_buttons[5].rect, 2)
        # Draw colored outlines on attack submenu buttons
        if self.attack_submenu_open:
            for btn, _, _ in self.attack_submenu_buttons:
                if hasattr(btn, '_outline_color'):
                    pygame.draw.rect(screen, btn._outline_color, btn.rect, 2)
        # Draw background behind action choice popup
        if self.action_choice_open and self.action_choice_buttons:
            first_btn = self.action_choice_buttons[0][0]
            last_btn = self.action_choice_buttons[-1][0]
            popup_rect = pygame.Rect(first_btn.rect.x - 6, first_btn.rect.y - 6,
                                     first_btn.rect.width + 12,
                                     last_btn.rect.bottom - first_btn.rect.y + 12)
            bg_surf = pygame.Surface((popup_rect.width, popup_rect.height), pygame.SRCALPHA)
            bg_surf.fill((10, 10, 30, 200))
            screen.blit(bg_surf, popup_rect.topleft)
            pygame.draw.rect(screen, (80, 80, 120), popup_rect, 1)
        self.draw_defeat_notifications()
        # Check for pending location screen (show after movement animation completes)
        if self.pending_location and not self.animating:
            loc_data = self.pending_location
            self.pending_location = None
            game.current_screen = "location"
            location_screen.initialize_screen(loc_data["card"], loc_data["pos"], loc_data["hex_grid"])
            return
        # Check for pending defeat screen (show after death animation completes)
        if (self.pending_defeat or self.hex_grid.game_over) and not self.animating:
            self.pending_defeat = False
            game.current_screen = "defeat"
            defeat_screen.initialize_screen()
            return
        # Process turn queue for consecutive unit animations
        if self.turn_phase not in ("player", "player1", "player2"):
            self.update_turn_queue()

# Game Settings screen
class GameSettingsScreen:
    def __init__(self):
        self.ui_elements = []

    def initialize_screen(self):
        manager.clear_and_reset()
        self.ui_elements = [
            UILabel(pygame.Rect(0, 50, WINDOW_WIDTH, 50), "Settings", manager, anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect(20, 20, 150, 50), "Return to Game", manager)
        ]

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED and event.ui_element == self.ui_elements[1]:
            game.current_screen = "game"
            game_screen.initialize_screen()

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)

# InstanceEventScreen class
class InstanceEventScreen:
    """Full-screen modal for instance events."""

    def __init__(self):
        self.ui_elements = []
        self.instance_card = None
        self.outcome_text = ""
        self.choices = []
        self.choice_buttons = []
        self.continue_button = None
        self.needs_choice = False
        self.closing = False  # Prevent event processing after close starts
        self.target_player = None  # Player affected by this instance

    def initialize_screen(self, instance_card, outcome_text, needs_choice=False, target_name="", target_player=None):
        """Display the event and its outcome."""
        manager.clear_and_reset()
        self.instance_card = instance_card
        self.outcome_text = outcome_text
        self.needs_choice = needs_choice
        self.target_name = target_name
        self.target_player = target_player  # Store affected player for choice resolution
        self.choice_buttons = []
        self.ui_elements = []
        self.closing = False  # Reset closing flag when screen opens

        # Target player label
        y_pos = 20
        if target_name:
            if game.multiplayer_mode and len(game.players) >= 2 and target_name == (game.players[1].name or "Player 2"):
                label_color = "#4488FF"  # Blue for P2
            else:
                label_color = "#44FF44"  # Green for P1
            target_text = f"<font color='{label_color}' size=4.5><b>Affecting: {target_name}</b></font>"
            target_box = UITextBox(
                target_text,
                pygame.Rect((WINDOW_WIDTH - 500) // 2, y_pos, 500, 40),
                manager
            )
            self.ui_elements.append(target_box)
            y_pos += 45

        # Title
        title_label = UILabel(
            pygame.Rect(0, y_pos, WINDOW_WIDTH, 50),
            f"EVENT: {instance_card.name}",
            manager,
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(title_label)
        y_pos += 55

        # Description box
        desc_text = f"<font color='#FFFFFF' size=4>{instance_card.description}</font>"
        desc_box = UITextBox(
            desc_text,
            pygame.Rect((WINDOW_WIDTH - 600) // 2, y_pos, 600, 100),
            manager
        )
        self.ui_elements.append(desc_box)
        y_pos += 110

        # Outcome text box
        outcome_display = f"<font color='#FFFF00' size=4>{outcome_text}</font>"
        outcome_box = UITextBox(
            outcome_display,
            pygame.Rect((WINDOW_WIDTH - 600) // 2, y_pos, 600, 150),
            manager
        )
        self.ui_elements.append(outcome_box)
        y_pos += 160

        if needs_choice:
            # Show choice buttons
            self.choices = game.instance_manager.get_pending_choices()
            for i, choice in enumerate(self.choices):
                choice_name = choice.get("name", f"Choice {i+1}")
                risk = choice.get("risk", 0)
                risk_text = f" (Risk: {int(risk * 100)}%)" if risk > 0 else ""
                btn = UIButton(
                    pygame.Rect((WINDOW_WIDTH - 300) // 2, y_pos, 300, 50),
                    f"{choice_name}{risk_text}",
                    manager
                )
                self.choice_buttons.append(btn)
                self.ui_elements.append(btn)
                y_pos += 60
        else:
            # Show continue button
            self.continue_button = UIButton(
                pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 50),
                "Continue",
                manager
            )
            self.ui_elements.append(self.continue_button)

    def show_result(self, result_text):
        """Show the result of a player choice."""
        manager.clear_and_reset()
        self.ui_elements = []
        self.choice_buttons = []

        # Title
        title_label = UILabel(
            pygame.Rect(0, 50, WINDOW_WIDTH, 50),
            f"EVENT: {self.instance_card.name}",
            manager,
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(title_label)

        # Result text box
        result_display = f"<font color='#00FF00' size=4>{result_text}</font>"
        result_box = UITextBox(
            result_display,
            pygame.Rect((WINDOW_WIDTH - 600) // 2, 150, 600, 200),
            manager
        )
        self.ui_elements.append(result_box)

        # Continue button
        self.continue_button = UIButton(
            pygame.Rect((WINDOW_WIDTH - 200) // 2, 400, 200, 50),
            "Continue",
            manager
        )
        self.ui_elements.append(self.continue_button)
        self.needs_choice = False

    def handle_event(self, event):
        # Prevent processing events after close has started
        if self.closing:
            return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            # Check for choice buttons
            for i, btn in enumerate(self.choice_buttons):
                if event.ui_element == btn:
                    result = game.instance_manager.resolve_player_choice(i, game_screen.hex_grid, self.target_player or game.current_player)
                    self.show_result(result)
                    return

            # Check for continue button
            if event.ui_element == self.continue_button:
                self.close()

    def close(self):
        """Return to game, resume player turn."""
        print(f"[DEBUG] InstanceEventScreen.close() called, current_screen={game._current_screen}")
        self.closing = True  # Prevent further event processing
        game.instance_manager.clear_pending()
        game.current_screen = "game"
        print(f"[DEBUG] Set current_screen to game, now={game._current_screen}")
        game_screen.initialize_screen()
        # Update player info in case HP or inventory changed
        game_screen.player_info_label.set_text(game_screen.get_player_info())
        # Resume the turn that was interrupted by the instance event
        print("[DEBUG] Calling resume_after_instance...")
        game_screen.resume_after_instance()
        print(f"[DEBUG] After resume_after_instance, current_screen={game._current_screen}")

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# TransitionEventScreen class
class TransitionEventScreen:
    """Full-screen modal for transition card events showing all outcomes."""

    def __init__(self):
        self.ui_elements = []
        self.transition_card = None
        self.all_outcomes = []
        self.selected_index = -1
        self.selected_outcome = None
        self.result_text = ""
        self.ok_button = None
        self.closing = False  # Prevent event processing after close starts
        self.target_label = ""

    def initialize_screen(self, transition_card, all_outcomes, selected_index, result_text, target_label=""):
        """Display the transition card with all outcomes, highlighting the selected one."""
        manager.clear_and_reset()
        self.transition_card = transition_card
        self.all_outcomes = all_outcomes
        self.selected_index = selected_index
        self.selected_outcome = all_outcomes[selected_index] if 0 <= selected_index < len(all_outcomes) else None
        self.result_text = result_text
        self.target_label = target_label
        self.ui_elements = []
        self.closing = False  # Reset closing flag when screen opens

        # Title - Card name and state
        state_text = " (Night)" if transition_card.current_state == 2 else " (Day)" if transition_card.states == 2 else ""
        is_survival = game.game_mode != "creative"

        if is_survival:
            # Survival mode: larger fonts throughout
            title_text = f"<font color='#FFFFFF' size=5.5><b>WORLD EVENT: {transition_card.get_current_name()}{state_text}</b></font>"
            title_box = UITextBox(
                title_text,
                pygame.Rect((WINDOW_WIDTH - 800) // 2, 20, 800, 50),
                manager
            )
            self.ui_elements.append(title_box)

            if target_label:
                if target_label == "Both Players":
                    label_color = "#FFD700"
                elif game.multiplayer_mode and len(game.players) >= 2 and target_label == (game.players[1].name or "Player 2"):
                    label_color = "#4488FF"
                else:
                    label_color = "#44FF44"
                target_text = f"<font color='{label_color}' size=5><b>Affecting: {target_label}</b></font>"
                target_box = UITextBox(
                    target_text,
                    pygame.Rect((WINDOW_WIDTH - 500) // 2, 70, 500, 45),
                    manager
                )
                self.ui_elements.append(target_box)

            desc_y = 125 if target_label else 80
            desc_text = f"<font color='#AAAAAA' size=4.5>{transition_card.get_current_description()}</font>"
            desc_box = UITextBox(
                desc_text,
                pygame.Rect((WINDOW_WIDTH - 800) // 2, desc_y, 800, 80),
                manager
            )
            self.ui_elements.append(desc_box)
        else:
            # Creative mode: original compact fonts
            title_label = UILabel(
                pygame.Rect(0, 20, WINDOW_WIDTH, 40),
                f"WORLD EVENT: {transition_card.get_current_name()}{state_text}",
                manager,
                anchors={'centerx': 'centerx'}
            )
            self.ui_elements.append(title_label)

            if target_label:
                if target_label == "Both Players":
                    label_color = "#FFD700"
                elif game.multiplayer_mode and len(game.players) >= 2 and target_label == (game.players[1].name or "Player 2"):
                    label_color = "#4488FF"
                else:
                    label_color = "#44FF44"
                target_text = f"<font color='{label_color}' size=4><b>Affecting: {target_label}</b></font>"
                target_box = UITextBox(
                    target_text,
                    pygame.Rect((WINDOW_WIDTH - 400) // 2, 55, 400, 35),
                    manager
                )
                self.ui_elements.append(target_box)

            desc_y = 95 if target_label else 60
            desc_text = f"<font color='#AAAAAA' size=3>{transition_card.get_current_description()}</font>"
            desc_box = UITextBox(
                desc_text,
                pygame.Rect((WINDOW_WIDTH - 700) // 2, desc_y, 700, 50),
                manager
            )
            self.ui_elements.append(desc_box)

        if game.game_mode == "creative":
            # Creative mode: show all outcomes with probabilities
            outcomes_header = UILabel(
                pygame.Rect((WINDOW_WIDTH - 700) // 2, desc_y + 55, 700, 25),
                "Possible Outcomes:",
                manager
            )
            self.ui_elements.append(outcomes_header)

            y_pos = desc_y + 85
            for i, outcome in enumerate(all_outcomes):
                prob = outcome.get("probability", 0)
                prob_pct = int(prob * 100)
                outcome_type = outcome.get("type", "none")
                outcome_text = outcome.get("text", "Something happens...")

                is_selected = (i == selected_index)

                if is_selected:
                    color = "#00FF00"
                    prefix = ">>> "
                    suffix = " <<<"
                else:
                    color = "#888888"
                    prefix = "    "
                    suffix = ""

                type_display = outcome_type.replace("_", " ").title()
                line_text = f"<font color='{color}' size=3>{prefix}[{prob_pct}%] {type_display}: {outcome_text}{suffix}</font>"

                outcome_box = UITextBox(
                    line_text,
                    pygame.Rect((WINDOW_WIDTH - 700) // 2, y_pos, 700, 35),
                    manager
                )
                self.ui_elements.append(outcome_box)
                y_pos += 38

            y_pos += 20
        else:
            # Survival mode: only show the selected outcome
            y_pos = desc_y + 55

        # Result section
        if game.game_mode == "creative":
            result_header = UILabel(
                pygame.Rect((WINDOW_WIDTH - 700) // 2, y_pos, 700, 25),
                "Result:",
                manager
            )
            self.ui_elements.append(result_header)
            y_pos += 30
            result_display = f"<font color='#FFFF00' size=4>{self.result_text}</font>"
            result_box = UITextBox(
                result_display,
                pygame.Rect((WINDOW_WIDTH - 700) // 2, y_pos, 700, 80),
                manager
            )
            self.ui_elements.append(result_box)
            y_pos += 100
        else:
            # Survival mode: larger, centered result with more breathing room
            y_pos += 20
            result_display = f"<font color='#FFFF00' size=5.5><b>{self.result_text}</b></font>"
            result_box = UITextBox(
                result_display,
                pygame.Rect((WINDOW_WIDTH - 800) // 2, y_pos, 800, 200),
                manager
            )
            self.ui_elements.append(result_box)
            y_pos += 220
        self.ok_button = UIButton(
            pygame.Rect((WINDOW_WIDTH - 150) // 2, y_pos, 150, 45),
            "OK",
            manager
        )
        self.ui_elements.append(self.ok_button)

    def handle_event(self, event):
        # Prevent processing events after close has started
        if self.closing:
            return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.ok_button:
                self.close()

    def close(self):
        """Return to game and continue the turn."""
        print(f"[DEBUG] TransitionEventScreen.close() called, current_screen={game._current_screen}")
        self.closing = True  # Prevent further event processing

        # Check if transition triggered an instance event BEFORE switching screens
        # This avoids rapidly switching game -> instance_event
        if game.instance_manager.pending_instance:
            instance_card = game.instance_manager.pending_instance
            target_player = game.instance_manager.pending_instance_player
            print(f"[DEBUG] Found pending instance: {instance_card.name}, target_player={target_player.name if target_player else 'None'}, calling show_instance_event")
            game_screen.show_instance_event(instance_card, target_player)
            print(f"[DEBUG] After show_instance_event, current_screen={game._current_screen}")
            return

        # No pending instance, go directly to game screen
        print("[DEBUG] No pending instance, going to game screen")
        game.current_screen = "game"
        game_screen.initialize_screen()
        # Update player info in case stats changed
        game_screen.player_info_label.set_text(game_screen.get_player_info())
        # Continue to player phase
        game_screen.resume_after_transition()
        print(f"[DEBUG] After resume_after_transition, current_screen={game._current_screen}")

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# ConfirmationScreen class
class PauseMenuScreen:
    """In-game pause menu with Continue, Save, Load, Restart, Settings, Main Menu, Quit."""

    def __init__(self):
        self.ui_elements = []
        self.buttons = {}
        self.game_snapshot = None  # Screenshot of the game behind the overlay

    def initialize_screen(self):
        # Capture current screen as background snapshot
        self.game_snapshot = screen.copy()
        manager.clear_and_reset()
        self.ui_elements = []
        self.buttons = {}

        # Title
        self.ui_elements.append(
            UILabel(pygame.Rect(0, 80, WINDOW_WIDTH, 60), "Paused", manager,
                    anchors={'centerx': 'centerx'})
        )

        # Centered column of buttons
        btn_width = 220
        btn_height = 46
        btn_spacing = 58
        button_labels = [
            "Continue", "Save Game", "Load Game",
            "Restart Level", "Settings", "Main Menu", "Quit Game"
        ]
        total_height = len(button_labels) * btn_spacing
        start_y = (WINDOW_HEIGHT - total_height) // 2 + 40
        btn_x = (WINDOW_WIDTH - btn_width) // 2

        for i, label in enumerate(button_labels):
            btn = UIButton(
                pygame.Rect(btn_x, start_y + i * btn_spacing, btn_width, btn_height),
                label, manager
            )
            self.buttons[label] = btn
            self.ui_elements.append(btn)

    def handle_event(self, event):
        # ESC returns to game (same as Continue)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            game.current_screen = "game"
            game_screen.initialize_screen()
            return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            text = event.ui_element.text
            if text == "Continue":
                game.current_screen = "game"
                game_screen.initialize_screen()
            elif text == "Save Game":
                is_player_turn = game_screen.turn_phase in ("player", "player1", "player2")
                if is_player_turn:
                    success, result = game_screen.save_manager.save_game(
                        game, game_screen, save_type="manual", save_label="Manual Save"
                    )
                    msg = "Game saved successfully." if success else f"Save failed: {result}"
                    game.current_screen = "confirmation"
                    confirmation_screen.initialize_screen(msg, options=["OK"],
                        callback=lambda _: self._return_to_pause())
                else:
                    game.current_screen = "confirmation"
                    confirmation_screen.initialize_screen(
                        "Can only save during your turn.", options=["OK"],
                        callback=lambda _: self._return_to_pause())
            elif text == "Load Game":
                game.current_screen = "confirmation"
                confirmation_screen.initialize_screen(
                    "Unsaved progress will be lost. Continue?",
                    options=["Yes", "No"],
                    callback=self._handle_load_confirm)
            elif text == "Restart Level":
                game.current_screen = "confirmation"
                confirmation_screen.initialize_screen(
                    "Are you sure you want to restart?",
                    options=["Yes", "No"],
                    callback=game_screen._handle_restart_confirm)
            elif text == "Settings":
                game.current_screen = "game_settings"
                game_settings_screen.initialize_screen()
            elif text == "Main Menu":
                game.current_screen = "confirmation"
                confirmation_screen.initialize_screen(
                    "Return to main menu? Unsaved progress will be lost.",
                    options=["Yes", "No"],
                    callback=self._handle_main_menu_confirm)
            elif text == "Quit Game":
                game.current_screen = "confirmation"
                confirmation_screen.initialize_screen(
                    "Are you sure you want to quit?",
                    options=["Yes", "No"],
                    callback=self._handle_quit_confirm)

    def _return_to_pause(self):
        game.current_screen = "pause_menu"
        self.initialize_screen()

    def _handle_load_confirm(self, choice):
        if choice == "Yes":
            game.current_screen = "save_load"
            save_load_screen.initialize_screen(mode="load")
        else:
            self._return_to_pause()

    def _handle_main_menu_confirm(self, choice):
        if choice == "Yes":
            game.current_screen = "main_menu"
            main_menu.initialize_buttons()
        else:
            self._return_to_pause()

    def _handle_quit_confirm(self, choice):
        if choice == "Yes":
            pygame.quit()
            sys.exit()
        else:
            self._return_to_pause()

    def draw(self):
        # Draw game snapshot behind a dark overlay
        if self.game_snapshot:
            screen.blit(self.game_snapshot, (0, 0))
            overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            overlay.fill((10, 10, 30, 180))
            screen.blit(overlay, (0, 0))
        else:
            screen.fill(DARK_CHARCOAL)
        # Draw title text manually with style
        title_font = pygame.font.Font(None, 64)
        title_shadow = title_font.render("Paused", True, (10, 10, 30))
        title_surf = title_font.render("Paused", True, (200, 180, 120))
        title_rect = title_surf.get_rect(centerx=WINDOW_WIDTH // 2, y=80)
        screen.blit(title_shadow, title_rect.move(2, 2))
        screen.blit(title_surf, title_rect)
        # Decorative line under title
        line_y = title_rect.bottom + 8
        pygame.draw.line(screen, (200, 180, 120, 100), (WINDOW_WIDTH // 2 - 100, line_y), (WINDOW_WIDTH // 2 + 100, line_y), 1)
        manager.draw_ui(screen)


class ConfirmationScreen:
    """A simple centered screen with a message and option buttons. Accepts a callback."""

    def __init__(self):
        self.ui_elements = []
        self.option_buttons = []
        self.callback = None

    def initialize_screen(self, message, options=None, callback=None):
        """
        Args:
            message: Text to display
            options: List of button labels (e.g. ["Yes", "No"])
            callback: Function called with the chosen option text
        """
        if options is None:
            options = ["OK"]
        self.callback = callback
        manager.clear_and_reset()
        self.ui_elements = []
        self.option_buttons = []

        # Message
        msg_width = min(600, WINDOW_WIDTH - 100)
        msg_height = 80
        msg_x = (WINDOW_WIDTH - msg_width) // 2
        msg_y = WINDOW_HEIGHT // 3
        self.ui_elements.append(
            UITextBox(f"<font color='#FFFFFF' size=4>{message}</font>",
                      pygame.Rect(msg_x, msg_y, msg_width, msg_height), manager)
        )

        # Option buttons
        btn_width = 180
        total_width = len(options) * btn_width + (len(options) - 1) * 20
        start_x = (WINDOW_WIDTH - total_width) // 2
        btn_y = msg_y + msg_height + 30

        for i, option_text in enumerate(options):
            btn = UIButton(
                pygame.Rect(start_x + i * (btn_width + 20), btn_y, btn_width, 50),
                option_text, manager
            )
            self.option_buttons.append(btn)
            self.ui_elements.append(btn)

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            for btn in self.option_buttons:
                if event.ui_element == btn:
                    if self.callback:
                        self.callback(btn.text)
                    return

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# SaveLoadScreen class
class SaveLoadScreen:
    """Full screen for browsing, loading, and deleting saves."""

    def __init__(self):
        self.ui_elements = []
        self.save_list = None
        self.detail_box = None
        self.load_button = None
        self.delete_button = None
        self.back_button = None
        self.mode = "load"  # "load" or "save"
        self.saves = []
        self.selected_index = -1
        self.save_manager = SaveManager()

    def initialize_screen(self, mode="load"):
        self.mode = mode
        self.selected_index = -1
        manager.clear_and_reset()
        self.ui_elements = []

        title_text = "Load Game" if mode == "load" else "Save Game"
        self.ui_elements.append(
            UILabel(pygame.Rect(0, 30, WINDOW_WIDTH, 50), title_text,
                    manager, anchors={'centerx': 'centerx'})
        )

        # Refresh saves list
        self.saves = self.save_manager.get_all_saves()
        display_items = [self.save_manager.format_save_display(s) for s in self.saves]

        # Save list
        list_width = WINDOW_WIDTH // 2
        list_height = WINDOW_HEIGHT - 250
        list_x = (WINDOW_WIDTH - list_width - 320) // 2
        list_y = 90

        self.save_list = UISelectionList(
            pygame.Rect(list_x, list_y, list_width, list_height),
            display_items, manager,
            allow_multi_select=False
        )
        self.ui_elements.append(self.save_list)

        # Detail box
        detail_x = list_x + list_width + 20
        detail_width = 300
        self.detail_box = UITextBox(
            "<font color='#AAAAAA'>Select a save to view details.</font>",
            pygame.Rect(detail_x, list_y, detail_width, list_height - 60),
            manager
        )
        self.ui_elements.append(self.detail_box)

        # Buttons at bottom
        btn_y = list_y + list_height + 15
        btn_width = 150

        self.load_button = UIButton(
            pygame.Rect(list_x, btn_y, btn_width, 45),
            "Load", manager
        )
        self.ui_elements.append(self.load_button)

        self.delete_button = UIButton(
            pygame.Rect(list_x + btn_width + 20, btn_y, btn_width, 45),
            "Delete", manager
        )
        self.ui_elements.append(self.delete_button)

        self.back_button = UIButton(
            pygame.Rect(list_x + (btn_width + 20) * 2, btn_y, btn_width, 45),
            "Back", manager
        )
        self.ui_elements.append(self.back_button)

    def handle_event(self, event):
        if event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.save_list:
                selected_text = event.text
                # Find the index
                display_items = [self.save_manager.format_save_display(s) for s in self.saves]
                if selected_text in display_items:
                    self.selected_index = display_items.index(selected_text)
                    # Show details
                    details = self.save_manager.format_save_details(self.saves[self.selected_index])
                    self.detail_box.set_text(f"<font color='#FFFFFF'>{details}</font>")
                else:
                    self.selected_index = -1

        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                # Return to wherever we came from
                if game_screen.game_started:
                    game.current_screen = "game"
                    game_screen.initialize_screen()
                else:
                    game.current_screen = "main_menu"
                    main_menu.initialize_buttons()

            elif event.ui_element == self.load_button:
                if self.selected_index >= 0 and self.selected_index < len(self.saves):
                    save_info = self.saves[self.selected_index]
                    save_data = self.save_manager.load_save_file(save_info["filepath"])
                    if save_data:
                        game.current_screen = "game"
                        game_screen.load_from_save(save_data)

            elif event.ui_element == self.delete_button:
                if self.selected_index >= 0 and self.selected_index < len(self.saves):
                    save_info = self.saves[self.selected_index]
                    self.save_manager.delete_save(save_info["filepath"])
                    # Refresh
                    self.initialize_screen(mode=self.mode)

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# DefeatScreen class
class DefeatScreen:
    def __init__(self):
        self.ui_elements = []
        self.load_save_button = None
        self.humorous_messages = [
            "You got smoked like a cheap cigar!",
            "Looks like you're the weakest link—goodbye!",
            "Defeated? Even the tutorial boss is laughing!",
            "You've been sent to the respawn realm!"
        ]

    def initialize_screen(self):
        manager.clear_and_reset()
        message = random.choice(self.humorous_messages)
        btn_x = (WINDOW_WIDTH - 200) // 2
        btn_y = WINDOW_HEIGHT // 2

        self.ui_elements = [
            UILabel(pygame.Rect(0, WINDOW_HEIGHT // 4, WINDOW_WIDTH, 50), message, manager, anchors={'centerx': 'centerx'}),
        ]

        # "Load Last Save" button (above Restart Level)
        save_mgr = SaveManager()
        latest_save = save_mgr.get_most_recent_save()
        if latest_save:
            self.load_save_button = UIButton(
                pygame.Rect(btn_x, btn_y, 200, 50), "Load Last Save", manager
            )
            self.ui_elements.append(self.load_save_button)
            btn_y += 70
        else:
            self.load_save_button = None

        restart_btn = UIButton(pygame.Rect(btn_x, btn_y, 200, 50), "Restart Level", manager)
        self.ui_elements.append(restart_btn)
        btn_y += 70
        menu_btn = UIButton(pygame.Rect(btn_x, btn_y, 200, 50), "Main Menu", manager)
        self.ui_elements.append(menu_btn)

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            text = event.ui_element.text
            if text == "Load Last Save":
                save_mgr = SaveManager()
                latest_save = save_mgr.get_most_recent_save()
                if latest_save:
                    save_data = save_mgr.load_save_file(latest_save["filepath"])
                    if save_data:
                        game.current_screen = "game"
                        game_screen.load_from_save(save_data)
            elif text == "Restart Level":
                game.current_screen = "game"
                game_screen.start_new_game(level_file=game_screen.current_level_file,
                                           campaign_file=game_screen.campaign_file if game_screen.campaign else None)
                game_screen.initialize_screen()
            elif text == "Main Menu":
                game.current_screen = "main_menu"
                main_menu.initialize_buttons()

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# Card Browser Screen (Creative Mode - browse and add any card to inventory)
class CardBrowserScreen:
    def __init__(self):
        self.window = None
        self.card_list = None
        self.filter_dropdown = None
        self.search_entry = None
        self.info_text = None
        self.add_button = None
        self.add_all_button = None
        self.close_button = None
        self.state_dropdown = None
        self.selected_cards = []  # List of selected card IDs
        self.all_cards = []  # List of all card data from index
        self.filtered_cards = []  # Currently displayed cards after filtering

    def initialize_screen(self):
        manager.clear_and_reset()
        window_rect = pygame.Rect((WINDOW_WIDTH - 1000) // 2, (WINDOW_HEIGHT - 700) // 2, 1000, 700)
        self.window = UIWindow(window_rect, manager, "Card Browser (Creative Mode)")

        # Header
        UILabel(pygame.Rect(10, 5, 980, 30), "Browse and add cards to your inventory", manager, container=self.window)

        # Filter controls row
        UILabel(pygame.Rect(10, 40, 80, 25), "Filter:", manager, container=self.window)
        filter_options = ["All Cards", "Junk Cards", "Document Cards"]
        self.filter_dropdown = UIDropDownMenu(filter_options, "All Cards",
                                              pygame.Rect(90, 40, 180, 30), manager, container=self.window)

        UILabel(pygame.Rect(290, 40, 60, 25), "Search:", manager, container=self.window)
        self.search_entry = UITextEntryLine(pygame.Rect(350, 40, 200, 30), manager, container=self.window)

        UILabel(pygame.Rect(570, 40, 80, 25), "Add as:", manager, container=self.window)
        self.state_dropdown = UIDropDownMenu(["State 1 (Raw)", "State 2 (Crafted)"], "State 2 (Crafted)",
                                             pygame.Rect(650, 40, 150, 30), manager, container=self.window)

        # Load all cards first
        self._load_all_cards()

        # Build initial display list
        self.filtered_cards = self.all_cards.copy()
        display_items = [f"[{card['type'][:4]}] {card['name']}" for card in self.filtered_cards]
        if not display_items:
            display_items = ["No cards available"]

        # Card list (left side)
        UILabel(pygame.Rect(10, 80, 200, 25), f"Available Cards ({len(self.all_cards)}):", manager, container=self.window)
        self.card_list = UISelectionList(pygame.Rect(10, 105, 550, 400),
                                         display_items, manager, container=self.window,
                                         allow_multi_select=True)

        # Selected cards info (right side)
        UILabel(pygame.Rect(580, 80, 200, 25), "Card Details:", manager, container=self.window)
        self.info_text = UITextBox("<font color='#FFFFFF'>Select a card to view details</font>",
                                   pygame.Rect(580, 105, 390, 400), manager, container=self.window)

        # Buttons at bottom
        self.add_button = UIButton(pygame.Rect(10, 520, 180, 40), "Add Selected", manager, container=self.window)
        self.add_all_button = UIButton(pygame.Rect(200, 520, 180, 40), "Add All Filtered", manager, container=self.window)
        self.clear_selection_button = UIButton(pygame.Rect(390, 520, 180, 40), "Clear Selection", manager, container=self.window)
        self.close_button = UIButton(pygame.Rect(850, 620, 120, 35), "Close", manager, container=self.window)

        # Status label
        self.status_label = UILabel(pygame.Rect(10, 570, 600, 25), "0 cards selected", manager, container=self.window)

    # Card types that can be added to player inventory
    INVENTORY_CARD_TYPES = {"Junk Card", "Document Card"}

    def _load_all_cards(self):
        """Load all cards from card_index.json. Only includes inventory-compatible types (Junk, Document)."""
        self.all_cards = []
        try:
            # Use the existing load_card_index function from card_utils
            card_index = load_card_index()

            for card_id, card_info in card_index.items():
                # card_index uses "type" not "card_type"
                card_type = card_info.get("type", "Unknown")
                # Only include card types that can be added to inventory
                # Also allow compound types like "Document/Skill"
                if not any(t in card_type for t in self.INVENTORY_CARD_TYPES):
                    continue
                card_name = card_info.get("name", card_id)
                self.all_cards.append({
                    "id": card_id,
                    "name": card_name,
                    "type": card_type
                })

            # Sort by type then name
            self.all_cards.sort(key=lambda x: (x["type"], x["name"]))
            print(f"Card browser loaded {len(self.all_cards)} cards")
        except Exception as e:
            print(f"Error loading card index: {e}")
            import traceback
            traceback.print_exc()

    def _apply_filter(self):
        """Apply filter and search to card list."""
        # Handle pygame_gui dropdown which may return tuple (text, id)
        filter_option = self.filter_dropdown.selected_option
        if isinstance(filter_option, tuple):
            filter_type = filter_option[0]
        else:
            filter_type = filter_option

        search_text = self.search_entry.get_text().lower().strip()

        print(f"[CardBrowser] Applying filter: type='{filter_type}', search='{search_text}', all_cards={len(self.all_cards)}")

        self.filtered_cards = []
        for card in self.all_cards:
            # Filter by type
            if filter_type != "All Cards":
                # Convert filter option to card type
                type_map = {
                    "Junk Cards": "Junk Card",
                    "Document Cards": "Document Card",
                }
                expected_type = type_map.get(filter_type, "")
                if expected_type not in card["type"]:
                    continue

            # Filter by search text
            if search_text and search_text not in card["name"].lower() and search_text not in card["id"].lower():
                continue

            self.filtered_cards.append(card)

        # Update list display
        display_items = [f"[{card['type'][:4]}] {card['name']}" for card in self.filtered_cards]
        print(f"[CardBrowser] Filtered to {len(self.filtered_cards)} cards, display_items={len(display_items)}")
        self.card_list.set_item_list(display_items if display_items else ["No cards match filter"])

    def _get_card_details(self, card_info):
        """Get detailed info about a card."""
        try:
            card_data = load_card(card_info["id"])
            if not card_data:
                return f"<b>{card_info['name']}</b><br>Card file not found"

            lines = [f"<b>{card_info['name']}</b>"]
            lines.append(f"<i>Type: {card_info['type']}</i>")
            lines.append(f"ID: {card_info['id']}")
            lines.append("")

            # Show state 1 data
            data = card_data.get("data", {})
            lines.append("<b>State 1:</b>")
            for key, value in data.items():
                if value and not key.startswith("2nd_state_") and key not in ["id"]:
                    # Truncate long values
                    str_val = str(value)
                    if len(str_val) > 50:
                        str_val = str_val[:50] + "..."
                    lines.append(f"  {key}: {str_val}")

            # Show state 2 data if exists
            state2_fields = {k: v for k, v in data.items() if k.startswith("2nd_state_") and v}
            if state2_fields:
                lines.append("")
                lines.append("<b>State 2:</b>")
                for key, value in state2_fields.items():
                    display_key = key.replace("2nd_state_", "")
                    str_val = str(value)
                    if len(str_val) > 50:
                        str_val = str_val[:50] + "..."
                    lines.append(f"  {display_key}: {str_val}")

            return "<br>".join(lines)
        except Exception as e:
            return f"Error loading card: {e}"

    def _add_cards_to_inventory(self, card_infos):
        """Add selected cards to player inventory."""
        if not game.current_player:
            return "No active player!"

        state = 2 if "State 2" in self.state_dropdown.selected_option else 1
        added_count = 0

        for card_info in card_infos:
            try:
                card_data = load_card(card_info["id"])
                if card_data:
                    inv_card = InventoryCard(card_data)
                    inv_card.current_state = state
                    game.current_player.inventory.append(inv_card)
                    added_count += 1
            except Exception as e:
                print(f"Error adding card {card_info['id']}: {e}")

        return f"Added {added_count} card(s) to inventory"

    def handle_event(self, event):
        if event.type == pygame_gui.UI_WINDOW_CLOSE:
            if event.ui_element == self.window:
                game.current_screen = "tabbed_menu"
                tabbed_menu_screen.active_tab = "Inventory"
                tabbed_menu_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                game.current_screen = "tabbed_menu"
                tabbed_menu_screen.active_tab = "Inventory"
                tabbed_menu_screen.initialize_screen()
            elif event.ui_element == self.add_button:
                # Add selected cards
                if self.selected_cards:
                    msg = self._add_cards_to_inventory(self.selected_cards)
                    self.status_label.set_text(msg)
                    self.selected_cards = []
                else:
                    self.status_label.set_text("No cards selected!")
            elif event.ui_element == self.add_all_button:
                # Add all filtered cards
                if self.filtered_cards:
                    msg = self._add_cards_to_inventory(self.filtered_cards)
                    self.status_label.set_text(msg)
                else:
                    self.status_label.set_text("No cards to add!")
            elif event.ui_element == self.clear_selection_button:
                self.selected_cards = []
                self.status_label.set_text("Selection cleared")

        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            if event.ui_element == self.filter_dropdown:
                self._apply_filter()
                self.selected_cards = []
                self.status_label.set_text("0 cards selected")

        elif event.type == pygame_gui.UI_TEXT_ENTRY_CHANGED:
            if event.ui_element == self.search_entry:
                self._apply_filter()
                self.selected_cards = []
                self.status_label.set_text("0 cards selected")

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.card_list:
                # Find selected card
                selected_text = event.text
                # Parse card name from display format "[Type] Name"
                if "] " in selected_text:
                    card_name = selected_text.split("] ", 1)[1]
                    for card in self.filtered_cards:
                        if card["name"] == card_name:
                            # Toggle selection
                            if card in self.selected_cards:
                                self.selected_cards.remove(card)
                            else:
                                self.selected_cards.append(card)
                            # Show details
                            self.info_text.set_text(f"<font color='#FFFFFF'>{self._get_card_details(card)}</font>")
                            break
                self.status_label.set_text(f"{len(self.selected_cards)} card(s) selected")

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# NPC Browser Screen (Creative Mode - browse and add NPCs to party)
class NpcBrowserScreen:
    def __init__(self):
        self.window = None
        self.npc_list = None
        self.search_entry = None
        self.info_text = None
        self.add_button = None
        self.add_all_button = None
        self.close_button = None
        self.clear_selection_button = None
        self.status_label = None
        self.selected_npcs = []
        self.all_npcs = []
        self.filtered_npcs = []

    def initialize_screen(self):
        manager.clear_and_reset()
        window_rect = pygame.Rect((WINDOW_WIDTH - 1000) // 2, (WINDOW_HEIGHT - 700) // 2, 1000, 700)
        self.window = UIWindow(window_rect, manager, "NPC Browser (Creative Mode)")

        # Header
        UILabel(pygame.Rect(10, 5, 980, 30), "Browse and add NPCs to your party", manager, container=self.window)

        # Search controls row
        UILabel(pygame.Rect(10, 40, 60, 25), "Search:", manager, container=self.window)
        self.search_entry = UITextEntryLine(pygame.Rect(70, 40, 250, 30), manager, container=self.window)

        # Load NPC cards
        self._load_all_npcs()

        # Build initial display list
        self.filtered_npcs = self.all_npcs.copy()
        display_items = [npc['name'] for npc in self.filtered_npcs]
        if not display_items:
            display_items = ["No NPCs available"]

        # NPC list (left side)
        UILabel(pygame.Rect(10, 80, 300, 25), f"Available NPCs ({len(self.all_npcs)}):", manager, container=self.window)
        self.npc_list = UISelectionList(pygame.Rect(10, 105, 550, 400),
                                         display_items, manager, container=self.window,
                                         allow_multi_select=True)

        # NPC details (right side)
        UILabel(pygame.Rect(580, 80, 200, 25), "NPC Details:", manager, container=self.window)
        self.info_text = UITextBox("<font color='#FFFFFF'>Select an NPC to view details</font>",
                                   pygame.Rect(580, 105, 390, 400), manager, container=self.window)

        # Buttons at bottom
        self.add_button = UIButton(pygame.Rect(10, 520, 180, 40), "Add Selected", manager, container=self.window)
        self.add_all_button = UIButton(pygame.Rect(200, 520, 180, 40), "Add All Filtered", manager, container=self.window)
        self.clear_selection_button = UIButton(pygame.Rect(390, 520, 180, 40), "Clear Selection", manager, container=self.window)
        self.close_button = UIButton(pygame.Rect(850, 620, 120, 35), "Close", manager, container=self.window)

        # Status label
        self.status_label = UILabel(pygame.Rect(10, 570, 600, 25), "0 NPCs selected", manager, container=self.window)

    def _load_all_npcs(self):
        """Load all NPC cards from card_index.json."""
        self.all_npcs = []
        try:
            card_index = load_card_index()
            for card_id, card_info in card_index.items():
                card_type = card_info.get("type", "Unknown")
                if card_type != "NPC Card":
                    continue
                card_name = card_info.get("name", card_id)
                self.all_npcs.append({
                    "id": card_id,
                    "name": card_name,
                    "type": card_type
                })
            self.all_npcs.sort(key=lambda x: x["name"])
            print(f"NPC browser loaded {len(self.all_npcs)} NPCs")
        except Exception as e:
            print(f"Error loading NPC index: {e}")

    def _apply_filter(self):
        """Apply search filter to NPC list."""
        search_text = self.search_entry.get_text().lower().strip()
        self.filtered_npcs = []
        for npc in self.all_npcs:
            if search_text and search_text not in npc["name"].lower() and search_text not in npc["id"].lower():
                continue
            self.filtered_npcs.append(npc)
        display_items = [npc['name'] for npc in self.filtered_npcs]
        self.npc_list.set_item_list(display_items if display_items else ["No NPCs match filter"])

    def _get_npc_details(self, npc_info):
        """Get detailed info about an NPC card."""
        try:
            card_data = load_card(npc_info["id"])
            if not card_data:
                return f"<b>{npc_info['name']}</b><br>Card file not found"

            lines = [f"<b>{npc_info['name']}</b>"]
            lines.append(f"ID: {npc_info['id']}")
            lines.append("")

            data = card_data.get("data", {})
            for key, value in data.items():
                if value and not key.startswith("2nd_state_") and key not in ["id"]:
                    str_val = str(value)
                    if len(str_val) > 50:
                        str_val = str_val[:50] + "..."
                    lines.append(f"{key}: {str_val}")

            return "<br>".join(lines)
        except Exception as e:
            return f"Error loading NPC: {e}"

    def _add_npcs_to_party(self, npc_infos):
        """Add selected NPCs to the player's party."""
        if not game.current_player:
            return "No active player!"

        added_count = 0
        for npc_info in npc_infos:
            try:
                card_data = load_card(npc_info["id"])
                if card_data:
                    inv_card = InventoryCard(card_data)
                    game.current_party.append(inv_card)
                    added_count += 1
            except Exception as e:
                print(f"Error adding NPC {npc_info['id']}: {e}")

        return f"Added {added_count} NPC(s) to party"

    def handle_event(self, event):
        if event.type == pygame_gui.UI_WINDOW_CLOSE:
            if event.ui_element == self.window:
                game.current_screen = "tabbed_menu"
                tabbed_menu_screen.active_tab = "Party"
                tabbed_menu_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                game.current_screen = "tabbed_menu"
                tabbed_menu_screen.active_tab = "Party"
                tabbed_menu_screen.initialize_screen()
            elif event.ui_element == self.add_button:
                if self.selected_npcs:
                    msg = self._add_npcs_to_party(self.selected_npcs)
                    self.status_label.set_text(msg)
                    self.selected_npcs = []
                else:
                    self.status_label.set_text("No NPCs selected!")
            elif event.ui_element == self.add_all_button:
                if self.filtered_npcs:
                    msg = self._add_npcs_to_party(self.filtered_npcs)
                    self.status_label.set_text(msg)
                else:
                    self.status_label.set_text("No NPCs to add!")
            elif event.ui_element == self.clear_selection_button:
                self.selected_npcs = []
                self.status_label.set_text("Selection cleared")

        elif event.type == pygame_gui.UI_TEXT_ENTRY_CHANGED:
            if event.ui_element == self.search_entry:
                self._apply_filter()
                self.selected_npcs = []
                self.status_label.set_text("0 NPCs selected")

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.npc_list:
                selected_text = event.text
                if selected_text and selected_text != "No NPCs available" and selected_text != "No NPCs match filter":
                    for npc in self.filtered_npcs:
                        if npc["name"] == selected_text:
                            if npc in self.selected_npcs:
                                self.selected_npcs.remove(npc)
                            else:
                                self.selected_npcs.append(npc)
                            self.info_text.set_text(f"<font color='#FFFFFF'>{self._get_npc_details(npc)}</font>")
                            break
                self.status_label.set_text(f"{len(self.selected_npcs)} NPC(s) selected")

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        manager.draw_ui(screen)


# Main Game class
class Game:
    def __init__(self):
        self._current_screen = "main_menu"
        self._screen_changed_this_frame = False  # Prevents stray events after screen change
        self.player = None
        self.party = []  # List of allied NPC cards in the player's party (single-player mode)
        self.card_manager = CardManager()
        self.quest_manager = QuestManager(self.card_manager)
        self.instance_manager = InstanceManager(self.card_manager)
        self.transition_manager = TransitionManager(self.card_manager, self.instance_manager)
        # Multiplayer support
        self.players = []  # List of players for multiplayer [player1, player2]
        self.current_player_index = 0  # Whose turn it is (0 or 1)
        self.multiplayer_mode = False  # True when in 2-player mode
        self.quest_managers = []  # Per-player quest managers in multiplayer
        # Game mode: "survival" (normal) or "creative" (testing with card browser)
        self.game_mode = "survival"
        self.screens = {
            "main_menu": main_menu,
            "player_count": player_count_screen,
            "character_creation": character_creation_screen,
            "multiplayer_character_creation": multiplayer_character_creation_screen,
            "settings": settings_screen,
            "game": game_screen,
            "game_settings": game_settings_screen,
            "crafting": crafting_screen,
            "inventory": inventory_screen,
            "location": location_screen,
            "recruitment": recruitment_screen,
            "party": party_screen,
            "skills": skills_screen,
            "quest": quest_screen,
            "defeat": defeat_screen,
            "instance_event": instance_event_screen,
            "transition_event": transition_event_screen,
            "card_browser": card_browser_screen,
            "tabbed_menu": tabbed_menu_screen,
            "npc_browser": npc_browser_screen,
            "pause_menu": pause_menu_screen,
            "confirmation": confirmation_screen,
            "save_load": save_load_screen
        }
        game_screen.set_card_manager(self.card_manager)

    @property
    def current_screen(self):
        return self._current_screen

    @current_screen.setter
    def current_screen(self, value):
        if value != self._current_screen:
            old_screen = self._current_screen
            self._current_screen = value
            self._screen_changed_this_frame = True  # Block further events this frame
            # Flush pygame mouse events to prevent stray clicks from triggering
            # buttons on the new screen. This is critical for preventing the bug where
            # clicking Continue on instance screen accidentally triggers Main Menu.
            pygame.event.clear([pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION])
            # Debug: log screen transitions to help track down main_menu bug
            if value == "main_menu" and old_screen not in ("", None):
                import traceback
                print(f"\n[DEBUG] Screen changed to main_menu from {old_screen}")
                print("Stack trace:")
                traceback.print_stack()
                print()

    def reset_frame_flags(self):
        """Called at start of each frame to reset per-frame state."""
        self._screen_changed_this_frame = False

    @property
    def current_player(self):
        """Get the player whose turn it is (multiplayer) or the single player."""
        if self.multiplayer_mode and self.players:
            return self.players[self.current_player_index]
        return self.player

    @property
    def current_party(self):
        """Get current player's party (multiplayer uses player.party, single-player uses game.party)."""
        if self.multiplayer_mode:
            return self.current_player.party
        return self.party

    @property
    def current_quest_manager(self):
        """Get current player's quest manager."""
        if self.multiplayer_mode and self.quest_managers:
            return self.quest_managers[self.current_player_index]
        return self.quest_manager

    def handle_event(self, event):
        # Skip event processing if screen changed this frame (prevents stray events)
        if self._screen_changed_this_frame:
            return
        self.screens[self._current_screen].handle_event(event)

    def draw(self):
        self.screens[self._current_screen].draw()

# Instantiate screens and game
main_menu = MainMenu()
player_count_screen = PlayerCountScreen()
character_creation_screen = CharacterCreationScreen()
multiplayer_character_creation_screen = MultiplayerCharacterCreationScreen()
settings_screen = SettingsScreen()
game_screen = GameScreen()
game_settings_screen = GameSettingsScreen()
crafting_screen = CraftingScreen()
inventory_screen = InventoryScreen()
location_screen = LocationScreen()
recruitment_screen = RecruitmentScreen()
party_screen = PartyScreen()
skills_screen = SkillsScreen()
quest_screen = QuestScreen()
pause_menu_screen = PauseMenuScreen()
confirmation_screen = ConfirmationScreen()
save_load_screen = SaveLoadScreen()
defeat_screen = DefeatScreen()
instance_event_screen = InstanceEventScreen()
transition_event_screen = TransitionEventScreen()
card_browser_screen = CardBrowserScreen()
tabbed_menu_screen = TabbedMenuScreen()
npc_browser_screen = NpcBrowserScreen()
game = Game()

# Parse command-line arguments for campaign/level launching
import argparse
parser = argparse.ArgumentParser(description="JunkRPG - Hexagonal Grid RPG")
parser.add_argument("--campaign", type=str, help="Path to campaign file to load")
parser.add_argument("--level", type=str, help="Path to level file to load")
args, _ = parser.parse_known_args()

# If campaign or level specified via command line, go directly to character creation
if args.campaign:
    game.current_screen = "character_creation"
    character_creation_screen.initialize_screen(campaign_file=args.campaign)
elif args.level:
    game.current_screen = "character_creation"
    character_creation_screen.initialize_screen(level_file=args.level)

# Main game loop
clock = pygame.time.Clock()
running = True
while running:
    time_delta = clock.tick(60) / 1000.0
    game.reset_frame_flags()  # Reset per-frame state (like screen change detection)
    for e in event.get():
        if e.type == pygame.QUIT:
            running = False
        game.handle_event(e)
        manager.process_events(e)
        # If screen changed during event handling, stop processing remaining events
        # to prevent stray clicks from triggering buttons on the new screen
        if game._screen_changed_this_frame:
            break
    manager.update(time_delta)
    game.draw()
    display.flip()

pygame.quit()
sys.exit()

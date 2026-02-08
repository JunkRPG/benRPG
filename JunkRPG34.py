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
manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT))

# Colors (synced with level maker where applicable)
DARK_INDIGO = (25, 25, 112)  # Background
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
        manager.draw_ui(screen)

# GameScreen class
class GameScreen:
    def __init__(self):
        self.hex_grid = None
        self.ui_elements = []
        self.left_panel_buttons = []
        self.right_panel_buttons = []
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
        self.current_location_hex = None
        self.transition_target_cycle = 0
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
                    player_pos = (game.player.row, game.player.col)
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
            self.card_manager.track_card_usage(dead_unit.card_id, {"action": "defeated", "screen": "game"})
            quest_results = game.current_quest_manager.update("unit_death", {"unit": dead_unit}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)

        # Check for game over
        if game.multiplayer_mode:
            # Log player deaths only once (when HP first reaches 0)
            for i, p in enumerate(game.players):
                if p.hp <= 0 and not getattr(p, '_death_logged', False):
                    self.add_to_log(f"Player {i+1} ({p.class_name}) has fallen!")
                    p._death_logged = True
            # Only defeat if ALL players are dead
            all_dead = all(p.hp <= 0 for p in game.players)
            if all_dead:
                quest_results = game.current_quest_manager.update("player_death", {}, self.hex_grid, game.current_player)
                for quest, result, msg in quest_results:
                    self.add_to_log(msg)
                self.turn_queue.clear()
                self.pending_defeat = True
                return True
        elif isinstance(self.hex_grid.player, Player) and self.hex_grid.player.hp <= 0:
            self.add_to_log("Player defeated!")
            quest_results = game.current_quest_manager.update("player_death", {}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)
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
        self.ui_elements = [
            UITextBox("<font color='#FFFFFF' size=4>Game Log</font>",
                      pygame.Rect((WINDOW_WIDTH - 600) // 2, WINDOW_HEIGHT - 150, 600, 140),
                      manager, object_id="#log_textbox"),
            UITextBox("<font color='#FFFFFF' size=4>Stats</font>",
                      pygame.Rect(WINDOW_WIDTH - 300, WINDOW_HEIGHT - 175, 290, 175),
                      manager, object_id="#stats_panel", visible=False),
            UITextBox("<font color='#FFFFFF' size=4>Player's Turn</font>",
                      pygame.Rect((WINDOW_WIDTH - 200) // 2, 10, 200, 30),
                      manager, object_id="#turn_label")
        ]
        # Minimized log: toggle button on left + single line at bottom
        log_x = (WINDOW_WIDTH - 600) // 2
        self.log_toggle_button = UIButton(
            pygame.Rect(log_x, WINDOW_HEIGHT - 30, 30, 28),
            "^", manager
        )
        self.log_mini_label = UITextBox(
            "<font color='#CCCCCC' size=3></font>",
            pygame.Rect(log_x + 32, WINDOW_HEIGHT - 30, 568, 28),
            manager
        )
        # Start minimized
        self.log_minimized = True
        self.ui_elements[0].hide()
        
        left_panel_width = WINDOW_WIDTH // 4
        button_width = (left_panel_width - 20) // 2
        self.player_info_label = UITextBox(
            f"<font color='#FFFFFF'>{self.get_player_info().replace('\n', '<br>')}</font>",
            pygame.Rect(10, 0, button_width + 10, 188),
            manager
        )
        self.ui_elements.append(self.player_info_label)
        
        y_pos = 200
        self.left_panel_buttons = []
        self.attack_submenu_open = False
        self.attack_submenu_buttons = []
        self.special_attack_button = None
        self.attack_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Attack", manager)
        self.left_panel_buttons.append(self.attack_button)
        self.attack_button_y = y_pos
        y_pos += 40
        self.movement_toggle_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Movement", manager)
        self.left_panel_buttons.append(self.movement_toggle_button)
        y_pos += 40
        self.crafting_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Crafting", manager)
        self.left_panel_buttons.append(self.crafting_button)
        y_pos += 40
        self.inventory_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Inventory", manager)
        self.left_panel_buttons.append(self.inventory_button)
        y_pos += 40
        self.skills_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Skills", manager)
        self.left_panel_buttons.append(self.skills_button)
        y_pos += 40
        self.party_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Party", manager)
        self.left_panel_buttons.append(self.party_button)
        y_pos += 40
        quest_count = len(game.current_quest_manager.active_quests)
        self.quest_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), f"Quests ({quest_count}/5)", manager)
        self.left_panel_buttons.append(self.quest_button)
        y_pos += 40
        self.recruit_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Recruit NPC", manager)
        self.left_panel_buttons.append(self.recruit_button)
        y_pos += 40
        self.search_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Search", manager)
        self.left_panel_buttons.append(self.search_button)
        y_pos += 40
        self.build_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Build", manager)
        self.left_panel_buttons.append(self.build_button)

        # Add equipped skill buttons
        self.skill_buttons = []
        y_pos += 40
        for skill_card in game.current_player.equipped_skills:
            skill_data = skill_card.get_current_data()
            skill_name = skill_data.get("Name", "Unknown")
            cooldown = game.current_player.skill_cooldowns.get(skill_name, 0)
            text = f"{skill_name} (CD:{cooldown})" if cooldown else skill_name
            btn = UIButton(pygame.Rect(10, y_pos, button_width, 30), text, manager)
            self.skill_buttons.append((btn, skill_card))
            self.left_panel_buttons.append(btn)
            y_pos += 40

        # Add equipped tool buttons (multi-slot support)
        self.tool_buttons = []  # List of (button, slot_index) tuples
        self.tool_button = None  # Legacy single button (for backwards compatibility)

        # Check multi-slot system first
        if game.current_player.equipped_tools:
            for slot_idx, tool in enumerate(game.current_player.equipped_tools):
                if tool:
                    tool_data = tool.get_current_data()
                    tool_name = tool_data.get("Name", "Tool")
                    effect_text = game.current_player.get_tool_effect_text(slot_idx)
                    slot_label = f"[{slot_idx + 1}] " if game.current_player.tool_slots > 1 else ""
                    btn_text = f"Use {slot_label}{tool_name} {effect_text}".strip()
                    btn = UIButton(pygame.Rect(10, y_pos, button_width, 30), btn_text, manager)
                    self.tool_buttons.append((btn, slot_idx))
                    self.left_panel_buttons.append(btn)
                    y_pos += 35
        # Fallback to legacy single slot
        elif game.current_player.equipped_tool:
            tool_data = game.current_player.equipped_tool.get_current_data()
            tool_name = tool_data.get("Name", "Tool")
            effect_text = game.current_player.get_tool_effect_text()
            btn_text = f"Use {tool_name} {effect_text}".strip()
            self.tool_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), btn_text, manager)
            self.left_panel_buttons.append(self.tool_button)
            y_pos += 40

        # End Turn button below skills, with spacing
        y_pos += 20  # Add extra spacing to avoid overlap
        self.end_turn_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "End Turn", manager)
        self.left_panel_buttons.append(self.end_turn_button)

        self.ui_elements.extend(self.left_panel_buttons)
        
        # Right panel now only has remaining controls
        right_button_width = 150
        right_panel_x = WINDOW_WIDTH - right_button_width - 10
        y_pos = 60
        right_controls = ["Main Menu", "Restart Match", "Save Game", "Settings"]
        self.right_panel_buttons = [
            UIButton(pygame.Rect(right_panel_x, y_pos + 40 * i, right_button_width, 30), control, manager) 
            for i, control in enumerate(right_controls)
        ]
        self.ui_elements.extend(self.right_panel_buttons)
        
        self.ui_elements[0].set_text("<font color='#FFFFFF' size=4>" + "<br>".join(reversed(self.log)) + "</font>")
        self.update_turn_label()
        self.show_stats(None)

    def get_player_info(self):
        p = game.current_player
        pos = p.position
        melee = p.melee_weapon.get_current_data().get("Name", "None") if p.melee_weapon else "None"
        proj = p.projectile_weapon.get_current_data().get("Name", "None") if p.projectile_weapon else "None"
        # Add player label in multiplayer mode
        player_label = ""
        if game.multiplayer_mode:
            player_label = f"Player {p.player_number}\n"
        info = f"{player_label}Class: {p.class_name}\nHP: {p.hp}/{p.max_hp}\nMovement: {p.movement}\nRange: {p.projectile_range}\nPosition: ({pos[0]}, {pos[1]})\nMelee: {melee}\nProj: {proj}"
        # Show attacks remaining for Warrior (passive dual strike)
        if p.class_name == "Warrior":
            info += f"\nAttacks: {p.warrior_attacks_remaining}/2"
        return info

    def add_to_log(self, message):
        if message:
            self.log.append(message)
            if len(self.log) > 10:
                self.log.pop(0)
            self.ui_elements[0].set_text("<font color='#FFFFFF' size=4>" + "<br>".join(reversed(self.log)) + "</font>")
            # Update minimized label with latest entry
            if self.log_mini_label:
                self.log_mini_label.set_text(f"<font color='#CCCCCC' size=3>{message}</font>")

    def show_stats(self, unit):
        if unit:
            self.ui_elements[1].set_text("<font color='#FFFFFF' size=4>" + unit.get_stats().replace('\n', '<br>') + "</font>")
            self.ui_elements[1].show()
        else:
            self.ui_elements[1].hide()

    def update_turn_label(self):
        if self.turn_phase == "player" and game.player:
            player_name = game.player.name if hasattr(game.player, 'name') and game.player.name else "Player"
            label = f"{player_name}'s Turn"
        elif self.turn_phase == "player1" and game.multiplayer_mode and len(game.players) > 0:
            player_name = game.players[0].name if hasattr(game.players[0], 'name') and game.players[0].name else "Player 1"
            label = f"{player_name}'s Turn"
        elif self.turn_phase == "player2" and game.multiplayer_mode and len(game.players) > 1:
            player_name = game.players[1].name if hasattr(game.players[1], 'name') and game.players[1].name else "Player 2"
            label = f"{player_name}'s Turn"
        else:
            phases = {
                "allied": "Allied Turn",
                "neutral": "Neutral Turn",
                "hostile": "Enemies' Turn",
                "location_defense": "Location Defense",
                "transition": "World Events"
            }
            label = phases.get(self.turn_phase, "Unknown")
        self.ui_elements[2].set_text(f"<font color='#FFFFFF' size=4>{label}</font>")

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
            f"<font color='#FFFFFF'>{self.get_player_info().replace(chr(10), '<br>')}</font>"
        )

        y_pos = 200
        self.attack_submenu_open = False
        self.attack_submenu_buttons = []
        self.special_attack_button = None
        self.attack_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Attack", manager)
        self.left_panel_buttons.append(self.attack_button)
        self.attack_button_y = y_pos
        y_pos += 40

        self.movement_toggle_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Movement", manager)
        self.left_panel_buttons.append(self.movement_toggle_button)
        y_pos += 40
        self.crafting_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Crafting", manager)
        self.left_panel_buttons.append(self.crafting_button)
        y_pos += 40
        self.inventory_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Inventory", manager)
        self.left_panel_buttons.append(self.inventory_button)
        y_pos += 40
        self.skills_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Skills", manager)
        self.left_panel_buttons.append(self.skills_button)
        y_pos += 40
        self.party_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Party", manager)
        self.left_panel_buttons.append(self.party_button)
        y_pos += 40
        quest_count = len(game.current_quest_manager.active_quests)
        self.quest_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), f"Quests ({quest_count}/5)", manager)
        self.left_panel_buttons.append(self.quest_button)
        y_pos += 40
        self.recruit_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Recruit NPC", manager)
        self.left_panel_buttons.append(self.recruit_button)
        y_pos += 40
        self.search_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Search", manager)
        self.left_panel_buttons.append(self.search_button)
        y_pos += 40
        self.build_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Build", manager)
        self.left_panel_buttons.append(self.build_button)

        # Add equipped skill buttons
        self.skill_buttons = []
        y_pos += 40
        for skill_card in current_player.equipped_skills:
            skill_data = skill_card.get_current_data()
            skill_name = skill_data.get("Name", "Unknown")
            cooldown = current_player.skill_cooldowns.get(skill_name, 0)
            text = f"{skill_name} (CD:{cooldown})" if cooldown else skill_name
            btn = UIButton(pygame.Rect(10, y_pos, button_width, 30), text, manager)
            self.skill_buttons.append((btn, skill_card))
            self.left_panel_buttons.append(btn)
            y_pos += 40

        # Add equipped tool buttons (multi-slot support)
        self.tool_buttons = []  # List of (button, slot_index) tuples
        self.tool_button = None  # Legacy single button (for backwards compatibility)

        # Check multi-slot system first
        if current_player.equipped_tools:
            for slot_idx, tool in enumerate(current_player.equipped_tools):
                if tool:
                    tool_data = tool.get_current_data()
                    tool_name = tool_data.get("Name", "Tool")
                    effect_text = current_player.get_tool_effect_text(slot_idx)
                    slot_label = f"[{slot_idx + 1}] " if current_player.tool_slots > 1 else ""
                    btn_text = f"Use {slot_label}{tool_name} {effect_text}".strip()
                    btn = UIButton(pygame.Rect(10, y_pos, button_width, 30), btn_text, manager)
                    self.tool_buttons.append((btn, slot_idx))
                    self.left_panel_buttons.append(btn)
                    y_pos += 35
        # Fallback to legacy single slot
        elif current_player.equipped_tool:
            tool_data = current_player.equipped_tool.get_current_data()
            tool_name = tool_data.get("Name", "Tool")
            effect_text = current_player.get_tool_effect_text()
            btn_text = f"Use {tool_name} {effect_text}".strip()
            self.tool_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), btn_text, manager)
            self.left_panel_buttons.append(self.tool_button)
            y_pos += 40

        # End Turn button
        y_pos += 20
        self.end_turn_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "End Turn", manager)
        self.left_panel_buttons.append(self.end_turn_button)

        self.ui_elements.extend(self.left_panel_buttons)
        self.update_turn_label()

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
            self.card_manager.track_card_usage(defeated_unit.card_id, {"action": "defeated", "screen": "game"})
            # Notify quest system of unit death
            quest_results = game.current_quest_manager.update("unit_death", {"unit": defeated_unit}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)

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
        # If we're still in transition phase (instance was triggered by transition card),
        # complete the transition and move to player phase
        if self.turn_phase == "transition":
            print("[DEBUG] In transition phase, completing transition...")
            # Complete transition phase processing
            self.hex_grid.on_turn_end()
            quest_results = game.current_quest_manager.update("turn_end", {}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)

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
                self.card_manager.track_card_usage(dead_unit.card_id, {"action": "defeated", "screen": "game"})
                quest_results = game.current_quest_manager.update("unit_death", {"unit": dead_unit}, self.hex_grid, game.current_player)
                for quest, result, msg in quest_results:
                    self.add_to_log(msg)
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
            unit.update_animation(self.hex_grid)  # Pass grid for damage text

        # Check for pending NPC arrivals (quest NPCs moving to locations)
        if game.current_quest_manager.has_pending_arrivals():
            messages = game.current_quest_manager.update_pending_arrivals()
            for msg in messages:
                self.add_to_log(msg)
            animating = True  # Keep animating while there are pending arrivals

        return animating

    def _is_click_on_ui(self, pos):
        """Check if a screen position overlaps any visible UI element."""
        for el in self.ui_elements:
            if hasattr(el, 'rect') and el.rect.collidepoint(pos):
                if hasattr(el, 'visible') and not el.visible:
                    continue
                return True
        return False

    def handle_event(self, event):
        # Always allow right panel buttons (Main Menu, Restart, Settings) even during animation
        if event.type == pygame_gui.UI_BUTTON_PRESSED and event.ui_element in self.right_panel_buttons:
            text = event.ui_element.text
            if text == "Main Menu":
                game.current_screen = "main_menu"
                main_menu.initialize_buttons()
            elif text == "Restart Match":
                game.current_screen = "confirmation"
                confirmation_screen.initialize_screen(
                    "Are you sure you want to restart?",
                    options=["Yes", "No"],
                    callback=self._handle_restart_confirm
                )
            elif text == "Save Game":
                is_player_turn = self.turn_phase in ("player", "player1", "player2")
                if is_player_turn:
                    success, result = self.save_manager.save_game(game, self, save_type="manual", save_label="Manual Save")
                    if success:
                        self.add_to_log("Game saved.")
                    else:
                        self.add_to_log(f"Save failed: {result}")
                else:
                    self.add_to_log("Can only save during your turn.")
            elif text == "Settings":
                game.current_screen = "game_settings"
                game_settings_screen.initialize_screen()
            return
        if self.animating:
            return
        elif event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            # Skip hex grid processing if click is on a UI element
            if self._is_click_on_ui(pos):
                return
            hex_pos = self.hex_grid.get_hex_at_pixel(pos[0], pos[1])
            # Check if it's the current player's turn (single-player: "player", multiplayer: "player1" or "player2")
            is_player_turn = self.turn_phase in ("player", "player1", "player2")
            if event.button == 1 and hex_pos and is_player_turn:
                self.hex_grid.selected_hex = hex_pos
                unit = self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"]
                self.show_stats(unit)
                current_player = game.current_player
                # Auto-detect attack type if clicking on an enemy in range (skip in recruit/skill modes)
                if not self.selected_attack and not current_player.action_used and unit and isinstance(unit, Unit) and self.player_mode not in ("recruit", "skill"):
                    melee_range = current_player.get_melee_attack_range(self.hex_grid)
                    proj_range = current_player.get_projectile_attack_range(self.hex_grid, game.current_party)
                    if melee_range and hex_pos in melee_range:
                        self.selected_attack = current_player.attacks["melee"]["name"]
                        self.player_mode = "attack"
                    elif proj_range and hex_pos in proj_range:
                        self.selected_attack = current_player.attacks["projectile"]["name"]
                        self.player_mode = "attack"
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
                                    self.hex_grid.units.remove(hit_unit)
                                    self.add_to_log(f"{hit_unit.name} defeated")
                                    self.card_manager.track_card_usage(hit_unit.card_id, {"action": "defeated", "screen": "game"})
                                    quest_results = game.current_quest_manager.update("unit_death", {"unit": hit_unit}, self.hex_grid, current_player)
                                    for quest, qresult, msg in quest_results:
                                        self.add_to_log(msg)
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
                                self.card_manager.track_card_usage(unit.card_id, {"action": "defeated", "screen": "game"})
                                quest_results = game.current_quest_manager.update("unit_death", {"unit": unit}, self.hex_grid, current_player)
                                for quest, qresult, msg in quest_results:
                                    self.add_to_log(msg)
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
                            self.card_manager.track_card_usage(unit.card_id, {"action": "defeated", "screen": "game"})
                            # Notify quest system of unit death
                            quest_results = game.current_quest_manager.update("unit_death", {"unit": unit}, self.hex_grid, current_player)
                            for quest, result, msg in quest_results:
                                self.add_to_log(msg)
                            self.update_quest_button()
                            self.show_stats(None)
                    self.player_info_label.set_text(self.get_player_info())
                    self.selected_skill = None
                    self.player_mode = "movement"
                    self.initialize_screen()  # Refresh to update cooldown display
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
        elif event.type == pygame.MOUSEMOTION and self.dragging:
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
                    self.log_toggle_button.set_relative_position((log_x, WINDOW_HEIGHT - 30))
                else:
                    self.ui_elements[0].show()
                    self.log_mini_label.hide()
                    self.log_toggle_button.set_text("v")
                    self.log_toggle_button.set_relative_position((log_x, WINDOW_HEIGHT - 150))
                return

            is_player_turn = self.turn_phase in ("player", "player1", "player2")

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

            if event.ui_element in self.left_panel_buttons:
                text = event.ui_element.text
                # Close attack submenu when clicking any other left panel button
                if self.attack_submenu_open and text != "Attack":
                    self._close_attack_submenu()
                if text == "Attack" and is_player_turn:
                    if self.attack_submenu_open:
                        self._close_attack_submenu()
                    else:
                        self._open_attack_submenu()
                    return
                elif text == "Crafting" and is_player_turn:
                    game.current_screen = "crafting"
                    crafting_screen.initialize_screen()
                elif text == "Inventory" and is_player_turn:
                    game.current_screen = "inventory"
                    inventory_screen.initialize_screen()
                elif text == "Skills" and is_player_turn:
                    game.current_screen = "skills"
                    skills_screen.initialize_screen()
                elif text == "Party" and is_player_turn:
                    game.current_screen = "party"
                    party_screen.initialize_screen()
                elif text.startswith("Quests") and is_player_turn:
                    game.current_screen = "quest"
                    quest_screen.initialize_screen()
                elif text == "Recruit NPC" and is_player_turn:
                    # Toggle recruit mode
                    if self.player_mode == "recruit":
                        self.player_mode = "movement"
                        self.add_to_log("Exited recruit mode")
                    else:
                        # Check for adjacent neutral NPCs
                        adjacent_neutrals = self._get_adjacent_neutral_npcs()
                        if adjacent_neutrals:
                            self.player_mode = "recruit"
                            # Display adjacent NPC costs
                            for unit in adjacent_neutrals:
                                cost = self._calculate_recruitment_cost(unit)
                                self.add_to_log(f"[Recruit] {unit.name} - Cost: {cost}")
                            self.add_to_log("Click on an adjacent neutral NPC to recruit")
                        else:
                            self.add_to_log("No adjacent neutral NPCs to recruit")
                elif text == "Search" and is_player_turn:
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
                elif text == "Build" and is_player_turn:
                    # Open build screen or toggle build mode
                    current_player = game.current_player
                    if self.placement_mode:
                        # Cancel placement mode
                        self.placement_mode = False
                        self.placement_card = None
                        self.add_to_log("Cancelled building placement")
                    else:
                        # Check for location plans
                        plans = current_player.get_location_plans()
                        if not plans:
                            self.add_to_log("No Location Plans in inventory")
                        elif not current_player.has_building_tool():
                            self.add_to_log("Need a hammer/building tool equipped")
                        else:
                            # For simplicity, use first available plan and auto-select materials
                            plan = plans[0]
                            can, missing = current_player.can_build(plan)
                            if can:
                                # Build and enter placement mode
                                # Gather material cards (for now just consume from inventory proportionally)
                                material_cards = [c for c in current_player.inventory
                                                 if c.get_current_data().get("Metal Value") or
                                                    c.get_current_data().get("Wood Value") or
                                                    c.get_current_data().get("Raw Material Value")]
                                success, msg, built_card = current_player.build(plan, material_cards[:5])  # Consume up to 5 material cards
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
                elif text == "Movement" and is_player_turn:
                    self.player_mode = "movement"
                    self.selected_attack = None
                    self.add_to_log("Switched to movement mode")
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
        screen.fill(DARK_INDIGO)
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

        if is_player_turn and player_alive and not current_player.action_used and not self.animating and self.player_mode != "recruit":
            melee_range = current_player.get_melee_attack_range(self.hex_grid)
            if melee_range:
                attack_ranges.append({"range": melee_range, "color": (255, 69, 0, 220), "outline": (139, 0, 0, 220), "inset": 0.75})
            proj_range = current_player.get_projectile_attack_range(self.hex_grid, game.current_party)
            if proj_range:
                attack_ranges.append({"range": proj_range, "color": (191, 0, 255, 220), "outline": (75, 0, 130, 220), "inset": 0.55})

        # In recruit mode, show white rings around recruitable adjacent NPCs
        if is_player_turn and self.player_mode == "recruit":
            adjacent_neutrals = self._get_adjacent_neutral_npcs()
            recruit_hexes = {npc_unit.position for npc_unit in adjacent_neutrals if npc_unit.position}
            if recruit_hexes:
                attack_ranges.append({"range": recruit_hexes, "color": (255, 255, 255, 220), "outline": (180, 180, 180, 220), "inset": 0.75})

        # Get targetable units for visual highlighting from all attack ranges
        targetable_units = None
        all_attack_hexes = set()
        for ar in attack_ranges:
            all_attack_hexes |= ar["range"]
        if all_attack_hexes:
            targetable_units = self.hex_grid.get_targetable_units(all_attack_hexes, "player")

        self.hex_grid.draw(screen, movement_range, attack_ranges, self.colors, targetable_units)
        for rect in (self.ui_elements[0].rect if not self.log_minimized else None, self.ui_elements[1].rect if self.ui_elements[1].visible else None, self.ui_elements[2].rect):
            if rect:
                pygame.draw.rect(screen, GRAY, rect)
        manager.draw_ui(screen)
        # Draw colored outlines on attack submenu buttons
        if self.attack_submenu_open:
            for btn, _, _ in self.attack_submenu_buttons:
                if hasattr(btn, '_outline_color'):
                    pygame.draw.rect(screen, btn._outline_color, btn.rect, 2)
        self.animating = self.check_animations()
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
        manager.draw_ui(screen)


# ConfirmationScreen class
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        screen.fill(DARK_INDIGO)
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
        filter_options = ["All Cards", "Junk Cards", "Document Cards", "Enemy Cards", "NPC Cards",
                         "Location Cards", "Quest Cards", "Instance Cards", "Transition Cards"]
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

    def _load_all_cards(self):
        """Load all cards from card_index.json."""
        self.all_cards = []
        try:
            # Use the existing load_card_index function from card_utils
            card_index = load_card_index()

            for card_id, card_info in card_index.items():
                # card_index uses "type" not "card_type"
                card_type = card_info.get("type", "Unknown")
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
                    "Enemy Cards": "Enemy Card",
                    "NPC Cards": "NPC Card",
                    "Location Cards": "Location Card",
                    "Quest Cards": "Quest Card",
                    "Instance Cards": "Instance Card",
                    "Transition Cards": "Transition Card"
                }
                if card["type"] != type_map.get(filter_type, ""):
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
                game.current_screen = "inventory"
                inventory_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                game.current_screen = "inventory"
                inventory_screen.initialize_screen()
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
        screen.fill(DARK_INDIGO)
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
confirmation_screen = ConfirmationScreen()
save_load_screen = SaveLoadScreen()
defeat_screen = DefeatScreen()
instance_event_screen = InstanceEventScreen()
transition_event_screen = TransitionEventScreen()
card_browser_screen = CardBrowserScreen()
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
        if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
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

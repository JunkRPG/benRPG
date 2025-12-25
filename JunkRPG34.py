import pygame
import sys
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UIWindow, UISelectionList, UIDropDownMenu, UILabel, UIPanel
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

# Animation constants
MOVE_SPEED = 5
ATTACK_FLASH_DURATION = 500

# Directories
os.makedirs("cards", exist_ok=True)
os.makedirs("levels", exist_ok=True)
os.makedirs("campaigns", exist_ok=True)
INDEX_FILE = "cards/card_index.json"
if not os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, 'w') as f:
        json.dump({}, f)

# Character classes
CHARACTER_CLASSES = {
    "Ranger": {"hp": 50, "movement": 5, "projectile_range": 5, "attacks": {"Sling": 8, "Punch": 4}, "special_attack": "Multi-target Projectile"},
    "Warrior": {"hp": 100, "movement": 4, "projectile_range": 4, "attacks": {"Throw Rock": 6, "Kick": 6}, "special_attack": "Double Attack"},
    "Tank": {"hp": 150, "movement": 3, "projectile_range": 3, "attacks": {"Spit": 4, "Head-butt": 8}, "special_attack": "Spin Punch"}
}

# CardManager class
class CardManager:
    def __init__(self):
        self.card_types = ["Junk Card", "Document Card", "Enemy Card", "NPC Card", "Location Card", "Quest Card", "Instance Card", "Boss Card"]

    def get_cards_for_game(self, card_type=None, filters=None):
        try:
            with open(INDEX_FILE, 'r') as f:
                index = json.load(f)
        except Exception as e:
            print(f"Error loading card index: {e}")
            return []

        cards = []
        for card_id, info in index.items():
            if card_type and info['type'] != card_type:
                continue
            card_file = os.path.join("cards", f"{card_id}.json")
            try:
                with open(card_file, 'r') as cf:
                    card_data = json.load(cf)
            except Exception as e:
                print(f"Error loading card {card_id}: {e}")
                continue
            if filters and not self._apply_filters(card_data, filters):
                continue
            is_valid, _ = self.validate_card_for_game(card_data)
            if is_valid:
                card_data["id"] = card_id
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
            "Document Card": ["Name"]
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
        self.tools_list = None
        self.info_text = None
        self.close_button = None
        self.selected_card = None

    def initialize_screen(self):
        manager.clear_and_reset()
        window_rect = pygame.Rect((WINDOW_WIDTH - 1200) // 2, (WINDOW_HEIGHT - 800) // 2, 1200, 800)
        self.window = UIWindow(window_rect, manager, "Inventory")
        self.header_label = UILabel(pygame.Rect(0, 0, 1200, 50), "Inventory", manager, container=self.window)
        column_width = 300
        column_height = 700

        junk_cards = [card for card in game.player.inventory if card.current_state == 1 and card.card_data["card_type"] == "Junk Card"]
        self.junk_list = UISelectionList(pygame.Rect(0, 50, column_width, column_height), 
                                         [card.get_current_data().get("Name", "Unnamed") for card in junk_cards], 
                                         manager, container=self.window)
        documents_cards = [card for card in game.player.inventory if card.current_state == 1 and card.card_data["card_type"] == "Document Card"]
        self.documents_list = UISelectionList(pygame.Rect(column_width, 50, column_width, column_height), 
                                              [card.get_current_data().get("Name", "Unnamed") for card in documents_cards], 
                                              manager, container=self.window)
        weapons_cards = [card for card in game.player.inventory if card.current_state == 2 and card.get_current_data().get("Type") in ["Melee", "Projectile"]]
        self.weapons_list = UISelectionList(pygame.Rect(2 * column_width, 50, column_width, 300), 
                                            [card.get_current_data().get("Name", "Unnamed") for card in weapons_cards], 
                                            manager, container=self.window)
        self.equip_button = UIButton(pygame.Rect(2 * column_width, 350, column_width, 50), "Equip", manager, container=self.window)
        consumables_cards = [card for card in game.player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Consumable"]
        self.consumables_list = UISelectionList(pygame.Rect(2 * column_width, 400, column_width, 300), 
                                                [card.get_current_data().get("Name", "Unnamed") for card in consumables_cards], 
                                                manager, container=self.window)
        self.use_button = UIButton(pygame.Rect(2 * column_width, 700, column_width, 50), "Use", manager, container=self.window)
        tools_cards = [card for card in game.player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Tool"]
        self.tools_list = UISelectionList(pygame.Rect(3 * column_width, 50, column_width, column_height), 
                                          [card.get_current_data().get("Name", "Unnamed") for card in tools_cards], 
                                          manager, container=self.window)
        self.info_text = UITextBox("Select an item to view details", pygame.Rect(2 * column_width, 750, column_width * 2, 50), manager, container=self.window)
        self.close_button = UIButton(pygame.Rect(1050, 720, 100, 30), "Close", manager, container=self.window)
        self.selected_card = None

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                game.current_screen = "game"
                game_screen.initialize_screen()
            elif event.ui_element == self.equip_button and self.selected_card and self.weapons_list.get_single_selection():
                game.player.equip_weapon(self.selected_card)
                game_screen.player_info_label.set_text(game_screen.get_player_info())
            elif event.ui_element == self.use_button and self.selected_card and self.consumables_list.get_single_selection():
                current_data = self.selected_card.get_current_data()
                if current_data.get("Type") == "Consumable":
                    hp_effect = current_data.get("Use_HP", "+0HP")
                    try:
                        # Handle case where hp_effect is a list
                        if isinstance(hp_effect, list):
                            hp_effect = next((effect for effect in hp_effect if effect and "HP" in effect), "+0HP")
                        hp_change = int(hp_effect.replace("+", "").replace("HP", ""))
                        if hp_change > 0:
                            old_hp = game.player.hp
                            game.player.hp = min(game.player.max_hp, game.player.hp + hp_change)
                            game_screen.add_to_log(f"Used {current_data.get('Name', 'Unnamed')} to restore {hp_change} HP ({old_hp} -> {game.player.hp})")
                            game.player.inventory.remove(self.selected_card)
                            self.initialize_screen()
                            game_screen.player_info_label.set_text(game_screen.get_player_info())
                        else:
                            game_screen.add_to_log(f"{current_data.get('Name', 'Unnamed')} has no HP effect")
                    except (ValueError, AttributeError) as e:
                        game_screen.add_to_log(f"Invalid HP effect for {current_data.get('Name', 'Unnamed')}: {hp_effect} ({str(e)})")
        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            selected_name = event.text
            if event.ui_element == self.junk_list:
                self.selected_card = next((card for card in game.player.inventory if card.current_state == 1 and card.card_data["card_type"] == "Junk Card" and card.get_current_data().get("Name") == selected_name), None)
            elif event.ui_element == self.documents_list:
                self.selected_card = next((card for card in game.player.inventory if card.current_state == 1 and card.card_data["card_type"] == "Document Card" and card.get_current_data().get("Name") == selected_name), None)
            elif event.ui_element == self.weapons_list:
                self.selected_card = next((card for card in game.player.inventory if card.current_state == 2 and card.get_current_data().get("Type") in ["Melee", "Projectile"] and card.get_current_data().get("Name") == selected_name), None)
            elif event.ui_element == self.consumables_list:
                self.selected_card = next((card for card in game.player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Consumable" and card.get_current_data().get("Name") == selected_name), None)
            elif event.ui_element == self.tools_list:
                self.selected_card = next((card for card in game.player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Tool" and card.get_current_data().get("Name") == selected_name), None)
            if self.selected_card:
                info_text = "<br>".join(f"{k}: {v}" for k, v in self.selected_card.get_current_data().items() if v)
                self.info_text.set_text(info_text)
            else:
                self.info_text.set_text("Select an item to view details")

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
        junk_cards = [card for card in game.player.inventory if card.card_data["card_type"] == "Junk Card" and card.is_two_state() and card.current_state == 1]
        self.junk_list = UISelectionList(pygame.Rect(15, 75, 330, 300), 
                                         [card.get_current_data().get("Name", "Unnamed") for card in junk_cards], 
                                         manager, container=self.window)
        blueprint_cards = [card for card in game.player.inventory if card.card_data["card_type"] == "Document Card" and card.card_data.get("subclass", "") == "Blueprint" and card.is_two_state() and card.current_state == 1]
        self.blueprint_list = UISelectionList(pygame.Rect(15, 390, 330, 300), 
                                              [card.get_current_data().get("Name", "Unnamed") for card in blueprint_cards], 
                                              manager, container=self.window)
        self.materials_list = UISelectionList(pygame.Rect(360, 75, 330, 750), 
                                              [], manager, container=self.window, allow_multi_select=True)
        self.update_materials_list()
        self.to_craft_info = UITextBox("<font color='#FFFFFF' size=4>To Craft</font>", pygame.Rect(705, 75, 330, 250), manager, container=self.window)
        self.selected_material_info = UITextBox("<font color='#FFFFFF' size=4>Selected Material</font>", pygame.Rect(705, 335, 330, 250), manager, container=self.window)
        self.state2_info = UITextBox("<font color='#FFFFFF' size=4>State 2 Info</font>", pygame.Rect(705, 595, 330, 250), manager, container=self.window)
        self.requirements_info = UITextBox("<font color='#FFFFFF' size=4>Requirements</font>", pygame.Rect(1050, 75, 330, 200), manager, container=self.window)
        self.craft_button = UIButton(pygame.Rect(1060, 375, 100, 30), "Craft", manager, container=self.window)
        self.close_button = UIButton(pygame.Rect(1170, 375, 100, 30), "Close", manager, container=self.window)
        self.success_label = UILabel(pygame.Rect(1060, 415, 310, 30), "", manager, container=self.window)
        self.update_requirements_display()

    def update_materials_list(self):
        materials_cards = [card for card in game.player.inventory if card.card_data["card_type"] == "Junk Card" and card.current_state == 1]
        if self.selected_to_craft and self.selected_to_craft.card_data["card_type"] == "Junk Card":
            materials_cards = [card for card in materials_cards if card != self.selected_to_craft]
        self.materials_list.set_item_list([card.get_current_data().get("Name", "Unnamed") for card in materials_cards])

    def update_requirements_display(self):
        if not self.selected_to_craft:
            self.requirements_info.set_text("<font color='#FFFFFF' size=4>Requirements</font>")
            return
        state1_data = self.selected_to_craft.get_state_data(1)
        requirements_text = "<font color='#FFFFFF' size=4>Requirements:<br>"
        provided_totals = {val_key: 0 for val_key in self.REQUIREMENT_TO_VALUE.values()}
        for material in self.selected_materials:
            material_data = material.get_current_data()
            for val_key in provided_totals:
                provided_totals[val_key] += int(material_data.get(val_key, 0) or 0)  # Handle empty or None values
        all_met = True
        for req_key, val_key in self.REQUIREMENT_TO_VALUE.items():
            required = int(state1_data.get(req_key, 0) or 0)  # Handle empty or None values
            provided = provided_totals[val_key]
            material_type = req_key.split(": ")[1]
            requirements_text += f"{material_type}: {required} / {provided}<br>"
            if provided < required:
                all_met = False
        # Handle specific card requirements
        specific_cards = state1_data.get("Requirements: Specific Cards", "")
        if specific_cards:
            required_cards = [card.strip() for card in specific_cards.split(",") if card.strip()]
            provided_cards = [material.get_current_data().get("Name", "Unnamed") for material in self.selected_materials]
            missing_cards = [card for card in required_cards if card not in provided_cards]
            requirements_text += f"Specific Cards: {len(required_cards) - len(missing_cards)} / {len(required_cards)}<br>"
            if missing_cards:
                all_met = False
        requirements_text += "</font>"
        if all_met:
            requirements_text += "<font color='#FFFFFF' size=4>Ready to Craft</font>"
        self.requirements_info.set_text(requirements_text)

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                game.current_screen = "game"
                game_screen.initialize_screen()
            elif event.ui_element == self.craft_button:
                if self.selected_to_craft and self.check_requirements():
                    for material in self.selected_materials:
                        game.player.inventory.remove(material)
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
                    [card for card in game.player.inventory if card.card_data["card_type"] == "Junk Card" and card.is_two_state() and card.current_state == 1]
                    if event.ui_element == self.junk_list else
                    [card for card in game.player.inventory if card.card_data["card_type"] == "Document Card" and card.card_data.get("subclass", "") == "Blueprint" and card.is_two_state() and card.current_state == 1]
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
                materials_cards = [card for card in game.player.inventory if card.card_data["card_type"] == "Junk Card" and card.current_state == 1]
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

# Main Menu screen (updated to include Load Campaign)
class MainMenu:
    def __init__(self):
        self.ui_elements = []
        self.initialize_buttons()

    def initialize_buttons(self):
        manager.clear_and_reset()
        self.ui_elements = [
            UILabel(pygame.Rect(0, 50, WINDOW_WIDTH, 50), "Hex-Grid RPG", manager, object_id="#title_label", anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, 200, 200, 50), "New Campaign", manager),
            UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, 270, 200, 50), "Load Campaign", manager),
            UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, 340, 200, 50), "Load Level", manager),
            UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, 410, 200, 50), "Settings", manager),
            UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, 480, 200, 50), "Quit", manager)
        ]

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.ui_elements[1]:  # New Campaign
                game.current_screen = "character_creation"
                character_creation_screen.initialize_screen()
            elif event.ui_element == self.ui_elements[2]:  # Load Campaign
                root = tk.Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(initialdir="campaigns", filetypes=[("JSON files", "*.json")])
                root.destroy()
                if file_path:
                    game.current_screen = "character_creation"
                    character_creation_screen.initialize_screen(campaign_file=file_path)
                else:
                    print("No campaign file selected")
            elif event.ui_element == self.ui_elements[3]:  # Load Level
                root = tk.Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(initialdir="levels", filetypes=[("JSON files", "*.json")])
                root.destroy()
                if file_path:
                    game.current_screen = "character_creation"
                    character_creation_screen.initialize_screen(level_file=file_path)
                else:
                    print("No level file selected")
            elif event.ui_element == self.ui_elements[4]:  # Settings
                game.current_screen = "settings"
                settings_screen.initialize_screen()
            elif event.ui_element == self.ui_elements[5]:  # Quit
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

    def initialize_screen(self, level_file=None, campaign_file=None):
        self.level_file = level_file
        self.campaign_file = campaign_file
        manager.clear_and_reset()
        self.ui_elements = [
            UILabel(pygame.Rect(0, 50, WINDOW_WIDTH, 50), "Choose Your Class", manager, anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect(20, 20, 100, 50), "Back", manager)
        ]
        self.class_buttons = []
        for i, (class_name, stats) in enumerate(CHARACTER_CLASSES.items()):
            y_pos = 150 + i * 100
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
                        game.current_screen = "game"
                        game_screen.start_new_game(level_file=self.level_file, campaign_file=self.campaign_file)
                        break

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
        self.is_player_turn = True
        self.selected_attack = None
        self.turn_phase = "player"
        self.animating = False
        self.dragging = False
        self.drag_start_x = self.drag_start_y = self.start_view_offset_x = self.start_view_offset_y = 0
        self.player_mode = "movement"
        self.player_info_label = None
        self.game_started = False
        self.campaign = None
        self.current_level_idx = 0
        self.current_level_file = None
        self.initial_inventory = []
        self.initial_melee_weapon = None
        self.initial_projectile_weapon = None
        self.player_class = None  # Store player's class for reset
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
            'PURPLE': PURPLE  # Added for linked level hexes
        }

    def set_card_manager(self, card_manager):
        self.card_manager = card_manager

    def start_new_game(self, level_file=None, campaign_file=None):
        # Reset game state
        self.hex_grid = HexGrid(16, 24, 30, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.current_level_file = level_file
        self.log.clear()
        self.turn_phase = "player"
        self.is_player_turn = True
        self.hex_grid.game_over = False
        
        # Reset player to initial state
        if self.player_class:
            game.player = Player(self.player_class)
        if not self.player_class and game.player:
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
        
        # Ensure all units are reset and active
        for unit in self.hex_grid.units:
            unit.hp = unit.max_hp
            unit.current_state = 1  # Reset to initial state if applicable
        
        self.game_started = True
        self.initialize_screen()

    def load_campaign_level(self):
        if self.campaign and self.current_level_idx < len(self.campaign["levels"]):
            level_data = self.campaign["levels"][self.current_level_idx]
            level_file = os.path.join("levels", level_data["level_file"])
            try:
                self.hex_grid.load_level(level_file, self.card_manager, game.player)
                self.log.append(f"Loaded level {self.current_level_idx + 1}: {level_data['level_file']}")
            except Exception as e:
                print(f"Error loading level '{level_file}': {e}")
                self.hex_grid.place_unit(game.player, self.hex_grid.rows // 2, self.hex_grid.cols // 2)
                self.log.append(f"Failed to load level {self.current_level_idx + 1}. Starting default level.")

    def check_level_completion(self):
        if not self.campaign or self.current_level_idx >= len(self.campaign["levels"]):
            return False
        transition = self.campaign["levels"][self.current_level_idx].get("transition_to_next")
        if not transition:  # Final level, assume defeat all enemies
            return len([u for u in self.hex_grid.units if u.allegiance == "Hostile"]) == 0
        if "Defeat Boss" in transition:
            boss_name = transition.split("'")[1] if "'" in transition else None
            if boss_name:
                return not any(u.name == boss_name and u.allegiance == "Hostile" for u in self.hex_grid.units)
        elif "Collect" in transition:
            item_name = transition.split("'")[1] if "'" in transition else None
            if item_name:
                return any(card.get_current_data().get("Name") == item_name for card in game.player.inventory)
        return len([u for u in self.hex_grid.units if u.allegiance == "Hostile"]) == 0

    def advance_turn(self):
        if self.turn_phase == "player":
            game.player.movement_used = game.player.action_used = False
            self.turn_phase = "allied"
            self.execute_turn("Allied")
        elif self.turn_phase == "allied":
            self.turn_phase = "neutral"
            self.execute_turn("Neutral")
        elif self.turn_phase == "neutral":
            self.turn_phase = "hostile"
            self.execute_turn("Hostile")
        elif self.turn_phase == "hostile":
            if self.check_level_completion():
                self.current_level_idx += 1
                if self.campaign and self.current_level_idx < len(self.campaign["levels"]):
                    self.load_campaign_level()
                    self.turn_phase = "player"
                    self.is_player_turn = True
                else:
                    self.add_to_log("Campaign Completed!")
                    game.current_screen = "main_menu"
                    main_menu.initialize_buttons()
            else:
                self.turn_phase = "player"
                self.is_player_turn = True
        self.update_turn_label()
        self.animating = self.check_animations()

    def execute_turn(self, allegiance):
        units_to_process = [unit for unit in self.hex_grid.units if unit.allegiance == allegiance]
        for unit in units_to_process[:]:
            for entry in unit.take_turn(self.hex_grid):
                self.add_to_log(entry)
            if isinstance(self.hex_grid.player, Player) and self.hex_grid.player.hp <= 0:
                self.add_to_log("Player defeated!")
                return  # Exit early; game over handled in draw()
            if unit.states == 2 and unit.hp < unit.max_hp * 0.3:
                switch_msg = unit.switch_state()
                if switch_msg:
                    self.add_to_log(switch_msg)
            if unit.hp <= 0:
                self.hex_grid.grid[unit.position[0]][unit.position[1]]["unit"] = None
                self.hex_grid.units.remove(unit)
                self.add_to_log(f"{unit.name} defeated")
                self.card_manager.track_card_usage(unit.card_id, {"action": "defeated", "screen": "game"})
        self.player_info_label.set_text(self.get_player_info())
        self.animating = self.check_animations()

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
        
        left_panel_width = WINDOW_WIDTH // 4
        button_width = (left_panel_width - 20) // 2
        self.player_info_label = UITextBox(
            f"<font color='#FFFFFF'>{self.get_player_info().replace('\n', '<br>')}</font>",
            pygame.Rect(10, 0, button_width + 10, 188),
            manager
        )
        self.ui_elements.append(self.player_info_label)
        
        y_pos = 200
        attacks_list = list(game.player.attacks.values())
        self.left_panel_buttons = [
            UIButton(pygame.Rect(10, y_pos + 40 * i, button_width, 30), 
                     f"{attack['name']} ({attack['damage']} dmg)", manager) 
            for i, attack in enumerate(attacks_list)
        ]
        y_pos += 40 * len(self.left_panel_buttons) + 40
        self.movement_toggle_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Movement", manager)
        self.left_panel_buttons.append(self.movement_toggle_button)
        y_pos += 40
        self.crafting_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Crafting", manager)
        self.left_panel_buttons.append(self.crafting_button)
        y_pos += 40
        self.inventory_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Inventory", manager)
        self.left_panel_buttons.append(self.inventory_button)
        
        # Move "Draw Card" and "End Turn" below Inventory, with spacing
        y_pos += 60  # Add extra spacing to avoid overlap
        self.draw_card_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Draw Card", manager)
        self.left_panel_buttons.append(self.draw_card_button)
        y_pos += 40
        self.end_turn_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "End Turn", manager)
        self.left_panel_buttons.append(self.end_turn_button)
        
        self.ui_elements.extend(self.left_panel_buttons)
        
        # Right panel now only has remaining controls
        right_button_width = 150
        right_panel_x = WINDOW_WIDTH - right_button_width - 10
        y_pos = 60
        right_controls = ["Main Menu", "Restart Match", "Settings"]
        self.right_panel_buttons = [
            UIButton(pygame.Rect(right_panel_x, y_pos + 40 * i, right_button_width, 30), control, manager) 
            for i, control in enumerate(right_controls)
        ]
        self.ui_elements.extend(self.right_panel_buttons)
        
        self.ui_elements[0].set_text("<font color='#FFFFFF' size=4>" + "<br>".join(self.log) + "</font>")
        self.update_turn_label()
        self.show_stats(None)

    def get_player_info(self):
        p = game.player
        pos = p.position
        melee = p.melee_weapon.get_current_data().get("Name", "None") if p.melee_weapon else "None"
        proj = p.projectile_weapon.get_current_data().get("Name", "None") if p.projectile_weapon else "None"
        return f"Class: {p.class_name}\nHP: {p.hp}/{p.max_hp}\nMovement: {p.movement}\nRange: {p.projectile_range}\nPosition: ({pos[0]}, {pos[1]})\nMelee: {melee}\nProj: {proj}"

    def add_to_log(self, message):
        if message:
            self.log.append(message)
            if len(self.log) > 10:
                self.log.pop(0)
            self.ui_elements[0].set_text("<font color='#FFFFFF' size=4>" + "<br>".join(self.log) + "</font>")

    def show_stats(self, unit):
        if unit:
            self.ui_elements[1].set_text("<font color='#FFFFFF' size=4>" + unit.get_stats().replace('\n', '<br>') + "</font>")
            self.ui_elements[1].show()
        else:
            self.ui_elements[1].hide()

    def update_turn_label(self):
        phases = {"player": "Player's Turn", "allied": "Allied Turn", "neutral": "Neutral Turn", "hostile": "Enemies' Turn"}
        self.ui_elements[2].set_text(f"<font color='#FFFFFF' size=4>{phases[self.turn_phase]}</font>")

    def check_animations(self):
        animating = False
        if self.hex_grid.player and self.hex_grid.player.animating:
            self.hex_grid.player.update_animation(self.hex_grid)  # Pass grid
            animating = True
        for unit in self.hex_grid.units:
            if unit.animating:
                unit.update_animation(self.hex_grid)  # Pass grid
                animating = True
            unit.update_animation(self.hex_grid)  # Pass grid for damage text
        return animating

    def handle_event(self, event):
        if self.animating:
            return
        elif event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            hex_pos = self.hex_grid.get_hex_at_pixel(pos[0], pos[1])
            if event.button == 1 and hex_pos and self.turn_phase == "player":
                self.hex_grid.selected_hex = hex_pos
                unit = self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"]
                self.show_stats(unit)
                if self.player_mode == "attack" and self.selected_attack and unit and isinstance(unit, Unit):
                    message, defeated = game.player.attack(unit, self.selected_attack, self.hex_grid)
                    self.add_to_log(message)
                    if message:
                        unit.attack_flash = True
                        unit.flash_start = pygame.time.get_ticks()
                        if defeated:
                            self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] = None
                            self.hex_grid.units.remove(unit)
                            self.add_to_log(f"{unit.name} defeated")
                            self.card_manager.track_card_usage(unit.card_id, {"action": "defeated", "screen": "game"})
                            self.show_stats(None)
                        self.player_info_label.set_text(self.get_player_info())
                        self.selected_attack = None
                elif self.player_mode == "movement" and not game.player.movement_used and not unit:
                    path = self.hex_grid.find_path(game.player.position, hex_pos)
                    if path and len(path) - 1 <= game.player.movement:
                        success, msg = self.hex_grid.move_unit(game.player, *hex_pos)
                        if success:
                            self.add_to_log(msg)
                            game.player.movement_used = True
                            # Draw card if applicable
                            card, card_msg = self.hex_grid.draw_card(hex_pos[0], hex_pos[1], self.card_manager)
                            if card:
                                game.player.inventory.append(card)
                                self.add_to_log(card_msg)
                            # Check for linked level only if explicitly set
                            for hex_data in self.hex_grid.card_drawing_hexes:
                                if hex_data["row"] == hex_pos[0] and hex_data["column"] == hex_pos[1]:
                                    if hex_data.get("linked_level") and isinstance(hex_data["linked_level"], str):
                                        linked_level_file = os.path.join("levels", hex_data["linked_level"])
                                        if os.path.exists(linked_level_file):
                                            self.add_to_log(f"Entering {hex_data['linked_level']}")
                                            self.hex_grid.load_level(linked_level_file, self.card_manager, game.player)
                                            # Teleport player to new start position
                                            player_start = self.hex_grid.player.position
                                            game.player.teleport(self.hex_grid, *player_start)
                                            # Teleport allied NPCs
                                            allied_units = [u for u in self.hex_grid.units if u.allegiance == "Allied"]
                                            for i, ally in enumerate(allied_units):
                                                neighbors = self.hex_grid.get_neighbors(*player_start)
                                                if i < len(neighbors):
                                                    ally.teleport(self.hex_grid, *neighbors[i])
                                            self.initialize_screen()
                                            game.player.movement_used = False
                                            game.player.action_used = False
                                            break
                                        else:
                                            self.add_to_log(f"Linked level file not found: {hex_data['linked_level']}")
                                    break  # Exit loop after handling this hex
                            self.player_info_label.set_text(self.get_player_info())
                    else:
                        self.add_to_log("No valid path within movement range")
            elif event.button == 3 and hex_pos:
                self.dragging = True
                self.drag_start_x, self.drag_start_y = pos
                self.start_view_offset_x, self.start_view_offset_y = self.hex_grid.view_offset_x, self.hex_grid.view_offset_y
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            dx = event.pos[0] - self.drag_start_x
            dy = event.pos[1] - self.drag_start_y
            self.hex_grid.view_offset_x = self.start_view_offset_x + dx
            self.hex_grid.view_offset_y = self.start_view_offset_y + dy
            grid_width = self.hex_grid.cols * self.hex_grid.hex_size * 1.5
            grid_height = self.hex_grid.rows * self.hex_grid.hex_size * 1.732
            min_offset_x = WINDOW_WIDTH - grid_width if grid_width > WINDOW_WIDTH else 0
            max_offset_x = 0 if grid_width > WINDOW_WIDTH else WINDOW_WIDTH - grid_width
            min_offset_y = WINDOW_HEIGHT - grid_height if grid_height > WINDOW_HEIGHT else 0
            max_offset_y = 0 if grid_height > WINDOW_HEIGHT else WINDOW_HEIGHT - grid_height
            self.hex_grid.view_offset_x = max(min(self.hex_grid.view_offset_x, max_offset_x), min_offset_x)
            self.hex_grid.view_offset_y = max(min(self.hex_grid.view_offset_y, max_offset_y), min_offset_y)
        elif event.type == pygame.MOUSEWHEEL:
            if event.y > 0:
                zoom_factor = 1.1
            elif event.y < 0:
                zoom_factor = 0.9
            else:
                zoom_factor = 1.0
            if zoom_factor != 1.0:
                mx, my = pygame.mouse.get_pos()
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
                min_offset_x = WINDOW_WIDTH - grid_width if grid_width > WINDOW_WIDTH else 0
                max_offset_x = 0 if grid_width > WINDOW_WIDTH else WINDOW_WIDTH - grid_width
                min_offset_y = WINDOW_HEIGHT - grid_height if grid_height > WINDOW_HEIGHT else 0
                max_offset_y = 0 if grid_height > WINDOW_HEIGHT else WINDOW_HEIGHT - grid_height
                self.hex_grid.view_offset_x = max(min(self.hex_grid.view_offset_x, max_offset_x), min_offset_x)
                self.hex_grid.view_offset_y = max(min(self.hex_grid.view_offset_y, max_offset_y), min_offset_y)
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element in self.left_panel_buttons:
                text = event.ui_element.text
                if text == "Crafting" and self.turn_phase == "player":
                    game.current_screen = "crafting"
                    crafting_screen.initialize_screen()
                elif text == "Inventory" and self.turn_phase == "player":
                    game.current_screen = "inventory"
                    inventory_screen.initialize_screen()
                elif text == "Movement" and self.turn_phase == "player":
                    self.player_mode = "movement"
                    self.selected_attack = None
                    self.add_to_log("Switched to movement mode")
                elif text == "Draw Card" and self.turn_phase == "player" and self.hex_grid.selected_hex:
                    card, msg = self.hex_grid.draw_card(*self.hex_grid.selected_hex, self.card_manager)
                    if card:
                        game.player.inventory.append(card)
                    self.add_to_log(msg)
                elif text == "End Turn" and self.turn_phase == "player":
                    self.advance_turn()
                elif self.turn_phase == "player":
                    attack_text = text.split(' (')[0]
                    if attack_text in [game.player.attacks["projectile"]["name"], game.player.attacks["melee"]["name"]]:
                        self.selected_attack = attack_text
                        self.player_mode = "attack"
                        self.hex_grid.selected_hex = None
                        self.add_to_log(f"Selected attack: {attack_text}")
            elif event.ui_element in self.right_panel_buttons:
                text = event.ui_element.text
                if text == "Main Menu":
                    game.current_screen = "main_menu"
                    main_menu.initialize_buttons()
                elif text == "Restart Match":
                    game.current_screen = "character_creation"
                    character_creation_screen.initialize_screen()
                elif text == "Settings":
                    game.current_screen = "game_settings"
                    game_settings_screen.initialize_screen()

    def draw(self):
        screen.fill(DARK_INDIGO)
        movement_range = self.hex_grid.get_valid_moves(game.player.position, game.player.movement) if self.turn_phase == "player" and self.player_mode == "movement" and not game.player.movement_used else None
        attack_range = (
            self.hex_grid.get_attack_range(game.player.position, game.player.projectile_range, is_projectile=True) 
            if self.selected_attack == game.player.attacks["projectile"]["name"] and self.turn_phase == "player" and not game.player.action_used 
            else self.hex_grid.get_attack_range(game.player.position, 1, is_projectile=False) 
            if self.selected_attack == game.player.attacks["melee"]["name"] and self.turn_phase == "player" and not game.player.action_used 
            else None
        )
        self.hex_grid.draw(screen, movement_range, attack_range, self.colors)
        for rect in (self.ui_elements[0].rect, self.ui_elements[1].rect if self.ui_elements[1].visible else None, self.ui_elements[2].rect):
            if rect:
                pygame.draw.rect(screen, GRAY, rect)
        manager.draw_ui(screen)
        self.animating = self.check_animations()
        if not self.animating and self.turn_phase != "player":
            self.advance_turn()
        if self.hex_grid.game_over:
            game.current_screen = "defeat"
            defeat_screen.initialize_screen()

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

# DefeatScreen class
class DefeatScreen:
    def __init__(self):
        self.ui_elements = []
        self.humorous_messages = [
            "You got smoked like a cheap cigar!",
            "Looks like you’re the weakest link—goodbye!",
            "Defeated? Even the tutorial boss is laughing!",
            "You’ve been sent to the respawn realm!"
        ]

    def initialize_screen(self):
        manager.clear_and_reset()
        message = random.choice(self.humorous_messages)
        self.ui_elements = [
            UILabel(pygame.Rect(0, WINDOW_HEIGHT // 4, WINDOW_WIDTH, 50), message, manager, anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, WINDOW_HEIGHT // 2, 200, 50), "Restart Level", manager),
            UIButton(pygame.Rect((WINDOW_WIDTH - 200) // 2, WINDOW_HEIGHT // 2 + 70, 200, 50), "Main Menu", manager)
        ]

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.ui_elements[1]:  # Restart Level
                game.current_screen = "game"
                game_screen.start_new_game(level_file=game_screen.current_level_file, 
                                           campaign_file=game_screen.campaign_file if game_screen.campaign else None)
                game_screen.initialize_screen()
            elif event.ui_element == self.ui_elements[2]:  # Main Menu
                game.current_screen = "main_menu"
                main_menu.initialize_buttons()

    def draw(self):
        screen.fill(DARK_INDIGO)
        manager.draw_ui(screen)

# Main Game class
class Game:
    def __init__(self):
        self.current_screen = "main_menu"
        self.player = None
        self.card_manager = CardManager()
        self.screens = {
            "main_menu": main_menu,
            "character_creation": character_creation_screen,
            "settings": settings_screen,
            "game": game_screen,
            "game_settings": game_settings_screen,
            "crafting": crafting_screen,
            "inventory": inventory_screen,
            "defeat": defeat_screen
        }
        game_screen.set_card_manager(self.card_manager)

    def handle_event(self, event):
        self.screens[self.current_screen].handle_event(event)

    def draw(self):
        self.screens[self.current_screen].draw()

# Instantiate screens and game
main_menu = MainMenu()
character_creation_screen = CharacterCreationScreen()
settings_screen = SettingsScreen()
game_screen = GameScreen()
game_settings_screen = GameSettingsScreen()
crafting_screen = CraftingScreen()
inventory_screen = InventoryScreen()
defeat_screen = DefeatScreen()
game = Game()

# Main game loop
clock = pygame.time.Clock()
running = True
while running:
    time_delta = clock.tick(60) / 1000.0
    for e in event.get():
        if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
            running = False
        game.handle_event(e)
        manager.process_events(e)
    manager.update(time_delta)
    game.draw()
    display.flip()

pygame.quit()
sys.exit()

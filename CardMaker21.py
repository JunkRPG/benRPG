import pygame
import sys
import tkinter as tk
from tkinter import filedialog
import pygame_gui
from pygame_gui.elements import UIButton, UITextEntryLine, UILabel, UIDropDownMenu
from pygame import display, event
import os
import json
import uuid
import re

# Constants
CARD_WIDTH = 400
CARD_HEIGHT = 600
LIGHT_TEAL = (173, 216, 230)
DARK_BRONZE = (139, 69, 19)
DARK_INDIGO = (75, 0, 130)
DARK_BRASS = (184, 115, 51)
LIGHT_CREAM = (245, 245, 220)
LIGHT_GOLDEN = (255, 215, 0)
SUPPORTED_IMAGE_FORMATS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')

# Initialize Pygame
pygame.init()

# Get display info for fullscreen
display_info = pygame.display.Info()
WINDOW_WIDTH = display_info.current_w
WINDOW_HEIGHT = display_info.current_h
CARD_SCALE = min((WINDOW_WIDTH - 40) / CARD_WIDTH, (WINDOW_HEIGHT - 200) / CARD_HEIGHT)

# Custom theme (unchanged)
THEME_JSON = {
    "@default": {
        "colours": {
            "normal_bg": f"#{LIGHT_TEAL[0]:02x}{LIGHT_TEAL[1]:02x}{LIGHT_TEAL[2]:02x}",
            "hovered_bg": f"#{LIGHT_TEAL[0]:02x}{LIGHT_TEAL[1]:02x}{LIGHT_TEAL[2]:02x}",
            "active_bg": f"#{LIGHT_TEAL[0]:02x}{LIGHT_TEAL[1]:02x}{LIGHT_TEAL[2]:02x}",
            "normal_text": f"#{DARK_BRONZE[0]:02x}{DARK_BRONZE[1]:02x}{DARK_BRONZE[2]:02x}",
            "hovered_text": f"#{DARK_BRONZE[0]:02x}{DARK_BRONZE[1]:02x}{DARK_BRONZE[2]:02x}",
            "selected_text": f"#{DARK_BRONZE[0]:02x}{DARK_BRONZE[1]:02x}{DARK_BRONZE[2]:02x}",
            "dark_bg": f"#{DARK_INDIGO[0]:02x}{DARK_INDIGO[1]:02x}{DARK_INDIGO[2]:02x}"
        }
    },
    "button": {
        "colours": {
            "normal_bg": f"#{DARK_BRASS[0]:02x}{DARK_BRASS[1]:02x}{DARK_BRASS[2]:02x}",
            "hovered_bg": f"#{DARK_BRASS[0]:02x}{DARK_BRASS[1]:02x}{DARK_BRASS[2]:02x}",
            "active_bg": f"#{DARK_BRASS[0]:02x}{DARK_BRASS[1]:02x}{DARK_BRASS[2]:02x}",
            "normal_text": f"#{LIGHT_CREAM[0]:02x}{LIGHT_CREAM[1]:02x}{LIGHT_CREAM[2]:02x}",
            "hovered_text": f"#{LIGHT_CREAM[0]:02x}{LIGHT_CREAM[1]:02x}{LIGHT_CREAM[2]:02x}",
            "selected_text": f"#{LIGHT_CREAM[0]:02x}{LIGHT_CREAM[1]:02x}{LIGHT_CREAM[2]:02x}"
        }
    },
    "label": {
        "colours": {"normal_text": f"#{LIGHT_GOLDEN[0]:02x}{LIGHT_GOLDEN[1]:02x}{LIGHT_GOLDEN[2]:02x}"}
    },
    "text_entry_line": {
        "colours": {
            "normal_bg": f"#{LIGHT_TEAL[0]:02x}{LIGHT_TEAL[1]:02x}{LIGHT_TEAL[2]:02x}",
            "hovered_bg": f"#{LIGHT_TEAL[0]:02x}{LIGHT_TEAL[1]:02x}{LIGHT_TEAL[2]:02x}",
            "active_bg": f"#{LIGHT_TEAL[0]:02x}{LIGHT_TEAL[1]:02x}{LIGHT_TEAL[2]:02x}",
            "normal_text": f"#{DARK_BRONZE[0]:02x}{DARK_BRONZE[1]:02x}{DARK_BRONZE[2]:02x}",
            "hovered_text": f"#{DARK_BRONZE[0]:02x}{DARK_BRONZE[1]:02x}{DARK_BRONZE[2]:02x}",
            "selected_text": f"#{DARK_BRONZE[0]:02x}{DARK_BRONZE[1]:02x}{DARK_BRONZE[2]:02x}"
        }
    },
    "drop_down_menu": {
        "colours": {
            "normal_bg": f"#{LIGHT_TEAL[0]:02x}{LIGHT_TEAL[1]:02x}{LIGHT_TEAL[2]:02x}",
            "hovered_bg": f"#{LIGHT_TEAL[0]:02x}{LIGHT_TEAL[1]:02x}{LIGHT_TEAL[2]:02x}",
            "active_bg": f"#{LIGHT_TEAL[0]:02x}{LIGHT_TEAL[1]:02x}{LIGHT_TEAL[2]:02x}",
            "normal_text": f"#{DARK_BRONZE[0]:02x}{DARK_BRONZE[1]:02x}{DARK_BRONZE[2]:02x}",
            "hovered_text": f"#{DARK_BRONZE[0]:02x}{DARK_BRONZE[1]:02x}{DARK_BRONZE[2]:02x}",
            "selected_text": f"#{DARK_BRONZE[0]:02x}{DARK_BRONZE[1]:02x}{DARK_BRONZE[2]:02x}"
        }
    },
    "#title_label": {"font": {"name": "freesansbold", "size": "30", "bold": "1", "italic": "0"}}
}

with open("theme.json", "w") as f:
    json.dump(THEME_JSON, f)
manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT), "theme.json")

screen = display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
display.set_caption("Card Management Application")

INDEX_FILE = "cards/card_index.json"
os.makedirs("cards", exist_ok=True)
if not os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, 'w') as f:
        json.dump({}, f)

# Load range options from Range Maker
RANGE_INDEX_FILE = "ranges/range_index.json"
RANGE_OPTIONS = ["None"]  # Default option
if os.path.exists(RANGE_INDEX_FILE):
    try:
        with open(RANGE_INDEX_FILE, 'r') as f:
            range_index = json.load(f)
        RANGE_OPTIONS.extend([range_id for range_id in range_index.keys()])
    except Exception as e:
        print(f"Error loading range index: {e}")

# Define HP options globally for consistency
HP_OPTIONS = ["+0HP", "+5HP", "+10HP", "+15HP", "+20HP", "+25HP", "+30HP", "+35HP", "+40HP", "+50HP", "+75HP", "+100HP"]
PLACEHOLDER_OPTIONS = ["TBD"]

# CardPreview class (unchanged)
class CardPreview:
    def __init__(self, card_data, card_id, back_action, edit_action=None):
        self.card_data = card_data
        self.card_id = card_id
        self.back_action = back_action
        self.edit_action = edit_action
        
        manager.clear_and_reset()
        
        card_scaled_width = int(CARD_WIDTH * CARD_SCALE)
        card_scaled_height = int(CARD_HEIGHT * CARD_SCALE)
        self.card_rect = pygame.Rect((WINDOW_WIDTH - card_scaled_width) // 2,
                                   (WINDOW_HEIGHT - card_scaled_height) // 2,
                                   card_scaled_width, card_scaled_height)
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Card Preview",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        
        button_y = self.card_rect.bottom + 20
        button_width = 150
        button_spacing = 20
        
        if self.edit_action:
            total_button_width = button_width * 2 + button_spacing
            button_x_start = (WINDOW_WIDTH - total_button_width) // 2
            self.back_button = UIButton(
                relative_rect=pygame.Rect(button_x_start, button_y, button_width, 40),
                text="Back to Menu",
                manager=manager,
                object_id="#back_to_menu"
            )
            self.edit_button = UIButton(
                relative_rect=pygame.Rect(button_x_start + button_width + button_spacing, 
                                        button_y, button_width, 40),
                text="Continue Editing",
                manager=manager,
                object_id="#continue_editing"
            )
        else:
            total_button_width = button_width
            button_x_start = (WINDOW_WIDTH - total_button_width) // 2
            self.back_button = UIButton(
                relative_rect=pygame.Rect(button_x_start, button_y, button_width, 40),
                text="Back",
                manager=manager,
                object_id="#back_to_menu"
            )
            self.edit_button = None

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                self.back_action()
            elif self.edit_button and event.ui_element == self.edit_button:
                self.edit_action()

    def draw(self):
        screen.fill(DARK_INDIGO)
        
        card_surface = pygame.Surface((CARD_WIDTH, CARD_HEIGHT))
        card_surface.fill(LIGHT_TEAL)  # Card background
        
        bg_path = self.card_data["data"].get("Background Image", 
                                           self.card_data["data"].get("Background Image File Path", ""))
        if bg_path and os.path.exists(bg_path):
            try:
                bg_image = pygame.image.load(bg_path).convert_alpha()
                bg_image = pygame.transform.scale(bg_image, (CARD_WIDTH, CARD_HEIGHT))
                card_surface.blit(bg_image, (0, 0))
            except pygame.error:
                pass

        image_key = {
            "Junk Card": "Junk Image" if "Junk Image" in self.card_data["data"] else "Junk Image File Path",
            "Enemy Card": "Enemy Image File Path",
            "Boss Card": "Boss Image File Path",
            "NPC Card": "NPC Image File Path",
            "Location Card": "Location Image File Path",
            "Document Card": "Background Image",
            "Transition Card": "Background Image"
        }.get(self.card_data["card_type"], "Background Image")
        image_path = self.card_data["data"].get(image_key, "")
        if image_path and os.path.exists(image_path):
            try:
                image = pygame.image.load(image_path).convert_alpha()
                image_scaled = pygame.transform.scale(image, (CARD_WIDTH//2, CARD_HEIGHT//2))
                image_rect = image_scaled.get_rect(center=(CARD_WIDTH//2, CARD_HEIGHT//2))
                card_surface.blit(image_scaled, image_rect)
            except pygame.error:
                pass

        font = pygame.font.Font(None, int(72 * CARD_SCALE))
        y_pos = int(20 * CARD_SCALE)
        name = self.card_data["data"].get("Name", 
                                        self.card_data["data"].get("Default Name", "Unnamed"))
        name_surface = font.render(name, True, DARK_BRONZE)
        name_rect = name_surface.get_rect(center=(CARD_WIDTH//2, y_pos))
        card_surface.blit(name_surface, name_rect)
        y_pos += int(120 * CARD_SCALE)

        for key, value in self.card_data["data"].items():
            if key not in ["Name", "Default Name", "Background Image", "Background Image File Path", 
                           "Junk Image", "Junk Image File Path", "Enemy Image File Path", 
                           "Boss Image File Path", "NPC Image File Path", 
                           "Location Image File Path",
                           "2nd_state_Weapon Image", "2nd_state_Tool Image", "2nd_state_Item Image",
                           "Book Image", "Pamphlet Image"]:
                if key in ["Upgraded Type (Weapon, Tool, Consumable, Armor)", "Upgraded Name"]:
                    value = value or "N/A"
                text = f"{key}: {value}"
                text_surface = font.render(text, True, DARK_BRONZE)
                text_rect = text_surface.get_rect(center=(CARD_WIDTH//2, y_pos))
                if text_rect.width > CARD_WIDTH - 20:
                    while text_rect.width > CARD_WIDTH - 20 and len(text) > 0:
                        text = text[:-1]
                        text_surface = font.render(text + "...", True, DARK_BRONZE)
                        text_rect = text_surface.get_rect(center=(CARD_WIDTH//2, y_pos))
                card_surface.blit(text_surface, text_rect)
                y_pos += int(90 * CARD_SCALE)

        scaled_card = pygame.transform.scale(card_surface, 
                                           (self.card_rect.width, self.card_rect.height))
        screen.blit(scaled_card, self.card_rect)

class CardEditor:
    def __init__(self, card_type, back_action):
        self.card_type = card_type
        self.back_action = back_action
        self.scroll_offset = 0
        self.max_scroll = 0
        self.selected_card = None
        self.ui_elements = []
        self.card_buttons = []
        self.input_boxes = []
        self.file_inputs = []
        self.dropdown_inputs = []
        self.submit_button = None
        self.delete_button = None
        self.load_cards()

    def load_cards(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.card_buttons = []
        self.submit_button = None
        self.delete_button = None
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text=f"Edit {self.card_type}",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)
        
        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        
        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)
        
        self.cards = []
        for card_id, info in index.items():
            if info['type'] == self.card_type:
                self.cards.append((card_id, info))
        self.cards.sort(key=lambda x: x[1]['name'].lower())

        y_start = 80
        for i, (card_id, info) in enumerate(self.cards):
            y_pos = y_start + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=info['name'],
                manager=manager,
                object_id=f"#card_{card_id}"
            )
            self.card_buttons.append((button, card_id))
            self.ui_elements.append(button)

        total_list_height = len(self.cards) * 60 + 100
        self.max_scroll = max(0, total_list_height - WINDOW_HEIGHT)

    def get_field_type(self, field, card_data):
        if field == "2nd_state_Type" and (card_data.get("subclass") in ["Junk_to_Weapon"] or 
                                          card_data.get("blueprint_subclass") in ["Blueprint_to_Weapon"]):
            return "dropdown"
        elif field == "2nd_state_Use_HP" and card_data.get("subclass") == "Junk_to_Consumable_Item":
            return "dropdown"
        elif field == "2nd_state_Use_Placeholder" and card_data.get("subclass") == "Junk_to_Consumable_Item":
            return "dropdown"
        elif field in ["range_id", "2nd_state_range_id"]:
            return "dropdown"
        elif "image" in field.lower() or "file" in field.lower():
            return "file"
        elif field == "Requirements: Specific Cards":
            return "card_selection"
        else:
            return "text"

    def load_card_for_edit(self, card_id):
        self.selected_card = card_id
        manager.clear_and_reset()
        self.ui_elements = []
        self.input_boxes = []
        self.file_inputs = []
        self.dropdown_inputs = []
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text=f"Edit {self.card_type}",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)
        
        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        
        self.submit_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, WINDOW_HEIGHT - 60, 200, 40),
            text="Submit",
            manager=manager,
            object_id="#submit_button"
        )
        self.ui_elements.append(self.submit_button)
        
        self.delete_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2 - 220, WINDOW_HEIGHT - 60, 200, 40),
            text="Delete",
            manager=manager,
            object_id="#delete_button"
        )
        self.ui_elements.append(self.delete_button)

        card_file = os.path.join("cards", f"{card_id}.json")
        with open(card_file, 'r') as f:
            card_data = json.load(f)
        
        y_start = 80
        if card_data["card_type"] == "Junk Card" and card_data.get("states") == 2:
            left_field_names = [
                "Name", "Description", "Raw Material Value", "Refined Material Value",
                "Metal Value", "Wood Value", "Background Image", "Junk Image"
            ]
            middle_field_names = [
                "Requirements: Raw Materials", "Requirements: Refined Materials",
                "Requirements: Wood", "Requirements: Metal", "Requirements: Specific Cards"
            ]
            left_fields = [(k, v) for k, v in card_data["data"].items() if k in left_field_names]
            middle_fields = [(k, v) for k, v in card_data["data"].items() if k in middle_field_names]
            right_fields = [(k, v) for k, v in card_data["data"].items() 
                           if k not in left_field_names and k not in middle_field_names]

            column_width = 300
            spacing = 50
            total_width = 3 * column_width + 2 * spacing
            left_margin = (WINDOW_WIDTH - total_width) // 2
            column1_x = left_margin
            column2_x = column1_x + column_width + spacing
            column3_x = column2_x + column_width + spacing

            for i, (field, value) in enumerate(left_fields):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(column1_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column1_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                elif field_type == "file":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column1_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(column1_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)

            for i, (field, value) in enumerate(middle_fields):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(column2_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column2_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                elif field_type == "card_selection":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column2_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(column2_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)

            for i, (field, value) in enumerate(right_fields):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(column3_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column3_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                elif field_type == "file":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column3_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(column3_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
                elif field_type == "dropdown":
                    if field == "2nd_state_Type":
                        options = ["Melee", "Projectile"]
                        default = value if value in options else options[0]
                    elif field == "2nd_state_Use_HP":
                        options = HP_OPTIONS
                        default = value if isinstance(value, str) and value in options else (value[0] if isinstance(value, list) and value and value[0] in options else options[0])
                    elif field == "2nd_state_Use_Placeholder":
                        options = PLACEHOLDER_OPTIONS
                        default = value if isinstance(value, str) and value in options else (value[0] if isinstance(value, list) and value and value[0] in options else options[0])
                    elif field in ["range_id", "2nd_state_range_id"]:
                        options = RANGE_OPTIONS
                        default = value if value in options else "None"
                    else:
                        continue
                    dropdown = UIDropDownMenu(
                        options_list=options,
                        starting_option=default,
                        relative_rect=pygame.Rect(right_column_x, y_pos, column_width, 40),
                        manager=manager,
                        object_id=f"#dropdown_{field.replace(' ', '_')}"
                    )
                    self.dropdown_inputs.append((dropdown, field))
                    self.ui_elements.append(dropdown)

            max_fields = max(len(left_fields), len(middle_fields), len(right_fields))
            total_form_height = max_fields * 80 + 140
            self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
        elif card_data.get("states") == 2:
            state_1_fields = {k: v for k, v in card_data["data"].items() if not k.lower().startswith("2nd_")}
            state_2_fields = {k: v for k, v in card_data["data"].items() if k.lower().startswith("2nd_")}
            
            column_width = 300
            left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
            right_column_x = left_column_x + column_width + 100
            
            for i, (field, value) in enumerate(state_1_fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(left_column_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = "file" if any(img in field.lower() for img in ["image", "file"]) else "text"
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(left_column_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                else:
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(left_column_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(left_column_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
            
            for i, (field, value) in enumerate(state_2_fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(right_column_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "dropdown":
                    if field == "2nd_state_Type":
                        options = ["Melee", "Projectile"]
                        default = value if value in options else options[0]
                    elif field == "2nd_state_Use_HP":
                        options = HP_OPTIONS
                        default = value if isinstance(value, str) and value in options else (value[0] if isinstance(value, list) and value and value[0] in options else options[0])
                    elif field == "2nd_state_Use_Placeholder":
                        options = PLACEHOLDER_OPTIONS
                        default = value if isinstance(value, str) and value in options else (value[0] if isinstance(value, list) and value and value[0] in options else options[0])
                    else:
                        continue
                    dropdown = UIDropDownMenu(
                        options_list=options,
                        starting_option=default,
                        relative_rect=pygame.Rect(right_column_x, y_pos, column_width, 40),
                        manager=manager,
                        object_id=f"#dropdown_{field.replace(' ', '_')}"
                    )
                    self.dropdown_inputs.append((dropdown, field))
                    self.ui_elements.append(dropdown)
                elif field_type == "file":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(right_column_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(right_column_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
                else:
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(right_column_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
            
            total_form_height = max(len(state_1_fields), len(state_2_fields)) * 80 + 140
            self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
        else:
            fields = card_data["data"]
            for i, (field, value) in enumerate(fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect((WINDOW_WIDTH - 300) // 2, y_pos - 30, 300, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect((WINDOW_WIDTH - 300) // 2, y_pos, 300, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                elif field_type == "file":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect((WINDOW_WIDTH - 300) // 2, y_pos, 220, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect((WINDOW_WIDTH + 240) // 2, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
                elif field_type == "dropdown":
                    options = RANGE_OPTIONS if field == "range_id" else []
                    default = value if value in options else "None"
                    dropdown = UIDropDownMenu(
                        options_list=options,
                        starting_option=default,
                        relative_rect=pygame.Rect((WINDOW_WIDTH - 300) // 2, y_pos, 300, 40),
                        manager=manager,
                        object_id=f"#dropdown_{field.replace(' ', '_')}"
                    )
                    self.dropdown_inputs.append((dropdown, field))
                    self.ui_elements.append(dropdown)
            
            total_form_height = len(fields) * 80 + 140
            self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)

    def submit_changes(self):
        if not self.selected_card:
            return
        
        card_file = os.path.join("cards", f"{self.selected_card}.json")
        with open(card_file, 'r') as f:
            card_data = json.load(f)
        
        new_data = {entry[1]: entry[0].get_text() for entry in self.input_boxes}
        new_data.update({entry[2]: entry[0].get_text() for entry in self.file_inputs})
        new_data.update({dropdown[1]: dropdown[0].selected_option for dropdown in self.dropdown_inputs})
        card_data["data"] = new_data
        
        with open(card_file, 'w') as f:
            json.dump(card_data, f, indent=2)
        
        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)
        
        index[self.selected_card]["name"] = card_data["data"].get("Name", 
                                                               card_data["data"].get("Default Name", "Unnamed"))
        
        with open(INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=2)
        
        print(f"Card updated: {self.selected_card}")
        self.preview_card(card_data)

    def delete_card(self):
        if not self.selected_card:
            return
        
        card_file = os.path.join("cards", f"{self.selected_card}.json")
        if os.path.exists(card_file):
            os.remove(card_file)
        
        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)
        
        if self.selected_card in index:
            del index[self.selected_card]
        
        with open(INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=2)
        
        print(f"Card deleted: {self.selected_card}")
        self.back_to_list()

    def preview_card(self, card_data):
        CardManager.instance.preview_screen = CardPreview(
            card_data,
            self.selected_card,
            CardManager.instance.back_to_main,
            lambda: self.load_card_for_edit(self.selected_card)
        )
        CardManager.instance.current_screen = "preview"
        self.selected_card = None
        self.back_action()

    def back_to_list(self):
        if self.selected_card:
            self.selected_card = None
            self.load_cards()
        else:
            self.back_action()

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                self.back_to_list()
            elif self.submit_button and event.ui_element == self.submit_button and self.selected_card:
                self.submit_changes()
            elif self.delete_button and event.ui_element == self.delete_button and self.selected_card:
                self.delete_card()
            else:
                for button, card_id in self.card_buttons:
                    if event.ui_element == button:
                        self.load_card_for_edit(card_id)
                        break
                for entry, browse, field in self.file_inputs:
                    if event.ui_element == browse:
                        root = tk.Tk()
                        root.withdraw()
                        file_path = filedialog.askopenfilename(
                            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")]
                        )
                        root.destroy()
                        if file_path and file_path.lower().endswith(SUPPORTED_IMAGE_FORMATS):
                            entry.set_text(file_path)
                            try:
                                pygame.image.load(file_path)
                            except pygame.error:
                                print(f"Error: Cannot load image file: {file_path}")
                                entry.set_text("")
        elif event.type == pygame.MOUSEWHEEL and self.selected_card:
            self.scroll_offset += event.y * 20
            self.scroll_offset = max(min(self.scroll_offset, 0), -self.max_scroll)
            for element in self.ui_elements:
                element.rect.y = element.relative_rect.y - self.scroll_offset

    def draw(self):
        screen.fill(DARK_INDIGO)

class CardViewer:
    def __init__(self, card_type, back_action):
        self.card_type = card_type
        self.back_action = back_action
        self.scroll_offset = 0
        self.max_scroll = 0
        self.selected_card = None
        self.preview = None
        self.ui_elements = []
        self.card_buttons = []
        self.load_cards()

    def load_cards(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.card_buttons = []
        self.preview = None
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text=f"{self.card_type}s",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)
        
        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        
        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)
        
        self.cards = []
        for card_id, info in index.items():
            if info['type'] == self.card_type:
                self.cards.append((card_id, info))
        self.cards.sort(key=lambda x: x[1]['name'].lower())

        y_start = 80
        for i, (card_id, info) in enumerate(self.cards):
            y_pos = y_start + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=info['name'],
                manager=manager,
                object_id=f"#card_{card_id}"
            )
            self.card_buttons.append((button, card_id))
            self.ui_elements.append(button)

        total_list_height = len(self.cards) * 60 + 100
        self.max_scroll = max(0, total_list_height - WINDOW_HEIGHT)

    def show_card_details(self, card_id):
        self.selected_card = card_id
        card_file = os.path.join("cards", f"{card_id}.json")
        with open(card_file, 'r') as f:
            card_data = json.load(f)
        
        self.preview = CardPreview(
            card_data,
            card_id,
            self.back_to_list
        )

    def back_to_list(self):
        if self.selected_card:
            self.selected_card = None
            self.preview = None
            self.load_cards()
        else:
            self.back_action()

    def handle_event(self, event):
        if self.preview:
            self.preview.handle_event(event)
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                self.back_to_list()
            else:
                for button, card_id in self.card_buttons:
                    if event.ui_element == button:
                        self.show_card_details(card_id)
                        break
        elif event.type == pygame.MOUSEWHEEL and not self.selected_card:
            self.scroll_offset += event.y * 20
            self.scroll_offset = max(min(self.scroll_offset, 0), -self.max_scroll)
            for element in self.ui_elements:
                element.rect.y = element.relative_rect.y - self.scroll_offset

    def draw(self):
        screen.fill(DARK_INDIGO)
        if self.preview:
            self.preview.draw()

class CardCreationScreen:
    def __init__(self, card_type, back_action):
        self.card_type = card_type
        self.back_action = back_action
        if card_type == "Document Card":
            self.current_screen = "subclass_selection"
        else:
            self.current_screen = "state_selection"
        self.selected_subclass = None
        self.selected_blueprint_subclass = None
        self.state = None
        self.scroll_offset = 0
        self.max_scroll = 0
        self.ui_elements = []
        self.input_boxes = []
        self.file_inputs = []
        self.dropdown_inputs = []
        self.initialize_screen()

    def initialize_screen(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.input_boxes = []
        self.file_inputs = []
        self.dropdown_inputs = []

        if self.card_type == "Document Card":
            if self.current_screen == "subclass_selection":
                self.initialize_document_subclass_selection()
            elif self.current_screen == "blueprint_subclass_selection":
                self.initialize_blueprint_subclass_selection()
            elif self.current_screen == "input_form":
                self.initialize_input_form()
        elif self.card_type == "Junk Card":
            if self.current_screen == "state_selection":
                self.initialize_state_selection()
            elif self.current_screen == "subclass_selection":
                self.initialize_junk_subclass_selection()
            elif self.current_screen == "input_form":
                self.initialize_input_form()
        else:
            if self.current_screen == "state_selection":
                self.initialize_state_selection()
            elif self.current_screen == "input_form":
                self.initialize_input_form()

    def initialize_document_subclass_selection(self):
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="What is the subclass of Document?",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        subclasses = ["Blueprint", "Journal", "Map", "Note", "Book", "Pamphlet"]
        for i, subclass in enumerate(subclasses):
            y_pos = 100 + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=subclass,
                manager=manager,
                object_id=f"#subclass_{subclass}"
            )
            self.ui_elements.append(button)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)

    def initialize_blueprint_subclass_selection(self):
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Sub-classification of Blueprint?",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        blueprint_subclasses = ["Blueprint_to_Weapon", "Blueprint_to_Tool", "Blueprint_to_Consumable_Item"]
        for i, subclass in enumerate(blueprint_subclasses):
            y_pos = 100 + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=subclass.replace("_", " "),
                manager=manager,
                object_id=f"#blueprint_subclass_{subclass}"
            )
            self.ui_elements.append(button)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)

    def initialize_junk_subclass_selection(self):
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="What is the subclass of Junk?",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        subclasses = ["Junk_to_Weapon", "Junk_to_Tool", "Junk_to_Consumable_Item"]
        for i, subclass in enumerate(subclasses):
            y_pos = 100 + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=subclass.replace("_", " "),
                manager=manager,
                object_id=f"#junk_subclass_{subclass}"
            )
            self.ui_elements.append(button)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)

    def initialize_state_selection(self):
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text=f"How many states will the {self.card_type} have?",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)
        
        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        
        self.state_1_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 220) // 2 - 110, 200, 100, 40),
            text="1",
            manager=manager,
            object_id="#state_1"
        )
        self.state_2_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH + 220) // 2 - 110, 200, 100, 40),
            text="2",
            manager=manager,
            object_id="#state_2"
        )
        self.ui_elements.append(self.state_1_button)
        self.ui_elements.append(self.state_2_button)

    def initialize_input_form(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.input_boxes = []
        self.file_inputs = []
        self.dropdown_inputs = []

        title_text = f"Create {self.card_type}"
        if self.card_type == "Document Card":
            title_text += f" - {self.selected_subclass}"
            if self.selected_subclass == "Blueprint":
                title_text += f" {self.selected_blueprint_subclass.replace('_', ' ')}"
        elif self.card_type == "Junk Card" and self.state == 2:
            title_text += f" - {self.selected_subclass.replace('_', ' ')}"

        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text=title_text,
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)

        self.submit_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, WINDOW_HEIGHT - 60, 200, 40),
            text="Submit",
            manager=manager,
            object_id="#submit_button"
        )
        self.ui_elements.append(self.submit_button)

        y_start = 80

        def create_field_ui(column_x, y_pos, field_info, column_width=300):
            if len(field_info) == 2:
                field, field_type = field_info
                default = ""
            elif len(field_info) == 3:
                field, field_type, default = field_info
            elif len(field_info) == 4:
                field, field_type, options, default = field_info
            else:
                return

            label = UILabel(
                relative_rect=pygame.Rect(column_x, y_pos - 30, column_width, 30),
                text=field,
                manager=manager,
                object_id=f"#label_{field.replace(' ', '_')}"
            )
            self.ui_elements.append(label)

            if field_type == "text":
                entry = UITextEntryLine(
                    relative_rect=pygame.Rect(column_x, y_pos, column_width, 40),
                    manager=manager,
                    initial_text=default,
                    object_id=f"#entry_{field.replace(' ', '_')}"
                )
                self.input_boxes.append((entry, field))
                self.ui_elements.append(entry)
            elif field_type == "file":
                entry = UITextEntryLine(
                    relative_rect=pygame.Rect(column_x, y_pos, column_width - 80, 40),
                    manager=manager,
                    initial_text=default,
                    object_id=f"#entry_{field.replace(' ', '_')}"
                )
                browse = UIButton(
                    relative_rect=pygame.Rect(column_x + column_width - 80, y_pos, 80, 40),
                    text="Browse",
                    manager=manager,
                    object_id=f"#browse_{field.replace(' ', '_')}"
                )
                self.file_inputs.append((entry, browse, field))
                self.ui_elements.append(entry)
                self.ui_elements.append(browse)
            elif field_type == "dropdown":
                dropdown = UIDropDownMenu(
                    options_list=options,
                    starting_option=default,
                    relative_rect=pygame.Rect(column_x, y_pos, column_width, 40),
                    manager=manager,
                    object_id=f"#dropdown_{field.replace(' ', '_')}"
                )
                self.dropdown_inputs.append((dropdown, field))
                self.ui_elements.append(dropdown)
            elif field_type == "card_selection":
                entry = UITextEntryLine(
                    relative_rect=pygame.Rect(column_x, y_pos, column_width - 80, 40),
                    manager=manager,
                    initial_text=default,
                    object_id=f"#entry_{field.replace(' ', '_')}",
                    placeholder_text="Select cards (TBD)"
                )
                browse = UIButton(
                    relative_rect=pygame.Rect(column_x + column_width - 80, y_pos, 80, 40),
                    text="Browse",
                    manager=manager,
                    object_id=f"#browse_{field.replace(' ', '_')}"
                )
                self.input_boxes.append((entry, field))
                self.ui_elements.append(entry)
                self.ui_elements.append(browse)

        if self.state == 2:
            if self.card_type == "Junk Card":
                left_fields = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Raw Material Value", "text"),
                    ("Refined Material Value", "text"),
                    ("Metal Value", "text"),
                    ("Wood Value", "text"),
                    ("Background Image", "file"),
                    ("Junk Image", "file"),
                ]
                middle_fields = [
                    ("Requirements: Raw Materials", "text"),
                    ("Requirements: Refined Materials", "text"),
                    ("Requirements: Wood", "text"),
                    ("Requirements: Metal", "text"),
                    ("Requirements: Specific Cards", "card_selection"),
                ]
                if self.selected_subclass == "Junk_to_Weapon":
                    right_fields = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "dropdown", ["Melee", "Projectile"], "Melee"),
                        ("2nd_state_Melee Damage", "text"),
                        ("2nd_state_Projectile Damage", "text"),
                        ("2nd_state_Projectile Range", "text"),
                        ("2nd_state_range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                        ("2nd_state_Weapon Image", "file"),
                    ]
                elif self.selected_subclass == "Junk_to_Tool":
                    right_fields = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "text", "Tool"),
                        ("2nd_state_Use", "text"),
                        ("2nd_state_Tool Image", "file"),
                    ]
                elif self.selected_subclass == "Junk_to_Consumable_Item":
                    right_fields = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "text", "Consumable"),
                        ("2nd_state_Use_HP", "dropdown", HP_OPTIONS, "+15HP"),
                        ("2nd_state_Use_Placeholder", "dropdown", PLACEHOLDER_OPTIONS, "TBD"),
                        ("2nd_state_Item Image", "file"),
                    ]
                else:
                    right_fields = []

                column_width = 300
                spacing = 50
                total_width = 3 * column_width + 2 * spacing
                left_margin = (WINDOW_WIDTH - total_width) // 2
                column1_x = left_margin
                column2_x = column1_x + column_width + spacing
                column3_x = column2_x + column_width + spacing

                for i, field_info in enumerate(left_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column1_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(middle_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column2_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(right_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column3_x, y_pos, field_info, column_width)

                max_fields = max(len(left_fields), len(middle_fields), len(right_fields))
                total_form_height = max_fields * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Document Card" and self.selected_subclass == "Blueprint":
                if self.selected_blueprint_subclass == "Blueprint_to_Weapon":
                    fields_state_1 = [
                        ("Name", "text"),
                        ("Requirements: Raw Materials", "text"),
                        ("Requirements: Refined Materials", "text"),
                        ("Requirements: Wood", "text"),
                        ("Requirements: Metal", "text"),
                        ("Requirements: Specific Cards", "card_selection"),
                        ("Background Image", "file"),
                    ]
                    fields_state_2 = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "dropdown", ["Melee", "Projectile"], "Melee"),
                        ("2nd_state_Melee Damage", "text"),
                        ("2nd_state_Projectile Damage", "text"),
                        ("2nd_state_Projectile Range", "text"),
                        ("2nd_state_range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                        ("2nd_state_Weapon Image", "file"),
                    ]
                elif self.selected_blueprint_subclass == "Blueprint_to_Tool":
                    fields_state_1 = [
                        ("Name", "text"),
                        ("Requirements: Raw Materials", "text"),
                        ("Requirements: Refined Materials", "text"),
                        ("Requirements: Wood", "text"),
                        ("Requirements: Metal", "text"),
                        ("Requirements: Specific Cards", "card_selection"),
                        ("Background Image", "file"),
                    ]
                    fields_state_2 = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "text", "Tool"),
                        ("2nd_state_Use", "text"),
                        ("2nd_state_Tool Image", "file"),
                    ]
                elif self.selected_blueprint_subclass == "Blueprint_to_Consumable_Item":
                    fields_state_1 = [
                        ("Name", "text"),
                        ("Requirements: Raw Materials", "text"),
                        ("Requirements: Refined Materials", "text"),
                        ("Requirements: Wood", "text"),
                        ("Requirements: Metal", "text"),
                        ("Requirements: Specific Cards", "card_selection"),
                        ("Background Image", "file"),
                    ]
                    fields_state_2 = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "text", "Consumable"),
                        ("2nd_state_Use_HP", "dropdown", HP_OPTIONS, "+15HP"),
                        ("2nd_state_Use_Placeholder", "dropdown", PLACEHOLDER_OPTIONS, "TBD"),
                        ("2nd_state_Item Image", "file"),
                    ]
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Enemy Card":
                fields_state_1 = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("Projectile Range", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Background Image File Path", "file"),
                    ("Enemy Image File Path", "file")
                ]
                fields_state_2 = [
                    ("2nd_State_Name", "text"),
                    ("2nd_State_Health", "text"),
                    ("2nd_State_Movement", "text"),
                    ("2nd_State_Melee Damage", "text"),
                    ("2nd_State_Projectile Damage", "text"),
                    ("2nd_State_Projectile Range", "text"),
                    ("2nd_state_range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id for 2nd state
                    ("2nd_State_Enemy Image File Path", "file")
                ]
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Boss Card":
                fields_state_1 = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("Projectile Range", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Background Image File Path", "file"),
                    ("Boss Image File Path", "file")
                ]
                fields_state_2 = [
                    ("2nd_State_Name", "text"),
                    ("2nd_State_Health", "text"),
                    ("2nd_State_Movement", "text"),
                    ("2nd_State_Melee Damage", "text"),
                    ("2nd_State_Projectile Damage", "text"),
                    ("2nd_State_Projectile Range", "text"),
                    ("2nd_state_range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id for 2nd state
                    ("2nd_State_Boss Image File Path", "file")
                ]
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "NPC Card":
                fields_state_1 = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("Projectile Range", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Allegiance (Hostile, Neutral, Allied)", "text"),
                    ("Special Skill", "text"),
                    ("Background Image File Path", "file"),
                    ("NPC Image File Path", "file")
                ]
                fields_state_2 = [
                    ("2nd_State_Name", "text"),
                    ("2nd_State_Health", "text"),
                    ("2nd_State_Movement", "text"),
                    ("2nd_State_Melee Damage", "text"),
                    ("2nd_State_Projectile Damage", "text"),
                    ("2nd_State_Projectile Range", "text"),
                    ("2nd_state_range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id for 2nd state
                    ("2nd_State_Allegiance (Hostile, Neutral, Allied)", "text"),
                    ("2nd_State_Special Skill", "text"),
                    ("2nd_State_NPC Image File Path", "file")
                ]
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Transition Card":
                fields_state_1 = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Background Image", "file"),
                ]
                fields_state_2 = [
                    ("2nd_State_Name", "text"),
                    ("2nd_State_Description", "text"),
                    ("2nd_State_Background Image", "file"),
                ]
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            else:
                fields_state_1 = []
                fields_state_2 = []
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
        else:
            if self.card_type == "Document Card":
                if self.selected_subclass == "Journal":
                    fields = [
                        ("Name", "text"),
                        ("Description", "text"),
                        ("Background Image", "file"),
                    ]
                elif self.selected_subclass == "Map":
                    fields = [("Name", "text"), ("Description", "text"), ("Background Image", "file")]
                elif self.selected_subclass == "Note":
                    fields = [
                        ("Name", "text"),
                        ("Contents", "text"),
                        ("Background Image", "file"),
                    ]
                elif self.selected_subclass == "Book":
                    fields = [
                        ("Name", "text"),
                        ("Description", "text"),
                        ("Background Image", "file"),
                        ("Book Image", "file"),
                    ]
                elif self.selected_subclass == "Pamphlet":
                    fields = [
                        ("Name", "text"),
                        ("Lesson", "text"),
                        ("Background Image", "file"),
                        ("Pamphlet Image", "file"),
                    ]
                else:
                    fields = []
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Junk Card":
                fields = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Raw Material Value", "text"),
                    ("Refined Material Value", "text"),
                    ("Metal Value", "text"),
                    ("Wood Value", "text"),
                    ("Background Image", "file"),
                    ("Junk Image", "file"),
                ]
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Enemy Card":
                fields = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Projectile Range", "text"),
                    ("Background Image File Path", "file"),
                    ("Enemy Image File Path", "file")
                ]
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Boss Card":
                fields = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("Projectile Range", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Background Image File Path", "file"),
                    ("Boss Image File Path", "file")
                ]
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "NPC Card":
                fields = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("Projectile Range", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Allegiance (Hostile, Neutral, Allied)", "text"),
                    ("Special Skill", "text"),
                    ("Background Image File Path", "file"),
                    ("NPC Image File Path", "file")
                ]
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Location Card":
                fields = [
                    ("Name", "text"),
                    ("Background Image File Path", "file"),
                    ("Location Image File Path", "file")
                ]
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Transition Card":
                dropdown_options = [
                    "1 junk", "1 document", "2 junk", "2 document",
                    "1 location", "1 enemy", "1 NPC", "1 instance", "1 quest"
                ]
                left_fields = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("From Card", "card_selection"),
                    ("To Card", "card_selection"),
                    ("Background Image", "file"),
                ]
                right_fields = [
                    ("Field 1", "dropdown", dropdown_options, "1 junk"),
                    ("Field 2", "dropdown", dropdown_options, "1 junk"),
                    ("Field 3", "dropdown", dropdown_options, "1 junk"),
                    ("Field 4", "dropdown", dropdown_options, "1 junk"),
                    ("Field 5", "dropdown", dropdown_options, "1 junk"),
                    ("Field 6", "dropdown", dropdown_options, "1 junk"),
                    ("Field 7", "dropdown", dropdown_options, "1 junk"),
                    ("Field 8", "dropdown", dropdown_options, "1 junk"),
                ]
                column_width = 300
                spacing = 100
                left_column_x = (WINDOW_WIDTH - 2 * column_width - spacing) // 2
                right_column_x = left_column_x + column_width + spacing

                for i, field_info in enumerate(left_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(right_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(left_fields), len(right_fields)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            else:
                fields = []
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
                
    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                if self.current_screen == "subclass_selection" or self.current_screen == "state_selection":
                    self.back_action()
                elif self.current_screen == "blueprint_subclass_selection":
                    self.current_screen = "subclass_selection"
                    self.selected_subclass = None
                    self.state = None
                    self.initialize_screen()
                elif self.current_screen == "input_form":
                    if self.card_type == "Document Card" and self.selected_subclass == "Blueprint":
                        self.current_screen = "blueprint_subclass_selection"
                    else:
                        self.current_screen = "subclass_selection" if self.card_type == "Document Card" else "state_selection"
                    self.state = None
                    self.initialize_screen()
                elif self.current_screen == "subclass_selection" and self.card_type == "Junk Card":
                    self.current_screen = "state_selection"
                    self.selected_subclass = None
                    self.initialize_screen()

            elif self.current_screen == "subclass_selection" and self.card_type == "Document Card":
                for subclass in ["Blueprint", "Journal", "Map", "Note", "Book", "Pamphlet"]:
                    if event.ui_element.object_ids and event.ui_element.object_ids[0] == f"#subclass_{subclass}":
                        self.selected_subclass = subclass
                        self.state = 2 if subclass == "Blueprint" else 1
                        self.current_screen = "blueprint_subclass_selection" if subclass == "Blueprint" else "input_form"
                        self.initialize_screen()
                        break

            elif self.current_screen == "blueprint_subclass_selection":
                for subclass in ["Blueprint_to_Weapon", "Blueprint_to_Tool", "Blueprint_to_Consumable_Item"]:
                    if event.ui_element.object_ids and event.ui_element.object_ids[0] == f"#blueprint_subclass_{subclass}":
                        self.selected_blueprint_subclass = subclass
                        self.current_screen = "input_form"
                        self.initialize_screen()
                        break

            elif self.current_screen == "state_selection":
                if event.ui_element == self.state_1_button:
                    self.state = 1
                    self.current_screen = "input_form"
                    self.initialize_screen()
                elif event.ui_element == self.state_2_button:
                    self.state = 2
                    self.current_screen = "subclass_selection" if self.card_type == "Junk Card" else "input_form"
                    self.initialize_screen()

            elif self.current_screen == "subclass_selection" and self.card_type == "Junk Card":
                for subclass in ["Junk_to_Weapon", "Junk_to_Tool", "Junk_to_Consumable_Item"]:
                    if event.ui_element.object_ids and event.ui_element.object_ids[0] == f"#junk_subclass_{subclass}":
                        self.selected_subclass = subclass
                        self.current_screen = "input_form"
                        self.initialize_screen()
                        break

            elif event.ui_element == self.submit_button and self.current_screen == "input_form":
                self.submit_card()

            else:
                for entry, browse, field in self.file_inputs:
                    if event.ui_element == browse:
                        root = tk.Tk()
                        root.withdraw()
                        file_path = filedialog.askopenfilename(
                            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")]
                        )
                        root.destroy()
                        if file_path and file_path.lower().endswith(SUPPORTED_IMAGE_FORMATS):
                            entry.set_text(file_path)
                            try:
                                pygame.image.load(file_path)
                            except pygame.error:
                                print(f"Error: Cannot load image file: {file_path}")
                                entry.set_text("")

        elif event.type == pygame.MOUSEWHEEL and self.current_screen == "input_form":
            self.scroll_offset += event.y * 20
            self.scroll_offset = max(min(self.scroll_offset, 0), -self.max_scroll)
            for element in self.ui_elements:
                element.rect.y = element.relative_rect.y - self.scroll_offset

    def submit_card(self):
        card_data = {
            "card_type": self.card_type,
            "subclass": self.selected_subclass if self.card_type in ["Document Card", "Junk Card"] else None,
            "blueprint_subclass": self.selected_blueprint_subclass if self.selected_subclass == "Blueprint" else None,
            "states": self.state,
            "data": {entry[1]: entry[0].get_text() for entry in self.input_boxes}
        }
        card_data["data"].update({entry[2]: entry[0].get_text() for entry in self.file_inputs})
        card_data["data"].update({dropdown[1]: dropdown[0].selected_option for dropdown in self.dropdown_inputs})
        
        # Debug print to verify dropdown values
        print("Submitting card data:")
        for key, value in card_data["data"].items():
            print(f"{key}: {value} (type: {type(value)})")
        
        card_id = str(uuid.uuid4())
        card_file = os.path.join("cards", f"{card_id}.json")
        with open(card_file, 'w') as f:
            json.dump(card_data, f, indent=2)
        
        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)
        
        index[card_id] = {
            "type": self.card_type,
            "subclass": card_data["subclass"],
            "blueprint_subclass": card_data["blueprint_subclass"],
            "states": self.state,
            "name": card_data["data"].get("Name", 
                                        card_data["data"].get("Default Name", "Unnamed"))
        }
        
        with open(INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=2)
        
        print(f"Card saved with ID: {card_id}")
        self.preview_card(card_data, card_id)

    def preview_card(self, card_data, card_id):
        CardManager.instance.preview_screen = CardPreview(
            card_data,
            card_id,
            CardManager.instance.back_to_main,
            lambda: CardManager.instance.edit_card(self.card_type)
        )
        CardManager.instance.current_screen = "preview"

    def draw(self):
        screen.fill(DARK_INDIGO)

class DeckMaker:
    def __init__(self, back_action):
        self.back_action = back_action
        self.selected_cards = []
        self.ui_elements = []
        self.deck_name_entry = None
        self.back_image_entry = None
        self.back_image_browse = None
        self.available_cards_list = None
        self.selected_cards_list = None
        self.remove_button = None
        self.load_cards()
        os.makedirs("decks", exist_ok=True)

    def load_cards(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.selected_cards = []

        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Deck Maker",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)

        column_width = WINDOW_WIDTH // 3
        y_start = 80
        list_height = WINDOW_HEIGHT - y_start - 150

        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)

        self.cards = [(card_id, info) for card_id, info in index.items()]
        self.cards.sort(key=lambda x: x[1]['name'].lower())
        available_cards_dict = {info['name']: card_id for card_id, info in self.cards}

        self.available_cards_list = pygame_gui.elements.UISelectionList(
            relative_rect=pygame.Rect(20, y_start, column_width - 40, list_height),
            item_list=list(available_cards_dict.keys()),
            manager=manager,
            allow_multi_select=True,
            object_id="#available_cards_list"
        )
        self.ui_elements.append(self.available_cards_list)
        self.available_cards_dict = available_cards_dict

        deck_info_x = column_width
        self.deck_name_label = UILabel(
            relative_rect=pygame.Rect(deck_info_x + 20, y_start, column_width - 40, 30),
            text="Deck Name:",
            manager=manager
        )
        self.deck_name_entry = UITextEntryLine(
            relative_rect=pygame.Rect(deck_info_x + 20, y_start + 30, column_width - 40, 40),
            manager=manager
        )
        self.back_image_label = UILabel(
            relative_rect=pygame.Rect(deck_info_x + 20, y_start + 90, column_width - 40, 30),
            text="Back Image (Optional):",
            manager=manager
        )
        self.back_image_entry = UITextEntryLine(
            relative_rect=pygame.Rect(deck_info_x + 20, y_start + 120, column_width - 120, 40),
            manager=manager
        )
        self.back_image_browse = UIButton(
            relative_rect=pygame.Rect(deck_info_x + column_width - 100, y_start + 120, 80, 40),
            text="Browse",
            manager=manager,
            object_id="#browse_back_image"
        )
        self.ui_elements.extend([
            self.deck_name_label, self.deck_name_entry,
            self.back_image_label, self.back_image_entry,
            self.back_image_browse
        ])

        selected_cards_x = 2 * column_width
        self.selected_cards_label = UILabel(
            relative_rect=pygame.Rect(selected_cards_x + 20, y_start, column_width - 40, 30),
            text="Selected Cards:",
            manager=manager
        )
        self.ui_elements.append(self.selected_cards_label)

        self.selected_cards_list = pygame_gui.elements.UISelectionList(
            relative_rect=pygame.Rect(selected_cards_x + 20, y_start + 30, column_width - 40, list_height - 30),
            item_list=[],
            manager=manager,
            allow_multi_select=True,
            object_id="#selected_cards_list"
        )
        self.ui_elements.append(self.selected_cards_list)

        button_y = WINDOW_HEIGHT - 60
        button_width = (column_width - 70) // 4
        self.create_deck_button = UIButton(
            relative_rect=pygame.Rect(selected_cards_x + 20, button_y, button_width, 40),
            text="Create Deck",
            manager=manager,
            object_id="#create_deck"
        )
        self.cancel_button = UIButton(
            relative_rect=pygame.Rect(selected_cards_x + 20 + button_width + 10, 
                                   button_y, button_width, 40),
            text="Cancel",
            manager=manager,
            object_id="#cancel_deck"
        )
        self.remove_button = UIButton(
            relative_rect=pygame.Rect(selected_cards_x + 20 + 2 * (button_width + 10), 
                                   button_y, button_width, 40),
            text="Remove",
            manager=manager,
            object_id="#remove_selected"
        )
        self.main_menu_button = UIButton(
            relative_rect=pygame.Rect(selected_cards_x + 20 + 3 * (button_width + 10), 
                                   button_y, button_width, 40),
            text="Main Menu",
            manager=manager,
            object_id="#main_menu"
        )
        self.ui_elements.extend([
            self.create_deck_button, self.cancel_button,
            self.remove_button, self.main_menu_button
        ])

    def update_selected_cards(self):
        selected_names = self.available_cards_list.get_multi_selection()
        self.selected_cards = [self.available_cards_dict[name] for name in selected_names 
                             if name in self.available_cards_dict]
        
        selected_names_list = [info['name'] for card_id, info in self.cards 
                             if card_id in self.selected_cards]
        self.selected_cards_list.set_item_list(selected_names_list)

    def remove_selected_cards(self):
        selected_names_to_remove = self.selected_cards_list.get_multi_selection()
        if not selected_names_to_remove:
            return
        
        self.selected_cards = [card_id for card_id in self.selected_cards 
                             if next(info['name'] for cid, info in self.cards if cid == card_id) 
                             not in selected_names_to_remove]
        
        selected_names_list = [info['name'] for card_id, info in self.cards 
                             if card_id in self.selected_cards]
        self.selected_cards_list.set_item_list(selected_names_list)
        
        current_selections = self.available_cards_list.get_multi_selection()
        all_cards = [info['name'] for _, info in self.cards]
        self.available_cards_list.set_item_list(all_cards)

    def create_deck(self):
        deck_name = self.deck_name_entry.get_text().strip()
        back_image = self.back_image_entry.get_text().strip()

        if not deck_name:
            print("Error: Deck name is required")
            return
        if not self.selected_cards:
            print("Error: At least one card must be selected")
            return

        safe_filename = re.sub(r'[^\w\s-]', '', deck_name).strip().replace(' ', '_')
        if not safe_filename:
            safe_filename = "unnamed_deck"

        deck_data = {
            "deck_name": deck_name,
            "back_image": back_image if back_image else None,
            "cards": self.selected_cards
        }

        deck_id = str(uuid.uuid4())
        deck_file = os.path.join("decks", f"{safe_filename}_{deck_id}.json")
        
        try:
            with open(deck_file, 'w') as f:
                json.dump(deck_data, f, indent=2)
            print(f"Deck saved: {deck_file}")
            self.load_cards()
        except Exception as e:
            print(f"Error saving deck: {e}")

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                self.back_action()
            elif event.ui_element == self.create_deck_button:
                self.create_deck()
            elif event.ui_element == self.cancel_button:
                self.load_cards()
            elif event.ui_element == self.main_menu_button:
                CardManager.instance.back_to_main()
            elif event.ui_element == self.back_image_browse:
                root = tk.Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(
                    filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")]
                )
                root.destroy()
                if file_path:
                    self.back_image_entry.set_text(file_path)
            elif event.ui_element == self.remove_button:
                self.remove_selected_cards()
        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.available_cards_list:
                self.update_selected_cards()

    def draw(self):
        screen.fill(DARK_INDIGO)

class CardManager:
    instance = None

    def __init__(self):
        CardManager.instance = self
        self.current_screen = "main"
        self.creation_screen = None
        self.viewer_screen = None
        self.editor_screen = None
        self.preview_screen = None
        self.deck_maker_screen = None
        self.ui_elements = []
        self.initialize_buttons()

    def initialize_buttons(self):
        manager.clear_and_reset()
        self.ui_elements = []
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Card Management System",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)
        
        self.create_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 200, 200, 40),
            text="Create Card",
            manager=manager,
            object_id="#create_card"
        )
        self.edit_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 260, 200, 40),
            text="Edit Card",
            manager=manager,
            object_id="#edit_card"
        )
        self.view_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 320, 200, 40),
            text="View Cards",
            manager=manager,
            object_id="#view_cards"
        )
        self.deck_maker_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 380, 200, 40),
            text="Deck Maker",
            manager=manager,
            object_id="#deck_maker"
        )
        self.quit_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 440, 200, 40),
            text="Quit",
            manager=manager,
            object_id="#quit_button"
        )
        self.update_index_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 500, 200, 40),
            text="Update Card Index",
            manager=manager,
            object_id="#update_index"
        )
        self.ui_elements.extend([
            self.create_button, self.edit_button, self.view_button,
            self.deck_maker_button, self.quit_button, self.update_index_button
        ])

        self.card_types = [
            "Junk Card", "Document Card", "Enemy Card", "NPC Card",
            "Location Card", "Quest Card", "Instance Card", "Boss Card", "Transition Card"
        ]
        self.create_buttons = []
        self.edit_buttons = []
        self.view_buttons = []

    def show_create_menu(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.current_screen = "create"
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Create Card",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.extend([self.title, self.back_button])
        
        y_start = 80
        for i, card_type in enumerate(self.card_types):
            y_pos = y_start + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=f"Create {card_type}",
                manager=manager,
                object_id=f"#create_{card_type.replace(' ', '_')}"
            )
            self.create_buttons.append((button, card_type))
            self.ui_elements.append(button)

    def show_edit_menu(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.current_screen = "edit"
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Edit Card",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.extend([self.title, self.back_button])
        
        y_start = 80
        for i, card_type in enumerate(self.card_types):
            y_pos = y_start + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=f"Edit {card_type}",
                manager=manager,
                object_id=f"#edit_{card_type.replace(' ', '_')}"
            )
            self.edit_buttons.append((button, card_type))
            self.ui_elements.append(button)

    def show_view_menu(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.current_screen = "view"
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="View Cards",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.extend([self.title, self.back_button])
        
        y_start = 80
        for i, card_type in enumerate(self.card_types):
            y_pos = y_start + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=f"View {card_type}s",
                manager=manager,
                object_id=f"#view_{card_type.replace(' ', '_')}"
            )
            self.view_buttons.append((button, card_type))
            self.ui_elements.append(button)

    def show_deck_maker(self):
        self.current_screen = "deck_maker"
        self.deck_maker_screen = DeckMaker(self.back_to_main)
        self.creation_screen = None
        self.viewer_screen = None
        self.editor_screen = None
        self.preview_screen = None

    def back_to_main(self):
        self.current_screen = "main"
        self.creation_screen = None
        self.viewer_screen = None
        self.editor_screen = None
        self.preview_screen = None
        self.deck_maker_screen = None
        self.initialize_buttons()

    def create_card(self, card_type):
        self.current_screen = "creation"
        self.creation_screen = CardCreationScreen(card_type, self.show_create_menu)
        self.viewer_screen = None
        self.editor_screen = None
        self.preview_screen = None
        self.deck_maker_screen = None

    def edit_card(self, card_type):
        self.current_screen = "editor"
        self.editor_screen = CardEditor(card_type, self.show_edit_menu)
        self.creation_screen = None
        self.viewer_screen = None
        self.preview_screen = None
        self.deck_maker_screen = None

    def view_cards(self, card_type):
        self.current_screen = "viewer"
        self.viewer_screen = CardViewer(card_type, self.show_view_menu)
        self.creation_screen = None
        self.editor_screen = None
        self.preview_screen = None
        self.deck_maker_screen = None

    def update_card_index(self):
        index = {}
        for filename in os.listdir("cards"):
            if filename.endswith(".json") and filename != "card_index.json":
                card_id = os.path.splitext(filename)[0]
                try:
                    with open(os.path.join("cards", filename), 'r') as f:
                        card_data = json.load(f)
                    if "card_type" in card_data and "data" in card_data:
                        name = card_data["data"].get("Name", card_data["data"].get("Default Name", "Unnamed"))
                        index[card_id] = {
                            "type": card_data["card_type"],
                            "subclass": card_data.get("subclass"),
                            "blueprint_subclass": card_data.get("blueprint_subclass"),
                            "states": card_data.get("states"),
                            "name": name
                        }
                    else:
                        print(f"Skipping {filename}: missing 'card_type' or 'data'")
                except json.JSONDecodeError:
                    print(f"Error decoding JSON in {filename}")
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
        with open(INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=2)
        print("Card index updated.")

    def handle_event(self, event):
        if self.current_screen == "creation" and self.creation_screen:
            self.creation_screen.handle_event(event)
            return
        if self.current_screen == "viewer" and self.viewer_screen:
            self.viewer_screen.handle_event(event)
            return
        if self.current_screen == "editor" and self.editor_screen:
            self.editor_screen.handle_event(event)
            return
        if self.current_screen == "preview" and self.preview_screen:
            self.preview_screen.handle_event(event)
            return
        if self.current_screen == "deck_maker" and self.deck_maker_screen:
            self.deck_maker_screen.handle_event(event)
            return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.create_button:
                self.show_create_menu()
            elif event.ui_element == self.edit_button:
                self.show_edit_menu()
            elif event.ui_element == self.view_button:
                self.show_view_menu()
            elif event.ui_element == self.deck_maker_button:
                self.show_deck_maker()
            elif event.ui_element == self.quit_button:
                pygame.quit()
                sys.exit()
            elif event.ui_element == self.update_index_button:
                self.update_card_index()
            elif self.current_screen in ["create", "edit", "view"] and event.ui_element == self.back_button:
                self.back_to_main()
            else:
                for button, card_type in self.create_buttons:
                    if event.ui_element == button:
                        self.create_card(card_type)
                        break
                for button, card_type in self.edit_buttons:
                    if event.ui_element == button:
                        self.edit_card(card_type)
                        break
                for button, card_type in self.view_buttons:
                    if event.ui_element == button:
                        self.view_cards(card_type)
                        break

    def draw(self):
        screen.fill(DARK_INDIGO)
        if self.current_screen == "creation" and self.creation_screen:
            self.creation_screen.draw()
        elif self.current_screen == "viewer" and self.viewer_screen:
            self.viewer_screen.draw()
        elif self.current_screen == "editor" and self.editor_screen:
            self.editor_screen.draw()
        elif self.current_screen == "preview" and self.preview_screen:
            self.preview_screen.draw()
        elif self.current_screen == "deck_maker" and self.deck_maker_screen:
            self.deck_maker_screen.draw()

def main():
    pygame.display.set_mode((1, 1))
    root = tk.Tk()
    root.withdraw()
    pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
    
    card_manager = CardManager()
    clock = pygame.time.Clock()

    while True:
        time_delta = clock.tick(60) / 1000.0
        for e in event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit()
            card_manager.handle_event(e)
            manager.process_events(e)

        manager.update(time_delta)
        card_manager.draw()
        manager.draw_ui(screen)
        display.flip()

if __name__ == "__main__":
    main()

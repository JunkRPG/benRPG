import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UILabel, UITextEntryLine, UIDropDownMenu
import os
import sys
import math
import json
import logging
import tkinter as tk
from tkinter import filedialog
from player import Player, CHARACTER_CLASSES
from quest_system import QuestManager
from sound_manager import sound_manager
import game_context as gc

logger = logging.getLogger("JunkRPG")


class PlayerCountScreen:
    def __init__(self):
        self.ui_elements = []
        self.level_file = None
        self.campaign_file = None
        self.mode_buttons = []
        self.selected_mode = "survival"

    def initialize_screen(self, level_file=None, campaign_file=None):
        self.level_file = level_file
        self.campaign_file = campaign_file
        self.selected_mode = "survival"  # Reset to default
        gc.manager.clear_and_reset()
        level_name = os.path.basename(campaign_file or level_file) if (campaign_file or level_file) else "Unknown"

        # Mode selection
        mode_label = UILabel(pygame.Rect(0, 50, gc.WINDOW_WIDTH, 30), "Select Game Mode", gc.manager, anchors={'centerx': 'centerx'})
        survival_btn = UIButton(pygame.Rect((gc.WINDOW_WIDTH - 420) // 2, 90, 200, 40), "Survival Mode", gc.manager)
        creative_btn = UIButton(pygame.Rect((gc.WINDOW_WIDTH - 420) // 2 + 220, 90, 200, 40), "Creative Mode", gc.manager)
        mode_desc = UILabel(pygame.Rect(0, 140, gc.WINDOW_WIDTH, 25), "Survival: Normal gameplay | Creative: Test with card browser", gc.manager, anchors={'centerx': 'centerx'})

        # Player count selection
        self.ui_elements = [
            UILabel(pygame.Rect(0, 190, gc.WINDOW_WIDTH, 50), "Select Number of Players", gc.manager, anchors={'centerx': 'centerx'}),
            UILabel(pygame.Rect(0, 240, gc.WINDOW_WIDTH, 30), f"Level: {level_name}", gc.manager, anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect((gc.WINDOW_WIDTH - 200) // 2, 290, 200, 50), "1 Player", gc.manager),
            UIButton(pygame.Rect((gc.WINDOW_WIDTH - 200) // 2, 360, 200, 50), "2 Players", gc.manager),
            UIButton(pygame.Rect((gc.WINDOW_WIDTH - 200) // 2, 430, 200, 50), "3 Players", gc.manager),
            UIButton(pygame.Rect((gc.WINDOW_WIDTH - 200) // 2, 500, 200, 50), "4 Players", gc.manager),
            UIButton(pygame.Rect((gc.WINDOW_WIDTH - 200) // 2, 600, 200, 50), "Back", gc.manager)
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
                gc.game.game_mode = self.selected_mode
                gc.game.current_screen = "character_creation"
                gc.character_creation_screen.initialize_screen(level_file=self.level_file, campaign_file=self.campaign_file)
            elif event.ui_element == self.ui_elements[3]:  # 2 Players
                gc.game.game_mode = self.selected_mode
                gc.game.current_screen = "multiplayer_character_creation"
                gc.multiplayer_character_creation_screen.initialize_screen(level_file=self.level_file, campaign_file=self.campaign_file, num_players=2)
            elif event.ui_element == self.ui_elements[4]:  # 3 Players
                gc.game.game_mode = self.selected_mode
                gc.game.current_screen = "multiplayer_character_creation"
                gc.multiplayer_character_creation_screen.initialize_screen(level_file=self.level_file, campaign_file=self.campaign_file, num_players=3)
            elif event.ui_element == self.ui_elements[5]:  # 4 Players
                gc.game.game_mode = self.selected_mode
                gc.game.current_screen = "multiplayer_character_creation"
                gc.multiplayer_character_creation_screen.initialize_screen(level_file=self.level_file, campaign_file=self.campaign_file, num_players=4)
            elif event.ui_element == self.ui_elements[6]:  # Back
                gc.game.current_screen = "main_menu"
                gc.main_menu.initialize_buttons()

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


# Main Menu screen (updated to include Load Campaign)
class MainMenu:
    def __init__(self):
        self.ui_elements = []
        self.title_font = pygame.font.Font(None, 80)
        self.subtitle_font = pygame.font.Font(None, 28)
        self.ver_font = pygame.font.Font(None, 18)
        self.initialize_buttons()

    def initialize_buttons(self):
        gc.manager.clear_and_reset()
        btn_x = (gc.WINDOW_WIDTH - 200) // 2
        self.ui_elements = [
            UIButton(pygame.Rect(btn_x, 200, 200, 50), "New Campaign", gc.manager),
            UIButton(pygame.Rect(btn_x, 270, 200, 50), "Load Campaign", gc.manager),
            UIButton(pygame.Rect(btn_x, 340, 200, 50), "Load Level", gc.manager),
            UIButton(pygame.Rect(btn_x, 410, 200, 50), "Load Game", gc.manager),
            UIButton(pygame.Rect(btn_x, 480, 200, 50), "Multiplayer", gc.manager),
            UIButton(pygame.Rect(btn_x, 550, 200, 50), "Settings", gc.manager),
            UIButton(pygame.Rect(btn_x, 620, 200, 50), "Quit", gc.manager)
        ]

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            text = event.ui_element.text
            if text == "New Campaign":
                gc.game.current_screen = "character_creation"
                gc.character_creation_screen.initialize_screen()
            elif text == "Load Campaign":
                root = tk.Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(initialdir="campaigns", filetypes=[("JSON files", "*.json")])
                root.destroy()
                if file_path:
                    gc.game.current_screen = "player_count"
                    gc.player_count_screen.initialize_screen(campaign_file=file_path)
                else:
                    logger.debug("No campaign file selected")
            elif text == "Load Level":
                root = tk.Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(initialdir="levels", filetypes=[("JSON files", "*.json")])
                root.destroy()
                if file_path:
                    gc.game.current_screen = "player_count"
                    gc.player_count_screen.initialize_screen(level_file=file_path)
                else:
                    logger.debug("No level file selected")
            elif text == "Load Game":
                gc.game.current_screen = "save_load"
                gc.save_load_screen.initialize_screen(mode="load")
            elif text == "Multiplayer":
                gc.game.current_screen = "multiplayer_character_creation"
                gc.multiplayer_character_creation_screen.initialize_screen()
            elif text == "Settings":
                gc.game.current_screen = "settings"
                gc.settings_screen.initialize_screen()
            elif text == "Quit":
                pygame.quit()
                sys.exit()

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        # Decorative background hex pattern
        hex_s = 40
        pat_color = (30, 30, 70)
        for pr in range(0, gc.WINDOW_HEIGHT + hex_s * 2, int(hex_s * 1.732)):
            for pc in range(0, gc.WINDOW_WIDTH + hex_s * 2, int(hex_s * 1.5)):
                offset = hex_s * 0.866 if (pc // int(hex_s * 1.5)) % 2 else 0
                pts = [(pc + hex_s * math.cos(math.radians(60 * i)),
                        pr + offset + hex_s * math.sin(math.radians(60 * i))) for i in range(6)]
                pygame.draw.polygon(gc.screen, pat_color, pts, 1)
        # Styled title
        title_text = "Junk RPG"
        shadow = self.title_font.render(title_text, True, (10, 10, 30))
        title = self.title_font.render(title_text, True, (200, 180, 120))
        tr = title.get_rect(centerx=gc.WINDOW_WIDTH // 2, y=50)
        gc.screen.blit(shadow, tr.move(3, 3))
        gc.screen.blit(title, tr)
        # Decorative line under title
        line_y = tr.bottom + 10
        pygame.draw.line(gc.screen, (120, 100, 60), (gc.WINDOW_WIDTH // 2 - 140, line_y), (gc.WINDOW_WIDTH // 2 + 140, line_y), 1)
        # Subtitle
        sub = self.subtitle_font.render("A Card-Based Tactical Adventure", True, (120, 120, 160))
        sr = sub.get_rect(centerx=gc.WINDOW_WIDTH // 2, y=line_y + 8)
        gc.screen.blit(sub, sr)
        # Version text
        ver = self.ver_font.render("v0.34", True, (80, 80, 110))
        gc.screen.blit(ver, (gc.WINDOW_WIDTH - 60, gc.WINDOW_HEIGHT - 30))
        gc.manager.draw_ui(gc.screen)


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
        self.load_custom_button = None
        gc.manager.clear_and_reset()
        self.ui_elements = [
            UILabel(pygame.Rect(0, 30, gc.WINDOW_WIDTH, 40), "Enter Your Name", gc.manager, anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect(20, 20, 100, 50), "Back", gc.manager)
        ]
        self.name_entry = UITextEntryLine(pygame.Rect((gc.WINDOW_WIDTH - 250) // 2, 70, 250, 40), gc.manager, placeholder_text="Player Name")
        self.ui_elements.append(self.name_entry)
        self.ui_elements.append(UILabel(pygame.Rect(0, 120, gc.WINDOW_WIDTH, 40), "Choose Your Class", gc.manager, anchors={'centerx': 'centerx'}))
        self.class_buttons = []
        for i, (class_name, stats) in enumerate(CHARACTER_CLASSES.items()):
            y_pos = 170 + i * 100
            button = UIButton(pygame.Rect((gc.WINDOW_WIDTH - 200) // 2, y_pos, 200, 50), class_name, gc.manager)
            self.class_buttons.append((button, class_name))
            self.ui_elements.append(button)
            desc = f"{stats['hp']} HP, {stats['movement']} Movement, {stats['projectile_range']} Range, " \
                   f"{list(stats['attacks'].keys())[0]} ({list(stats['attacks'].values())[0]} dmg), " \
                   f"{list(stats['attacks'].keys())[1]} ({list(stats['attacks'].values())[1]} dmg), {stats['special_attack']}"
            self.ui_elements.append(UILabel(pygame.Rect((gc.WINDOW_WIDTH - 600) // 2, y_pos + 60, 600, 30), desc, gc.manager))

        # "Load Custom Character" button below class buttons
        custom_y = 170 + len(CHARACTER_CLASSES) * 100 + 10
        self.load_custom_button = UIButton(pygame.Rect((gc.WINDOW_WIDTH - 250) // 2, custom_y, 250, 50), "Load Custom Character", gc.manager)
        self.ui_elements.append(self.load_custom_button)

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.ui_elements[1]:
                gc.game.current_screen = "main_menu"
                gc.main_menu.initialize_buttons()
            elif self.load_custom_button and event.ui_element == self.load_custom_button:
                self._load_custom_character()
            else:
                for button, class_name in self.class_buttons:
                    if event.ui_element == button:
                        gc.game.player = Player(class_name)
                        entered_name = self.name_entry.get_text().strip() if self.name_entry else ""
                        gc.game.player.name = entered_name if entered_name else class_name
                        gc.game.current_screen = "game"
                        gc.game_screen.start_new_game(level_file=self.level_file, campaign_file=self.campaign_file)
                        break

    def _load_custom_character(self):
        """Open file dialog to load a custom character JSON and start the game."""
        characters_dir = os.path.join(os.path.dirname(__file__), "characters")
        if not os.path.isdir(characters_dir):
            characters_dir = os.path.dirname(__file__)
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file_path = filedialog.askopenfilename(
            title="Load Custom Character",
            initialdir=characters_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        root.destroy()
        if not file_path:
            return
        try:
            with open(file_path, 'r') as f:
                custom_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Error loading character file: {e}")
            return
        gc.game.player = Player("Custom", custom_data=custom_data)
        # Override name with entry field if provided, otherwise use character file name
        entered_name = self.name_entry.get_text().strip() if self.name_entry else ""
        if entered_name:
            gc.game.player.name = entered_name
        elif not gc.game.player.name:
            gc.game.player.name = custom_data.get("name", "Custom")
        gc.game.current_screen = "game"
        gc.game_screen.start_new_game(level_file=self.level_file, campaign_file=self.campaign_file)

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


# Multiplayer Character Creation Screen (2-4 player local)
class MultiplayerCharacterCreationScreen:
    def __init__(self):
        self.ui_elements = []
        self.class_buttons = []
        self.current_player_selecting = 1
        self.num_players = 2
        self.player_selections = []  # List of {"class": ..., "name": ...}
        self.level_file = None
        self.campaign_file = None
        self.name_entry = None

    def initialize_screen(self, level_file=None, campaign_file=None, num_players=2):
        self.level_file = level_file
        self.campaign_file = campaign_file
        self.num_players = num_players
        self.current_player_selecting = 1
        self.player_selections = []
        gc.manager.clear_and_reset()
        self._build_selection_ui()

    def _build_selection_ui(self):
        """Build the class selection UI for the current player."""
        gc.manager.clear_and_reset()
        player_label = f"Player {self.current_player_selecting} of {self.num_players}: Enter Name & Choose Class"
        idx = self.current_player_selecting - 1
        color_name = gc.PLAYER_COLOR_NAMES[idx] if idx < len(gc.PLAYER_COLOR_NAMES) else "Unknown"
        color_hint = f"({color_name})"
        self.ui_elements = [
            UILabel(pygame.Rect(0, 30, gc.WINDOW_WIDTH, 40), player_label, gc.manager, anchors={'centerx': 'centerx'}),
            UILabel(pygame.Rect(0, 70, gc.WINDOW_WIDTH, 30), color_hint, gc.manager, anchors={'centerx': 'centerx'}),
            UIButton(pygame.Rect(20, 20, 100, 50), "Back", gc.manager)
        ]
        placeholder = f"Player {self.current_player_selecting} Name"
        self.name_entry = UITextEntryLine(pygame.Rect((gc.WINDOW_WIDTH - 250) // 2, 105, 250, 40), gc.manager, placeholder_text=placeholder)
        self.ui_elements.append(self.name_entry)
        self.class_buttons = []
        for i, (class_name, stats) in enumerate(CHARACTER_CLASSES.items()):
            y_pos = 170 + i * 100
            button = UIButton(pygame.Rect((gc.WINDOW_WIDTH - 200) // 2, y_pos, 200, 50), class_name, gc.manager)
            self.class_buttons.append((button, class_name))
            self.ui_elements.append(button)
            desc = f"{stats['hp']} HP, {stats['movement']} Movement, {stats['projectile_range']} Range, " \
                   f"{list(stats['attacks'].keys())[0]} ({list(stats['attacks'].values())[0]} dmg), " \
                   f"{list(stats['attacks'].keys())[1]} ({list(stats['attacks'].values())[1]} dmg), {stats['special_attack']}"
            self.ui_elements.append(UILabel(pygame.Rect((gc.WINDOW_WIDTH - 600) // 2, y_pos + 60, 600, 30), desc, gc.manager))

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.ui_elements[2]:  # Back button
                if self.current_player_selecting > 1:
                    # Go back to previous player selection
                    self.current_player_selecting -= 1
                    self.player_selections.pop()
                    self._build_selection_ui()
                else:
                    gc.game.current_screen = "main_menu"
                    gc.main_menu.initialize_buttons()
            else:
                for button, class_name in self.class_buttons:
                    if event.ui_element == button:
                        entered_name = self.name_entry.get_text().strip() if self.name_entry else ""
                        player_name = entered_name if entered_name else f"Player {self.current_player_selecting}"
                        self.player_selections.append({"class": class_name, "name": player_name})

                        if self.current_player_selecting < self.num_players:
                            # Move to next player selection
                            self.current_player_selecting += 1
                            self._build_selection_ui()
                        else:
                            # All players selected - start the game
                            self._start_multiplayer_game(self.player_selections)
                        break

    def _start_multiplayer_game(self, player_selections):
        """Create all players and start the multiplayer game."""
        players = []
        for i, sel in enumerate(player_selections):
            p = Player(sel["class"])
            p.name = sel["name"]
            p.player_number = i + 1
            p.player_color = gc.PLAYER_COLORS[i] if i < len(gc.PLAYER_COLORS) else (200, 200, 200)
            p.party = []
            players.append(p)

        # Set up multiplayer mode
        gc.game.multiplayer_mode = True
        gc.game.players = players
        gc.game.current_player_index = 0
        gc.game.player = players[0]  # For backwards compatibility

        # Create per-player quest managers
        gc.game.quest_managers = [QuestManager(gc.game.card_manager) for _ in players]

        # Start the game
        gc.game.current_screen = "game"
        gc.game_screen.start_new_game_multiplayer(level_file=self.level_file, campaign_file=self.campaign_file)

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


# Settings screen
class SettingsScreen:
    def __init__(self):
        self.ui_elements = []
        self.sound_toggle = None
        self.speed_dropdown = None
        self.autosave_dropdown = None

    def initialize_screen(self):
        gc.manager.clear_and_reset()
        self.ui_elements = []
        col_x = (gc.WINDOW_WIDTH - 400) // 2
        y = 120

        # Title
        self.ui_elements.append(
            UILabel(pygame.Rect(0, 50, gc.WINDOW_WIDTH, 50), "Settings", gc.manager, anchors={'centerx': 'centerx'})
        )

        # Back button
        back_btn = UIButton(pygame.Rect(20, 20, 200, 50), "Back to Main Menu", gc.manager)
        self.ui_elements.append(back_btn)

        # Sound toggle
        self.ui_elements.append(
            UILabel(pygame.Rect(col_x, y, 200, 30), "Sound Effects:", gc.manager)
        )
        sound_text = "ON" if sound_manager.enabled else "OFF"
        self.sound_toggle = UIButton(pygame.Rect(col_x + 210, y, 100, 30), sound_text, gc.manager)
        self.ui_elements.append(self.sound_toggle)
        y += 60

        # Animation speed
        self.ui_elements.append(
            UILabel(pygame.Rect(col_x, y, 200, 30), "Animation Speed:", gc.manager)
        )
        current_delay = getattr(gc.game_screen, 'turn_action_delay', 500)
        speed_options = ["Slow (800ms)", "Normal (500ms)", "Fast (300ms)", "Instant (100ms)"]
        if current_delay >= 700:
            default = speed_options[0]
        elif current_delay >= 400:
            default = speed_options[1]
        elif current_delay >= 200:
            default = speed_options[2]
        else:
            default = speed_options[3]
        self.speed_dropdown = UIDropDownMenu(speed_options, default,
            pygame.Rect(col_x + 210, y, 190, 30), gc.manager)
        self.ui_elements.append(self.speed_dropdown)
        y += 60

        # Autosave frequency
        self.ui_elements.append(
            UILabel(pygame.Rect(col_x, y, 200, 30), "Autosave Every:", gc.manager)
        )
        autosave_options = ["3 turns", "5 turns", "10 turns", "Off"]
        current_freq = getattr(gc.game, '_autosave_frequency', 5)
        if current_freq <= 0:
            default_as = autosave_options[3]
        elif current_freq <= 3:
            default_as = autosave_options[0]
        elif current_freq <= 5:
            default_as = autosave_options[1]
        else:
            default_as = autosave_options[2]
        self.autosave_dropdown = UIDropDownMenu(autosave_options, default_as,
            pygame.Rect(col_x + 210, y, 190, 30), gc.manager)
        self.ui_elements.append(self.autosave_dropdown)

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.ui_elements[1]:
                gc.game.current_screen = "main_menu"
                gc.main_menu.initialize_buttons()
            elif event.ui_element == self.sound_toggle:
                sound_manager.enabled = not sound_manager.enabled
                self.sound_toggle.set_text("ON" if sound_manager.enabled else "OFF")
        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            if event.ui_element == self.speed_dropdown:
                text = event.text
                delay_map = {"Slow (800ms)": 800, "Normal (500ms)": 500, "Fast (300ms)": 300, "Instant (100ms)": 100}
                gc.game_screen.turn_action_delay = delay_map.get(text, 500)
            elif event.ui_element == self.autosave_dropdown:
                text = event.text
                freq_map = {"3 turns": 3, "5 turns": 5, "10 turns": 10, "Off": 0}
                gc.game._autosave_frequency = freq_map.get(text, 5)

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)

import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UILabel, UISelectionList, UIDropDownMenu
import sys
import logging
from sound_manager import sound_manager
from save_system import SaveManager
import game_context as gc

logger = logging.getLogger("JunkRPG")


class GameSettingsScreen:
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
        back_btn = UIButton(pygame.Rect(20, 20, 200, 50), "Return to Game", gc.manager)
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
        current_delay = gc.game_screen.turn_action_delay if hasattr(gc.game_screen, 'turn_action_delay') else 500
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
                gc.game.current_screen = "pause_menu"
                gc.pause_menu_screen.initialize_screen()
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


class PauseMenuScreen:
    """In-game pause menu with Continue, Save, Load, Restart, Settings, Main Menu, Quit."""

    def __init__(self):
        self.ui_elements = []
        self.buttons = {}
        self.game_snapshot = None  # Screenshot of the game behind the overlay
        self.title_font = pygame.font.Font(None, 64)

    def initialize_screen(self):
        # Capture current screen as background snapshot
        self.game_snapshot = gc.screen.copy()
        gc.manager.clear_and_reset()
        self.ui_elements = []
        self.buttons = {}

        # Title
        self.ui_elements.append(
            UILabel(pygame.Rect(0, 80, gc.WINDOW_WIDTH, 60), "Paused", gc.manager,
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
        start_y = (gc.WINDOW_HEIGHT - total_height) // 2 + 40
        btn_x = (gc.WINDOW_WIDTH - btn_width) // 2

        for i, label in enumerate(button_labels):
            btn = UIButton(
                pygame.Rect(btn_x, start_y + i * btn_spacing, btn_width, btn_height),
                label, gc.manager
            )
            self.buttons[label] = btn
            self.ui_elements.append(btn)

    def handle_event(self, event):
        # ESC returns to game (same as Continue)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            gc.game.current_screen = "game"
            gc.game_screen.initialize_screen()
            return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            text = event.ui_element.text
            if text == "Continue":
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
            elif text == "Save Game":
                is_player_turn = gc.game_screen._is_player_phase()
                if is_player_turn:
                    success, result = gc.game_screen.save_manager.save_game(
                        gc.game, gc.game_screen, save_type="manual", save_label="Manual Save"
                    )
                    msg = "Game saved successfully." if success else f"Save failed: {result}"
                    gc.game.current_screen = "confirmation"
                    gc.confirmation_screen.initialize_screen(msg, options=["OK"],
                        callback=lambda _: self._return_to_pause())
                else:
                    gc.game.current_screen = "confirmation"
                    gc.confirmation_screen.initialize_screen(
                        "Can only save during your turn.", options=["OK"],
                        callback=lambda _: self._return_to_pause())
            elif text == "Load Game":
                gc.game.current_screen = "confirmation"
                gc.confirmation_screen.initialize_screen(
                    "Unsaved progress will be lost. Continue?",
                    options=["Yes", "No"],
                    callback=self._handle_load_confirm)
            elif text == "Restart Level":
                gc.game.current_screen = "confirmation"
                gc.confirmation_screen.initialize_screen(
                    "Are you sure you want to restart?",
                    options=["Yes", "No"],
                    callback=gc.game_screen._handle_restart_confirm)
            elif text == "Settings":
                gc.game.current_screen = "game_settings"
                gc.game_settings_screen.initialize_screen()
            elif text == "Main Menu":
                gc.game.current_screen = "confirmation"
                gc.confirmation_screen.initialize_screen(
                    "Return to main menu? Unsaved progress will be lost.",
                    options=["Yes", "No"],
                    callback=self._handle_main_menu_confirm)
            elif text == "Quit Game":
                gc.game.current_screen = "confirmation"
                gc.confirmation_screen.initialize_screen(
                    "Are you sure you want to quit?",
                    options=["Yes", "No"],
                    callback=self._handle_quit_confirm)

    def _return_to_pause(self):
        gc.game.current_screen = "pause_menu"
        self.initialize_screen()

    def _handle_load_confirm(self, choice):
        if choice == "Yes":
            gc.game.current_screen = "save_load"
            gc.save_load_screen.initialize_screen(mode="load")
        else:
            self._return_to_pause()

    def _handle_main_menu_confirm(self, choice):
        if choice == "Yes":
            gc.game.current_screen = "main_menu"
            gc.main_menu.initialize_buttons()
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
            gc.screen.blit(self.game_snapshot, (0, 0))
            overlay = pygame.Surface((gc.WINDOW_WIDTH, gc.WINDOW_HEIGHT), pygame.SRCALPHA)
            overlay.fill((10, 10, 30, 180))
            gc.screen.blit(overlay, (0, 0))
        else:
            gc.screen.fill(gc.DARK_CHARCOAL)
        # Draw title text manually with style
        title_shadow = self.title_font.render("Paused", True, (10, 10, 30))
        title_surf = self.title_font.render("Paused", True, (200, 180, 120))
        title_rect = title_surf.get_rect(centerx=gc.WINDOW_WIDTH // 2, y=80)
        gc.screen.blit(title_shadow, title_rect.move(2, 2))
        gc.screen.blit(title_surf, title_rect)
        # Decorative line under title
        line_y = title_rect.bottom + 8
        pygame.draw.line(gc.screen, (200, 180, 120, 100), (gc.WINDOW_WIDTH // 2 - 100, line_y), (gc.WINDOW_WIDTH // 2 + 100, line_y), 1)
        gc.manager.draw_ui(gc.screen)


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
        gc.manager.clear_and_reset()
        self.ui_elements = []
        self.option_buttons = []

        # Message
        msg_width = min(600, gc.WINDOW_WIDTH - 100)
        msg_height = 80
        msg_x = (gc.WINDOW_WIDTH - msg_width) // 2
        msg_y = gc.WINDOW_HEIGHT // 3
        self.ui_elements.append(
            UITextBox(f"<font color='#FFFFFF' size=4>{message}</font>",
                      pygame.Rect(msg_x, msg_y, msg_width, msg_height), gc.manager)
        )

        # Option buttons
        btn_width = 180
        total_width = len(options) * btn_width + (len(options) - 1) * 20
        start_x = (gc.WINDOW_WIDTH - total_width) // 2
        btn_y = msg_y + msg_height + 30

        for i, option_text in enumerate(options):
            btn = UIButton(
                pygame.Rect(start_x + i * (btn_width + 20), btn_y, btn_width, 50),
                option_text, gc.manager
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
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


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
        gc.manager.clear_and_reset()
        self.ui_elements = []

        title_text = "Load Game" if mode == "load" else "Save Game"
        self.ui_elements.append(
            UILabel(pygame.Rect(0, 30, gc.WINDOW_WIDTH, 50), title_text,
                    gc.manager, anchors={'centerx': 'centerx'})
        )

        # Refresh saves list
        self.saves = self.save_manager.get_all_saves()
        display_items = [self.save_manager.format_save_display(s) for s in self.saves]

        # Save list
        list_width = gc.WINDOW_WIDTH // 2
        list_height = gc.WINDOW_HEIGHT - 250
        list_x = (gc.WINDOW_WIDTH - list_width - 320) // 2
        list_y = 90

        self.save_list = UISelectionList(
            pygame.Rect(list_x, list_y, list_width, list_height),
            display_items, gc.manager,
            allow_multi_select=False
        )
        self.ui_elements.append(self.save_list)

        # Detail box
        detail_x = list_x + list_width + 20
        detail_width = 300
        self.detail_box = UITextBox(
            "<font color='#AAAAAA'>Select a save to view details.</font>",
            pygame.Rect(detail_x, list_y, detail_width, list_height - 60),
            gc.manager
        )
        self.ui_elements.append(self.detail_box)

        # Buttons at bottom
        btn_y = list_y + list_height + 15
        btn_width = 150

        self.load_button = UIButton(
            pygame.Rect(list_x, btn_y, btn_width, 45),
            "Load", gc.manager
        )
        self.ui_elements.append(self.load_button)

        self.delete_button = UIButton(
            pygame.Rect(list_x + btn_width + 20, btn_y, btn_width, 45),
            "Delete", gc.manager
        )
        self.ui_elements.append(self.delete_button)

        self.back_button = UIButton(
            pygame.Rect(list_x + (btn_width + 20) * 2, btn_y, btn_width, 45),
            "Back", gc.manager
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
                if gc.game_screen.game_started:
                    gc.game.current_screen = "game"
                    gc.game_screen.initialize_screen()
                else:
                    gc.game.current_screen = "main_menu"
                    gc.main_menu.initialize_buttons()

            elif event.ui_element == self.load_button:
                if self.selected_index >= 0 and self.selected_index < len(self.saves):
                    save_info = self.saves[self.selected_index]
                    save_data = self.save_manager.load_save_file(save_info["filepath"])
                    if save_data:
                        gc.game.current_screen = "game"
                        gc.game_screen.load_from_save(save_data)

            elif event.ui_element == self.delete_button:
                if self.selected_index >= 0 and self.selected_index < len(self.saves):
                    save_info = self.saves[self.selected_index]
                    self.save_manager.delete_save(save_info["filepath"])
                    # Refresh
                    self.initialize_screen(mode=self.mode)

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)

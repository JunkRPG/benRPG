import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UILabel
import random
import logging
from save_system import SaveManager
import game_context as gc

logger = logging.getLogger("JunkRPG")


class TeleportPartyScreen:
    """Screen for selecting which party NPCs to bring through a teleport pad."""

    def __init__(self):
        self.ui_elements = []
        self.npc_buttons = []
        self.npc_selected = []
        self.npcs = []
        self.confirm_btn = None
        self.cancel_btn = None
        self.callback = None
        self.cancel_callback = None

    def initialize_screen(self, allied_npcs, callback, cancel_callback):
        self.callback = callback
        self.cancel_callback = cancel_callback
        self.npcs = allied_npcs
        self.npc_selected = [True] * len(allied_npcs)
        gc.manager.clear_and_reset()
        self.ui_elements = []
        self.npc_buttons = []

        msg_width = min(600, gc.WINDOW_WIDTH - 100)
        msg_x = (gc.WINDOW_WIDTH - msg_width) // 2
        msg_y = gc.WINDOW_HEIGHT // 5

        self.ui_elements.append(
            UITextBox(f"<font color='#FFFFFF' size=4>Select party members to bring:</font>",
                      pygame.Rect(msg_x, msg_y, msg_width, 50), gc.manager))

        y_offset = msg_y + 60
        for i, npc in enumerate(allied_npcs):
            btn = UIButton(
                pygame.Rect(msg_x + 20, y_offset + i * 40, msg_width - 40, 35),
                f"[X] {npc.name} (HP: {npc.hp}/{npc.max_hp})", gc.manager)
            self.npc_buttons.append(btn)
            self.ui_elements.append(btn)

        btn_y = y_offset + len(allied_npcs) * 40 + 20
        self.confirm_btn = UIButton(
            pygame.Rect(msg_x + 50, btn_y, 200, 50), "Teleport", gc.manager)
        self.cancel_btn = UIButton(
            pygame.Rect(msg_x + msg_width - 250, btn_y, 200, 50), "Cancel", gc.manager)
        self.ui_elements.extend([self.confirm_btn, self.cancel_btn])

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            for i, btn in enumerate(self.npc_buttons):
                if event.ui_element == btn:
                    self.npc_selected[i] = not self.npc_selected[i]
                    npc = self.npcs[i]
                    marker = "[X]" if self.npc_selected[i] else "[ ]"
                    btn.set_text(f"{marker} {npc.name} (HP: {npc.hp}/{npc.max_hp})")
                    return
            if event.ui_element == self.confirm_btn:
                selected = [npc for npc, sel in zip(self.npcs, self.npc_selected) if sel]
                if self.callback:
                    self.callback(selected)
            elif event.ui_element == self.cancel_btn:
                if self.cancel_callback:
                    self.cancel_callback()

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


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
        gc.manager.clear_and_reset()
        message = random.choice(self.humorous_messages)
        btn_x = (gc.WINDOW_WIDTH - 200) // 2
        btn_y = gc.WINDOW_HEIGHT // 2

        self.ui_elements = [
            UILabel(pygame.Rect(0, gc.WINDOW_HEIGHT // 4, gc.WINDOW_WIDTH, 50), message, gc.manager, anchors={'centerx': 'centerx'}),
        ]

        # "Load Last Save" button (above Restart Level)
        save_mgr = SaveManager()
        latest_save = save_mgr.get_most_recent_save()
        if latest_save:
            self.load_save_button = UIButton(
                pygame.Rect(btn_x, btn_y, 200, 50), "Load Last Save", gc.manager
            )
            self.ui_elements.append(self.load_save_button)
            btn_y += 70
        else:
            self.load_save_button = None

        restart_btn = UIButton(pygame.Rect(btn_x, btn_y, 200, 50), "Restart Level", gc.manager)
        self.ui_elements.append(restart_btn)
        btn_y += 70
        menu_btn = UIButton(pygame.Rect(btn_x, btn_y, 200, 50), "Main Menu", gc.manager)
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
                        gc.game.current_screen = "game"
                        gc.game_screen.load_from_save(save_data)
            elif text == "Restart Level":
                gc.game.current_screen = "game"
                gc.game_screen.start_new_game(level_file=gc.game_screen.current_level_file,
                                              campaign_file=gc.game_screen.campaign_file if gc.game_screen.campaign else None)
                gc.game_screen.initialize_screen()
            elif text == "Main Menu":
                gc.game.current_screen = "main_menu"
                gc.main_menu.initialize_buttons()

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)

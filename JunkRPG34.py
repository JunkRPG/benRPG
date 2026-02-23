import pygame
import sys
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UIWindow, UISelectionList, UIDropDownMenu, UILabel, UIPanel, UITextEntryLine
from pygame import display, event
import math
import os
import json
import datetime
import random
import copy
import logging
from collections import deque
import tkinter as tk
from tkinter import filedialog
from player import Player, CHARACTER_CLASSES  # Import Player from player.py
from unit import Unit      # Import Unit from unit.py
from hexgrid import HexGrid, DIRECTIONS  # Import HexGrid from hexgrid.py
from inventory_card import InventoryCard
from quest_system import QuestManager
from instance_system import InstanceManager
from transition_system import TransitionManager
from deck_utils import resolve_deck_path
from card_utils import load_card, load_card_index
from terrain_config import TERRAIN_CONFIG, get_terrain_color
from save_system import SaveManager
from sound_manager import sound_manager, play_card_acquired_sound
import game_context as gc
from game_context import (DARK_CHARCOAL, GRAY, YELLOW, GOLDEN_YELLOW, BLUE, RED,
                          DARK_RED_ALPHA, WHITE, GREEN, LIGHT_GREEN, PURPLE, ORANGE,
                          PLAYER_COLORS, PLAYER_COLOR_NAMES, PLAYER_COLOR_HEX,
                          MOVE_SPEED, ATTACK_FLASH_DURATION,
                          add_card_to_player, _check_builder_wood_perk)
from screens.card_manager import CardManager
from screens.menu_screens import (MainMenu, PlayerCountScreen, CharacterCreationScreen,
                                  MultiplayerCharacterCreationScreen, SettingsScreen)
from screens.pause_screens import (PauseMenuScreen, GameSettingsScreen,
                                   ConfirmationScreen, SaveLoadScreen)
from screens.game_overlay_screens import TeleportPartyScreen, DefeatScreen
from screens.party_screens import PartyScreen, QuestScreen, SkillsScreen
from screens.crafting_screen import CraftingScreen
from screens.location_screens import LocationScreen, RecruitmentScreen, CardGivingScreen
from screens.inventory_screens import InventoryScreen, CardBrowserScreen, NpcBrowserScreen
from screens.tabbed_menu_screen import TabbedMenuScreen

logger = logging.getLogger("JunkRPG")

# Initialize Pygame and Pygame-GUI
pygame.init()

# Set up fullscreen display
display_info = pygame.display.Info()
WINDOW_WIDTH = display_info.current_w
WINDOW_HEIGHT = display_info.current_h
screen = display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
display.set_caption("Junk RPG")

# Initialize UIManager
manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT), "theme.json")

# Populate game_context with pygame display objects
gc.screen = screen
gc.manager = manager
gc.WINDOW_WIDTH = WINDOW_WIDTH
gc.WINDOW_HEIGHT = WINDOW_HEIGHT

# Directories
os.makedirs("cards", exist_ok=True)
os.makedirs("levels", exist_ok=True)
os.makedirs("campaigns", exist_ok=True)
os.makedirs("saves", exist_ok=True)
INDEX_FILE = "cards/card_index.json"
if not os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, 'w') as f:
        json.dump({}, f)


def _load_custom_font(path, size, fallback_name="Arial", fallback_bold=False):
    """Load a TTF font file with SysFont fallback."""
    try:
        return pygame.font.Font(path, size)
    except Exception:
        return pygame.font.SysFont(fallback_name, size, bold=fallback_bold)


class PlayerInfoPanelProxy:
    """Drop-in replacement for UITextBox that just flags the panel dirty."""
    def __init__(self, game_screen):
        self._game_screen = game_screen
    def set_text(self, html_text):
        self._game_screen._player_panel_dirty = True
    def kill(self):
        pass
    def show(self):
        pass
    def hide(self):
        pass


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
        self.defensive_hex_options = []  # Valid hexes for defensive posture selection
        self.defend_button = None        # Defend button on left panel
        self.leave_tower_button = None   # Leave Tower button (shown when manning)
        self.toggle_weapon_button = None # Toggle tower/personal weapon mode
        self.selected_skill = None  # Currently selected skill for use
        self.skill_buttons = []     # List of (button, skill_card) tuples
        self.skills_button = None   # Skills menu button
        self.special_attack_button = None  # Special attack button
        self.super_attack_button = None    # Super attack button (charged)
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
        # Unit turn preview system
        self.unit_preview_phase = None    # None | "range" | "selection"
        self.unit_preview_start = 0       # pygame.time.get_ticks() when phase began
        self.unit_preview_plan = None     # plan_turn() result dict
        self.unit_preview_unit = None     # the unit being previewed
        # Pending location screen (show after movement animation completes)
        self.pending_location = None  # {"card": loc_card, "pos": hex_pos, "hex_grid": hex_grid}
        # Pending defeat screen (show after death animation completes)
        self.pending_defeat = False
        # Pending unit removals - defer grid removal until attack animations finish
        self.pending_defeats = []
        self.defeat_notifications = []  # [(name, timestamp), ...]
        self.turn_banner = None  # (label, color_tuple, timestamp) or None
        self._ammo_banner = None  # (label, color_rgb, start_timestamp) or None
        self._pending_advance_after_banner = False  # Wait for banner to finish before advancing
        # Location defense autopan queue
        self._loc_defense_queue = []       # [(pos, loc_data), ...]
        self._loc_defense_active = False   # True while processing queue
        self._loc_defense_wait_until = None  # pygame.time.get_ticks() deadline for animation wait
        self._loc_defense_shot_queue = None   # Per-NPC staggered shot queue
        self.current_location_hex = None  # (row, col) if player is on a location
        # Building/placement mode
        self.placement_mode = False
        self.placement_card = None  # The location card being placed
        # Multiplayer transition target cycle: 0=P1, 1=P2, 2=Both
        self.transition_target_cycle = 0
        # Turn cycle counter for autosave timing
        self.turn_cycle_count = 0
        # Boss encounter tracking
        self.boss_encounter_phase = 0  # 0=not started, 1=initial boss active, 2=phase-2 bosses spawned, 3=completed
        self.boss_encounter_phase2_tags = []  # ["phase2_boss_0", ...]
        self.level_completed = False
        # Save manager
        self.save_manager = SaveManager()
        # Autopan smooth camera state
        self.autopan_active = False
        self.autopan_start_x = 0.0
        self.autopan_start_y = 0.0
        self.autopan_target_x = 0.0
        self.autopan_target_y = 0.0
        self.autopan_start_time = 0
        self.autopan_duration = 0
        self.autopan_callback = None
        # Teleport pad state
        self.pending_teleport = None  # Dict with pad/destination info when awaiting confirmation
        self._level_state_cache = {}  # In-memory cache of level state keyed by level file path
        # Equipment toolbar (bottom of screen)
        self.equip_toolbar_buttons = []    # 6 UIButtons for Melee/Proj/Acc/Tool/Action/Items slots
        self.equip_action_tool = None      # Reference to the equipped tool providing the current action
        self.equip_popup_open = False      # Whether a popup is showing
        self.equip_popup_slot = None       # "melee"/"projectile"/"tool"/"accessory"
        self.equip_popup_buttons = []      # List of (UIButton, slot_type, data) tuples
        # Items button / consumable targeting mode
        self.selected_item = None          # Consumable card selected for use
        self.item_targeting_mode = False   # Whether in item targeting mode
        # Behavior target selection mode (party screen assigns follow/attack targets)
        self.behavior_target_type = None         # "follow_target" or "attack_target"
        self.behavior_target_npc_card_id = None  # card_id of NPC being configured
        # Action choice popup (shown when multiple actions available on a unit)
        self.action_choice_open = False
        self.action_choice_buttons = []    # List of (button, action_type, data) tuples
        self.action_choice_target = None   # The unit being targeted
        # Body move/place mode
        self.body_move_unit = None         # Dead unit being moved/picked up
        self.body_place_card = None        # InventoryCard of body being placed from inventory
        # Junk pile move/place mode
        self.junk_pile_move_unit = None    # Junk pile unit being moved/picked up
        self.junk_pile_place_card = None   # InventoryCard of junk pile being placed from inventory
        # Right panel layout (computed in initialize_screen)
        self.rp_width = 234
        self.rp_pad = 10
        self.rp_x = 0
        self.rp_inner_w = 0
        self.rp_pi_y = 0
        self.rp_stats_y = 0
        self.rp_menu_y = 0
        self.rp_height = 0
        self.rp_header_font = pygame.font.SysFont("Candara", 20, bold=True)
        self.rp_body_font = pygame.font.SysFont("Candara", 15, bold=True)
        self.rp_body_bold = pygame.font.SysFont("Candara", 16, bold=True)
        self.rp_icon_font = pygame.font.SysFont("Segoe UI Symbol", 15)
        self._player_panel_surface = None
        self._player_panel_height = 175
        self._player_panel_dirty = True
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
        # === Dialogue popup state ===
        self.dialogue_active = False
        self.dialogue_text = ""
        self.dialogue_speaker = ""
        # === Event banner overlay state ===
        self.event_banner_active = False
        self.event_banner_type = ""        # "transition" or "instance"
        self.event_banner_start_time = 0
        self.event_banner_phase = "main"   # "main" or "result"
        # Transition banner data
        self.event_transition_card = None
        self.event_transition_all_outcomes = []
        self.event_transition_selected_index = -1
        self.event_transition_result_text = ""
        self.event_transition_target_label = ""
        # Instance banner data
        self.event_instance_card = None
        self.event_instance_outcome_text = ""
        self.event_instance_needs_choice = False
        self.event_instance_choices = []
        self.event_instance_target_name = ""
        self.event_instance_target_player = None
        self.event_instance_result_text = ""
        # Banner buttons (manually drawn, not pygame-gui)
        self.event_banner_buttons = []     # [{"rect": Rect, "label": str, "action": str|int}, ...]
        self.event_banner_hovered_btn = None
        # Cached fonts for banner rendering
        self.event_title_font = pygame.font.SysFont("Arial", 36, bold=True)
        self.event_subtitle_font = pygame.font.SysFont("Arial", 28, bold=True)
        self.event_desc_font = pygame.font.SysFont("Arial", 22)
        self.event_outcome_font = pygame.font.SysFont("Arial", 24)
        self.event_result_font = pygame.font.SysFont("Arial", 30, bold=True)
        self.event_btn_font = pygame.font.SysFont("Arial", 22, bold=True)
        self.event_small_font = pygame.font.SysFont("Arial", 18)
        # Cached fonts for dialogue, banners, and popups
        self.dialogue_speaker_font = pygame.font.SysFont("arial", 22, bold=True)
        self.dialogue_text_font = pygame.font.SysFont("arial", 18)
        self.dialogue_hint_font = pygame.font.SysFont("arial", 14)
        self.defeat_font = pygame.font.SysFont("Arial", 36, bold=True)
        self.turn_banner_font = pygame.font.SysFont("Arial", 46, bold=True)
        self.ammo_banner_font = pygame.font.SysFont("Arial", 36, bold=True)
        self.action_popup_header_font = pygame.font.SysFont("freesansbold", 15, bold=True)
        # In-memory hex attempt tracking (replaces temp/ directory files)
        self._hex_attempts = {}  # {card_id: set of (row, col) tuples}

    # === Dialogue popup ===

    def _draw_dialogue(self):
        """Draw a modal dialogue overlay from a Messenger NPC."""
        if not self.dialogue_active:
            return
        # Dim background
        dim = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        screen.blit(dim, (0, 0))

        # Dialogue box (centered, 700x250)
        box_w, box_h = 700, 250
        box_x = (WINDOW_WIDTH - box_w) // 2
        box_y = (WINDOW_HEIGHT - box_h) // 2
        pygame.draw.rect(screen, (40, 30, 20), (box_x, box_y, box_w, box_h), border_radius=12)
        pygame.draw.rect(screen, (180, 150, 100), (box_x, box_y, box_w, box_h), 3, border_radius=12)

        # Speaker name
        speaker_surf = self.dialogue_speaker_font.render(self.dialogue_speaker, True, (255, 220, 150))
        screen.blit(speaker_surf, (box_x + 20, box_y + 15))

        # Dialogue text (word-wrapped)
        words = self.dialogue_text.split()
        lines = []
        current_line = ""
        for word in words:
            test = current_line + (" " if current_line else "") + word
            if self.dialogue_text_font.size(test)[0] < box_w - 40:
                current_line = test
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        y = box_y + 50
        for line in lines:
            surf = self.dialogue_text_font.render(line, True, (230, 230, 220))
            screen.blit(surf, (box_x + 20, y))
            y += 26

        # Dismiss hint
        hint = self.dialogue_hint_font.render("Click or press any key to continue", True, (150, 150, 140))
        screen.blit(hint, (box_x + box_w // 2 - hint.get_width() // 2, box_y + box_h - 30))

    # === Event banner overlay helpers ===

    def _wrap_text(self, text, font, max_width):
        """Word-wrap text to fit within max_width pixels. Returns list of lines."""
        words = text.split()
        if not words:
            return [""]
        lines = []
        current_line = words[0]
        for word in words[1:]:
            test = current_line + " " + word
            if font.size(test)[0] <= max_width:
                current_line = test
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
        return lines

    def _clear_event_banner(self):
        """Reset all event banner state to defaults."""
        self.event_banner_active = False
        self.event_banner_type = ""
        self.event_banner_start_time = 0
        self.event_banner_phase = "main"
        self.event_transition_card = None
        self.event_transition_all_outcomes = []
        self.event_transition_selected_index = -1
        self.event_transition_result_text = ""
        self.event_transition_target_label = ""
        self.event_instance_card = None
        self.event_instance_outcome_text = ""
        self.event_instance_needs_choice = False
        self.event_instance_choices = []
        self.event_instance_target_name = ""
        self.event_instance_target_player = None
        self.event_instance_result_text = ""
        self.event_banner_buttons = []
        self.event_banner_hovered_btn = None

    def _show_transition_banner(self, transition_card, all_outcomes, selected_index, result_text, target_label=""):
        """Activate the transition event banner overlay."""
        self.event_banner_active = True
        self.event_banner_type = "transition"
        self.event_banner_start_time = pygame.time.get_ticks()
        self.event_banner_phase = "main"
        self.event_transition_card = transition_card
        self.event_transition_all_outcomes = all_outcomes
        self.event_transition_selected_index = selected_index
        self.event_transition_result_text = result_text
        self.event_transition_target_label = target_label
        self._build_event_banner_buttons()

    def _build_event_banner_buttons(self):
        """Compute button rects for the current event banner state."""
        self.event_banner_buttons = []
        btn_h = 50
        # Center-screen Y for choice buttons
        center_btn_y = WINDOW_HEIGHT - 120

        # Position single OK/Continue buttons just above the End Turn button
        if hasattr(self, 'end_turn_button') and self.end_turn_button:
            et_rect = self.end_turn_button.rect
            single_btn_y = et_rect.top - 8 - btn_h
            single_btn_cx = et_rect.centerx
        else:
            single_btn_y = center_btn_y
            single_btn_cx = WINDOW_WIDTH // 2

        if self.event_banner_type == "transition":
            # Single "OK" button, above End Turn
            btn_w = 220
            btn_x = single_btn_cx - btn_w // 2
            self.event_banner_buttons.append({
                "rect": pygame.Rect(btn_x, single_btn_y, btn_w, btn_h),
                "label": "OK",
                "action": "ok_transition"
            })

        elif self.event_banner_type == "instance":
            if self.event_banner_phase == "result":
                # Result phase: single Continue button, above End Turn
                btn_w = 220
                btn_x = single_btn_cx - btn_w // 2
                self.event_banner_buttons.append({
                    "rect": pygame.Rect(btn_x, single_btn_y, btn_w, btn_h),
                    "label": "Continue",
                    "action": "continue_instance"
                })
            elif self.event_instance_needs_choice and self.event_instance_choices:
                # Choice buttons stacked vertically upward from center_btn_y (stay centered)
                btn_w = 360
                num_choices = len(self.event_instance_choices)
                total_h = num_choices * (btn_h + 8) - 8
                start_y = center_btn_y - total_h + btn_h
                btn_x = (WINDOW_WIDTH - btn_w) // 2
                for i, choice in enumerate(self.event_instance_choices):
                    choice_name = choice.get("name", f"Choice {i+1}")
                    risk = choice.get("risk", 0)
                    risk_text = f" (Risk: {int(risk * 100)}%)" if risk > 0 else ""
                    self.event_banner_buttons.append({
                        "rect": pygame.Rect(btn_x, start_y + i * (btn_h + 8), btn_w, btn_h),
                        "label": f"{choice_name}{risk_text}",
                        "action": i
                    })
            else:
                # No choice: single Continue button, above End Turn
                btn_w = 220
                btn_x = single_btn_cx - btn_w // 2
                self.event_banner_buttons.append({
                    "rect": pygame.Rect(btn_x, single_btn_y, btn_w, btn_h),
                    "label": "Continue",
                    "action": "continue_instance"
                })

    def draw_event_banner(self):
        """Draw the event banner overlay on top of the game board."""
        if not self.event_banner_active:
            return

        now = pygame.time.get_ticks()

        # 1. Dim overlay
        dim = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 100))
        screen.blit(dim, (0, 0))

        # 2. Text content
        if self.event_banner_type == "transition":
            self._draw_transition_banner_text()
        elif self.event_banner_type == "instance":
            self._draw_instance_banner_text()

        # 3. Buttons with pulsing borders
        pulse = math.sin(now / 400.0)
        border_alpha = int(120 + (255 - 120) * (pulse * 0.5 + 0.5))

        for i, btn_info in enumerate(self.event_banner_buttons):
            rect = btn_info["rect"]
            is_hovered = (i == self.event_banner_hovered_btn)

            # Button background
            btn_bg = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            if is_hovered:
                btn_bg.fill((60, 60, 80, 220))
            else:
                btn_bg.fill((20, 20, 35, 200))
            screen.blit(btn_bg, rect.topleft)

            # Pulsing border
            if is_hovered:
                border_color = (220, 200, 80, 255)
            else:
                border_color = (180, 160, 60, border_alpha)
            # Draw border on a SRCALPHA surface for alpha support
            border_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(border_surf, border_color, (0, 0, rect.width, rect.height), 2)
            screen.blit(border_surf, rect.topleft)

            # Button label
            label_surf = self.event_btn_font.render(btn_info["label"], True, (255, 255, 255))
            lw, lh = label_surf.get_size()
            screen.blit(label_surf, (rect.x + (rect.width - lw) // 2, rect.y + (rect.height - lh) // 2))

        # 4. Bouncing arrow after 4 seconds
        elapsed = now - self.event_banner_start_time
        if elapsed > 4000 and self.event_banner_buttons:
            last_btn = self.event_banner_buttons[-1]["rect"]
            arrow_x_base = last_btn.right + 20
            arrow_y = last_btn.y + last_btn.height // 2
            offset_x = int(10 * math.sin(now / 300.0))
            # Draw left-pointing triangle
            arrow_pts = [
                (arrow_x_base + offset_x, arrow_y),
                (arrow_x_base + 14 + offset_x, arrow_y - 8),
                (arrow_x_base + 14 + offset_x, arrow_y + 8),
            ]
            pygame.draw.polygon(screen, (180, 160, 60), arrow_pts)

    def _draw_transition_banner_text(self):
        """Draw transition event text content in the upper portion of the screen."""
        card = self.event_transition_card
        cx = WINDOW_WIDTH // 2
        max_w = 700
        y = 60

        # Title
        state_text = " (Night)" if card.current_state == 2 else " (Day)" if card.states == 2 else ""
        title = f"{card.get_current_name()}{state_text}"
        title_surf = self.event_title_font.render(title, True, (255, 255, 255))
        shadow_surf = self.event_title_font.render(title, True, (0, 0, 0))
        tw = title_surf.get_width()
        screen.blit(shadow_surf, (cx - tw // 2 + 2, y + 2))
        screen.blit(title_surf, (cx - tw // 2, y))
        y += 50

        # Target label
        if self.event_transition_target_label:
            label = self.event_transition_target_label
            if label == "Both Players":
                color = (255, 215, 0)
            elif game.multiplayer_mode and len(game.players) >= 2 and label == (game.players[1].name or "Player 2"):
                color = (68, 136, 255)
            else:
                color = (68, 255, 68)
            target_surf = self.event_subtitle_font.render(f"Affecting: {label}", True, color)
            screen.blit(target_surf, (cx - target_surf.get_width() // 2, y))
            y += 40

        # Description
        desc = card.get_current_description()
        desc_lines = self._wrap_text(desc, self.event_desc_font, max_w)
        for line in desc_lines:
            line_surf = self.event_desc_font.render(line, True, (170, 170, 170))
            screen.blit(line_surf, (cx - line_surf.get_width() // 2, y))
            y += 28
        y += 15

        # Creative mode: show all outcomes with probabilities
        if game.game_mode == "creative":
            header_surf = self.event_small_font.render("Possible Outcomes:", True, (200, 200, 200))
            screen.blit(header_surf, (cx - header_surf.get_width() // 2, y))
            y += 25
            for i, outcome in enumerate(self.event_transition_all_outcomes):
                prob = outcome.get("probability", 0)
                prob_pct = int(prob * 100)
                outcome_type = outcome.get("type", "none").replace("_", " ").title()
                outcome_text = outcome.get("text", "Something happens...")
                is_selected = (i == self.event_transition_selected_index)
                if is_selected:
                    color = (0, 255, 0)
                    prefix = ">>> "
                    suffix = " <<<"
                else:
                    color = (136, 136, 136)
                    prefix = "    "
                    suffix = ""
                line = f"{prefix}[{prob_pct}%] {outcome_type}: {outcome_text}{suffix}"
                line_surf = self.event_small_font.render(line, True, color)
                screen.blit(line_surf, (cx - max_w // 2, y))
                y += 22
            y += 15

        # Result text
        if game.game_mode == "creative":
            rh_surf = self.event_small_font.render("Result:", True, (200, 200, 200))
            screen.blit(rh_surf, (cx - rh_surf.get_width() // 2, y))
            y += 25

        result_lines = self._wrap_text(self.event_transition_result_text, self.event_result_font, max_w)
        for line in result_lines:
            line_surf = self.event_result_font.render(line, True, (255, 255, 0))
            screen.blit(line_surf, (cx - line_surf.get_width() // 2, y))
            y += 36

    def _draw_instance_banner_text(self):
        """Draw instance event text content in the upper portion of the screen."""
        card = self.event_instance_card
        cx = WINDOW_WIDTH // 2
        max_w = 700
        y = 60

        # Target label
        if self.event_instance_target_name:
            name = self.event_instance_target_name
            if game.multiplayer_mode and len(game.players) >= 2 and name == (game.players[1].name or "Player 2"):
                color = (68, 136, 255)
            else:
                color = (68, 255, 68)
            target_surf = self.event_subtitle_font.render(f"Affecting: {name}", True, color)
            screen.blit(target_surf, (cx - target_surf.get_width() // 2, y))
            y += 40

        # Title
        title = f"EVENT: {card.name}"
        title_surf = self.event_title_font.render(title, True, (255, 255, 255))
        shadow_surf = self.event_title_font.render(title, True, (0, 0, 0))
        tw = title_surf.get_width()
        screen.blit(shadow_surf, (cx - tw // 2 + 2, y + 2))
        screen.blit(title_surf, (cx - tw // 2, y))
        y += 50

        # Description
        desc = card.description if hasattr(card, 'description') else ""
        if desc:
            desc_lines = self._wrap_text(desc, self.event_desc_font, max_w)
            for line in desc_lines:
                line_surf = self.event_desc_font.render(line, True, (255, 255, 255))
                screen.blit(line_surf, (cx - line_surf.get_width() // 2, y))
                y += 28
            y += 10

        if self.event_banner_phase == "result":
            # Show result in green
            result_lines = self._wrap_text(self.event_instance_result_text, self.event_result_font, max_w)
            for line in result_lines:
                line_surf = self.event_result_font.render(line, True, (0, 255, 0))
                screen.blit(line_surf, (cx - line_surf.get_width() // 2, y))
                y += 36
        else:
            # Show outcome text in yellow
            if self.event_instance_outcome_text:
                outcome_lines = self._wrap_text(self.event_instance_outcome_text, self.event_outcome_font, max_w)
                for line in outcome_lines:
                    line_surf = self.event_outcome_font.render(line, True, (255, 255, 0))
                    screen.blit(line_surf, (cx - line_surf.get_width() // 2, y))
                    y += 30

    def _handle_event_banner(self, event):
        """Handle input events while the event banner is active."""
        if event.type == pygame.MOUSEMOTION:
            pos = event.pos
            self.event_banner_hovered_btn = None
            for i, btn_info in enumerate(self.event_banner_buttons):
                if btn_info["rect"].collidepoint(pos):
                    self.event_banner_hovered_btn = i
                    break

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            for btn_info in self.event_banner_buttons:
                if btn_info["rect"].collidepoint(pos):
                    self._handle_event_banner_click(btn_info["action"])
                    return

        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            # Press single button with keyboard
            if len(self.event_banner_buttons) == 1:
                self._handle_event_banner_click(self.event_banner_buttons[0]["action"])

    def _handle_event_banner_click(self, action):
        """Dispatch a banner button click based on its action."""
        if action == "ok_transition":
            # Check for chained instance event
            if game.instance_manager.pending_instance:
                instance_card = game.instance_manager.pending_instance
                target_player = game.instance_manager.pending_instance_player
                self._clear_event_banner()
                self.show_instance_event(instance_card, target_player)
                return

            # No pending instance — clear banner and resume
            self._clear_event_banner()
            self.player_info_label.set_text(self.get_player_info())
            self.resume_after_transition()

        elif action == "continue_instance":
            self._clear_event_banner()
            game.instance_manager.clear_pending()
            self.player_info_label.set_text(self.get_player_info())
            self.resume_after_instance()

        elif isinstance(action, int):
            # Player chose a choice option
            target = self.event_instance_target_player or game.current_player
            result = game.instance_manager.resolve_player_choice(action, self.hex_grid, target)
            self.event_banner_phase = "result"
            self.event_instance_result_text = result
            self.event_banner_start_time = pygame.time.get_ticks()
            self._build_event_banner_buttons()

    # ── Autopan smooth camera helpers ──────────────────────────────────

    def _ease_in_out_cubic(self, t):
        """Cubic ease-in-out: smooth acceleration and deceleration."""
        if t < 0.5:
            return 4.0 * t * t * t
        return 0.5 * (2.0 * t - 2.0) ** 3 + 1.0

    def _is_hex_in_viewport_center(self, row, col):
        """Return True if (row, col) is within the central 50% of the viewport."""
        pixel_x = self.hex_grid.view_offset_x + col * self.hex_grid.hex_size * 1.5
        pixel_y = (self.hex_grid.view_offset_y + row * self.hex_grid.hex_size * 1.732
                   + (col % 2) * self.hex_grid.hex_size * 0.866)
        margin_x = WINDOW_WIDTH * 0.25
        margin_y = WINDOW_HEIGHT * 0.25
        return (margin_x <= pixel_x <= WINDOW_WIDTH - margin_x and
                margin_y <= pixel_y <= WINDOW_HEIGHT - margin_y)

    def _calculate_autopan_duration(self, dx, dy):
        """Scale pan duration with distance: short pans are gentle, long pans cap at 1200ms."""
        dist = math.sqrt(dx * dx + dy * dy)
        return max(350, min(1200, int(dist * 1.2)))

    def _start_autopan(self, row, col, callback=None):
        """Smoothly pan camera to center on hex (row, col). Fires callback when done."""
        if self._is_hex_in_viewport_center(row, col):
            # Already visible — skip pan
            if callback:
                callback()
            return
        # Target offset to center the hex on screen
        pixel_x = col * self.hex_grid.hex_size * 1.5
        pixel_y = row * self.hex_grid.hex_size * 1.732 + (col % 2) * self.hex_grid.hex_size * 0.866
        target_x = WINDOW_WIDTH / 2 - pixel_x
        target_y = WINDOW_HEIGHT / 2 - pixel_y
        dx = target_x - self.hex_grid.view_offset_x
        dy = target_y - self.hex_grid.view_offset_y
        if abs(dx) < 1 and abs(dy) < 1:
            # Already centered
            if callback:
                callback()
            return
        self.autopan_start_x = self.hex_grid.view_offset_x
        self.autopan_start_y = self.hex_grid.view_offset_y
        self.autopan_target_x = target_x
        self.autopan_target_y = target_y
        self.autopan_start_time = pygame.time.get_ticks()
        self.autopan_duration = self._calculate_autopan_duration(dx, dy)
        self.autopan_callback = callback
        self.autopan_active = True

    def _update_autopan(self):
        """Advance the autopan interpolation. Called every frame from draw()."""
        if not self.autopan_active:
            return
        elapsed = pygame.time.get_ticks() - self.autopan_start_time
        if elapsed >= self.autopan_duration:
            # Snap to final position
            self.hex_grid.view_offset_x = self.autopan_target_x
            self.hex_grid.view_offset_y = self.autopan_target_y
            self.autopan_active = False
            cb = self.autopan_callback
            self.autopan_callback = None
            if cb:
                cb()
            return
        t = elapsed / self.autopan_duration
        eased = self._ease_in_out_cubic(t)
        self.hex_grid.view_offset_x = self.autopan_start_x + (self.autopan_target_x - self.autopan_start_x) * eased
        self.hex_grid.view_offset_y = self.autopan_start_y + (self.autopan_target_y - self.autopan_start_y) * eased

    # ── End autopan helpers ─────────────────────────────────────────────

    def add_defeat_notification(self, name):
        self.defeat_notifications.append((name, pygame.time.get_ticks()))
        sound_manager.play("entity_defeated")

    def _get_banner_y(self):
        """Return y position for banners, just below the log panel."""
        if self.log_minimized:
            return 80   # just below minimized log (bottom ~73)
        else:
            return 190  # just below expanded log (bottom ~185)

    def draw_defeat_notifications(self):
        now = pygame.time.get_ticks()
        self.defeat_notifications = [(n, t) for n, t in self.defeat_notifications if now - t < 3000]
        if not self.defeat_notifications:
            return
        cx = WINDOW_WIDTH // 2
        start_y = self._get_banner_y()
        for i, (name, timestamp) in enumerate(self.defeat_notifications):
            elapsed = now - timestamp
            alpha = 255 if elapsed < 2000 else max(0, 255 - int(255 * (elapsed - 2000) / 1000))
            # Upward drift: float up 30px over the full duration
            drift_y = int(30 * elapsed / 3000)
            text = f"{name} defeated!"
            text_surf = self.defeat_font.render(text, True, (255, 215, 0))
            shadow_surf = self.defeat_font.render(text, True, (0, 0, 0))
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

    def show_turn_banner(self, label, hex_color):
        """Show a temporary turn phase banner. hex_color is like '#66DD66'."""
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        self.turn_banner = (label, (r, g, b), pygame.time.get_ticks())

    def draw_turn_banner(self):
        """Draw the current turn phase banner with fade-out."""
        if not self.turn_banner:
            return
        label, color, timestamp = self.turn_banner
        now = pygame.time.get_ticks()
        elapsed = now - timestamp
        duration = 2000  # Total duration in ms
        opaque_time = 1200  # Fully opaque portion
        if elapsed >= duration:
            self.turn_banner = None
            return
        if elapsed < opaque_time:
            alpha = 255
        else:
            alpha = max(0, 255 - int(255 * (elapsed - opaque_time) / (duration - opaque_time)))
        text_surf = self.turn_banner_font.render(label, True, color)
        shadow_surf = self.turn_banner_font.render(label, True, (10, 10, 30))
        tw, th = text_surf.get_size()
        bw, bh = tw + 60, th + 30
        cx = WINDOW_WIDTH // 2
        by = self._get_banner_y()
        banner = pygame.Surface((bw, bh), pygame.SRCALPHA)
        banner.fill((10, 10, 30, min(alpha, 200)))
        pygame.draw.rect(banner, (58, 58, 92, min(alpha, 160)), (0, 0, bw, bh), 1)
        banner.blit(shadow_surf, (32, 17))
        banner.blit(text_surf, (30, 15))
        banner.set_alpha(alpha)
        screen.blit(banner, (cx - bw // 2, by))

    def _check_ammo_runout_banner(self, player):
        """Check if player has a pending ammo runout and schedule the banner."""
        if player.ammo_runout_pending:
            delay = self.hex_grid.attack_anims.get_max_remaining_ms() if hasattr(self.hex_grid, 'attack_anims') else 0
            name = player.ammo_runout_pending
            self._ammo_banner = (f"{name} ran out!", (255, 170, 50), pygame.time.get_ticks() + delay)
            player.ammo_runout_pending = None
            self.rebuild_left_panel()  # Refresh toolbar to clear the emptied ammo slot

    def draw_ammo_banner(self):
        """Draw the ammo runout banner with fade-out."""
        if not self._ammo_banner:
            return
        label, color, start_time = self._ammo_banner
        now = pygame.time.get_ticks()
        # start_time may be in the future (delayed until animation finishes)
        if now < start_time:
            return
        elapsed = now - start_time
        duration = 2500
        opaque_time = 1500
        if elapsed >= duration:
            self._ammo_banner = None
            return
        if elapsed < opaque_time:
            alpha = 255
        else:
            alpha = max(0, 255 - int(255 * (elapsed - opaque_time) / (duration - opaque_time)))
        text_surf = self.ammo_banner_font.render(label, True, color)
        shadow_surf = self.ammo_banner_font.render(label, True, (10, 10, 30))
        tw, th = text_surf.get_size()
        bw, bh = tw + 40, th + 20
        cx = WINDOW_WIDTH // 2
        by = self._get_banner_y() + 60  # offset below turn banner
        banner = pygame.Surface((bw, bh), pygame.SRCALPHA)
        banner.fill((10, 10, 30, min(alpha, 200)))
        pygame.draw.rect(banner, (58, 58, 92, min(alpha, 160)), (0, 0, bw, bh), 1)
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
        self.unit_preview_phase = None
        self.unit_preview_plan = None
        self.unit_preview_unit = None
        self.pending_location = None
        self.pending_defeat = False
        self.pending_defeats = []
        self.defeat_notifications = []
        self.current_location_hex = None
        self.transition_target_cycle = 0
        self.selected_item = None
        self.item_targeting_mode = False
        self.action_choice_open = False
        self.action_choice_buttons = []
        self.action_choice_target = None
        self._clear_event_banner()
        self.autopan_active = False
        self.autopan_callback = None
        self._level_state_cache = {}
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
                logger.error(f"Error loading campaign file '{campaign_file}': {e}")
                self.hex_grid.place_unit(game.player, self.hex_grid.rows // 2, self.hex_grid.cols // 2)
                self.log.append("Failed to load campaign. Starting default level.")
        elif level_file:
            try:
                self.hex_grid.load_level(level_file, self.card_manager, game.player)
                self.log.append(f"Loaded level: {level_file}")
                # Read optional player/unit transition fields from level JSON
                try:
                    with open(level_file, 'r') as f:
                        level_data = json.load(f)
                    pt_card = level_data.get("player_transition_card")
                    if pt_card:
                        game.transition_manager.load_player_transition_card(pt_card)
                    ut_card = level_data.get("unit_transition_card")
                    if ut_card:
                        game.transition_manager.load_unit_transition_card(ut_card)
                    ut_chance = level_data.get("unit_transition_trigger_chance")
                    if ut_chance is not None:
                        game.transition_manager.set_unit_transition_trigger_chance(ut_chance)
                except Exception as e:
                    logger.error(f"Error reading transition fields from level: {e}")
            except Exception as e:
                logger.error(f"Error loading level '{level_file}': {e}")
                self.hex_grid.place_unit(game.player, self.hex_grid.rows // 2, self.hex_grid.cols // 2)
                self.log.append("Failed to load level. Starting default level.")
        else:
            self.hex_grid.place_unit(game.player, self.hex_grid.rows // 2, self.hex_grid.cols // 2)
            self.log.append("Started default level.")

        # Load starter kit from player object
        starter_kit = game.player.starting_kit
        for item in starter_kit:
            card_id = item.get("card_id")
            card_data = load_card(card_id)
            if card_data:
                inv_card = InventoryCard(card_data)
                if item.get("state", 1) == 2:
                    inv_card.current_state = 2
                game.player.inventory.append(inv_card)
                logger.debug(f"Added starter kit item: {inv_card.get_current_data().get('Name', card_id)}")
            else:
                logger.warning(f"Starter kit card '{card_id}' not found")

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
        game.player.moves_per_turn = game.player.base_moves_per_turn  # Reset Scout sprint
        game.player.action_used = False
        game.player.reset_double_attack()

        # Ensure all units are reset and active
        for unit in self.hex_grid.units:
            unit.hp = unit.max_hp
            unit.current_state = 1  # Reset to initial state if applicable
        
        self.hex_grid.active_turn_unit = game.player
        self.game_started = True
        self.turn_cycle_count = 0
        self._detect_boss_encounter()
        self.initialize_screen()
        # Autosave at level start
        self.save_manager.save_game(game, self, save_type="autosave", save_label="Level Start")

    def start_new_game_multiplayer(self, level_file=None, campaign_file=None):
        """Start a new multiplayer game with 2-4 players."""
        # Reset game state
        self.hex_grid = HexGrid(16, 24, 30, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.hex_grid.players = game.players  # Set players list on hex_grid
        self.hex_grid._num_players = len(game.players)
        self.current_level_file = level_file
        self.campaign_file = campaign_file
        self.log.clear()
        self.turn_phase = "multiplayer_player"  # Start with first player's turn
        game.current_player_index = 0
        self.is_player_turn = True
        self.hex_grid.game_over = False
        # Reset turn queue
        self.turn_queue = []
        self.current_acting_unit = None
        self.waiting_for_animation = False
        self.unit_preview_phase = None
        self.unit_preview_plan = None
        self.unit_preview_unit = None
        self.pending_location = None
        self.pending_defeat = False
        self.pending_defeats = []
        self.current_location_hex = None
        self.transition_target_cycle = 0
        self._clear_event_banner()
        self.autopan_active = False
        self.autopan_callback = None
        self._level_state_cache = {}

        # Reset instance manager and try to load test deck
        game.instance_manager = InstanceManager(self.card_manager, self.hex_grid)
        game.instance_manager.load_instance_deck("test_instance_deck.json")
        # Reset transition manager and try to load test transition card
        game.transition_manager = TransitionManager(self.card_manager, game.instance_manager)
        game.transition_manager.load_transition_card("test_transition_forest")

        # Load campaign, level, or use default placement
        player1 = game.players[0]

        if campaign_file:
            try:
                with open(campaign_file, 'r') as f:
                    self.campaign = json.load(f)
                self.load_campaign_level()
                self.log.append(f"Loaded campaign: {campaign_file}")
            except Exception as e:
                logger.error(f"Error loading campaign file '{campaign_file}': {e}")
                for i, player in enumerate(game.players):
                    self.hex_grid.place_unit(player, self.hex_grid.rows // 2 + i, self.hex_grid.cols // 2)
                self.log.append("Failed to load campaign. Starting default level.")
        elif level_file:
            try:
                # Load level with player 1 first
                self.hex_grid.load_level(level_file, self.card_manager, player1)
                self.log.append(f"Loaded level: {level_file}")
                # Place remaining players at adjacent accessible hexes
                placed_positions = {player1.position}
                for player in game.players[1:]:
                    placed = False
                    for existing_pos in list(placed_positions):
                        for n_row, n_col in self.hex_grid.get_neighbors(existing_pos[0], existing_pos[1]):
                            if (0 <= n_row < self.hex_grid.rows and 0 <= n_col < self.hex_grid.cols and
                                (n_row, n_col) not in placed_positions and
                                self.hex_grid.grid[n_row][n_col]["unit"] is None and
                                self.hex_grid.grid[n_row][n_col]["accessible"]):
                                self.hex_grid.place_unit(player, n_row, n_col)
                                placed_positions.add((n_row, n_col))
                                placed = True
                                break
                        if placed:
                            break
                    if not placed:
                        # Fallback: offset from center
                        fallback_row = self.hex_grid.rows // 2 + len(placed_positions)
                        fallback_col = self.hex_grid.cols // 2
                        self.hex_grid.place_unit(player, fallback_row, fallback_col)
                        placed_positions.add((fallback_row, fallback_col))
            except Exception as e:
                logger.error(f"Error loading level '{level_file}': {e}")
                # Place all players in default positions near center
                for i, player in enumerate(game.players):
                    self.hex_grid.place_unit(player, self.hex_grid.rows // 2 + i, self.hex_grid.cols // 2)
                self.log.append("Failed to load level. Starting default level.")
        else:
            # Default placement - cluster near center
            for i, player in enumerate(game.players):
                self.hex_grid.place_unit(player, self.hex_grid.rows // 2 + i, self.hex_grid.cols // 2)
            self.log.append(f"Started default level ({len(game.players)}-Player).")

        # Load starter kits for both players
        for player in game.players:
            starter_kit = player.starting_kit
            for item in starter_kit:
                card_id = item.get("card_id")
                card_data = load_card(card_id)
                if card_data:
                    inv_card = InventoryCard(card_data)
                    if item.get("state", 1) == 2:
                        inv_card.current_state = 2
                    player.inventory.append(inv_card)
                    logger.debug(f"Added starter kit item for {player.name}: {inv_card.get_current_data().get('Name', card_id)}")
                else:
                    logger.warning(f"Starter kit card '{card_id}' not found")

        # Reset both players
        for player in game.players:
            player.hp = player.max_hp
            player.melee_weapon = None
            player.projectile_weapon = None
            player.movement_used = False
            player.moves_per_turn = player.base_moves_per_turn  # Reset Scout sprint
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
        self._detect_boss_encounter()
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
            player1 = game.players[0] if game.multiplayer_mode and game.players else game.player
            # Clear manning state for all players before level transition
            all_lc_players = game.players if game.multiplayer_mode and game.players else [game.player]
            for p in all_lc_players:
                p.leave_manning()
            # Collect carry-over NPCs before loading new level (which clears the grid)
            carry_over_npcs = []
            carry_over_unit_objects = []
            for unit in self.hex_grid.units:
                if getattr(unit, 'carry_to_next_level', False) and unit.hp > 0:
                    carry_over_unit_objects.append(unit)
                    carry_over_npcs.append({
                        "card_id": unit.card_id,
                        "hp": unit.hp,
                        "max_hp": unit.max_hp,
                        "behavior_follow_target": unit.behavior_follow_target,
                        "carry_to_next_level": True,
                        "behavior_tree": list(unit.behavior_tree),
                    })
            # Snapshot current level state before leaving (carry-over NPCs excluded)
            self._snapshot_level_state(exclude_units=carry_over_unit_objects)
            # Set multiplayer state so load_level can filter multiplayer_only units
            num_players = len(game.players) if game.multiplayer_mode and game.players else 1
            self.hex_grid._num_players = num_players
            self.hex_grid.load_level(level_file, self.card_manager, player1)
            self.current_level_file = level_file
            # Restore cached state if revisiting this level
            self._restore_level_state(level_file)
            stage_name = stage_data.get("name", f"Stage {self.current_level_idx + 1}")
            self.log.append(f"Loaded {stage_name}: {os.path.basename(level_file)}")
            # Place remaining multiplayer players at adjacent hexes
            if game.multiplayer_mode and game.players and player1.position:
                placed_positions = {player1.position}
                for player in game.players[1:]:
                    placed = False
                    for existing_pos in list(placed_positions):
                        for n_row, n_col in self.hex_grid.get_neighbors(existing_pos[0], existing_pos[1]):
                            if (0 <= n_row < self.hex_grid.rows and 0 <= n_col < self.hex_grid.cols and
                                (n_row, n_col) not in placed_positions and
                                self.hex_grid.grid[n_row][n_col]["unit"] is None and
                                self.hex_grid.grid[n_row][n_col]["accessible"]):
                                self.hex_grid.place_unit(player, n_row, n_col)
                                placed_positions.add((n_row, n_col))
                                placed = True
                                break
                        if placed:
                            break
                    if not placed:
                        fallback_row = self.hex_grid.rows // 2 + len(placed_positions)
                        fallback_col = self.hex_grid.cols // 2
                        self.hex_grid.place_unit(player, fallback_row, fallback_col)
                        placed_positions.add((fallback_row, fallback_col))
            # Respawn carry-over NPCs near their follow targets
            if carry_over_npcs:
                all_players = game.players if game.multiplayer_mode and game.players else [game.player]
                for npc_info in carry_over_npcs:
                    card_data = load_card(npc_info["card_id"])
                    if not card_data:
                        continue
                    unit = Unit(card_data)
                    unit.hp = npc_info["hp"]
                    unit.max_hp = npc_info["max_hp"]
                    unit.carry_to_next_level = True
                    unit.behavior_tree = npc_info["behavior_tree"]
                    if npc_info.get("behavior_follow_target"):
                        unit.behavior_follow_target = npc_info["behavior_follow_target"]
                    # Find the follow target player to spawn near
                    spawn_near = player1
                    if unit.behavior_follow_target and unit.behavior_follow_target.startswith("player_"):
                        try:
                            idx = int(unit.behavior_follow_target.split("_")[1])
                            if idx < len(all_players) and all_players[idx].hp > 0:
                                spawn_near = all_players[idx]
                        except (ValueError, IndexError):
                            pass
                    # Find empty neighbor hex near the target player
                    placed = False
                    if spawn_near.position:
                        for n_row, n_col in self.hex_grid.get_neighbors(*spawn_near.position):
                            if (0 <= n_row < self.hex_grid.rows and 0 <= n_col < self.hex_grid.cols and
                                self.hex_grid.grid[n_row][n_col]["unit"] is None and
                                self.hex_grid.grid[n_row][n_col]["accessible"]):
                                self.hex_grid.place_unit(unit, n_row, n_col)
                                self.add_to_log(f"{unit.name} continues with the party")
                                placed = True
                                break
                    if not placed:
                        # Fallback: place near center
                        for r in range(self.hex_grid.rows):
                            for c in range(self.hex_grid.cols):
                                if (self.hex_grid.grid[r][c]["unit"] is None and
                                    self.hex_grid.grid[r][c]["accessible"]):
                                    self.hex_grid.place_unit(unit, r, c)
                                    self.add_to_log(f"{unit.name} continues with the party")
                                    placed = True
                                    break
                            if placed:
                                break
        except Exception as e:
            logger.error(f"Error loading level '{level_file}': {e}")
            import traceback
            traceback.print_exc()
            if game.multiplayer_mode and game.players:
                for i, player in enumerate(game.players):
                    self.hex_grid.place_unit(player, self.hex_grid.rows // 2 + i, self.hex_grid.cols // 2)
            else:
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
                logger.error(f"Error loading transition deck: {e}")

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

        # Load player transition deck
        player_transition_deck = deck_config.get("player_transition_deck", "")
        if player_transition_deck:
            try:
                deck_path = resolve_deck_path(player_transition_deck)
                if os.path.exists(deck_path):
                    with open(deck_path, 'r') as f:
                        deck_data = json.load(f)
                    card_ids = deck_data.get("cards", [])
                    if card_ids:
                        card_id = card_ids[0]
                        if game.transition_manager.load_player_transition_card(card_id):
                            self.log.append(f"Loaded player transition card: {game.transition_manager.player_transition.name}")
            except Exception as e:
                logger.error(f"Error loading player transition deck: {e}")

        # Load unit transition deck
        unit_transition_deck = deck_config.get("unit_transition_deck", "")
        if unit_transition_deck:
            try:
                deck_path = resolve_deck_path(unit_transition_deck)
                if os.path.exists(deck_path):
                    with open(deck_path, 'r') as f:
                        deck_data = json.load(f)
                    card_ids = deck_data.get("cards", [])
                    if card_ids:
                        card_id = card_ids[0]
                        if game.transition_manager.load_unit_transition_card(card_id):
                            self.log.append(f"Loaded unit transition card: {game.transition_manager.unit_transition.name}")
            except Exception as e:
                logger.error(f"Error loading unit transition deck: {e}")

    def _handle_delete_prev_saves(self, choice):
        """Callback for the level transition save deletion confirmation."""
        prev_level = getattr(self, '_pending_delete_level_saves', None)
        if choice == "Yes" and prev_level:
            deleted = self.save_manager.delete_saves_for_level(prev_level)
            self.add_to_log(f"Deleted {deleted} save(s) from previous level.")
        self._pending_delete_level_saves = None
        game.current_screen = "game"
        self.initialize_screen()

    def _show_campaign_complete(self):
        """Show a victory dialog instead of immediately dumping to main menu."""
        self.add_to_log("Campaign Completed!")
        game.current_screen = "confirmation"
        confirmation_screen.initialize_screen(
            "Campaign Complete!\nCongratulations, you have finished the campaign!",
            options=["Return to Main Menu"],
            callback=self._handle_campaign_complete
        )

    def _handle_campaign_complete(self, choice):
        """Callback for campaign complete dialog."""
        game.current_screen = "main_menu"
        main_menu.initialize_buttons()

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

        # Set up level/campaign info (cache is empty after load; teleporting will build it)
        self._level_state_cache = {}
        self.current_level_file = save_data.get("level_file")
        self.campaign_file = save_data.get("campaign_file")
        self.current_level_idx = save_data.get("current_level_idx", 0)
        self.campaign = save_data.get("campaign")

        # Restore game screen state
        gs = save_data.get("game_screen", {})
        loaded_phase = gs.get("turn_phase", "player")
        # Compatibility: old saves used "player1"/"player2", map to new unified phase
        if loaded_phase in ("player1", "player2"):
            loaded_phase = "multiplayer_player"
        self.turn_phase = loaded_phase
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
                logger.error(f"Error loading level for save restore: {e}")
        elif self.campaign_file and self.campaign:
            try:
                self.load_campaign_level()
            except Exception as e:
                logger.error(f"Error loading campaign level for save restore: {e}")

        # Clear auto-loaded units and player placement from level load
        for unit in list(self.hex_grid.units):
            if unit.position:
                self.hex_grid.grid[unit.position[0]][unit.position[1]]["unit"] = None
        self.hex_grid.units.clear()
        # Clear player(s) from grid (will re-place from save data)
        if multiplayer:
            for p in game.players:
                if p and p.position:
                    r, c = p.position
                    if 0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols:
                        self.hex_grid.grid[r][c]["unit"] = None
        else:
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

        # Restore party behavior overrides
        game.party_behavior_overrides = save_data.get("party_behavior_overrides", {})

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
        self.unit_preview_phase = None
        self.unit_preview_plan = None
        self.unit_preview_unit = None
        self.pending_location = None
        self.pending_defeat = False
        self.pending_defeats = []
        self.current_location_hex = None
        self.is_player_turn = self._is_player_phase()
        self.hex_grid.game_over = False

        # Set active turn unit
        if multiplayer:
            idx = game.current_player_index
            self.hex_grid.active_turn_unit = game.players[idx] if idx < len(game.players) else game.players[0]
        else:
            self.hex_grid.active_turn_unit = game.player

        # Restore boss encounter state from save
        self.boss_encounter_phase = save_data.get("boss_encounter_phase", 0)
        self.boss_encounter_phase2_tags = save_data.get("boss_encounter_phase2_tags", [])
        self.level_completed = save_data.get("level_completed", False)
        # If no saved boss state, detect from units
        if self.boss_encounter_phase == 0:
            self._detect_boss_encounter()

        self.game_started = True
        self.initialize_screen()
        self.add_to_log("Game loaded from save.")

    def _detect_boss_encounter(self):
        """Detect if the level has a boss encounter and set the initial phase."""
        if any(u.special_skill == "Repair" and u.repair_value > 0 for u in self.hex_grid.units):
            self.boss_encounter_phase = 1

    def _trigger_boss_phase_2(self):
        """All enemy spawn locations destroyed — spawn 3 phase-2 bosses."""
        if self.boss_encounter_phase >= 2:
            return  # Already triggered
        self.boss_encounter_phase = 2
        self.show_turn_banner("Boss Wave Incoming!", "#FF4444")

        boss_cards = [
            "beta_boss_repair_master",  # Repair boss
            "beta_boss_war_healer",     # Healer boss
            "beta_boss_war_chief",      # Attacker boss
        ]
        # Preferred spawn positions (right side, near spawn locations)
        preferred_positions = [(8, 35), (13, 37), (17, 35)]

        self.boss_encounter_phase2_tags = []
        for i, card_id in enumerate(boss_cards):
            card_data = load_card(card_id)
            if not card_data:
                continue
            boss = Unit(card_data)
            boss.boss_encounter_tag = f"phase2_boss_{i}"
            # Try preferred position, then find nearest empty hex
            pos = preferred_positions[i]
            placed = False
            if (0 <= pos[0] < self.hex_grid.rows and 0 <= pos[1] < self.hex_grid.cols
                    and self.hex_grid.grid[pos[0]][pos[1]]["unit"] is None
                    and self.hex_grid.grid[pos[0]][pos[1]]["accessible"]):
                self.hex_grid.place_unit(boss, pos[0], pos[1])
                placed = True
            if not placed:
                # Find nearest empty accessible hex
                for r in range(max(0, pos[0]-3), min(self.hex_grid.rows, pos[0]+4)):
                    for c in range(max(0, pos[1]-3), min(self.hex_grid.cols, pos[1]+4)):
                        if (self.hex_grid.grid[r][c]["unit"] is None
                                and self.hex_grid.grid[r][c]["accessible"]):
                            self.hex_grid.place_unit(boss, r, c)
                            placed = True
                            break
                    if placed:
                        break
            self.boss_encounter_phase2_tags.append(boss.boss_encounter_tag)
            self.add_to_log(f"{boss.name} has appeared!")

    def _check_boss_encounter_completion(self):
        """Check if all phase-2 bosses are defeated."""
        if self.boss_encounter_phase != 2 or not self.boss_encounter_phase2_tags:
            return
        alive_tags = {u.boss_encounter_tag for u in self.hex_grid.units
                      if u.boss_encounter_tag and u.hp > 0}
        if not any(tag in alive_tags for tag in self.boss_encounter_phase2_tags):
            self.boss_encounter_phase = 3
            self.level_completed = True
            self.show_turn_banner("Level Completed!", "#FFD700")
            self.add_to_log("All bosses defeated! Level Completed!")

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
                return len([u for u in self.hex_grid.units if u.allegiance == "Hostile" and u.hp > 0]) == 0

            elif comp_type == "defeat_boss":
                if target:
                    return not any(u.name == target and u.allegiance == "Hostile" and u.hp > 0 for u in self.hex_grid.units)
                # If no target specified, check for any boss-type units
                return len([u for u in self.hex_grid.units if u.allegiance == "Hostile" and u.hp > 0]) == 0

            elif comp_type == "collect_item":
                if target:
                    all_players = game.players if game.multiplayer_mode and game.players else [game.player]
                    return any(
                        any(card.get_current_data().get("Name") == target for card in p.inventory)
                        for p in all_players if p.hp > 0
                    )
                return False

            elif comp_type == "reach_location":
                if target:
                    # Find all location hexes matching the target name
                    target_positions = set()
                    for loc_hex in self.hex_grid.location_hexes:
                        pos = (loc_hex["row"], loc_hex["column"])
                        loc_data = self.hex_grid.location_data.get(pos)
                        if loc_data and loc_data.get("card"):
                            if loc_data["card"].get_current_data().get("Name") == target:
                                target_positions.add(pos)
                    if not target_positions:
                        return False
                    # All living players must be at a matching location
                    all_players = game.players if game.multiplayer_mode and game.players else [game.player]
                    living = [p for p in all_players if p.hp > 0]
                    return all(p.position in target_positions for p in living)
                return False

            elif comp_type == "survive_turns":
                if turn_limit:
                    return self.turn_cycle_count >= turn_limit
                # No turn limit specified — fall back to defeat all
                return len([u for u in self.hex_grid.units if u.allegiance == "Hostile" and u.hp > 0]) == 0

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
                    all_players = game.players if game.multiplayer_mode and game.players else [game.player]
                    return any(
                        any(card.get_current_data().get("Name") == item_name for card in p.inventory)
                        for p in all_players if p.hp > 0
                    )

        # Default: defeat all enemies
        return len([u for u in self.hex_grid.units if u.allegiance == "Hostile"]) == 0

    def _find_teleport_destination(self, pad_id):
        """Find the destination for a teleport pad from campaign teleport_links.
        Returns dict {dest_pad_id, dest_level_file, dest_stage_id, dest_name} or None."""
        if not self.campaign:
            return None
        for link in self.campaign.get("teleport_links", []):
            if link["pad_a"]["pad_id"] == pad_id:
                return {
                    "dest_pad_id": link["pad_b"]["pad_id"],
                    "dest_level_file": link["pad_b"]["level_file"],
                    "dest_stage_id": link["pad_b"]["stage_id"],
                    "dest_name": link.get("display_name_a", link["pad_b"]["level_file"])
                }
            elif link["pad_b"]["pad_id"] == pad_id:
                return {
                    "dest_pad_id": link["pad_a"]["pad_id"],
                    "dest_level_file": link["pad_a"]["level_file"],
                    "dest_stage_id": link["pad_a"]["stage_id"],
                    "dest_name": link.get("display_name_b", link["pad_a"]["level_file"])
                }
        return None

    def _handle_teleport_confirm(self, choice):
        """Callback for teleport pad confirmation dialog."""
        if choice == "Yes" and self.pending_teleport:
            # Collect alive allied NPCs from grid
            allied_npcs = [u for u in self.hex_grid.units
                          if u.allegiance == "Allied" and u.hp > 0
                          and not isinstance(u, Player)]
            if allied_npcs:
                game.current_screen = "teleport_party"
                teleport_party_screen.initialize_screen(
                    allied_npcs,
                    callback=self._execute_teleport,
                    cancel_callback=self._cancel_teleport
                )
            else:
                self._execute_teleport([])
        else:
            self._cancel_teleport()

    def _cancel_teleport(self):
        """Cancel a pending teleport — return player to pre-move position."""
        if self.pending_teleport:
            tp = self.pending_teleport
            player = tp["player"]
            pre_pos = tp["player_pre_pos"]
            # Move player back
            if player.position:
                r, c = player.position
                if self.hex_grid.grid[r][c]["unit"] is player:
                    self.hex_grid.grid[r][c]["unit"] = None
            player.position = pre_pos
            self.hex_grid.grid[pre_pos[0]][pre_pos[1]]["unit"] = player
            player.movement_used = False
            player.action_used = False
            self.pending_teleport = None
        game.current_screen = "game"
        self.initialize_screen()

    def _place_unit_near(self, unit, center_pos, placed_positions):
        """Place a unit on the nearest empty accessible hex near center_pos using BFS.
        Updates placed_positions set. Returns True if placed successfully."""
        visited = set()
        queue = deque([center_pos])
        visited.add(center_pos)
        while queue:
            pos = queue.popleft()
            row, col = pos
            if col % 2 == 0:
                offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1)]
            else:
                offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (1, -1), (1, 1)]
            for dr, dc in offsets:
                nr, nc = row + dr, col + dc
                if (nr, nc) in visited:
                    continue
                visited.add((nr, nc))
                if not (0 <= nr < self.hex_grid.rows and 0 <= nc < self.hex_grid.cols):
                    continue
                if ((nr, nc) not in placed_positions
                        and self.hex_grid.grid[nr][nc]["unit"] is None
                        and self.hex_grid.grid[nr][nc]["accessible"]):
                    self.hex_grid.place_unit(unit, nr, nc)
                    placed_positions.add((nr, nc))
                    return True
                queue.append((nr, nc))
        # Last resort: place at center_pos itself
        cr, cc = center_pos
        if self.hex_grid.grid[cr][cc]["unit"] is None:
            self.hex_grid.place_unit(unit, cr, cc)
            placed_positions.add(center_pos)
            return True
        self.add_to_log(f"Warning: Could not place {getattr(unit, 'name', 'unit')} near teleport pad")
        return False

    def _snapshot_level_state(self, exclude_units=None):
        """Snapshot current level's dynamic state into the cache before leaving.
        exclude_units: list of Unit objects that are travelling with the party
        (carry-over NPCs, teleport-selected NPCs) — they should NOT be cached."""
        if not self.current_level_file:
            return
        exclude_set = set(id(u) for u in (exclude_units or []))
        # Also exclude all player objects
        all_players = game.players if game.multiplayer_mode and game.players else [game.player]
        for p in all_players:
            exclude_set.add(id(p))
        # Temporarily remove excluded units so they aren't serialized
        original_units = self.hex_grid.units
        self.hex_grid.units = [u for u in original_units if id(u) not in exclude_set]
        try:
            units_data = self.save_manager._serialize_units(self.hex_grid)
            location_data = self.save_manager._serialize_location_data(self.hex_grid)
        finally:
            self.hex_grid.units = original_units
        self._level_state_cache[self.current_level_file] = {
            "units": units_data,
            "location_data": location_data,
            "card_drawing_hexes": copy.deepcopy(self.hex_grid.card_drawing_hexes),
            "turn_cycle_count": self.turn_cycle_count,
            "boss_encounter_phase": self.boss_encounter_phase,
            "boss_encounter_phase2_tags": list(self.boss_encounter_phase2_tags),
        }

    def _restore_level_state(self, level_file):
        """Restore a previously cached level state after load_level reloaded the JSON.
        Returns True if cache was found and restored, False if first visit (use JSON defaults)."""
        if level_file not in self._level_state_cache:
            return False
        cached = self._level_state_cache[level_file]
        # Clear auto-loaded units from grid (load_level already placed fresh units from JSON)
        # Keep player objects that load_level placed
        all_players = game.players if game.multiplayer_mode and game.players else [game.player]
        player_ids = set(id(p) for p in all_players)
        for unit in self.hex_grid.units:
            if id(unit) not in player_ids and unit.position:
                r, c = unit.position
                if (0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols
                        and self.hex_grid.grid[r][c]["unit"] is unit):
                    self.hex_grid.grid[r][c]["unit"] = None
        self.hex_grid.units = [u for u in self.hex_grid.units if id(u) in player_ids]
        # Rebuild cached units
        self.save_manager.rebuild_units(cached["units"], self.hex_grid)
        # Overlay cached location data
        self.save_manager.rebuild_location_data(cached["location_data"], self.hex_grid)
        # Restore other state
        if "card_drawing_hexes" in cached:
            self.hex_grid.card_drawing_hexes = cached["card_drawing_hexes"]
        self.turn_cycle_count = cached.get("turn_cycle_count", 0)
        self.boss_encounter_phase = cached.get("boss_encounter_phase", 0)
        self.boss_encounter_phase2_tags = cached.get("boss_encounter_phase2_tags", [])
        return True

    def _execute_teleport(self, selected_npcs):
        """Execute teleport: load destination level, place players and selected NPCs."""
        tp = self.pending_teleport
        if not tp:
            game.current_screen = "game"
            self.initialize_screen()
            return

        dest_level_file = tp["dest_level_file"]
        dest_pad_id = tp["dest_pad_id"]
        dest_stage_id = tp["dest_stage_id"]
        dest_name = tp["dest_name"]

        # Normalize level file path
        if not dest_level_file.startswith("levels"):
            dest_level_file = os.path.join("levels", dest_level_file)

        if not os.path.exists(dest_level_file):
            self.add_to_log(f"Destination level file not found: {dest_level_file}")
            self._cancel_teleport()
            return

        # Autosave before teleporting
        # Clear manning state for all players before teleport
        all_tp_players = game.players if game.multiplayer_mode and game.players else [game.player]
        for p in all_tp_players:
            p.leave_manning()

        self.save_manager.save_game(game, self, save_type="autosave", save_label="Pre-Teleport")

        # Collect selected NPC data
        carry_npcs = []
        for npc in selected_npcs:
            carry_npcs.append({
                "card_id": npc.card_id,
                "hp": npc.hp,
                "max_hp": npc.max_hp,
                "allegiance": npc.allegiance,
                "behavior_follow_target": npc.behavior_follow_target,
                "behavior_tree": list(npc.behavior_tree),
                "carry_to_next_level": getattr(npc, 'carry_to_next_level', False),
            })

        # Snapshot current level state before leaving (selected NPCs excluded from cache)
        self._snapshot_level_state(exclude_units=selected_npcs)

        # Find destination stage for deck config
        dest_stage = None
        stages = self.campaign.get("stages") or self.campaign.get("levels", [])
        for i, stage in enumerate(stages):
            if stage.get("stage_id") == dest_stage_id:
                dest_stage = stage
                self.current_level_idx = i
                break

        # Get all players
        all_players = game.players if game.multiplayer_mode and game.players else [game.player]
        player1 = all_players[0]

        # Load the new level
        num_players = len(all_players)
        self.hex_grid._num_players = num_players
        self.hex_grid.load_level(dest_level_file, self.card_manager, player1)
        self.current_level_file = dest_level_file
        # Restore cached state if revisiting this level
        self._restore_level_state(dest_level_file)

        # Find destination pad position
        dest_pad_pos = None
        for pad in self.hex_grid.teleport_pads:
            if pad["pad_id"] == dest_pad_id:
                dest_pad_pos = (pad["row"], pad["column"])
                break

        if not dest_pad_pos:
            self.add_to_log("Destination teleport pad not found in level!")
            dest_pad_pos = player1.position or (self.hex_grid.rows // 2, self.hex_grid.cols // 2)

        # Place players on accessible neighbors of destination pad
        placed_positions = set()
        placed_positions.add(dest_pad_pos)  # Reserve the pad hex itself

        for player in all_players:
            if player.hp <= 0:
                continue
            # Clear old position if any
            if player.position:
                r, c = player.position
                if (0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols
                        and self.hex_grid.grid[r][c]["unit"] is player):
                    self.hex_grid.grid[r][c]["unit"] = None
                player.position = None
            self._place_unit_near(player, dest_pad_pos, placed_positions)

        # Spawn selected NPCs near their follow-target player
        for npc_info in carry_npcs:
            card_data = load_card(npc_info["card_id"])
            if not card_data:
                continue
            unit = Unit(card_data)
            unit.hp = npc_info["hp"]
            unit.max_hp = npc_info["max_hp"]
            unit.set_allegiance(npc_info["allegiance"])
            unit.behavior_tree = npc_info["behavior_tree"]
            if npc_info.get("behavior_follow_target"):
                unit.behavior_follow_target = npc_info["behavior_follow_target"]
            unit.carry_to_next_level = npc_info.get("carry_to_next_level", False)

            # Find follow target player to spawn near
            spawn_near_pos = dest_pad_pos
            if unit.behavior_follow_target and unit.behavior_follow_target.startswith("player_"):
                try:
                    idx = int(unit.behavior_follow_target.split("_")[1])
                    if idx < len(all_players) and all_players[idx].hp > 0 and all_players[idx].position:
                        spawn_near_pos = all_players[idx].position
                except (ValueError, IndexError):
                    pass

            self._place_unit_near(unit, spawn_near_pos, placed_positions)
            self.add_to_log(f"{unit.name} teleported with the party")

        # Apply deck config from destination stage
        if dest_stage:
            deck_config = dest_stage.get("deck_config", {})
            self._load_stage_decks(deck_config)

        # Reset player turn state
        for player in all_players:
            player.movement_used = False
            player.moves_per_turn = player.base_moves_per_turn  # Reset Scout sprint
            player.action_used = False
            if hasattr(player, 'reset_double_attack'):
                player.reset_double_attack()

        # Reset turn phase
        if game.multiplayer_mode:
            self.turn_phase = "multiplayer_player"
            game.current_player_index = 0
            if game.players:
                self.hex_grid.active_turn_unit = game.players[0]
        else:
            self.turn_phase = "player"
            self.hex_grid.active_turn_unit = game.player

        self.is_player_turn = True
        self.pending_teleport = None
        self.turn_cycle_count = 0
        self._detect_boss_encounter()

        self.add_to_log(f"Teleported to {dest_name}")

        # Snap camera to center on destination pad (avoid slow drift from old position)
        pad_row, pad_col = dest_pad_pos
        pixel_x = pad_col * self.hex_grid.hex_size * 1.5
        pixel_y = pad_row * self.hex_grid.hex_size * 1.732 + (pad_col % 2) * self.hex_grid.hex_size * 0.866
        self.hex_grid.view_offset_x = WINDOW_WIDTH / 2 - pixel_x
        self.hex_grid.view_offset_y = WINDOW_HEIGHT / 2 - pixel_y
        self.autopan_active = False

        game.current_screen = "game"
        self.initialize_screen()

        # Autosave at new level
        self.save_manager.save_game(game, self, save_type="autosave", save_label="Level Start (Teleport)")

    def _check_reach_location_instant(self, pos):
        """Check if stepping on this location hex should trigger instant level transition.
        Returns True if campaign completion type is reach_location and all living players
        are on matching target location hexes."""
        if not self.campaign:
            return False
        stages = self.campaign.get("stages") or self.campaign.get("levels", [])
        if not stages or self.current_level_idx >= len(stages):
            return False
        stage_data = stages[self.current_level_idx]
        completion = stage_data.get("completion_conditions", {})
        if not completion or completion.get("type") != "reach_location":
            return False
        target = completion.get("target", "")
        if not target:
            return False
        # Build set of matching location positions
        target_positions = set()
        for loc_hex in self.hex_grid.location_hexes:
            lpos = (loc_hex["row"], loc_hex["column"])
            loc_data = self.hex_grid.location_data.get(lpos)
            if loc_data and loc_data.get("card"):
                if loc_data["card"].get_current_data().get("Name") == target:
                    target_positions.add(lpos)
        if not target_positions:
            return False
        # Check if all living players are on a target location
        all_players = game.players if game.multiplayer_mode and game.players else [game.player]
        living = [p for p in all_players if p.hp > 0]
        return all(p.position in target_positions for p in living)

    def _trigger_instant_level_transition(self):
        """Trigger an immediate level transition without waiting for the turn cycle."""
        self.add_to_log("Reached destination! Moving to next area...")
        # Autosave before level transition
        self.save_manager.save_game(game, self, save_type="autosave", save_label="Level Complete")
        self.current_level_idx += 1
        stages = self.campaign.get("stages") or self.campaign.get("levels", []) if self.campaign else []
        if self.campaign and self.current_level_idx < len(stages):
            prev_level_file = self.current_level_file
            self.load_campaign_level()
            if game.multiplayer_mode:
                self.turn_phase = "multiplayer_player"
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
            self._show_campaign_complete()

    def _setup_multiplayer_player_phase(self):
        """Set up the correct player phase, skipping dead players."""
        for i, player in enumerate(game.players):
            if player.hp > 0:
                self.turn_phase = "multiplayer_player"
                game.current_player_index = i
                self.hex_grid.active_turn_unit = player
                self.rebuild_left_panel()
                # Player transition will be processed after _start_player_turn is called
                return
        # All dead - trigger defeat
        self.turn_phase = "multiplayer_player"
        game.current_player_index = 0
        self.hex_grid.active_turn_unit = game.players[0]
        self.pending_defeat = True

    def _is_player_phase(self):
        """Check if it's currently any player's turn (single or multiplayer)."""
        return self.turn_phase in ("player", "multiplayer_player")

    def _start_player_turn(self):
        """Reset UI state and center camera on the current active player."""
        self.player_mode = "movement"
        self.selected_attack = None
        self.defensive_hex_options = []
        self._close_attack_submenu()
        # Clear defensive posture at start of this player's turn
        current_player = game.current_player
        current_player.clear_defensive_posture()
        # Smooth pan camera to the active player
        if current_player and current_player.position:
            row, col = current_player.position
            self._start_autopan(row, col)

    def _get_defense_hex_options(self, player):
        """Get the hexes a player can defend: 6 adjacent + mist shadow neighbors."""
        if not player.position:
            return []
        row, col = player.position
        options = []
        # 6 adjacent hexes (all neighbors at distance 1, regardless of accessibility)
        adj_hexes = self.hex_grid.get_hexes_at_distance(player.position, 1)
        for pos in adj_hexes:
            r, c = pos
            if 0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols:
                options.append(pos)
        # Mist shadow direction hexes (nearest hex in each diagonal)
        mist_hexes = self.hex_grid.calculate_range(player.position, 2, "mist_shadow", False, False)
        # Only keep the nearest mist shadow hex in each direction (distance 2)
        for mh in mist_hexes:
            if mh not in options and 0 <= mh[0] < self.hex_grid.rows and 0 <= mh[1] < self.hex_grid.cols:
                if self.hex_grid.hex_distance(player.position, mh) <= 2:
                    options.append(mh)
        return options

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
        elif self.turn_phase == "multiplayer_player":
            # Multiplayer: End current player's turn
            current = game.current_player
            for msg in current.apply_passive_skills(self.hex_grid, "Turn_End"):
                self.add_to_log(msg)
            current.tick_cooldowns()
            current.movement_used = current.action_used = False
            current.reset_double_attack()

            # Find next alive player
            next_idx = None
            for i in range(game.current_player_index + 1, len(game.players)):
                if game.players[i].hp > 0:
                    next_idx = i
                    break

            if next_idx is not None:
                # Switch to next player
                game.current_player_index = next_idx
                self.turn_phase = "multiplayer_player"
                self.is_player_turn = True
                self.hex_grid.active_turn_unit = game.players[next_idx]
                self.rebuild_left_panel()
                self._start_player_turn()
                # Apply Turn_Start passives for next player
                for msg in game.players[next_idx].apply_passive_skills(self.hex_grid, "Turn_Start"):
                    self.add_to_log(msg)
                # Process player transition card for next player
                self._process_player_transition(game.players[next_idx])
            else:
                # All players done, move to allied phase
                self.turn_phase = "allied"
                self.execute_turn("Allied")
        elif self.turn_phase == "allied":
            self.turn_phase = "neutral"
            self.execute_turn("Neutral")
        elif self.turn_phase == "neutral":
            self.turn_phase = "hostile"
            self.execute_turn("Hostile")
        elif self.turn_phase == "hostile":
            # Clear passthrough defense cache
            self._clear_defense_range_cache()
            self.hex_grid.active_turn_unit = None
            # Skip location_defense phase entirely if no active defenses
            if self.hex_grid.get_active_defensive_locations():
                self.turn_phase = "location_defense"
                self.update_turn_label()
                self.process_location_defense_turn()
            else:
                self.turn_phase = "transition"
                self.update_turn_label()
                self.process_transition_turn()
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
                        self.turn_phase = "multiplayer_player"
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
                    self._show_campaign_complete()
            else:
                # Spy disguise super charging: +1 per turn cycle while disguised
                if game.multiplayer_mode:
                    for p in game.players:
                        if getattr(p, 'is_disguised', False):
                            p.add_super_charge()
                            self.add_to_log(f"{p.name or p.class_name}'s disguise charges super (+1)")
                else:
                    if getattr(game.player, 'is_disguised', False):
                        game.player.add_super_charge()
                        self.add_to_log(f"{game.player.name or game.player.class_name}'s disguise charges super (+1)")

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

                # Process player transition card at turn start
                self._process_player_transition(current_player)

                # Periodic autosave
                autosave_freq = getattr(game, '_autosave_frequency', 5)
                if autosave_freq > 0 and self.turn_cycle_count > 0 and self.turn_cycle_count % autosave_freq == 0:
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

        units_to_process = [unit for unit in self.hex_grid.units if unit.allegiance == allegiance and unit.hp > 0]
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

        # Pan to unit first, then execute turn via callback
        if unit.position:
            row, col = unit.position
            self._start_autopan(row, col, callback=lambda u=unit: self._execute_unit_turn(u))
        else:
            self._execute_unit_turn(unit)

    def _execute_unit_turn(self, unit):
        """Execute a unit's AI turn (called after autopan completes)."""
        PREVIEW_RANGE_MS = 500
        PREVIEW_SELECT_MS = 400

        # Guard: unit may have died during pan
        if unit not in self.hex_grid.units or unit.hp <= 0:
            self.process_next_unit()
            return

        self.last_action_time = pygame.time.get_ticks()

        # Check for unit transition event (trip_fall, etc.)
        if game.transition_manager.has_unit_transition():
            unit_trans_result = game.transition_manager.process_unit_transition_turn(self.hex_grid, unit)
            if unit_trans_result:
                outcome_type, result_text, log_msgs = unit_trans_result
                for msg in log_msgs:
                    self.add_to_log(msg)
                if outcome_type == "trip_fall":
                    unit.skip_turn = True
                    # Unit loses its turn — check if it died from damage
                    if unit.hp <= 0:
                        self._post_attack_processing(unit)
                    else:
                        self.player_info_label.set_text(self.get_player_info())
                        self.waiting_for_animation = True
                    return  # Skip unit's normal turn

        # Preview system: plan the turn and show range overlay before executing
        plan = unit.plan_turn(self.hex_grid)
        if plan["action"] == "idle":
            # No action to preview — execute immediately
            self._do_unit_turn(unit)
        else:
            # Enter range preview phase
            self.unit_preview_unit = unit
            self.unit_preview_plan = plan
            self.unit_preview_phase = "range"
            self.unit_preview_start = pygame.time.get_ticks()

    def _do_unit_turn(self, unit):
        """Execute a unit's actual turn (after preview completes or directly for idle)."""
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
        dead_units = [u for u in self.hex_grid.units if u.hp <= 0 and not getattr(u, '_death_processed', False)]
        for dead_unit in dead_units:
            if dead_unit.position:
                row, col = dead_unit.position
                # Displace body off location hex (body stays in grid)
                if dead_unit.position in self.hex_grid.location_data:
                    for nr, nc in self.hex_grid.get_adjacent_hexes(row, col):
                        if ((nr, nc) not in self.hex_grid.location_data
                                and 0 <= nr < self.hex_grid.rows and 0 <= nc < self.hex_grid.cols
                                and self.hex_grid.grid[nr][nc]["accessible"]
                                and self.hex_grid.grid[nr][nc]["unit"] is None):
                            self.hex_grid.grid[row][col]["unit"] = None
                            dead_unit.position = (nr, nc)
                            self.hex_grid.grid[nr][nc]["unit"] = dead_unit
                            break
            dead_unit._death_processed = True
            self.add_to_log(f"{dead_unit.name} defeated")
            self.add_defeat_notification(dead_unit.name)
            self.card_manager.track_card_usage(dead_unit.card_id, {"action": "defeated", "screen": "game"})
            quest_results = game.current_quest_manager.update("unit_death", {"unit": dead_unit}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)
            self._handle_quest_chain()

        # Check boss encounter phase-2 completion
        if dead_units:
            self._check_boss_encounter_completion()

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
                self.turn_queue.clear()
                self.pending_defeat = True
                return True
        elif isinstance(self.hex_grid.player, Player) and self.hex_grid.player.hp <= 0:
            self.add_to_log("Player defeated!")
            self.add_defeat_notification("Player")
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
        # --- Unit preview phase machine ---
        if self.unit_preview_phase:
            PREVIEW_RANGE_MS = 500
            PREVIEW_SELECT_MS = 400
            elapsed = pygame.time.get_ticks() - self.unit_preview_start
            if self.unit_preview_phase == "range" and elapsed >= PREVIEW_RANGE_MS:
                self.unit_preview_phase = "selection"
                self.unit_preview_start = pygame.time.get_ticks()
                return
            elif self.unit_preview_phase == "selection" and elapsed >= PREVIEW_SELECT_MS:
                unit = self.unit_preview_unit
                self.unit_preview_phase = None
                self.unit_preview_plan = None
                self.unit_preview_unit = None
                # Check unit still alive before executing
                if unit and unit in self.hex_grid.units and unit.hp > 0:
                    self._do_unit_turn(unit)
                else:
                    self.process_next_unit()
            return  # Don't process anything else while previewing

        if not self.waiting_for_animation:
            return

        if self._loc_defense_active:
            return  # Don't process turn queue while location defense is animating

        if self.autopan_active:
            return  # Wait for camera pan to complete before processing

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

        # Check for pending dialogue from Messenger NPCs
        if self.current_acting_unit and hasattr(self.current_acting_unit, 'pending_dialogue') and self.current_acting_unit.pending_dialogue:
            # Don't activate dialogue while event banner is showing — leave pending for next frame
            if self.event_banner_active:
                return
            dlg = self.current_acting_unit.pending_dialogue
            self.current_acting_unit.pending_dialogue = None
            self.dialogue_active = True
            self.dialogue_speaker = dlg["speaker"]
            self.dialogue_text = dlg["text"]
            # Distribute gift cards to all players
            gift_ids = dlg.get("gift_card_ids", [])
            if gift_ids:
                all_players = game.players if game.multiplayer_mode and game.players else [game.player]
                for card_id in gift_ids:
                    for p in all_players:
                        card_data = load_card(card_id)
                        if card_data:
                            inv_card = InventoryCard(card_data)
                            p.inventory.append(inv_card)
                self.add_to_log(f"{dlg['speaker']} gave you some items!")

        # Check for pending quest offer from quest giver NPCs
        if (self.current_acting_unit and
            hasattr(self.current_acting_unit, 'pending_quest_offer') and
            self.current_acting_unit.pending_quest_offer):
            if self.event_banner_active:
                return  # Wait for banner to clear
            offer = self.current_acting_unit.pending_quest_offer
            self.current_acting_unit.pending_quest_offer = None
            # Store offer data and show Accept/Decline popup
            self._pending_quest_offer = {
                "quest_card_id": offer["quest_card_id"],
                "offering_unit": self.current_acting_unit,
                "speaker": offer.get("speaker", "NPC")
            }
            speaker = offer.get("speaker", "A mysterious traveler")
            game.current_screen = "confirmation"
            confirmation_screen.initialize_screen(
                f"{speaker} offers you a quest. Accept?",
                ["Accept", "Decline"],
                self._handle_quest_offer_response
            )
            return

        # Block turn queue while dialogue is showing
        if self.dialogue_active:
            return

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
                # Healer with no melee weapon: show "Heal (20 HP)" instead of melee damage
                if attack_key == "melee" and current_player.is_healer and current_player.melee_weapon is None:
                    btn = UIButton(pygame.Rect(x, y, button_width, 30),
                                   "Heal (20 HP)", manager)
                    btn._outline_color = (0, 200, 0)  # Green for healing
                else:
                    btn = UIButton(pygame.Rect(x, y, button_width, 30),
                                   f"{attack['name']} ({attack['damage']} dmg)", manager)
                    btn._outline_color = outline_color
                self.attack_submenu_buttons.append((btn, "attack", attack))
                y += 34

        # Special attack (passive specials don't need a button)
        passive_specials = ("Dual Strike", "Piercing Shot", "Heal", "Master Builder")
        if current_player.special_attack not in passive_specials:
            btn = UIButton(pygame.Rect(x, y, button_width, 30),
                           f"[Special] {current_player.special_attack}", manager)
            self.attack_submenu_buttons.append((btn, "special", None))
            self.special_attack_button = btn
            y += 34

        # Super attack button (when charged)
        if current_player.super_attack_ready:
            # Healer super: Revive (needs targeting mode)
            if current_player.is_healer:
                super_label = "[SUPER] Revive"
            elif current_player.piercing_projectile and current_player.is_manning():
                super_label = "[SUPER] Sniper Mode"
            else:
                super_label = f"[SUPER] {current_player.special_attack}"
            btn = UIButton(pygame.Rect(x, y, button_width, 30),
                           super_label, manager)
            self.attack_submenu_buttons.append((btn, "super", None))
            self.super_attack_button = btn
            y += 34

        self.attack_submenu_open = True

    def _close_attack_submenu(self):
        """Close the attack submenu."""
        for btn, _, _ in self.attack_submenu_buttons:
            btn.kill()
        self.attack_submenu_buttons = []
        self.attack_submenu_open = False
        self.special_attack_button = None
        self.super_attack_button = None

    def initialize_screen(self):
        manager.clear_and_reset()
        # Compute right panel geometry
        rp_w = self.rp_width  # 234
        rp_pad = self.rp_pad  # 10
        rp_x = WINDOW_WIDTH - rp_w
        rp_inner_w = rp_w - 2 * rp_pad  # 214
        toolbar_clearance = 60
        section_header_h = 20
        stats_h = 175

        pi_y = section_header_h + 4  # Below "Player" label
        # Render panel once to get actual height
        self._player_panel_dirty = True
        self._render_player_panel()
        player_info_h = self._player_panel_height
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
        self.player_info_label = PlayerInfoPanelProxy(self)

        y_pos = 200
        self.left_panel_buttons = []
        self.attack_submenu_open = False
        self.attack_submenu_buttons = []
        self.special_attack_button = None
        self.super_attack_button = None
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

        # Add Defend button
        self.defend_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Defend", manager)
        self.left_panel_buttons.append(self.defend_button)
        y_pos += 40

        # Add Leave Tower button (when manning a defensive location)
        self.leave_tower_button = None
        self.toggle_weapon_button = None
        if game.current_player.is_manning():
            self.leave_tower_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Leave Tower", manager)
            self.left_panel_buttons.append(self.leave_tower_button)
            y_pos += 40
            mode_label = "Mode: Tower Weapon" if game.current_player.manning_weapon_mode == "tower" else "Mode: Personal Weapon"
            self.toggle_weapon_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), mode_label, manager)
            self.left_panel_buttons.append(self.toggle_weapon_button)
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
        if hasattr(p, 'moves_per_turn') and p.moves_per_turn > 1:
            # Calculate effective max moves (include sprint 3rd move if available)
            effective_max = p.moves_per_turn
            if (p.special_attack == "Double Move" and p.super_attack_ready
                and p._movement_count >= p.moves_per_turn):
                effective_max = 3
            remaining = effective_max - p._movement_count
            if remaining < 0:
                remaining = 0
            mv_color = "#888888" if remaining <= 0 else "#CCCCDD"
            sprint_tag = " SPRINT!" if p._movement_count >= p.moves_per_turn and remaining > 0 else ""
            lines.append(f"<font color='#999999'>Move:</font> <font color='{mv_color}'>{remaining}/{effective_max}{sprint_tag} ({p.movement} hexes)</font>")
        else:
            mv_color = "#888888" if p.movement_used else "#CCCCDD"
            lines.append(f"<font color='#999999'>Move:</font> <font color='{mv_color}'>{p.movement}</font>")
        lines.append(f"<font color='#999999'>Range:</font> <font color='#CCCCDD'>{p.projectile_range}</font>")
        act_color = "#888888" if p.action_used else "#CCCCDD"
        lines.append(f"<font color='#999999'>Action:</font> <font color='{act_color}'>{'Used' if p.action_used else 'Ready'}</font>")
        if p.class_name == "Warrior":
            lines.append(f"<font color='#999999'>Attacks:</font> <font color='#CCCCDD'>{p.warrior_attacks_remaining}/2</font>")
        # Healer info: show heal mode and revive charge
        if p.is_healer:
            if p.melee_weapon is None:
                lines.append(f"<font color='#00CC00'>Heal Mode (20 HP)</font>")
            else:
                lines.append(f"<font color='#999999'>Melee weapon equipped</font>")
        # Disguise status indicator
        if getattr(p, 'is_disguised', False):
            if getattr(p, 'is_boss_disguised', False):
                lines.append(f"<font color='#FF4444'>BOSS DISGUISE ACTIVE</font>")
            else:
                lines.append(f"<font color='#FFAA00'>DISGUISED</font>")
        # Super charge meter
        charge_pips = ">" * p.super_charge + "." * (p.super_charge_max - p.super_charge)
        charge_color = "#FFD700" if p.super_attack_ready else "#888888"
        if p.is_healer:
            lines.append(f"<font color='#999999'>Revive:</font> <font color='{charge_color}'>[{charge_pips}]</font>")
        elif getattr(p, 'is_spy', False):
            lines.append(f"<font color='#999999'>Order:</font> <font color='{charge_color}'>[{charge_pips}]</font>")
        elif p.special_attack == "Double Move":
            lines.append(f"<font color='#999999'>Sprint:</font> <font color='{charge_color}'>[{charge_pips}]</font>")
        else:
            lines.append(f"<font color='#999999'>Super:</font> <font color='{charge_color}'>[{charge_pips}]</font>")
        # Manning tower info
        if p.is_manning():
            loc_data = self.hex_grid.location_data.get(p.manning_location)
            if loc_data:
                loc_name = loc_data["card"].get_current_data().get("Name", "Tower") if loc_data.get("card") else "Tower"
                lines.append(f"<font color='#FFD700'>Manning: {loc_name}</font>")
                if p.manning_weapon_mode == "tower":
                    defenses = loc_data.get("defenses", [])
                    if defenses:
                        best = max(defenses, key=lambda d: d.get("damage", 0))
                        lines.append(f"<font color='#FFD700'>Tower: {best['damage']} dmg / {best.get('range_distance', 0)} range</font>")
                else:
                    lines.append(f"<font color='#AAD4FF'>Using: Personal Weapon</font>")
        return "<br>".join(lines)

    # --- Custom player info panel rendering ---

    def _render_icon(self, icon_char, font, fallback_font, color):
        """Render a unicode icon, falling back to symbol font if needed."""
        surf = font.render(icon_char, True, color)
        # Check if it rendered as a tofu box (very narrow or blank)
        if surf.get_width() < 5:
            surf = fallback_font.render(icon_char, True, color)
        return surf

    def _draw_stat_line(self, surf, y, icon, label, value, value_color, label_color=(190, 190, 200)):
        """Draw an icon + label + value line on the panel surface."""
        x = 6
        icon_surf = self._render_icon(icon, self.rp_body_font, self.rp_icon_font, label_color)
        surf.blit(icon_surf, (x, y))
        x += icon_surf.get_width() + 3
        lbl_surf = self.rp_body_font.render(f"{label}: ", True, label_color)
        surf.blit(lbl_surf, (x, y))
        x += lbl_surf.get_width()
        val_surf = self.rp_body_bold.render(str(value), True, value_color)
        surf.blit(val_surf, (x, y))
        return self.rp_body_font.get_linesize()

    def _draw_hp_bar(self, surf, y, p):
        """Draw a graphical HP bar with colored fill and text overlay."""
        bar_x = 6
        bar_w = surf.get_width() - 12
        bar_h = 16
        hp_ratio = p.hp / p.max_hp if p.max_hp > 0 else 0
        # Background
        pygame.draw.rect(surf, (40, 40, 50), (bar_x, y, bar_w, bar_h), border_radius=3)
        # Fill color by HP ratio
        if hp_ratio > 0.6:
            fill_color = (80, 200, 80)
        elif hp_ratio > 0.3:
            fill_color = (200, 200, 60)
        else:
            fill_color = (200, 60, 60)
        fill_w = max(0, int(bar_w * hp_ratio))
        if fill_w > 0:
            pygame.draw.rect(surf, fill_color, (bar_x, y, fill_w, bar_h), border_radius=3)
        # Border
        pygame.draw.rect(surf, (80, 80, 100), (bar_x, y, bar_w, bar_h), 1, border_radius=3)
        # HP text centered with shadow
        hp_text = f"{p.hp}/{p.max_hp}"
        hp_txt_surf = self.rp_body_bold.render(hp_text, True, (0, 0, 0))
        tx = bar_x + (bar_w - hp_txt_surf.get_width()) // 2
        ty = y + (bar_h - hp_txt_surf.get_height()) // 2
        surf.blit(hp_txt_surf, (tx + 1, ty + 1))  # shadow
        hp_txt_surf = self.rp_body_bold.render(hp_text, True, (255, 255, 255))
        surf.blit(hp_txt_surf, (tx, ty))
        # Icon at left
        icon_surf = self._render_icon("\u2665", self.rp_body_font, self.rp_icon_font, fill_color)
        surf.blit(icon_surf, (bar_x + 3, y + (bar_h - icon_surf.get_height()) // 2))
        return bar_h + 2

    def _draw_charge_bar(self, surf, y, p, label):
        """Draw a segmented super charge bar with pulse animation when full."""
        x = 6
        # Label
        lbl_color = (190, 190, 200)
        icon_surf = self._render_icon("\u26A1", self.rp_body_font, self.rp_icon_font, lbl_color)
        surf.blit(icon_surf, (x, y))
        lbl_surf = self.rp_body_font.render(f"{label}: ", True, lbl_color)
        surf.blit(lbl_surf, (x + icon_surf.get_width() + 3, y))
        bar_x = x + icon_surf.get_width() + 3 + lbl_surf.get_width() + 4
        bar_w = surf.get_width() - bar_x - 6
        bar_h = 12
        pip_count = p.super_charge_max if p.super_charge_max > 0 else 1
        pip_w = max(4, (bar_w - (pip_count - 1) * 2) // pip_count)
        bar_y = y + (self.rp_body_font.get_linesize() - bar_h) // 2
        # Animation pulse when fully charged
        ticks = pygame.time.get_ticks()
        pulse = 0.0
        if p.super_attack_ready:
            pulse = (math.sin(ticks / 400.0) + 1.0) / 2.0  # 0..1
        for i in range(pip_count):
            px = bar_x + i * (pip_w + 2)
            if i < p.super_charge:
                if p.super_attack_ready:
                    r = int(200 + 55 * pulse)
                    g = int(160 + 95 * pulse)
                    b = int(40 + 215 * pulse)
                    pip_color = (min(r, 255), min(g, 255), min(b, 255))
                else:
                    pip_color = (200, 160, 40)
            else:
                pip_color = (50, 50, 60)
            pygame.draw.rect(surf, pip_color, (px, bar_y, pip_w, bar_h), border_radius=2)
        # Glow overlay when fully charged
        if p.super_attack_ready:
            glow_alpha = int(30 * pulse)
            glow_surf = pygame.Surface((bar_w + 4, bar_h + 4), pygame.SRCALPHA)
            glow_surf.fill((255, 220, 100, glow_alpha))
            surf.blit(glow_surf, (bar_x - 2, bar_y - 2))
        return self.rp_body_font.get_linesize()

    def _render_player_panel(self):
        """Build the custom player info panel surface."""
        p = game.current_player
        if p is None:
            self._player_panel_surface = pygame.Surface((self.rp_inner_w, 20), pygame.SRCALPHA)
            self._player_panel_height = 20
            return
        w = self.rp_inner_w if self.rp_inner_w > 0 else 214
        line_h = self.rp_body_font.get_linesize()
        pad = 4  # vertical padding within sections

        # --- Pre-calculate total height ---
        h = 0
        # Section: Class header
        h += self.rp_header_font.get_linesize() + pad
        # Section: HP bar
        h += 18 + pad  # bar_h(16) + 2 gap + pad
        # Section: Stats (move, range, action)
        stat_lines = 3
        if p.class_name == "Warrior":
            stat_lines += 1
        if p.is_healer:
            stat_lines += 1
        if getattr(p, 'is_disguised', False):
            stat_lines += 1
        h += stat_lines * line_h + pad
        # Section: Charge bar
        h += line_h + pad
        # Section: Manning
        if p.is_manning():
            manning_lines = 2
            h += manning_lines * line_h + pad
        # Multiplayer indicator
        if game.multiplayer_mode:
            h += line_h

        h += pad  # bottom padding

        # --- Create surface ---
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        y = 0

        # --- Class header with warm tint background ---
        header_h = self.rp_header_font.get_linesize() + pad
        tint = pygame.Surface((w, header_h), pygame.SRCALPHA)
        tint.fill((50, 40, 10, 30))
        surf.blit(tint, (0, y))
        # Multiplayer indicator
        if game.multiplayer_mode:
            mp_surf = self.rp_body_font.render(f"Player {p.player_number}", True, (170, 170, 255))
            surf.blit(mp_surf, (6, y))
            y += line_h
        class_surf = self.rp_header_font.render(p.class_name, True, (255, 215, 0))
        surf.blit(class_surf, (6, y))
        y += self.rp_header_font.get_linesize() + pad

        # --- HP section with subtle green tint ---
        hp_section_h = 18 + pad
        tint = pygame.Surface((w, hp_section_h), pygame.SRCALPHA)
        tint.fill((20, 50, 20, 25))
        surf.blit(tint, (0, y))
        y += self._draw_hp_bar(surf, y, p)
        y += pad

        # --- Stats section with subtle blue tint ---
        stats_section_h = stat_lines * line_h + pad
        tint = pygame.Surface((w, stats_section_h), pygame.SRCALPHA)
        tint.fill((20, 20, 50, 20))
        surf.blit(tint, (0, y))

        # Movement
        if hasattr(p, 'moves_per_turn') and p.moves_per_turn > 1:
            effective_max = p.moves_per_turn
            if (p.special_attack == "Double Move" and p.super_attack_ready
                    and p._movement_count >= p.moves_per_turn):
                effective_max = 3
            remaining = max(0, effective_max - p._movement_count)
            mv_color = (160, 160, 170) if remaining <= 0 else (240, 240, 255)
            sprint_tag = " SPRINT!" if p._movement_count >= p.moves_per_turn and remaining > 0 else ""
            mv_val = f"{remaining}/{effective_max}{sprint_tag} ({p.movement} hexes)"
        else:
            mv_color = (160, 160, 170) if p.movement_used else (240, 240, 255)
            mv_val = str(p.movement)
        y += self._draw_stat_line(surf, y, "\u25B6", "Move", mv_val, mv_color)

        # Range
        y += self._draw_stat_line(surf, y, "\u25CE", "Range", str(p.projectile_range), (240, 240, 255))

        # Action
        act_color = (160, 160, 170) if p.action_used else (240, 240, 255)
        act_val = "Used" if p.action_used else "Ready"
        y += self._draw_stat_line(surf, y, "\u2694", "Action", act_val, act_color)

        # Warrior attacks
        if p.class_name == "Warrior":
            y += self._draw_stat_line(surf, y, "\u2694", "Attacks", f"{p.warrior_attacks_remaining}/2", (240, 240, 255))

        # Healer mode
        if p.is_healer:
            if p.melee_weapon is None:
                heal_surf = self.rp_body_bold.render("Heal Mode (20 HP)", True, (50, 230, 50))
            else:
                heal_surf = self.rp_body_font.render("Melee weapon equipped", True, (190, 190, 200))
            surf.blit(heal_surf, (6, y))
            y += line_h

        # Disguise status
        if getattr(p, 'is_disguised', False):
            if getattr(p, 'is_boss_disguised', False):
                dis_surf = self.rp_body_bold.render("BOSS DISGUISE ACTIVE", True, (255, 68, 68))
            else:
                dis_surf = self.rp_body_bold.render("DISGUISED", True, (255, 170, 0))
            surf.blit(dis_surf, (6, y))
            y += line_h

        y += pad

        # --- Charge bar section with warm gold tint ---
        charge_section_h = line_h + pad
        tint = pygame.Surface((w, charge_section_h), pygame.SRCALPHA)
        tint.fill((50, 40, 10, 25))
        surf.blit(tint, (0, y))
        # Pick label by class
        if p.is_healer:
            charge_label = "Revive"
        elif getattr(p, 'is_spy', False):
            charge_label = "Order"
        elif p.special_attack == "Double Move":
            charge_label = "Sprint"
        else:
            charge_label = "Super"
        y += self._draw_charge_bar(surf, y, p, charge_label)
        y += pad

        # --- Manning section ---
        if p.is_manning():
            manning_section_h = 2 * line_h + pad
            tint = pygame.Surface((w, manning_section_h), pygame.SRCALPHA)
            tint.fill((50, 35, 10, 30))
            surf.blit(tint, (0, y))
            loc_data = self.hex_grid.location_data.get(p.manning_location)
            if loc_data:
                loc_name = loc_data["card"].get_current_data().get("Name", "Tower") if loc_data.get("card") else "Tower"
                y += self._draw_stat_line(surf, y, "\u2656", "Manning", loc_name, (255, 215, 0))
                if p.manning_weapon_mode == "tower":
                    defenses = loc_data.get("defenses", [])
                    if defenses:
                        best = max(defenses, key=lambda d: d.get("damage", 0))
                        tw_val = f"{best['damage']} dmg / {best.get('range_distance', 0)} range"
                        y += self._draw_stat_line(surf, y, " ", "Tower", tw_val, (255, 215, 0))
                    else:
                        y += line_h
                else:
                    wpn_surf = self.rp_body_font.render("Using: Personal Weapon", True, (170, 212, 255))
                    surf.blit(wpn_surf, (6, y))
                    y += line_h
            y += pad

        self._player_panel_surface = surf
        self._player_panel_height = y
        self._player_panel_dirty = False

    def _handle_quest_chain(self):
        """Check for pending quest chain and handle by mode (auto_activate or offer)."""
        # Check for transition card swap from quest chain
        transition_swap = game.current_quest_manager.get_pending_transition_swap()
        if transition_swap:
            if game.transition_manager.load_transition_card(transition_swap):
                self.add_to_log(f"The world shifts... ({game.transition_manager.active_transition.name})")
            else:
                logger.warning(f"Could not load transition card '{transition_swap}' from quest chain")

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

    def _handle_quest_offer_response(self, choice):
        """Callback for quest NPC offer (Accept/Decline)."""
        game.current_screen = "game"
        if choice == "Accept" and hasattr(self, '_pending_quest_offer'):
            offer = self._pending_quest_offer
            quest_card_id = offer["quest_card_id"]
            card_data = load_card(quest_card_id)
            if card_data:
                inv_card = InventoryCard(card_data)
                success, msg = game.current_quest_manager.activate_quest(
                    inv_card, self.hex_grid, game.current_player
                )
                self.add_to_log(msg)
                # Clear the offering unit's quest data so it doesn't re-offer
                offering_unit = offer.get("offering_unit")
                if offering_unit:
                    offering_unit.quest_offer_card_id = None
                    offering_unit.quest_offer_target = None
            else:
                self.add_to_log(f"Quest card '{quest_card_id}' not found.")
        else:
            speaker = self._pending_quest_offer.get("speaker", "NPC") if hasattr(self, '_pending_quest_offer') else "NPC"
            self.add_to_log(f"Declined quest from {speaker}.")
        if hasattr(self, '_pending_quest_offer'):
            del self._pending_quest_offer

    def _handle_instance_quest_offer_response(self, choice):
        """Callback for instance card offer_quest outcome (Accept/Decline)."""
        self.active_screen = "game"
        if choice == "Accept" and hasattr(self, '_pending_instance_quest_offer'):
            offer = self._pending_instance_quest_offer
            quest_card = offer["quest_card"]
            success, msg = game.current_quest_manager.activate_quest(
                quest_card, self.hex_grid, game.current_player
            )
            self.add_to_log(msg)
        else:
            self.add_to_log("Quest opportunity declined.")
        if hasattr(self, '_pending_instance_quest_offer'):
            del self._pending_instance_quest_offer
        # Continue normal post-instance flow
        self.resume_after_instance()

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
            # Show HP for spawn locations
            if loc_data.get("is_spawn_location", False) and loc_data.get("health", 0) > 0:
                hp = loc_data["health"]
                max_hp = loc_data.get("max_health", hp)
                hp_ratio = hp / max_hp if max_hp > 0 else 0
                if hp_ratio > 0.6:
                    hc = "#66DD66"
                elif hp_ratio > 0.3:
                    hc = "#DDDD44"
                else:
                    hc = "#DD4444"
                lines.append(f"<font color='#999999'>HP:</font> <font color='{hc}'>{hp}/{max_hp}</font>")
            elif loc_data.get("is_npc_spawn_location", False) and loc_data.get("npc_health", 0) > 0:
                hp = loc_data["npc_health"]
                max_hp = loc_data.get("npc_max_health", hp)
                hp_ratio = hp / max_hp if max_hp > 0 else 0
                if hp_ratio > 0.6:
                    hc = "#66DD66"
                elif hp_ratio > 0.3:
                    hc = "#DDDD44"
                else:
                    hc = "#DD4444"
                lines.append(f"<font color='#999999'>HP:</font> <font color='{hc}'>{hp}/{max_hp}</font>")
        return "<br>".join(lines)

    def update_turn_label(self):
        if self.turn_phase == "player" and game.player:
            player_name = game.player.name if hasattr(game.player, 'name') and game.player.name else "Player"
            label = f"{player_name}'s Turn"
            color = "#66DD66"  # Green for player
        elif self.turn_phase == "multiplayer_player" and game.multiplayer_mode:
            idx = game.current_player_index
            player = game.players[idx]
            player_name = player.name if hasattr(player, 'name') and player.name else f"Player {idx + 1}"
            label = f"{player_name}'s Turn"
            color = PLAYER_COLOR_HEX[idx] if idx < len(PLAYER_COLOR_HEX) else "#FFFFFF"
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
        if self.turn_phase != "transition":
            self.show_turn_banner(label, color)

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

        y_pos = 200
        self.attack_submenu_open = False
        self.attack_submenu_buttons = []
        self.special_attack_button = None
        self.super_attack_button = None

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

        # Add Defend button
        self.defend_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Defend", manager)
        self.left_panel_buttons.append(self.defend_button)
        y_pos += 40

        # Add Leave Tower button (when manning a defensive location)
        self.leave_tower_button = None
        self.toggle_weapon_button = None
        if current_player.is_manning():
            self.leave_tower_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), "Leave Tower", manager)
            self.left_panel_buttons.append(self.leave_tower_button)
            y_pos += 40
            mode_label = "Mode: Tower Weapon" if current_player.manning_weapon_mode == "tower" else "Mode: Personal Weapon"
            self.toggle_weapon_button = UIButton(pygame.Rect(10, y_pos, button_width, 30), mode_label, manager)
            self.left_panel_buttons.append(self.toggle_weapon_button)
            y_pos += 40

        self.ui_elements.extend(self.left_panel_buttons)
        self.update_turn_label()
        self._create_equipment_toolbar()

    def _create_equipment_toolbar(self):
        """Create 8 bottom toolbar buttons (Menu + 6 equipment + End Turn)."""
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
        total_w = btn_w * 8 + gap * 7
        start_x = (WINDOW_WIDTH - total_w) // 2
        y = WINDOW_HEIGHT - 50

        # Melee slot label
        if p.melee_weapon:
            melee_name = p.melee_weapon.get_current_data().get("Name", "???")
        else:
            melee_name = p.attacks.get("melee", {}).get("name", "Fist")
        # Projectile slot label
        if p.projectile_weapon:
            proj_name = p.projectile_weapon.get_current_data().get("Name", "???")
        else:
            proj_name = p.attacks.get("projectile", {}).get("name", "Throw Rock")
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

        labels = ["Menu", f"Melee: {melee_name}", f"Proj: {proj_name}", f"Acc: {acc_name}", f"Tool: {tool_label}", f"Action: {action_label}", "Items"]
        for i, label in enumerate(labels):
            bx = start_x + i * (btn_w + gap)
            btn = UIButton(pygame.Rect(bx, y, btn_w, btn_h), label, manager)
            self.equip_toolbar_buttons.append(btn)
            self.ui_elements.append(btn)

        # End Turn as 8th button in the same row
        end_x = start_x + 7 * (btn_w + gap)
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
                # Pass terrain for Builder's wood perk
                player_pos = current_player.position
                terrain = self.hex_grid.grid[player_pos[0]][player_pos[1]].get("terrain", "grass")
                can, missing = current_player.can_build(plan, terrain=terrain)
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
        """Get set of attempted hex positions for a card from in-memory tracking."""
        card_id = self._get_card_id(card)
        return self._hex_attempts.get(card_id, set())

    def _save_hex_attempt(self, card, hex_pos):
        """Record a hex as attempted for a card in memory."""
        card_id = self._get_card_id(card)
        if card_id not in self._hex_attempts:
            self._hex_attempts[card_id] = set()
        self._hex_attempts[card_id].add(tuple(hex_pos))

    def _clear_hex_attempts(self, card):
        """Clear hex attempt tracking for a card."""
        card_id = self._get_card_id(card)
        self._hex_attempts.pop(card_id, None)

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

        # Get the Items button (index 6)
        if len(self.equip_toolbar_buttons) < 7:
            return
        slot_btn = self.equip_toolbar_buttons[6]

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

        # Add body cards with [Body] suffix and "place_body" action type
        for card in p.inventory:
            cdata = card.get_current_data()
            if cdata.get("_is_dead_body") == "true":
                name = cdata.get("Name", "???")
                items.append((f"Place {name} [Body]", card))

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
        slot_idx_map = {"melee": 1, "projectile": 2, "accessory": 3, "tool": 4}
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
                    # Infer weapon type from damage fields when Type is missing
                    if not ctype and card.card_data.get("subclass") in ("Junk_to_Weapon", "Blueprint_to_Weapon"):
                        if int(cdata.get("Melee Damage", 0) or 0) > 0:
                            ctype = "Melee"
                    if ctype == "Melee":
                        items.append((cdata.get("Name", "???"), card))
            if p.melee_weapon:
                items.append(("-- Unequip --", "unequip"))

        elif slot_type == "projectile":
            for card in p.inventory:
                if card.current_state == 2 and card is not p.projectile_weapon:
                    cdata = card.get_current_data()
                    ctype = cdata.get("Type", "")
                    # Infer weapon type from damage fields when Type is missing
                    if not ctype and card.card_data.get("subclass") in ("Junk_to_Weapon", "Blueprint_to_Weapon"):
                        if int(cdata.get("Projectile Damage", 0) or 0) > 0:
                            ctype = "Projectile"
                    if ctype == "Projectile":
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
                    if ctype in ("Tool_Belt", "Accessory", "Belt", "Pouch", "Ammunition", "Shield", "Armor"):
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
            btn = UIButton(pygame.Rect(start_x, y, btn_w, btn_h), label, manager,
                           object_id="#action_choice_btn")
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
        was_disguised = getattr(current_player, 'is_disguised', False)
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
                                self.pending_defeats.append(hit_unit)
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
                            self.pending_defeats.append(target)
                            self.add_to_log(f"{target.name} defeated")
                            self.add_defeat_notification(target.name)
                            self.card_manager.track_card_usage(target.card_id, {"action": "defeated", "screen": "game"})
                            quest_results = game.current_quest_manager.update("unit_death", {"unit": target}, self.hex_grid, current_player)
                            for quest, qresult, msg in quest_results:
                                self.add_to_log(msg)
                            self._handle_quest_chain()
                            self.update_quest_button()
                            self.show_stats(None)
                self._check_ammo_runout_banner(current_player)
                # Check if disguise broke during attack
                if was_disguised and not current_player.is_disguised:
                    self.add_to_log("Disguise broken! Enemies are now aware of your presence!")
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
                                self.pending_defeats.append(hit_unit)
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
                            self.pending_defeats.append(target)
                            self.add_to_log(f"{target.name} defeated")
                            self.add_defeat_notification(target.name)
                            self.card_manager.track_card_usage(target.card_id, {"action": "defeated", "screen": "game"})
                            quest_results = game.current_quest_manager.update("unit_death", {"unit": target}, self.hex_grid, current_player)
                            for quest, qresult, msg in quest_results:
                                self.add_to_log(msg)
                            self._handle_quest_chain()
                            self.update_quest_button()
                            self.show_stats(None)
                self._check_ammo_runout_banner(current_player)
                # Check if disguise broke during attack
                if was_disguised and not current_player.is_disguised:
                    self.add_to_log("Disguise broken! Enemies are now aware of your presence!")
                self.player_info_label.set_text(self.get_player_info())
                self.selected_attack = None
                if current_player.action_used and not current_player.movement_used:
                    self.player_mode = "movement"
        elif action_type == "recruit":
            game.current_screen = "recruitment"
            recruitment_screen.initialize_screen(target)
        elif action_type == "feed":
            # Taming mechanic: feed food to wild mount
            taming_food = self._get_taming_food(current_player)
            if not taming_food:
                self.add_to_log("No food available for taming!")
                return
            food_card, taming_chance = taming_food[0]
            food_name = food_card.get_current_data().get("Name", "food")

            # Consume the food card
            if food_card in current_player.inventory:
                current_player.inventory.remove(food_card)

            # Mark action used
            current_player.action_used = True

            # Roll for taming
            roll = random.randint(1, 100)
            if roll <= taming_chance:
                # Success: remove unit from grid, add tamed version to party
                hex_pos = target.position
                if hex_pos:
                    self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] = None
                if target in self.hex_grid.units:
                    self.hex_grid.units.remove(target)
                tamed_name = target.second_state.get("name", target.name)
                # Load card and add to party
                card_data = load_card(target.card_id)
                if card_data:
                    tamed_card = InventoryCard(card_data)
                    game.current_party.append(tamed_card)
                self.add_to_log(f"Fed {food_name} to {target.name} - {tamed_name} tamed!")
                self.add_defeat_notification(f"{tamed_name} tamed!")
            else:
                # Failure
                self.add_to_log(f"{target.name} rejected the {food_name}! ({taming_chance}% chance)")

            self.player_info_label.set_text(self.get_player_info())
            if current_player.action_used and not current_player.movement_used:
                self.player_mode = "movement"
        elif action_type == "heal_player":
            # Healer healing another player in multiplayer
            message, _ = current_player.heal_target(target, self.hex_grid)
            self.add_to_log(message)
            self.player_info_label.set_text(self.get_player_info())
            self._create_equipment_toolbar()
        elif action_type == "order_enemy":
            # Boss Disguise: reorder enemy's behavior tree
            self._open_enemy_order_editor(target, current_player)
        elif action_type == "give_to_player":
            game.current_screen = "card_giving"
            card_giving_screen.initialize_screen(data)
        elif action_type == "search_junk_pile":
            pile = data
            remaining = getattr(pile, '_junk_searches_remaining', 0)
            chance = getattr(pile, '_junk_search_chance', 50)
            if remaining > 0:
                roll = random.randint(1, 100)
                if roll <= chance:
                    # Draw a card from the campaign junk deck
                    junk_deck_path = getattr(self, 'current_junk_deck', None)
                    drawn_card = None
                    if junk_deck_path:
                        drawn_card = self.card_manager.draw_from_deck(junk_deck_path)
                    if drawn_card:
                        party_msg = add_card_to_player(drawn_card)
                        if party_msg:
                            self.add_to_log(party_msg)
                        card_name = drawn_card.get_current_data().get("Name", "something")
                        self.add_to_log(f"Found {card_name} in the junk pile!")
                    else:
                        self.add_to_log("Searched the junk pile but the deck is empty.")
                else:
                    self.add_to_log("Searched the junk pile but found nothing useful.")
                pile._junk_searches_remaining = remaining - 1
                pile._junk_search_chance = max(10, chance - 15)
                current_player.action_used = True
                self.player_info_label.set_text(self.get_player_info())
            else:
                self.add_to_log("This junk pile has been thoroughly searched.")
        elif action_type == "move_junk_pile":
            self.junk_pile_move_unit = data
            self.player_mode = "junk_pile_move"
            self.add_to_log("Select destination for junk pile (or click yourself to pick up)")
        elif action_type == "move_body":
            self.body_move_unit = data
            self.player_mode = "body_move"
            self.add_to_log(f"Select destination for {data.name}'s body (or click yourself to pick up)")
        elif action_type == "revive_body":
            # Use healer super attack to revive the dead unit
            message, defeated_units = current_player.use_super_attack(data, self.hex_grid)
            self.add_to_log(message)
            self.player_info_label.set_text(self.get_player_info())
            self._create_equipment_toolbar()
            self.rebuild_left_panel()

    def _open_enemy_order_editor(self, unit, player):
        """Open behavior tree editor for an enemy unit (Spy Boss Disguise ability).
        Uses the existing behavior tree reorder pattern: cycles the top behavior to the bottom."""
        from unit import Unit
        # Store original before first modification
        if unit not in player.ordered_enemy_originals:
            player.ordered_enemy_originals[unit] = list(unit.behavior_tree)
        if unit not in player.ordered_enemies:
            player.ordered_enemies.append(unit)

        # Cycle the behavior tree: move first entry to the end
        if len(unit.behavior_tree) > 1:
            unit.behavior_tree.append(unit.behavior_tree.pop(0))

        # Show what the new priority is
        top_behavior = unit.behavior_tree[0] if unit.behavior_tree else "none"
        info = Unit.BEHAVIOR_REGISTRY.get(top_behavior, {})
        label = info.get("label", top_behavior)
        self.add_to_log(f"Ordered {unit.name} - new priority: {label}")

        # Consume super charge
        player.super_charge = 0
        player.super_attack_ready = False
        self.player_info_label.set_text(self.get_player_info())

    def _handle_equip_popup_selection(self, slot_type, data):
        """Handle equip/unequip from the popup menu."""
        if data is None:
            self._close_equip_popup()
            return

        p = game.current_player

        if slot_type == "melee":
            if data == "unequip":
                old_melee = p.melee_weapon
                p.melee_weapon = None
                p.attacks["melee"] = dict(p.default_attacks["melee"])
                # If both-type weapon was in projectile slot too, clear it
                if p.projectile_weapon and p.projectile_weapon is old_melee:
                    p.projectile_weapon = None
                    p.attacks["projectile"] = dict(p.default_attacks["projectile"])
                    p.projectile_range = p.default_projectile_range
                self.add_to_log("Unequipped melee weapon")
            else:
                p.equip_weapon(data)
                name = data.get_current_data().get("Name", "???")
                self.add_to_log(f"Equipped {name}")

        elif slot_type == "projectile":
            if data == "unequip":
                # If both-type weapon, clear melee too
                if p.melee_weapon and p.projectile_weapon is p.melee_weapon:
                    p.melee_weapon = None
                    p.attacks["melee"] = dict(p.default_attacks["melee"])
                p.projectile_weapon = None
                p.attacks["projectile"] = dict(p.default_attacks["projectile"])
                p.projectile_range = p.default_projectile_range
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
            # Check if it's a junk pile card — enter junk-pile-place mode
            if data and data.get_current_data().get("_is_junk_pile") == "true":
                self.junk_pile_place_card = data
                self.player_mode = "junk_pile_place"
                self.add_to_log("Click adjacent empty hex to place junk pile")
                self._close_equip_popup()
                return
            # Check if it's a dead body card — enter body-place mode
            if data and data.get_current_data().get("_is_dead_body") == "true":
                body_name = data.get_current_data().get("Name", "???")
                self.body_place_card = data
                self.player_mode = "body_place"
                self.add_to_log(f"Click adjacent empty hex to place {body_name}'s body")
                self._close_equip_popup()
                return
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

        # Handle defeated units - defer grid removal until animations finish
        for defeated_unit in defeated_units:
            self.pending_defeats.append(defeated_unit)
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

    def _is_recruitable(self, unit):
        """Check if a unit can be recruited. Neutral NPCs are always recruitable.
        Allied NPCs are recruitable if not already in the current party."""
        if not unit or not hasattr(unit, 'allegiance') or isinstance(unit, Player):
            return False
        if unit.allegiance == "Neutral":
            return True
        if unit.allegiance == "Allied":
            # Already in party? Check card_id against party card IDs
            party_ids = {card.card_data.get("id") for card in game.current_party}
            return unit.card_id not in party_ids
        return False

    def _get_adjacent_recruitable_npcs(self):
        """Get list of recruitable NPCs adjacent to the player."""
        if not game.current_player or not game.current_player.position:
            return []

        adjacent_hexes = self.hex_grid.get_adjacent_hexes(*game.current_player.position)
        recruitable_npcs = []

        for row, col in adjacent_hexes:
            if 0 <= row < self.hex_grid.rows and 0 <= col < self.hex_grid.cols:
                unit = self.hex_grid.grid[row][col].get("unit")
                if unit and self._is_recruitable(unit):
                    recruitable_npcs.append(unit)

        return recruitable_npcs

    def _get_adjacent_dead_bodies(self):
        """Get list of dead units adjacent to the current player."""
        player = game.current_player
        if not player or not player.position:
            return []
        result = []
        for r, c in self.hex_grid.get_adjacent_hexes(*player.position):
            if 0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols:
                unit = self.hex_grid.grid[r][c].get("unit")
                if unit and getattr(unit, 'hp', 1) <= 0 and getattr(unit, '_death_processed', False):
                    result.append(unit)
        return result

    def _calculate_recruitment_cost(self, unit):
        """Calculate recruitment cost based on NPC stats: HP/10 + melee + ranged + movement + 5"""
        if not unit:
            return 10
        hp_component = unit.max_hp // 10
        melee = unit.melee_damage if hasattr(unit, 'melee_damage') else 0
        ranged = unit.projectile_damage if hasattr(unit, 'projectile_damage') else 0
        movement = unit.movement if hasattr(unit, 'movement') else 3
        return hp_component + melee + ranged + movement + 5

    def _get_taming_food(self, player):
        """Get list of (card, taming_chance) tuples from player inventory, sorted by best chance first."""
        food_list = []
        for card in player.inventory:
            if card.current_state != 2:
                continue
            card_data = card.get_current_data()
            # Check for dedicated taming food (Taming_Chance field)
            taming_chance = card_data.get("Taming_Chance")
            if taming_chance:
                try:
                    chance = int(taming_chance)
                    if chance > 0:
                        food_list.append((card, chance))
                        continue
                except (ValueError, TypeError):
                    pass
            # Check for generic consumable with Use_HP (fallback 25% chance)
            if card_data.get("Use_HP"):
                food_list.append((card, 25))
        food_list.sort(key=lambda x: x[1], reverse=True)
        return food_list

    def show_instance_event(self, instance_card, target_player=None):
        """Show an instance event as a banner overlay."""
        # Use provided target player, or fall back to stored pending player, then current player
        if target_player is None:
            target_player = game.instance_manager.pending_instance_player or game.current_player

        # Update hex_grid reference in instance manager
        game.instance_manager.set_hex_grid(self.hex_grid)

        # Resolve the instance and get outcome using the correct target player
        try:
            outcome_text, needs_choice = game.instance_manager.resolve_instance(
                instance_card, self.hex_grid, target_player
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            outcome_text, needs_choice = "Error occurred.", False

        # Determine target player name for display
        target_name = target_player.name if target_player and target_player.name else "Player"

        # Set banner state
        self.event_banner_active = True
        self.event_banner_type = "instance"
        self.event_banner_start_time = pygame.time.get_ticks()
        self.event_banner_phase = "main"
        self.event_instance_card = instance_card
        self.event_instance_outcome_text = outcome_text
        self.event_instance_needs_choice = needs_choice
        self.event_instance_target_name = target_name
        self.event_instance_target_player = target_player
        self.event_instance_result_text = ""

        # Get choices if needed
        if needs_choice:
            self.event_instance_choices = game.instance_manager.get_pending_choices()
        else:
            self.event_instance_choices = []

        self._build_event_banner_buttons()

        # Log the event
        self.add_to_log(f"EVENT: {instance_card.name}")

    def resume_after_instance(self):
        """Called after an instance event is resolved to continue the turn."""
        # Show defeat notifications for any units killed by the instance event
        for name in game.instance_manager.defeated_units:
            self.add_defeat_notification(name)
        game.instance_manager.defeated_units.clear()

        # Check for pending quest offer from offer_quest instance outcome
        instance_quest_offer = game.instance_manager.get_pending_quest_offer()
        if instance_quest_offer:
            quest_card_id = instance_quest_offer.get("quest_card_id")
            quest_deck = instance_quest_offer.get("quest_deck")
            # Load the quest card
            quest_card = None
            if quest_card_id:
                card_data = load_card(quest_card_id)
                if card_data:
                    quest_card = InventoryCard(card_data)
            elif quest_deck:
                # Draw random quest from deck
                deck_path = resolve_deck_path(quest_deck)
                try:
                    with open(deck_path, 'r') as f:
                        deck_data = json.load(f)
                    card_ids = deck_data.get("cards", [])
                    if card_ids:
                        selected_id = random.choice(card_ids)
                        card_data = load_card(selected_id)
                        if card_data:
                            quest_card = InventoryCard(card_data)
                except Exception as e:
                    logger.error(f"Error loading quest from deck for instance offer: {e}")

            if quest_card:
                self._pending_instance_quest_offer = {"quest_card": quest_card}
                confirmation_screen.initialize_screen(
                    "A quest opportunity presents itself! Accept?",
                    ["Accept", "Decline"],
                    self._handle_instance_quest_offer_response
                )
                self.active_screen = "confirmation"
                return

        # If we're still in transition phase (instance was triggered by transition card),
        # complete the transition and move to player phase
        if self.turn_phase == "transition":
            # Complete transition phase processing
            self.hex_grid.on_turn_end()
            quest_results = game.current_quest_manager.update("turn_end", {}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)
            self._handle_quest_chain()

            # Check level completion (only matters for campaigns)
            level_complete = self.check_level_completion()
            if level_complete:
                self.current_level_idx += 1
                stages = self.campaign.get("stages") or self.campaign.get("levels", []) if self.campaign else []
                if self.campaign and self.current_level_idx < len(stages):
                    self.load_campaign_level()
                    if game.multiplayer_mode:
                        self.turn_phase = "multiplayer_player"
                        game.current_player_index = 0
                        self.hex_grid.active_turn_unit = game.players[0]
                        self.rebuild_left_panel()
                else:
                    self._show_campaign_complete()
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

        # Apply Turn_Start passives
        for msg in game.current_player.apply_passive_skills(self.hex_grid, "Turn_Start"):
            self.add_to_log(msg)
        self.update_turn_label()
        self.animating = self.check_animations()

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
                    self.turn_phase = "multiplayer_player"
                    game.current_player_index = 0
                    self.hex_grid.active_turn_unit = game.players[0]
                    self.rebuild_left_panel()
                else:
                    self.turn_phase = "player"
                    self.hex_grid.active_turn_unit = game.player
                self.is_player_turn = True
                self._start_player_turn()
            else:
                self._show_campaign_complete()
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
        """Process defensive location attacks against hostile units with autopan."""
        active_locations = self.hex_grid.get_active_defensive_locations()
        if not active_locations:
            self._pending_advance_after_banner = True
            return

        # Build queue: only locations that have garrison AND hostiles in range
        self._loc_defense_queue = []
        for pos, loc_data in active_locations:
            garrison = loc_data.get("garrison_npcs", [])
            if not garrison:
                continue
            # Pre-check: does this location have any defense that can hit a hostile?
            has_targets = False
            for defense in loc_data.get("defenses", []):
                if not defense.get("requires_npc") or defense.get("damage", 0) <= 0:
                    continue
                d_range = self.hex_grid.calculate_range(
                    pos, defense["range_distance"], defense["range_type"],
                    defense.get("include_position", False), defense.get("exclude_adjacent", False)
                )
                for hex_pos in d_range:
                    r, c = hex_pos
                    if 0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols:
                        unit = self.hex_grid.grid[r][c].get("unit")
                        if unit and hasattr(unit, 'allegiance') and unit.allegiance == "Hostile" and unit.hp > 0:
                            has_targets = True
                            break
                if has_targets:
                    break
            if has_targets:
                self._loc_defense_queue.append((pos, loc_data))

        if not self._loc_defense_queue:
            self._pending_advance_after_banner = True
            return

        self._loc_defense_active = True
        self._process_next_loc_defense()

    def _process_next_loc_defense(self):
        """Pan to the next location in the defense queue and fire."""
        if not self._loc_defense_queue:
            self._finish_loc_defense()
            return
        pos, loc_data = self._loc_defense_queue.pop(0)
        self._start_autopan(pos[0], pos[1], callback=lambda: self._fire_loc_defense(pos, loc_data))

    def _fire_loc_defense(self, pos, loc_data):
        """Build shot queue for this location and fire the first shot."""
        garrison = loc_data.get("garrison_npcs", [])
        if not garrison:
            self._loc_defense_wait_until = pygame.time.get_ticks() + 100
            return

        # Collect hostiles in range for each defense
        defense_data = []  # (defense_dict, hostiles_in_range_list)
        for defense in loc_data.get("defenses", []):
            if not defense.get("requires_npc") or defense.get("damage", 0) <= 0:
                continue
            d_range = self.hex_grid.calculate_range(
                pos, defense["range_distance"], defense["range_type"],
                defense.get("include_position", False), defense.get("exclude_adjacent", False)
            )
            hostiles_in_range = []
            for hex_pos in d_range:
                r, c = hex_pos
                if 0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols:
                    unit = self.hex_grid.grid[r][c].get("unit")
                    if unit and hasattr(unit, 'allegiance') and unit.allegiance == "Hostile" and unit.hp > 0:
                        hostiles_in_range.append(unit)
            if hostiles_in_range:
                defense_data.append((defense, hostiles_in_range))

        if not defense_data:
            self._loc_defense_wait_until = pygame.time.get_ticks() + 100
            return

        # Build shot queue: each garrison NPC fires each defense once
        loc_name = loc_data.get("card").get_current_data().get("Name", "Defense") if loc_data.get("card") else "Defense"
        self._loc_defense_shot_queue = []
        for npc in garrison:
            for defense, hostiles in defense_data:
                self._loc_defense_shot_queue.append({
                    "npc_name": npc.get("name", "Garrison NPC"),
                    "damage": defense.get("damage", 0),
                    "hostiles": hostiles,
                    "pos": pos,
                    "loc_name": loc_name,
                })

        # Fire first shot
        self._fire_next_defense_shot()

    def _fire_next_defense_shot(self):
        """Fire the next individual shot from the defense queue."""
        while self._loc_defense_shot_queue:
            shot = self._loc_defense_shot_queue.pop(0)
            alive = [u for u in shot["hostiles"] if u.hp > 0]
            if not alive:
                continue  # All targets from this defense are dead, skip

            target = random.choice(alive)
            target.hp -= shot["damage"]
            target.set_damage_text(shot["damage"])
            src = self.hex_grid.get_hex_center(*shot["pos"])
            if hasattr(self.hex_grid, 'attack_anims') and target.position:
                tgt = self.hex_grid.get_hex_center(*target.position)
                self.hex_grid.attack_anims.create_projectile(src, tgt)
            self.add_to_log(f"{shot['npc_name']} ({shot['loc_name']}) hits {target.name} for {shot['damage']} damage")

            # Set timer for next shot (stagger by 400ms)
            self._loc_defense_wait_until = pygame.time.get_ticks() + 400
            return

        # Queue exhausted — short wait then process deaths
        self._loc_defense_wait_until = pygame.time.get_ticks() + 200
        self._loc_defense_shot_queue = None  # Signal queue done

    def _process_loc_defense_deaths(self):
        """Process deaths from the most recent location defense volley, then continue queue."""
        dead_units = [u for u in self.hex_grid.units if u.hp <= 0 and not getattr(u, '_death_processed', False)]
        for dead_unit in dead_units:
            if dead_unit.position:
                row, col = dead_unit.position
                # Displace body off location hex (body stays in grid)
                if dead_unit.position in self.hex_grid.location_data:
                    for nr, nc in self.hex_grid.get_adjacent_hexes(row, col):
                        if ((nr, nc) not in self.hex_grid.location_data
                                and 0 <= nr < self.hex_grid.rows and 0 <= nc < self.hex_grid.cols
                                and self.hex_grid.grid[nr][nc]["accessible"]
                                and self.hex_grid.grid[nr][nc]["unit"] is None):
                            self.hex_grid.grid[row][col]["unit"] = None
                            dead_unit.position = (nr, nc)
                            self.hex_grid.grid[nr][nc]["unit"] = dead_unit
                            break
            dead_unit._death_processed = True
            self.add_to_log(f"{dead_unit.name} defeated")
            self.add_defeat_notification(dead_unit.name)
            self.card_manager.track_card_usage(dead_unit.card_id, {"action": "defeated", "screen": "game"})
            quest_results = game.current_quest_manager.update("unit_death", {"unit": dead_unit}, self.hex_grid, game.current_player)
            for quest, result, msg in quest_results:
                self.add_to_log(msg)
            self._handle_quest_chain()
        self._process_next_loc_defense()

    def _finish_loc_defense(self):
        """Clean up after all location defenses have fired."""
        self._loc_defense_active = False
        self._loc_defense_wait_until = None
        self._check_boss_encounter_completion()
        self.player_info_label.set_text(self.get_player_info())
        self._pending_advance_after_banner = True

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
                num_p = len(game.players)
                cycle = self.transition_target_cycle

                if cycle < num_p:
                    target_player = game.players[cycle]
                    target_label = target_player.name or f"Player {cycle + 1}"
                else:
                    target_player = game.players[0]  # Primary target for "All" cycle
                    target_label = "All Players"

                # Roll and apply to primary target
                selected_index, result_text, log_messages = game.transition_manager.process_transition_turn_with_index(
                    self.hex_grid, target_player
                )

                # For "All" cycle, also apply same outcome to remaining players
                if cycle >= num_p and 0 <= selected_index < len(all_outcomes):
                    outcome = all_outcomes[selected_index]
                    outcome_type = outcome.get("type", "none")
                    params = outcome.get("params", {})
                    for p in game.players[1:]:
                        extra_result = game.transition_manager.apply_outcome(outcome_type, params, self.hex_grid, p)
                        if extra_result:
                            result_text += f"\n{extra_result}"
                            log_messages.append(extra_result)

                self.transition_target_cycle = (self.transition_target_cycle + 1) % (num_p + 1)
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

            # Show the transition event as a banner overlay
            self._show_transition_banner(transition_card, all_outcomes, selected_index, result_text, target_label)
            return  # Wait for user to click OK

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            logger.error(f"Error in transition turn: {e}")
            logger.error(f"Full traceback:\n{tb_str}")
            self.add_to_log(f"[Transition Error]")
            # Skip to player phase on error (don't call advance_turn which would re-process transition)
            if game.multiplayer_mode:
                self.turn_phase = "multiplayer_player"
                game.current_player_index = 0
                self.hex_grid.active_turn_unit = game.players[0]
                self.rebuild_left_panel()
            else:
                self.turn_phase = "player"
                self.hex_grid.active_turn_unit = game.player
            self.is_player_turn = True
            self.update_turn_label()

    def _process_player_transition(self, player):
        """Process the player transition card at the start of a player's turn."""
        if not game.transition_manager.has_player_transition():
            return
        result = game.transition_manager.process_player_transition_turn(self.hex_grid, player)
        if result is None:
            return  # Outcome was 'none', no banner
        selected_index, outcome_text, result_text, log_messages = result
        for msg in log_messages:
            self.add_to_log(msg)
        self.player_info_label.set_text(self.get_player_info())
        # Show banner using the player transition card data
        transition_card = game.transition_manager.player_transition
        all_outcomes = transition_card.get_current_outcomes()
        player_name = getattr(player, 'name', None) or getattr(player, 'class_name', '')
        self._show_transition_banner(transition_card, all_outcomes, selected_index, result_text, player_name)

    def check_animations(self):
        animating = False
        # Update animations for all players (multiplayer or single player)
        all_players = self.hex_grid.players if self.hex_grid.players else ([self.hex_grid.player] if self.hex_grid.player else [])
        for player in all_players:
            if player and (player.animating or player.attack_flash or player.damage_text):
                player.update_animation(self.hex_grid)
                if player.animating:
                    animating = True
        for unit in self.hex_grid.units:
            if unit.animating:
                unit.update_animation(self.hex_grid)  # Pass grid
                animating = True
            elif unit.damage_text or unit.attack_flash:
                unit.update_animation(self.hex_grid)  # Update damage text/flash fade

        # Check for active attack animations
        if self.hex_grid.attack_anims.is_animating():
            animating = True

        # Check for pending NPC arrivals (quest NPCs moving to locations)
        if game.current_quest_manager.has_pending_arrivals():
            messages = game.current_quest_manager.update_pending_arrivals()
            for msg in messages:
                self.add_to_log(msg)
            animating = True  # Keep animating while there are pending arrivals

        # Process deferred unit removals once all animations finish
        if not animating and self.pending_defeats:
            for unit in self.pending_defeats:
                if getattr(unit, '_death_processed', False):
                    continue
                if unit.position:
                    row, col = unit.position
                    # Displace body off location hex (body stays in grid)
                    if unit.position in self.hex_grid.location_data:
                        for nr, nc in self.hex_grid.get_adjacent_hexes(row, col):
                            if ((nr, nc) not in self.hex_grid.location_data
                                    and 0 <= nr < self.hex_grid.rows and 0 <= nc < self.hex_grid.cols
                                    and self.hex_grid.grid[nr][nc]["accessible"]
                                    and self.hex_grid.grid[nr][nc]["unit"] is None):
                                self.hex_grid.grid[row][col]["unit"] = None
                                unit.position = (nr, nc)
                                self.hex_grid.grid[nr][nc]["unit"] = unit
                                break
                unit._death_processed = True
            self.pending_defeats.clear()
            self._check_boss_encounter_completion()

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
        # Event banner modal — block ALL other game input
        if self.event_banner_active:
            self._handle_event_banner(event)
            return
        # Dialogue popup modal — block ALL other game input
        if self.dialogue_active:
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self.dialogue_active = False
            return
        # ESC opens pause menu
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            game.current_screen = "pause_menu"
            pause_menu_screen.initialize_screen()
            return
        # Keyboard shortcuts to open menu tabs (i/c/p/s/q)
        if event.type == pygame.KEYDOWN and self._is_player_phase():
            tab_map = {
                pygame.K_i: "Inventory",
                pygame.K_c: "Crafting",
                pygame.K_p: "Party",
                pygame.K_s: "Skills",
                pygame.K_q: "Quests",
            }
            tab = tab_map.get(event.key)
            if tab:
                if self.attack_submenu_open:
                    self._close_attack_submenu()
                if self.action_choice_open:
                    self._close_action_choice_popup()
                game.current_screen = "tabbed_menu"
                tabbed_menu_screen.active_tab = tab
                tabbed_menu_screen.initialize_screen()
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
            # Check if it's the current player's turn (single-player: "player", multiplayer: "multiplayer_player")
            is_player_turn = self._is_player_phase()
            if event.button == 1 and hex_pos and is_player_turn:
                self.hex_grid.selected_hex = hex_pos
                unit = self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"]
                self.show_stats(unit, hex_pos)
                current_player = game.current_player

                # Handle defensive posture hex selection
                if self.player_mode == "defensive" and hex_pos in self.defensive_hex_options:
                    current_player.defensive_posture = True
                    current_player.defended_hex = hex_pos
                    current_player.defense_value = current_player.get_shield_defense_value()
                    shield_name = ""
                    if current_player.equipped_accessory:
                        acc_data = current_player.equipped_accessory.get_current_data()
                        if acc_data.get("Type") == "Shield":
                            shield_name = f" with {acc_data.get('Name', 'shield')}"
                    player_name = current_player.name if current_player.name else current_player.class_name
                    self.add_to_log(f"{player_name} takes a defensive posture{shield_name}! (Defense: {current_player.defense_value})")
                    self.player_mode = "movement"
                    self.defensive_hex_options = []
                    self.advance_turn()
                    return
                elif self.player_mode == "defensive":
                    # Clicked a non-valid hex while in defensive mode - cancel
                    self.player_mode = "movement"
                    self.defensive_hex_options = []
                    self.add_to_log("Cancelled defensive posture selection")
                    return

                # Handle body-move mode destination
                if self.player_mode == "body_move" and self.body_move_unit and hex_pos:
                    body = self.body_move_unit
                    adj = set(self.hex_grid.get_adjacent_hexes(*current_player.position))
                    if hex_pos == current_player.position:
                        # Pick up body into inventory
                        old_r, old_c = body.position
                        self.hex_grid.grid[old_r][old_c]["unit"] = None
                        if body in self.hex_grid.units:
                            self.hex_grid.units.remove(body)
                        body.position = None
                        full_card = load_card(body.card_id, silent=True)
                        if full_card:
                            body_card = InventoryCard(full_card)
                            body_card.card_data["data"]["_is_dead_body"] = "true"
                            body_card.card_data["data"]["_body_hp"] = str(body.hp)
                            body_card.card_data["data"]["_body_max_hp"] = str(body.max_hp)
                            current_player.inventory.append(body_card)
                        self.add_to_log(f"Picked up {body.name}'s body")
                        self.body_move_unit = None
                        self.player_mode = "movement"
                    elif (hex_pos in adj
                          and self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] is None
                          and self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]):
                        # Move body to target hex
                        old_r, old_c = body.position
                        self.hex_grid.grid[old_r][old_c]["unit"] = None
                        body.position = hex_pos
                        self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] = body
                        self.add_to_log(f"Moved {body.name}'s body")
                        self.body_move_unit = None
                        self.player_mode = "movement"
                    else:
                        # Invalid click — cancel
                        self.body_move_unit = None
                        self.player_mode = "movement"
                    return

                # Handle body-place mode destination
                if self.player_mode == "body_place" and self.body_place_card and hex_pos:
                    adj = set(self.hex_grid.get_adjacent_hexes(*current_player.position))
                    if (hex_pos in adj
                            and self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] is None
                            and self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]):
                        card_data = self.body_place_card.card_data
                        placed_unit = Unit(card_data)
                        placed_unit.hp = int(card_data["data"].get("_body_hp", 0))
                        placed_unit.max_hp = int(card_data["data"].get("_body_max_hp", placed_unit.max_hp))
                        placed_unit._death_processed = True
                        placed_unit.position = hex_pos
                        self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] = placed_unit
                        self.hex_grid.units.append(placed_unit)
                        if self.body_place_card in current_player.inventory:
                            current_player.inventory.remove(self.body_place_card)
                        self.add_to_log(f"Placed {placed_unit.name}'s body")
                        self.body_place_card = None
                        self.player_mode = "movement"
                    else:
                        # Invalid click — cancel
                        self.body_place_card = None
                        self.player_mode = "movement"
                    return

                # Handle junk-pile-move mode destination
                if self.player_mode == "junk_pile_move" and self.junk_pile_move_unit and hex_pos:
                    pile = self.junk_pile_move_unit
                    adj = set(self.hex_grid.get_adjacent_hexes(*current_player.position))
                    if hex_pos == current_player.position:
                        # Pick up junk pile into inventory
                        old_r, old_c = pile.position
                        self.hex_grid.grid[old_r][old_c]["unit"] = None
                        if pile in self.hex_grid.units:
                            self.hex_grid.units.remove(pile)
                        pile.position = None
                        full_card = load_card(pile.card_id, silent=True)
                        if full_card:
                            pile_card = InventoryCard(full_card)
                            pile_card.card_data["data"]["_is_junk_pile"] = "true"
                            pile_card.card_data["data"]["_junk_search_chance"] = str(getattr(pile, '_junk_search_chance', 0))
                            pile_card.card_data["data"]["_junk_searches_remaining"] = str(getattr(pile, '_junk_searches_remaining', 0))
                            current_player.inventory.append(pile_card)
                        self.add_to_log("Picked up junk pile")
                        self.junk_pile_move_unit = None
                        self.player_mode = "movement"
                    elif (hex_pos in adj
                          and self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] is None
                          and self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]):
                        # Move junk pile to target hex
                        old_r, old_c = pile.position
                        self.hex_grid.grid[old_r][old_c]["unit"] = None
                        pile.position = hex_pos
                        self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] = pile
                        self.add_to_log("Moved junk pile")
                        self.junk_pile_move_unit = None
                        self.player_mode = "movement"
                    else:
                        # Invalid click — cancel
                        self.junk_pile_move_unit = None
                        self.player_mode = "movement"
                    return

                # Handle junk-pile-place mode destination
                if self.player_mode == "junk_pile_place" and self.junk_pile_place_card and hex_pos:
                    adj = set(self.hex_grid.get_adjacent_hexes(*current_player.position))
                    if (hex_pos in adj
                            and self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] is None
                            and self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]):
                        card_data = self.junk_pile_place_card.card_data
                        placed_pile = Unit(card_data)
                        placed_pile.hp = 0
                        placed_pile._death_processed = True
                        placed_pile._is_junk_pile = True
                        placed_pile._junk_search_chance = int(card_data["data"].get("_junk_search_chance", 0))
                        placed_pile._junk_searches_remaining = int(card_data["data"].get("_junk_searches_remaining", 0))
                        placed_pile.position = hex_pos
                        self.hex_grid.grid[hex_pos[0]][hex_pos[1]]["unit"] = placed_pile
                        self.hex_grid.units.append(placed_pile)
                        if self.junk_pile_place_card in current_player.inventory:
                            current_player.inventory.remove(self.junk_pile_place_card)
                        self.add_to_log("Placed junk pile")
                        self.junk_pile_place_card = None
                        self.player_mode = "movement"
                    else:
                        # Invalid click — cancel
                        self.junk_pile_place_card = None
                        self.player_mode = "movement"
                    return

                # Handle behavior target selection (from party screen)
                if self.player_mode == "behavior_target_select" and self.behavior_target_type:
                    card_id = self.behavior_target_npc_card_id
                    target_ref = None
                    if self.behavior_target_type == "follow_target":
                        # Accept player or allied unit
                        if hex_pos == current_player.position:
                            target_ref = "player_0"
                        elif unit and isinstance(unit, Unit) and unit.allegiance == "Allied":
                            target_ref = unit.card_id
                        # Check other players in multiplayer
                        if not target_ref and hasattr(game, 'players') and game.players:
                            for i, p in enumerate(game.players):
                                if p.position == hex_pos:
                                    target_ref = f"player_{i}"
                                    break
                    elif self.behavior_target_type == "attack_target":
                        # Accept hostile unit
                        if unit and isinstance(unit, Unit) and unit.allegiance == "Hostile":
                            target_ref = unit.card_id
                    if target_ref:
                        # Save target to overrides and deployed unit
                        if card_id not in game.party_behavior_overrides:
                            game.party_behavior_overrides[card_id] = {"tree": ["attack_closest"]}
                        if self.behavior_target_type == "follow_target":
                            game.party_behavior_overrides[card_id]["follow_target"] = target_ref
                        else:
                            game.party_behavior_overrides[card_id]["attack_target"] = target_ref
                        # Update deployed unit if exists
                        for u in self.hex_grid.units:
                            if u.card_id == card_id and u.allegiance == "Allied":
                                if self.behavior_target_type == "follow_target":
                                    u.behavior_follow_target = target_ref
                                else:
                                    u.behavior_attack_target = target_ref
                                break
                        target_name = target_ref
                        if unit:
                            target_name = getattr(unit, 'name', target_ref)
                        elif target_ref.startswith("player_"):
                            target_name = current_player.name or current_player.class_name
                        self.add_to_log(f"Behavior target set: {target_name}")
                    else:
                        self.add_to_log("Invalid target for this behavior type")
                    self.player_mode = "movement"
                    self.behavior_target_type = None
                    self.behavior_target_npc_card_id = None
                    return

                # Healer tower healing: manning healer (no melee weapon) clicks friendly unit
                if (current_player.is_manning() and current_player.is_healer
                    and current_player.melee_weapon is None
                    and not current_player.action_used
                    and self.player_mode not in ("super_attack",)):
                    # Check for allied/neutral unit or player that needs healing
                    heal_target = None
                    if unit and isinstance(unit, Unit) and unit.allegiance in ("Allied", "Neutral") and unit.hp < unit.max_hp:
                        heal_target = unit
                    elif game.multiplayer_mode:
                        for p in game.players:
                            if p is not current_player and p.position == hex_pos and p.hp > 0 and p.hp < p.max_hp:
                                heal_target = p
                                break
                    if heal_target:
                        tower_range = current_player.get_manning_attack_range(self.hex_grid)
                        if hex_pos in tower_range or current_player.manning_weapon_mode == "personal":
                            message, _ = current_player.heal_target(heal_target, self.hex_grid)
                            self.add_to_log(message)
                            # Green projectile animation from tower to target
                            if hasattr(self.hex_grid, 'attack_anims'):
                                src = self.hex_grid.get_hex_center(*current_player.manning_location)
                                tgt = self.hex_grid.get_hex_center(*hex_pos)
                                self.hex_grid.attack_anims.create_projectile(src, tgt, color=(0, 200, 100))
                            self.player_info_label.set_text(self.get_player_info())
                            return

                # Tower attack: manning player clicks on a hostile unit (tower weapon mode only)
                if (current_player.is_manning() and current_player.manning_weapon_mode == "tower"
                    and unit and isinstance(unit, Unit) and unit.allegiance == "Hostile"
                    and (not current_player.action_used or (current_player.double_attack_active and current_player.warrior_attacks_remaining > 0))
                    and self.player_mode not in ("super_attack",)):
                    tower_range = current_player.get_manning_attack_range(self.hex_grid)
                    if hex_pos in tower_range:
                        defenses = current_player.get_manning_defenses(self.hex_grid)
                        if defenses:
                            best_defense = max(defenses, key=lambda d: d.get("damage", 0))
                            damage = best_defense.get("damage", 0)
                            best_range = best_defense.get("range_distance", 0)
                            loc_data = self.hex_grid.location_data.get(current_player.manning_location)
                            loc_name = loc_data["card"].get_current_data().get("Name", "Tower") if loc_data and loc_data.get("card") else "Tower"

                            # Ranger piercing tower shot
                            if current_player.piercing_projectile:
                                tower_row, tower_col = current_player.manning_location
                                attack_line = []
                                for direction in DIRECTIONS:
                                    line = self.hex_grid.get_line(tower_row, tower_col, direction, best_range)
                                    if hex_pos in line:
                                        attack_line = line
                                        break

                                if attack_line:
                                    # Animate to end of line
                                    end_pos = attack_line[-1]
                                    anim = None
                                    delay = 0
                                    if hasattr(self.hex_grid, 'attack_anims'):
                                        src = self.hex_grid.get_hex_center(*current_player.manning_location)
                                        tgt = self.hex_grid.get_hex_center(*end_pos)
                                        anim = self.hex_grid.attack_anims.create_projectile(src, tgt)
                                        delay = self.hex_grid.attack_anims.get_max_remaining_ms()
                                    # Hit ALL hostile units along the line
                                    hit_units = []
                                    for line_pos in attack_line:
                                        for u in self.hex_grid.units:
                                            if u.position == line_pos and isinstance(u, Unit) and u.allegiance == "Hostile" and u.hp > 0:
                                                u.hp -= damage
                                                u.set_damage_text(damage, delay, anim=anim)
                                                hit_units.append(u)
                                                if u.hp <= 0:
                                                    self.pending_defeats.append(u)
                                    hit_names = ", ".join(u.name for u in hit_units) if hit_units else unit.name
                                    self.add_to_log(f"{loc_name} piercing shot hits {hit_names} for {damage} damage!")
                                    # Warrior dual strike action tracking
                                    current_player.add_super_charge()
                                    if current_player.double_attack_active:
                                        current_player.warrior_attacks_remaining -= 1
                                        if current_player.warrior_attacks_remaining <= 0:
                                            current_player.action_used = True
                                    else:
                                        current_player.action_used = True
                                    self.player_info_label.set_text(self.get_player_info())
                                    return

                            # Standard tower shot (single target)
                            anim = None
                            delay = 0
                            if hasattr(self.hex_grid, 'attack_anims'):
                                src = self.hex_grid.get_hex_center(*current_player.manning_location)
                                tgt = self.hex_grid.get_hex_center(*hex_pos)
                                anim = self.hex_grid.attack_anims.create_projectile(src, tgt)
                                delay = self.hex_grid.attack_anims.get_max_remaining_ms()
                            unit.hp -= damage
                            unit.set_damage_text(damage, delay, anim=anim)
                            # Warrior dual strike action tracking
                            current_player.add_super_charge()
                            if current_player.double_attack_active:
                                current_player.warrior_attacks_remaining -= 1
                                if current_player.warrior_attacks_remaining <= 0:
                                    current_player.action_used = True
                            else:
                                current_player.action_used = True
                            self.add_to_log(f"{loc_name} fires at {unit.name} for {damage} damage!")
                            if unit.hp <= 0:
                                self.pending_defeats.append(unit)
                            self.player_info_label.set_text(self.get_player_info())
                    else:
                        self.add_to_log("Target not in tower range")
                    return

                # Junk pile interaction (before dead body check)
                if (not self.selected_attack and unit and isinstance(unit, Unit)
                        and getattr(unit, '_is_junk_pile', False)
                        and self.hex_grid.hex_distance(current_player.position, hex_pos) == 1
                        and self.player_mode not in ("body_move", "body_place", "junk_pile_move", "junk_pile_place", "recruit", "skill", "item", "super_attack")):
                    actions = []
                    remaining = getattr(unit, '_junk_searches_remaining', 0)
                    if remaining > 0 and not current_player.action_used:
                        chance = getattr(unit, '_junk_search_chance', 50)
                        actions.append((f"Search Junk Pile ({remaining} left, {chance}%)", "search_junk_pile", unit))
                    actions.append(("Move Junk Pile", "move_junk_pile", unit))
                    self._open_action_choice_popup(unit, hex_pos, actions)
                    return

                # Dead body interaction
                if (not self.selected_attack and unit and isinstance(unit, Unit) and unit.hp <= 0
                        and getattr(unit, '_death_processed', False)
                        and not getattr(unit, '_is_junk_pile', False)
                        and self.hex_grid.hex_distance(current_player.position, hex_pos) == 1
                        and self.player_mode not in ("body_move", "body_place", "junk_pile_move", "junk_pile_place", "recruit", "skill", "item", "super_attack")):
                    actions = [("Move Body", "move_body", unit)]
                    # Healer with super ready can revive
                    if (current_player.is_healer and current_player.super_attack_ready
                            and not current_player.action_used):
                        actions.insert(0, (f"Revive {unit.name}", "revive_body", unit))
                    if len(actions) == 1:
                        self._open_action_choice_popup(unit, hex_pos, actions)
                    else:
                        self._open_action_choice_popup(unit, hex_pos, actions)
                    return

                # Auto-detect available actions when clicking on a unit (skip in recruit/skill modes)
                if not self.selected_attack and unit and isinstance(unit, Unit) and unit.hp > 0 and self.player_mode not in ("recruit", "skill", "item"):
                    available_actions = []
                    # Attack options only available if action not yet used
                    if not current_player.action_used:
                        melee_range = current_player.get_melee_attack_range(self.hex_grid)
                        proj_range = current_player.get_projectile_attack_range(self.hex_grid, game.current_party)
                        if melee_range and hex_pos in melee_range:
                            # Healer with no melee weapon: show heal label
                            if current_player.is_healer and current_player.melee_weapon is None:
                                available_actions.append(("Heal (20 HP)", "melee", None))
                            else:
                                melee_name = current_player.attacks["melee"]["name"]
                                melee_dmg = current_player.attacks["melee"]["damage"]
                                available_actions.append((f"Melee: {melee_name} ({melee_dmg} dmg)", "melee", None))
                        if proj_range and hex_pos in proj_range:
                            proj_name = current_player.attacks["projectile"]["name"]
                            proj_dmg = current_player.attacks["projectile"]["damage"]
                            available_actions.append((f"Proj: {proj_name} ({proj_dmg} dmg)", "projectile", None))
                    # Recruit option available regardless of action_used
                    if self._is_recruitable(unit) and self.hex_grid.hex_distance(current_player.position, hex_pos) == 1:
                        cost = self._calculate_recruitment_cost(unit)
                        available_actions.append((f"Recruit {unit.name} (Cost: {cost})", "recruit", unit))
                    # Feed option for taming wild mounts
                    if (not current_player.action_used and
                        unit.allegiance == "Neutral" and
                        self.hex_grid.hex_distance(current_player.position, hex_pos) == 1 and
                        unit.states == 2 and unit.current_state == 1 and
                        unit.special_skill == "Mount"):
                        taming_food = self._get_taming_food(current_player)
                        if taming_food:
                            best_chance = taming_food[0][1]
                            available_actions.append((f"Feed {unit.name} ({best_chance}% tame)", "feed", unit))
                    # Boss Disguise: Order enemy
                    if (getattr(current_player, 'is_boss_disguised', False)
                        and current_player.super_attack_ready
                        and unit.allegiance == "Hostile" and unit.hp > 0):
                        available_actions.append((f"Order {unit.name}", "order_enemy", unit))
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
                        elif action_type == "feed":
                            self._handle_action_choice("feed", available_actions[0][2])
                            return
                        elif action_type == "order_enemy":
                            self._handle_action_choice("order_enemy", available_actions[0][2])
                            return
                    elif len(available_actions) >= 2:
                        self._open_action_choice_popup(unit, hex_pos, available_actions)
                        return
                # Give card / Heal adjacent player in multiplayer
                if (not self.selected_attack and unit and isinstance(unit, Player)
                    and unit is not current_player and game.multiplayer_mode
                    and self.hex_grid.hex_distance(current_player.position, hex_pos) == 1
                    and self.player_mode not in ("recruit", "skill", "item")):
                    target_name = unit.name or unit.class_name
                    actions = [(f"Give to {target_name}", "give_to_player", unit)]
                    # Healer can heal other players
                    if (current_player.is_healer and current_player.melee_weapon is None
                        and not current_player.action_used and unit.hp > 0 and unit.hp < unit.max_hp):
                        actions.insert(0, ("Heal (20 HP)", "heal_player", unit))
                    if len(actions) == 1:
                        if actions[0][1] == "heal_player":
                            message, _ = current_player.heal_target(unit, self.hex_grid)
                            self.add_to_log(message)
                            self.player_info_label.set_text(self.get_player_info())
                            self._create_equipment_toolbar()
                            return
                    self._open_action_choice_popup(unit, hex_pos, actions)
                    return
                if self.player_mode == "attack" and self.selected_attack and unit and isinstance(unit, Unit) and unit.hp > 0:
                    message, result = current_player.attack(unit, self.selected_attack, self.hex_grid, game.current_party)
                    self.add_to_log(message)
                    if message:
                        # Handle piercing attack (returns list of hit units)
                        if isinstance(result, list):
                            for hit_unit, hit_dmg, hit_defeated in result:
                                hit_unit.attack_flash = True
                                hit_unit.flash_start = pygame.time.get_ticks()
                                if hit_defeated:
                                    self.pending_defeats.append(hit_unit)
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
                                self.pending_defeats.append(unit)
                                self.add_to_log(f"{unit.name} defeated")
                                self.add_defeat_notification(unit.name)
                                self.card_manager.track_card_usage(unit.card_id, {"action": "defeated", "screen": "game"})
                                quest_results = game.current_quest_manager.update("unit_death", {"unit": unit}, self.hex_grid, current_player)
                                for quest, qresult, msg in quest_results:
                                    self.add_to_log(msg)
                                self._handle_quest_chain()
                                self.update_quest_button()
                                self.show_stats(None)
                        self._check_ammo_runout_banner(current_player)
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
                        # Check if all enemy spawns destroyed — trigger boss phase 2
                        if self.boss_encounter_phase == 1 and self.hex_grid.are_all_enemy_spawns_destroyed():
                            self._trigger_boss_phase_2()
                        self._check_ammo_runout_banner(current_player)
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
                            self.pending_defeats.append(unit)
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
                    # Check if clicked unit is adjacent and recruitable
                    distance = self.hex_grid.hex_distance(current_player.position, hex_pos)
                    if distance == 1 and self._is_recruitable(unit):
                        # Open recruitment screen
                        game.current_screen = "recruitment"
                        recruitment_screen.initialize_screen(unit)
                    elif not self._is_recruitable(unit):
                        self.add_to_log(f"{unit.name} cannot be recruited")
                    else:
                        self.add_to_log("NPC is not adjacent to you")
                elif self.player_mode == "super_attack":
                    # Ranger Sniper Mode: manning tower, click any visible hostile
                    if current_player.piercing_projectile and current_player.is_manning():
                        if unit and isinstance(unit, Unit) and unit.allegiance == "Hostile" and unit.hp > 0:
                            message, defeated_units = current_player.use_super_attack(unit, self.hex_grid)
                            self.add_to_log(message)
                            # Projectile animation from tower to target
                            if hasattr(self.hex_grid, 'attack_anims'):
                                src = self.hex_grid.get_hex_center(*current_player.manning_location)
                                tgt = self.hex_grid.get_hex_center(*hex_pos)
                                self.hex_grid.attack_anims.create_projectile(src, tgt)
                            for defeated_unit in defeated_units:
                                self.pending_defeats.append(defeated_unit)
                            self.player_info_label.set_text(self.get_player_info())
                        else:
                            self.add_to_log("Select a visible hostile enemy for Sniper Shot")
                        self.player_mode = "movement"
                    else:
                        # Healer Revive: find dead unit/player at clicked hex
                        revive_target = None
                        # Check units (including dead ones stored with positions)
                        for u in self.hex_grid.units:
                            if u.position == hex_pos and u.hp <= 0:
                                revive_target = u
                                break
                        # Check other players in multiplayer
                        if not revive_target and game.multiplayer_mode:
                            for p in game.players:
                                if p is not current_player and p.position == hex_pos and p.hp <= 0:
                                    revive_target = p
                                    break
                        if revive_target:
                            message, defeated_units = current_player.use_super_attack(revive_target, self.hex_grid)
                            self.add_to_log(message)
                            self.player_info_label.set_text(self.get_player_info())
                        else:
                            self.add_to_log("No dead unit at that location to revive")
                        self.player_mode = "movement"
                elif self.player_mode == "special_attack" and unit and isinstance(unit, Unit):
                    # Execute special attack on target
                    self._execute_special_attack(unit)
                elif hex_pos == current_player.position and current_player.is_healer and current_player.melee_weapon is None and not current_player.action_used and current_player.hp < current_player.max_hp:
                    # Healer self-heal: clicking own hex heals self
                    message, _ = current_player.heal_target(current_player, self.hex_grid)
                    self.add_to_log(message)
                    self.player_info_label.set_text(self.get_player_info())
                    self._create_equipment_toolbar()
                elif hex_pos == current_player.position and self.hex_grid.is_location_hex(hex_pos[0], hex_pos[1]) and not current_player.is_manning():
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
                elif not current_player.movement_used and not unit and not current_player.is_manning():
                    path = self.hex_grid.find_path(current_player.position, hex_pos, moving_unit=current_player)
                    effective_movement = current_player.get_effective_movement(game.current_party)
                    if path and len(path) - 1 <= effective_movement:
                        pre_move_pos = current_player.position  # Save before moving
                        success, msg = self.hex_grid.move_unit(current_player, *hex_pos)
                        if success:
                            self.add_to_log(msg)
                            current_player.movement_used = True
                            # Scout: +1 super charge when using 2nd move
                            if (current_player.special_attack == "Double Move"
                                and current_player._movement_count == 2):
                                current_player.add_super_charge()
                            # Scout sprint: consume super charge on 3rd move
                            if (current_player.special_attack == "Double Move"
                                and current_player._movement_count == 3):
                                current_player.super_charge = 0
                                current_player.super_attack_ready = False
                                self.add_to_log(f"{current_player.name or current_player.class_name} used SPRINT!")
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
                                            current_player.leave_manning()
                                            self.add_to_log(f"Entering {hex_data['linked_level']}")
                                            self._snapshot_level_state(exclude_units=[])
                                            self.hex_grid.load_level(linked_level_file, self.card_manager, current_player)
                                            self.current_level_file = linked_level_file
                                            self._restore_level_state(linked_level_file)
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
                                            current_player.moves_per_turn = current_player.base_moves_per_turn
                                            current_player.action_used = False
                                            current_player.reset_double_attack()
                                            break
                                        else:
                                            self.add_to_log(f"Linked level file not found: {hex_data['linked_level']}")
                                    break  # Exit loop after handling this hex
                            # Check for teleport pad
                            if self.hex_grid.is_teleport_pad(hex_pos[0], hex_pos[1]):
                                pad_id = self.hex_grid.get_teleport_pad_id(hex_pos[0], hex_pos[1])
                                dest = self._find_teleport_destination(pad_id)
                                if dest:
                                    self.pending_teleport = {
                                        "pad_id": pad_id,
                                        "dest_pad_id": dest["dest_pad_id"],
                                        "dest_level_file": dest["dest_level_file"],
                                        "dest_stage_id": dest["dest_stage_id"],
                                        "dest_name": dest["dest_name"],
                                        "player_pre_pos": pre_move_pos,
                                        "player": current_player
                                    }
                                    game.current_screen = "confirmation"
                                    confirmation_screen.initialize_screen(
                                        f"Teleport to {dest['dest_name']}?",
                                        options=["Yes", "No"],
                                        callback=self._handle_teleport_confirm
                                    )
                                    return
                                else:
                                    self.add_to_log(f"Teleport pad '{pad_id}' is not linked to any destination")
                                    # Cancel move
                                    if current_player.position:
                                        r, c = current_player.position
                                        if self.hex_grid.grid[r][c]["unit"] is current_player:
                                            self.hex_grid.grid[r][c]["unit"] = None
                                    current_player.position = pre_move_pos
                                    self.hex_grid.grid[pre_move_pos[0]][pre_move_pos[1]]["unit"] = current_player
                                    current_player.movement_used = False
                            # Check for location hex
                            if self.hex_grid.is_location_hex(hex_pos[0], hex_pos[1]):
                                loc_data = self.hex_grid.location_data.get((hex_pos[0], hex_pos[1]))
                                loc_card = loc_data.get("card") if loc_data else None

                                if loc_card:
                                    # Queue location UI to show after movement animation completes
                                    self.pending_location = {
                                        "card": loc_card,
                                        "pos": hex_pos,
                                        "hex_grid": self.hex_grid
                                    }
                                else:
                                    # Defer card draw until animation finishes
                                    self.pending_location = {
                                        "card": None,
                                        "pos": hex_pos,
                                        "hex_grid": self.hex_grid,
                                        "needs_draw": True
                                    }
                                    # Don't show immediately - will show after animation in draw()

                            self.player_info_label.set_text(self.get_player_info())
                    else:
                        self.add_to_log("No valid path within movement range")
            elif event.button in (2, 3) and hex_pos:  # Middle mouse (2) or right-click (3) to pan
                # Cancel autopan if player manually pans
                if self.autopan_active:
                    self.autopan_active = False
                    self.autopan_callback = None
                self.dragging = True
                self.drag_button = event.button
                self.drag_start_x, self.drag_start_y = pos
                self.start_view_offset_x, self.start_view_offset_y = self.hex_grid.view_offset_x, self.hex_grid.view_offset_y
        elif event.type == pygame.MOUSEBUTTONUP and event.button in (2, 3):
            was_drag = False
            if hasattr(self, 'drag_button') and event.button == self.drag_button:
                # Check if mouse actually moved (drag vs click)
                dx = abs(event.pos[0] - self.drag_start_x)
                dy = abs(event.pos[1] - self.drag_start_y)
                was_drag = dx > 5 or dy > 5
                self.dragging = False
            # Right-click cancels body-move/body-place/junk-pile modes
            if event.button == 3 and not was_drag and self._is_player_phase():
                if self.player_mode in ("body_move", "body_place", "junk_pile_move", "junk_pile_place"):
                    self.body_move_unit = None
                    self.body_place_card = None
                    self.junk_pile_move_unit = None
                    self.junk_pile_place_card = None
                    self.player_mode = "movement"
                    self.add_to_log("Cancelled")
            # Right-click on player's own hex without dragging = enter defend mode
            if event.button == 3 and not was_drag and self._is_player_phase():
                hex_pos = self.hex_grid.get_hex_at_pixel(event.pos[0], event.pos[1])
                current_player = game.current_player
                if hex_pos and hex_pos == current_player.position and current_player.hp > 0:
                    if self.player_mode == "defensive":
                        self.player_mode = "movement"
                        self.defensive_hex_options = []
                        self.add_to_log("Cancelled defensive posture selection")
                    else:
                        self.player_mode = "defensive"
                        self.defensive_hex_options = self._get_defense_hex_options(current_player)
                        self.add_to_log("Choose a direction to defend (click a highlighted hex)")
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
                    elif self.hex_grid.is_attackable_location(hover_pos[0], hover_pos[1]):
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

            is_player_turn = self._is_player_phase()

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
                slot_types = ["menu", "melee", "projectile", "accessory", "tool", "action", "items"]
                for i, btn in enumerate(self.equip_toolbar_buttons):
                    if event.ui_element == btn:
                        if slot_types[i] == "menu":
                            if self.attack_submenu_open:
                                self._close_attack_submenu()
                            if self.action_choice_open:
                                self._close_action_choice_popup()
                            game.current_screen = "tabbed_menu"
                            tabbed_menu_screen.initialize_screen()
                            return
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
                        elif action_type == "super" and is_player_turn:
                            if not current_player.super_attack_ready:
                                self.add_to_log("Super attack not ready")
                            elif current_player.action_used:
                                self.add_to_log("Action already used this turn")
                            elif current_player.is_healer:
                                # Healer super: enter targeting mode to select dead unit to revive
                                self.player_mode = "super_attack"
                                self.selected_attack = None
                                self.selected_skill = None
                                self.add_to_log("Select an adjacent dead unit to Revive (click on them)")
                            elif current_player.piercing_projectile and current_player.is_manning():
                                # Ranger super: Sniper Mode - unlimited range shot from tower
                                self.player_mode = "super_attack"
                                self.selected_attack = None
                                self.selected_skill = None
                                self.add_to_log("SNIPER MODE! Click any visible enemy")
                            else:
                                message, defeated_units = current_player.use_super_attack(None, self.hex_grid)
                                self.add_to_log(message)
                                for defeated_unit in defeated_units:
                                    self.pending_defeats.append(defeated_unit)
                                    self.add_to_log(f"{defeated_unit.name} defeated")
                                    self.add_defeat_notification(defeated_unit.name)
                                self.player_mode = "movement"
                                self.player_info_label.set_text(self.get_player_info())
                        self._close_attack_submenu()
                        return

            # End Turn button (in toolbar, not left panel)
            if hasattr(self, 'end_turn_button') and event.ui_element == self.end_turn_button and is_player_turn:
                self.advance_turn()
                return

            # Defend button
            if hasattr(self, 'defend_button') and self.defend_button and event.ui_element == self.defend_button and is_player_turn:
                current_player = game.current_player
                if self.player_mode == "defensive":
                    # Cancel defensive mode
                    self.player_mode = "movement"
                    self.defensive_hex_options = []
                    self.add_to_log("Cancelled defensive posture selection")
                else:
                    self.player_mode = "defensive"
                    self.defensive_hex_options = self._get_defense_hex_options(current_player)
                    self.add_to_log("Choose a direction to defend (click a highlighted hex)")
                return

            # Toggle Weapon Mode button (tower/personal)
            if hasattr(self, 'toggle_weapon_button') and self.toggle_weapon_button and event.ui_element == self.toggle_weapon_button and is_player_turn:
                current_player = game.current_player
                new_mode = current_player.toggle_manning_weapon_mode()
                mode_name = "Tower Weapon" if new_mode == "tower" else "Personal Weapon"
                self.add_to_log(f"{current_player.name or current_player.class_name} switches to {mode_name}")
                self.player_info_label.set_text(self.get_player_info())
                self.rebuild_left_panel()
                return

            # Leave Tower button
            if hasattr(self, 'leave_tower_button') and self.leave_tower_button and event.ui_element == self.leave_tower_button and is_player_turn:
                current_player = game.current_player
                current_player.leave_manning()
                self.add_to_log(f"{current_player.name or current_player.class_name} leaves the tower")
                self.player_info_label.set_text(self.get_player_info())
                self.rebuild_left_panel()
                self._create_equipment_toolbar()
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
        self._update_autopan()
        current_player = game.current_player
        if not current_player:
            return
        is_player_turn = self._is_player_phase()
        # Check animation state early so range displays are accurate this frame
        self.animating = self.check_animations()
        player_alive = current_player.hp > 0
        effective_movement = current_player.get_effective_movement(game.current_party)
        movement_range = self.hex_grid.get_valid_moves(current_player.position, effective_movement, moving_unit=current_player) if is_player_turn and player_alive and not current_player.movement_used and not self.animating else None

        # Build list of all available attack ranges to display simultaneously
        attack_ranges = []

        # Defense range rings only for manned/garrisoned locations
        for def_pos, def_loc in self.hex_grid.get_active_defensive_locations():
            for defense in def_loc.get("defenses", []):
                if not defense.get("requires_npc"):
                    continue
                d_range = self.hex_grid.calculate_range(
                    def_pos, defense["range_distance"], defense["range_type"],
                    defense.get("include_position", False), defense.get("exclude_adjacent", False)
                )
                if d_range:
                    r, g, b = defense.get("color", (255, 165, 0))
                    alpha = 90
                    attack_ranges.append({
                        "range": d_range,
                        "color": (r, g, b, alpha),
                        "outline": (max(0, r - 60), max(0, g - 60), max(0, b - 60), alpha),
                        "inset": 0.40
                    })

        # Unit turn preview overlay
        if self.unit_preview_phase and self.unit_preview_unit and self.unit_preview_plan:
            preview_unit = self.unit_preview_unit
            plan = self.unit_preview_plan
            pos = preview_unit.position

            if self.unit_preview_phase == "range" and pos:
                action = plan["action"]
                range_hexes = set()
                range_color = (80, 140, 220, 100)  # Blue default (movement)

                if action in ("move", "move_melee", "move_projectile", "move_repair"):
                    range_hexes = self.hex_grid.get_movement_range(pos, preview_unit.movement, moving_unit=preview_unit)
                    range_color = (80, 140, 220, 100)
                elif action == "melee":
                    range_hexes = set(self.hex_grid.get_adjacent_hexes(*pos))
                    range_color = (220, 80, 60, 100)
                elif action == "projectile":
                    range_hexes = self.hex_grid.calculate_range(
                        pos, preview_unit.projectile_range, "line_of_sight", False, False)
                    if range_hexes is None:
                        range_hexes = set()
                    range_color = (220, 80, 60, 100)
                elif action in ("heal", "revive"):
                    range_hexes = self.hex_grid.calculate_range(
                        pos, preview_unit.heal_range, "area_effect", True, False)
                    if range_hexes is None:
                        range_hexes = set()
                    range_color = (60, 200, 80, 100)
                elif action == "repair":
                    range_hexes = set(self.hex_grid.get_adjacent_hexes(*pos))
                    range_color = (220, 200, 60, 100)

                if range_hexes:
                    attack_ranges.append({
                        "range": range_hexes,
                        "color": range_color,
                        "outline": (range_color[0], range_color[1], range_color[2], min(255, range_color[3] + 60)),
                        "inset": 0.55
                    })

            elif self.unit_preview_phase == "selection" and pos:
                elapsed = pygame.time.get_ticks() - self.unit_preview_start
                pulse_alpha = 120 + int(60 * math.sin(elapsed * 0.008))

                if plan.get("move_dest"):
                    attack_ranges.append({
                        "range": {plan["move_dest"]},
                        "color": (100, 255, 255, pulse_alpha),
                        "outline": (60, 200, 200, pulse_alpha),
                        "inset": 0.55
                    })
                if plan.get("target_pos"):
                    action = plan["action"]
                    if action in ("heal", "revive"):
                        sel_color = (80, 255, 100, pulse_alpha)
                        sel_outline = (40, 200, 60, pulse_alpha)
                    else:
                        sel_color = (255, 80, 60, pulse_alpha)
                        sel_outline = (200, 40, 30, pulse_alpha)
                    attack_ranges.append({
                        "range": {plan["target_pos"]},
                        "color": sel_color,
                        "outline": sel_outline,
                        "inset": 0.55
                    })

        has_action = not current_player.action_used or (current_player.double_attack_active and current_player.warrior_attacks_remaining > 0)
        if is_player_turn and player_alive and has_action and not self.animating and self.player_mode not in ("recruit", "item"):
            if current_player.is_manning():
                if current_player.manning_weapon_mode == "tower":
                    # Show tower attack range
                    tower_range = current_player.get_manning_attack_range(self.hex_grid)
                    if tower_range:
                        if current_player.is_healer and current_player.melee_weapon is None:
                            # Green for healing range
                            attack_ranges.append({"range": tower_range, "color": (0, 200, 100, 200), "outline": (0, 140, 70, 220), "inset": 0.55})
                        else:
                            # Gold for tower weapon range
                            attack_ranges.append({"range": tower_range, "color": (255, 200, 50, 200), "outline": (200, 150, 30, 220), "inset": 0.55})
                else:
                    # Personal weapon mode: show normal melee + projectile ranges
                    melee_range = current_player.get_melee_attack_range(self.hex_grid)
                    if melee_range:
                        attack_ranges.append({"range": melee_range, "color": (200, 80, 60, 220), "outline": (139, 0, 0, 220), "inset": 0.75})
                    proj_range = current_player.get_projectile_attack_range(self.hex_grid, game.current_party)
                    if proj_range:
                        attack_ranges.append({"range": proj_range, "color": (80, 50, 180, 220), "outline": (50, 30, 140, 220), "inset": 0.55})
            else:
                melee_range = current_player.get_melee_attack_range(self.hex_grid)
                if melee_range:
                    attack_ranges.append({"range": melee_range, "color": (200, 80, 60, 220), "outline": (139, 0, 0, 220), "inset": 0.75})
                proj_range = current_player.get_projectile_attack_range(self.hex_grid, game.current_party)
                if proj_range:
                    attack_ranges.append({"range": proj_range, "color": (80, 50, 180, 220), "outline": (50, 30, 140, 220), "inset": 0.55})

        # Show white rings around recruitable adjacent NPCs (always visible on player turn)
        if is_player_turn:
            adjacent_neutrals = self._get_adjacent_recruitable_npcs()
            recruit_hexes = {npc_unit.position for npc_unit in adjacent_neutrals if npc_unit.position}
            if recruit_hexes:
                attack_ranges.append({"range": recruit_hexes, "color": (255, 255, 255, 220), "outline": (180, 180, 180, 220), "inset": 0.75})

        # Amber rings around adjacent junk piles (interactable)
        if is_player_turn and self.player_mode not in ("junk_pile_move", "junk_pile_place", "body_move", "body_place"):
            junk_pile_hexes = set()
            for r, c in self.hex_grid.get_adjacent_hexes(*current_player.position):
                if 0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols:
                    u = self.hex_grid.grid[r][c].get("unit")
                    if u and getattr(u, '_is_junk_pile', False):
                        junk_pile_hexes.add((r, c))
            if junk_pile_hexes:
                attack_ranges.append({"range": junk_pile_hexes, "color": (210, 170, 60, 220), "outline": (180, 140, 40, 220), "inset": 0.75})

        # White rings around adjacent dead bodies (interactable, exclude junk piles)
        if is_player_turn and self.player_mode not in ("body_move", "body_place", "junk_pile_move", "junk_pile_place"):
            adjacent_dead = [u for u in self._get_adjacent_dead_bodies() if not getattr(u, '_is_junk_pile', False)]
            dead_hexes = {u.position for u in adjacent_dead if u.position}
            if dead_hexes:
                attack_ranges.append({"range": dead_hexes, "color": (255, 255, 255, 220), "outline": (180, 180, 180, 220), "inset": 0.75})

        # Body-move mode: show valid destinations
        if is_player_turn and self.player_mode == "body_move" and self.body_move_unit:
            dest_hexes = set()
            for r, c in self.hex_grid.get_adjacent_hexes(*current_player.position):
                if (0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols
                        and self.hex_grid.grid[r][c]["unit"] is None
                        and self.hex_grid.grid[r][c]["accessible"]):
                    dest_hexes.add((r, c))
            dest_hexes.add(current_player.position)  # Player hex = pickup
            attack_ranges.append({"range": dest_hexes, "color": (255, 255, 255, 220), "outline": (180, 180, 180, 220), "inset": 0.70})

        # Body-place mode: show valid placement hexes
        if is_player_turn and self.player_mode == "body_place" and self.body_place_card:
            place_hexes = set()
            for r, c in self.hex_grid.get_adjacent_hexes(*current_player.position):
                if (0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols
                        and self.hex_grid.grid[r][c]["unit"] is None
                        and self.hex_grid.grid[r][c]["accessible"]):
                    place_hexes.add((r, c))
            if place_hexes:
                attack_ranges.append({"range": place_hexes, "color": (255, 255, 255, 220), "outline": (180, 180, 180, 220), "inset": 0.70})

        # Junk-pile-move mode: show valid destinations
        if is_player_turn and self.player_mode == "junk_pile_move" and self.junk_pile_move_unit:
            dest_hexes = set()
            for r, c in self.hex_grid.get_adjacent_hexes(*current_player.position):
                if (0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols
                        and self.hex_grid.grid[r][c]["unit"] is None
                        and self.hex_grid.grid[r][c]["accessible"]):
                    dest_hexes.add((r, c))
            dest_hexes.add(current_player.position)  # Player hex = pickup
            attack_ranges.append({"range": dest_hexes, "color": (210, 170, 60, 220), "outline": (180, 140, 40, 220), "inset": 0.70})

        # Junk-pile-place mode: show valid placement hexes
        if is_player_turn and self.player_mode == "junk_pile_place" and self.junk_pile_place_card:
            place_hexes = set()
            for r, c in self.hex_grid.get_adjacent_hexes(*current_player.position):
                if (0 <= r < self.hex_grid.rows and 0 <= c < self.hex_grid.cols
                        and self.hex_grid.grid[r][c]["unit"] is None
                        and self.hex_grid.grid[r][c]["accessible"]):
                    place_hexes.add((r, c))
            if place_hexes:
                attack_ranges.append({"range": place_hexes, "color": (210, 170, 60, 220), "outline": (180, 140, 40, 220), "inset": 0.70})

        # In item targeting mode, show green rings on adjacent hexes + self
        if is_player_turn and self.player_mode == "item" and self.selected_item:
            item_hexes = set(self.hex_grid.get_adjacent_hexes(*current_player.position))
            item_hexes.add(current_player.position)
            attack_ranges.append({"range": item_hexes, "color": (0, 200, 100, 200), "outline": (0, 140, 70, 200), "inset": 0.75})

        # In defensive posture selection mode, show blue rings on valid defense hexes
        if is_player_turn and self.player_mode == "defensive" and self.defensive_hex_options:
            defense_hexes = set(self.defensive_hex_options)
            attack_ranges.append({"range": defense_hexes, "color": (60, 140, 220, 200), "outline": (40, 100, 180, 220), "inset": 0.70})

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

        # --- Custom player info panel ---
        if self._player_panel_dirty or (game.current_player and game.current_player.super_attack_ready):
            self._render_player_panel()
        if self._player_panel_surface is not None:
            screen.blit(self._player_panel_surface, (self.rp_x + self.rp_pad, self.rp_pi_y))
        # Dynamically shift "Selected" panel if height changed
        new_stats_y = self.rp_pi_y + self._player_panel_height + self.rp_pad + 24
        if new_stats_y != self.rp_stats_y:
            self.rp_stats_y = new_stats_y
            # Update stats panel position (ui_elements[1] is the stats panel)
            self.ui_elements[1].set_position((self.rp_x + self.rp_pad, new_stats_y))

        # "Selected" header
        selected_hdr = header_font.render("Selected", True, header_color)
        screen.blit(selected_hdr, (self.rp_x + self.rp_pad, self.rp_stats_y - 20))

        # Section divider lines
        # Divider between Player and Selected
        div1_y = self.rp_stats_y - 24
        pygame.draw.line(screen, panel_border_color,
                         (self.rp_x + self.rp_pad, div1_y),
                         (self.rp_x + self.rp_width - self.rp_pad, div1_y), 1)
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
        # Draw background behind action choice popup (before manager.draw_ui so buttons render on top)
        if self.action_choice_open and self.action_choice_buttons:
            first_btn = self.action_choice_buttons[0][0]
            last_btn = self.action_choice_buttons[-1][0]
            pad = 10
            header_h = 22
            popup_rect = pygame.Rect(first_btn.rect.x - pad, first_btn.rect.y - pad - header_h,
                                     first_btn.rect.width + pad * 2,
                                     last_btn.rect.bottom - first_btn.rect.y + pad * 2 + header_h)
            bg_surf = pygame.Surface((popup_rect.width, popup_rect.height), pygame.SRCALPHA)
            bg_surf.fill((20, 16, 10, 235))
            screen.blit(bg_surf, popup_rect.topleft)
            pygame.draw.rect(screen, (200, 150, 44), popup_rect, 2, border_radius=6)
            # Header text
            header_text = self.action_popup_header_font.render("Choose Action", True, (255, 215, 100))
            screen.blit(header_text, (popup_rect.x + pad, popup_rect.y + 5))
        manager.draw_ui(screen)
        # Draw colored borders on equipment toolbar buttons
        if self.equip_toolbar_buttons and len(self.equip_toolbar_buttons) >= 3:
            # Melee button: red-orange border (matches melee range color)
            pygame.draw.rect(screen, (255, 69, 0), self.equip_toolbar_buttons[1].rect, 2)
            # Projectile button: purple border (matches projectile range color)
            pygame.draw.rect(screen, (191, 0, 255), self.equip_toolbar_buttons[2].rect, 2)
        # Dim empty toolbar slots with a dark overlay
        if self.equip_toolbar_buttons and len(self.equip_toolbar_buttons) >= 7:
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
        if self.item_targeting_mode and len(self.equip_toolbar_buttons) >= 7:
            pygame.draw.rect(screen, (0, 200, 100), self.equip_toolbar_buttons[6].rect, 2)
        # Draw colored outlines on attack submenu buttons
        if self.attack_submenu_open:
            for btn, _, _ in self.attack_submenu_buttons:
                if hasattr(btn, '_outline_color'):
                    pygame.draw.rect(screen, btn._outline_color, btn.rect, 2)
        self.draw_defeat_notifications()
        self.draw_turn_banner()
        self.draw_ammo_banner()
        # Location defense animation timer — fire next queued shot or process deaths
        if self._loc_defense_active and self._loc_defense_wait_until is not None:
            if pygame.time.get_ticks() >= self._loc_defense_wait_until:
                self._loc_defense_wait_until = None
                if self._loc_defense_shot_queue:
                    self._fire_next_defense_shot()
                else:
                    self._process_loc_defense_deaths()
        # Advance turn once the Location Defense banner has finished displaying
        if self._pending_advance_after_banner and self.turn_banner is None:
            self._pending_advance_after_banner = False
            self.advance_turn()
        self.draw_event_banner()
        self._draw_dialogue()
        # Check for pending location screen (show after movement animation completes)
        if self.pending_location and not self.animating:
            loc_data = self.pending_location
            # Check if this location triggers instant campaign level transition
            if self.campaign and self._check_reach_location_instant(loc_data["pos"]):
                self.pending_location = None
                self._trigger_instant_level_transition()
                return
            self.pending_location = None
            # Draw location card now if deferred from movement
            if loc_data.get("needs_draw"):
                loc_card, draw_msg = loc_data["hex_grid"].draw_location_card(
                    loc_data["pos"][0], loc_data["pos"][1], self.card_manager
                )
                if draw_msg:
                    self.add_to_log(draw_msg)
                loc_data["card"] = loc_card
            if loc_data["card"]:
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
        if not self._is_player_phase():
            self.update_turn_queue()


# Main Game class
class Game:
    def __init__(self):
        self._current_screen = "main_menu"
        self._screen_changed_this_frame = False  # Prevents stray events after screen change
        self.player = None
        self.party = []  # List of allied NPC cards in the player's party (single-player mode)
        self.party_behavior_overrides = {}  # {card_id: {"tree": [...], "follow_target": ..., "attack_target": ...}}
        self.card_manager = CardManager()
        self.quest_manager = QuestManager(self.card_manager)
        self.instance_manager = InstanceManager(self.card_manager)
        self.transition_manager = TransitionManager(self.card_manager, self.instance_manager)
        # Multiplayer support
        self.players = []  # List of players for multiplayer (2-4 players)
        self.current_player_index = 0  # Whose turn it is (0 or 1)
        self.multiplayer_mode = False  # True when in 2-player mode
        self.quest_managers = []  # Per-player quest managers in multiplayer
        # Game mode: "survival" (normal) or "creative" (testing with card browser)
        self.game_mode = "survival"
        # Settings
        self._autosave_frequency = 5  # Autosave every N turn cycles (0 = disabled)
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
            "card_giving": card_giving_screen,
            "party": party_screen,
            "skills": skills_screen,
            "quest": quest_screen,
            "defeat": defeat_screen,
            "card_browser": card_browser_screen,
            "tabbed_menu": tabbed_menu_screen,
            "npc_browser": npc_browser_screen,
            "pause_menu": pause_menu_screen,
            "confirmation": confirmation_screen,
            "teleport_party": teleport_party_screen,
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
card_giving_screen = CardGivingScreen()
party_screen = PartyScreen()
skills_screen = SkillsScreen()
quest_screen = QuestScreen()
pause_menu_screen = PauseMenuScreen()
confirmation_screen = ConfirmationScreen()
teleport_party_screen = TeleportPartyScreen()
save_load_screen = SaveLoadScreen()
defeat_screen = DefeatScreen()
card_browser_screen = CardBrowserScreen()
tabbed_menu_screen = TabbedMenuScreen()
npc_browser_screen = NpcBrowserScreen()
game = Game()

# Populate game_context slots so screen modules can access via gc.*
gc.game_screen = game_screen
gc.main_menu = main_menu
gc.player_count_screen = player_count_screen
gc.character_creation_screen = character_creation_screen
gc.multiplayer_character_creation_screen = multiplayer_character_creation_screen
gc.settings_screen = settings_screen
gc.game_settings_screen = game_settings_screen
gc.crafting_screen = crafting_screen
gc.inventory_screen = inventory_screen
gc.location_screen = location_screen
gc.recruitment_screen = recruitment_screen
gc.card_giving_screen = card_giving_screen
gc.party_screen = party_screen
gc.skills_screen = skills_screen
gc.quest_screen = quest_screen
gc.pause_menu_screen = pause_menu_screen
gc.confirmation_screen = confirmation_screen
gc.teleport_party_screen = teleport_party_screen
gc.save_load_screen = save_load_screen
gc.defeat_screen = defeat_screen
gc.card_browser_screen = card_browser_screen
gc.tabbed_menu_screen = tabbed_menu_screen
gc.npc_browser_screen = npc_browser_screen
gc.game = game

# Parse command-line arguments for campaign/level launching
import argparse
parser = argparse.ArgumentParser(description="JunkRPG - Hexagonal Grid RPG")
parser.add_argument("--campaign", type=str, help="Path to campaign file to load")
parser.add_argument("--level", type=str, help="Path to level file to load")
args, _ = parser.parse_known_args()

# If campaign or level specified via command line, go to player count selection
if args.campaign:
    game.current_screen = "player_count"
    player_count_screen.initialize_screen(campaign_file=args.campaign)
elif args.level:
    game.current_screen = "player_count"
    player_count_screen.initialize_screen(level_file=args.level)

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
        # If screen changed during this event, skip passing it to pygame_gui
        # to prevent the same click from triggering buttons on the new screen
        if not game._screen_changed_this_frame:
            manager.process_events(e)
        else:
            break
    manager.update(time_delta)
    game.draw()
    display.flip()

pygame.quit()
sys.exit()

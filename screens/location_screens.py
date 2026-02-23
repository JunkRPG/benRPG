import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UIWindow, UISelectionList, UILabel
import json
import os
import logging
from inventory_card import InventoryCard
from card_utils import load_card
import game_context as gc

logger = logging.getLogger("JunkRPG")


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
        # Man Tower button
        self.man_tower_button = None

    def initialize_screen(self, location_card, hex_pos, hex_grid):
        self.location_card = location_card
        self.hex_pos = hex_pos
        self.hex_grid = hex_grid
        self.selected_shop_item = None
        self.selected_materials = []

        gc.manager.clear_and_reset()

        window_rect = pygame.Rect((gc.WINDOW_WIDTH - 1200) // 2, (gc.WINDOW_HEIGHT - 800) // 2, 1200, 800)
        self.window = pygame_gui.elements.UIWindow(window_rect, gc.manager, "Location")

        loc_data = location_card.get_current_data()
        loc_name = loc_data.get("Name", "Unknown Location")
        description = loc_data.get("Description", "")

        # Header with location name
        self.header_label = pygame_gui.elements.UILabel(
            pygame.Rect(10, 5, 1150, 50), loc_name, gc.manager, container=self.window,
            object_id="#location_title"
        )

        # Description
        self.desc_text = pygame_gui.elements.UITextBox(
            f"<font color='#FFFFFF'>{description}</font>",
            pygame.Rect(10, 55, 380, 70), gc.manager, container=self.window
        )

        # Choices panel (left side)
        self.choices_label = pygame_gui.elements.UILabel(
            pygame.Rect(10, 130, 380, 25), "Actions:", gc.manager, container=self.window
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
                pygame.Rect(10, y_pos, 380, 35), btn_text, gc.manager, container=self.window
            )
            self.choice_buttons.append((btn, choice))
            y_pos += 40

        # Add Leave button if not in choices
        if not any(c.get("action") == "exit" for c in choices):
            leave_btn = pygame_gui.elements.UIButton(
                pygame.Rect(10, y_pos, 380, 35), "Leave (Free)", gc.manager, container=self.window
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
                pygame.Rect(400, 130, 380, 25), "Shop:", gc.manager, container=self.window
            )

            shop_inventory = hex_grid.get_shop_inventory(hex_pos[0], hex_pos[1])
            shop_items = []
            for item in shop_inventory:
                card = item.get("card")
                price = item.get("price", {})
                if card:
                    item_name = item.get("display_name") or card.get_current_data().get("Name", "Unknown")
                    price_str = f"{price.get('amount', 0)} {price.get('type', 'metal')}"
                    shop_items.append(f"{item_name} - {price_str}")

            # Store shop item names for index lookup in handle_event
            self.shop_item_names = shop_items if shop_items else []

            self.shop_items_list = pygame_gui.elements.UISelectionList(
                pygame.Rect(400, 160, 380, 250),
                shop_items if shop_items else ["Shop is empty"],
                gc.manager, container=self.window
            )

            self.buy_button = pygame_gui.elements.UIButton(
                pygame.Rect(400, 420, 185, 35), "Buy Item", gc.manager, container=self.window
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
                pygame.Rect(400, 465, 380, 25), f"Materials for Payment ({shop_currency}):", gc.manager, container=self.window
            )

            material_cards = [card for card in gc.game.current_player.inventory
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
                gc.manager, container=self.window,
                allow_multi_select=True
            )

        # Upgrade panel (right side) - only if location can be upgraded
        self.upgrade_panel_visible = False
        if location_card.states == 2 and location_card.current_state == 1:
            upgrade_npc_type = loc_data.get("Upgrade_NPC_Type", "")
            if upgrade_npc_type:
                self.upgrade_panel_visible = True
                self.upgrade_label = pygame_gui.elements.UILabel(
                    pygame.Rect(790, 130, 380, 25), "Upgrade Location:", gc.manager, container=self.window
                )

                upgrade_cost = loc_data.get("Upgrade_Material_Cost", "{}")
                self.upgrade_info = pygame_gui.elements.UITextBox(
                    f"<font color='#FFFFFF'>Requires {upgrade_npc_type} NPC<br>Materials: {upgrade_cost}</font>",
                    pygame.Rect(790, 160, 380, 80), gc.manager, container=self.window
                )

                # Get allied NPCs from party
                allied_npcs = [card for card in gc.game.current_party
                              if "Allied" in card.get_current_data().get("Allegiance (Hostile, Neutral, Allied)", "")]
                npc_names = [card.get_current_data().get("Name", "Unknown") for card in allied_npcs]

                self.npc_list = pygame_gui.elements.UISelectionList(
                    pygame.Rect(790, 250, 380, 150),
                    npc_names if npc_names else ["No allied NPCs"],
                    gc.manager, container=self.window
                )

                self.assign_npc_button = pygame_gui.elements.UIButton(
                    pygame.Rect(790, 410, 380, 35), "Assign NPC (Upgrade)", gc.manager, container=self.window
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
                pygame.Rect(790, recruit_y, 380, 25), "NPCs Available to Recruit:", gc.manager, container=self.window
            )

            npc_names = [npc.get("name", "Unknown") for npc in available_npcs]
            self.recruit_npc_list = pygame_gui.elements.UISelectionList(
                pygame.Rect(790, recruit_y + 30, 380, 150),
                npc_names,
                gc.manager, container=self.window
            )

            self.recruit_button = pygame_gui.elements.UIButton(
                pygame.Rect(790, recruit_y + 190, 380, 35), "Recruit to Party", gc.manager, container=self.window
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
                f"Garrison ({len(garrison)}/3):", gc.manager, container=self.window
            )

            # Current garrison members
            garrison_names = [f"{g.get('name', 'Unknown')} (HP: {g.get('hp', 0)}/{g.get('max_hp', 0)})" for g in garrison]

            # Party NPCs available to garrison
            party_npc_names = []
            self._garrison_party_npcs = []
            for card in gc.game.current_party:
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
                gc.manager, container=self.window
            )

            if len(garrison) < 3 and party_npc_names:
                self.garrison_button = pygame_gui.elements.UIButton(
                    pygame.Rect(790, garrison_y + 220, 380, 35),
                    "Garrison NPC", gc.manager, container=self.window
                )

        # Man Tower button - player can man a defensive location to use its weapons
        self.man_tower_button = None
        if loc_data_dict and location_card.current_state == 2:
            all_defenses = loc_data_dict.get("defenses", [])
            current_player = gc.game.current_player
            player_on_hex = current_player and current_player.position == hex_pos
            already_manning = hasattr(current_player, 'is_manning') and current_player.is_manning()
            if all_defenses and player_on_hex and not already_manning:
                self.man_tower_button = pygame_gui.elements.UIButton(
                    pygame.Rect(10, 600, 380, 35), "Man Tower", gc.manager, container=self.window
                )

        # Quest selection panel (shows when view_quests action is used)
        self.quest_list = None
        self.quest_details_text = None
        self.accept_quest_button = None
        self.back_to_shop_button = None

        if self.quest_panel_visible:
            # Quest panel in the middle area
            pygame_gui.elements.UILabel(
                pygame.Rect(400, 130, 380, 25), "Available Quests:", gc.manager, container=self.window
            )

            quest_names = [q.get_current_data().get("Name", "Unknown Quest") for q in self.available_quests]
            self.quest_list = pygame_gui.elements.UISelectionList(
                pygame.Rect(400, 160, 380, 150),
                quest_names,
                gc.manager, container=self.window
            )

            pygame_gui.elements.UILabel(
                pygame.Rect(400, 320, 380, 25), "Quest Details:", gc.manager, container=self.window
            )

            self.quest_details_text = pygame_gui.elements.UITextBox(
                "<font color='#FFFFFF'>Select a quest to view details</font>",
                pygame.Rect(400, 350, 380, 200), gc.manager, container=self.window
            )

            self.accept_quest_button = pygame_gui.elements.UIButton(
                pygame.Rect(400, 560, 185, 35), "Accept Quest", gc.manager, container=self.window
            )

            self.back_to_shop_button = pygame_gui.elements.UIButton(
                pygame.Rect(595, 560, 185, 35), "Back to Shop", gc.manager, container=self.window
            )

        # Info panel (bottom)
        self.info_text = pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select an action or shop item</font>",
            pygame.Rect(10, 700, 1150, 60), gc.manager, container=self.window
        )

        # Close button
        self.close_button = pygame_gui.elements.UIButton(
            pygame.Rect(1050, 5, 100, 30), "Close", gc.manager, container=self.window
        )

    def handle_event(self, event):
        # Handle window X button (same as Close)
        if event.type == pygame_gui.UI_WINDOW_CLOSE:
            if event.ui_element == self.window:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            # Handle close button
            if event.ui_element == self.close_button:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
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

            # Handle Man Tower button
            if self.man_tower_button and event.ui_element == self.man_tower_button:
                current_player = gc.game.current_player
                current_player.enter_manning(self.hex_pos)
                loc_name = self.location_card.get_current_data().get("Name", "Tower")
                gc.game_screen.add_to_log(f"{current_player.name or current_player.class_name} mans the {loc_name}!")
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
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

        if costs_action and gc.game.current_player.action_used:
            self.info_text.set_text("<font color='#FF0000'>Action already used this turn!</font>")
            return

        if action == "exit":
            gc.game.current_screen = "game"
            gc.game_screen.initialize_screen()
        elif action == "draw_card":
            outcome_card, msg = self.hex_grid.trigger_location_outcome(self.hex_pos[0], self.hex_pos[1], gc.game_screen.card_manager)
            if outcome_card:
                party_msg = gc.add_card_to_player(outcome_card)
                if party_msg:
                    gc.game_screen.add_to_log(party_msg)
            gc.game_screen.add_to_log(msg)
            if costs_action:
                gc.game.current_player.action_used = True
            self.hex_grid.mark_location_visited(self.hex_pos[0], self.hex_pos[1])
            self.info_text.set_text(f"<font color='#FFFFFF'>{msg}</font>")
        elif action == "heal":
            hp_amount = int(params.get("amount", 10))
            old_hp = gc.game.current_player.hp
            gc.game.current_player.hp = min(gc.game.current_player.max_hp, gc.game.current_player.hp + hp_amount)
            msg = f"Healed for {gc.game.current_player.hp - old_hp} HP"
            gc.game_screen.add_to_log(msg)
            if costs_action:
                gc.game.current_player.action_used = True
            self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
        elif action == "shop":
            self.info_text.set_text("<font color='#FFFFFF'>Select items from the shop above</font>")
        elif action == "trade":
            self.info_text.set_text("<font color='#FFFFFF'>Select materials to trade</font>")
        elif action == "accept_quest":
            # Accept a quest from this location
            deck_file = params.get("deck", "decks/test_quest_deck.json")

            # Check if player can accept more quests
            if not gc.game.current_quest_manager.can_accept_quest():
                self.info_text.set_text("<font color='#FF0000'>Quest log full! Complete or abandon a quest first.</font>")
                return

            # Draw a quest card from the specified deck
            quest_card = gc.game.card_manager.draw_from_deck(deck_file)
            if not quest_card:
                self.info_text.set_text("<font color='#FF0000'>No quests available at this location.</font>")
                return

            # Check if player already has this quest active
            quest_name = quest_card.get_current_data().get("Name", "Unknown")
            for active in gc.game.current_quest_manager.active_quests:
                if active.quest_card.get_current_data().get("Name") == quest_name:
                    self.info_text.set_text(f"<font color='#FF0000'>Already have quest: {quest_name}</font>")
                    return

            # Activate the quest
            success, msg = gc.game.current_quest_manager.activate_quest(quest_card, self.hex_grid, gc.game.current_player)

            if success:
                if costs_action:
                    gc.game.current_player.action_used = True
                gc.game_screen.add_to_log(f"New quest accepted: {quest_name}")
                self.info_text.set_text(f"<font color='#00FF00'>Quest accepted: {quest_name}</font>")
                # Update quest button count
                gc.game_screen.update_quest_button()
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
            if not gc.game.current_player.has_building_tool():
                self.info_text.set_text("<font color='#FF0000'>You need a hammer equipped to repair!</font>")
                return

            # Calculate player's available materials
            totals = {"Metal": 0, "Wood": 0, "Raw": 0, "Refined": 0}
            for card in gc.game.current_player.inventory:
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
            for card in gc.game.current_player.inventory[:]:  # Copy list to avoid modification during iteration
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
                if card in gc.game.current_player.inventory:
                    gc.game.current_player.inventory.remove(card)

            # Perform the repair
            success, healed, rebuilt, msg = self.hex_grid.repair_npc_location(
                self.hex_pos[0], self.hex_pos[1], heal_amount, can_rebuild
            )

            if success:
                gc.game_screen.add_to_log(msg)
                if costs_action:
                    gc.game.current_player.action_used = True
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
                    logger.error(f"Error loading quest {quest_id}: {e}")
        except Exception as e:
            logger.error(f"Error loading quest deck {deck_file}: {e}")

        # Refresh the screen to show quest panel
        self.initialize_screen(self.location_card, self.hex_pos, self.hex_grid)

    def accept_selected_quest(self):
        """Accept the currently selected quest."""
        if self.selected_quest_index is None:
            self.info_text.set_text("<font color='#FF0000'>Select a quest first!</font>")
            return

        if not gc.game.current_quest_manager.can_accept_quest():
            self.info_text.set_text("<font color='#FF0000'>Quest log full! Complete or abandon a quest first.</font>")
            return

        quest_card = self.available_quests[self.selected_quest_index]
        quest_name = quest_card.get_current_data().get("Name", "Unknown")

        # Check if player already has this quest active
        for active in gc.game.current_quest_manager.active_quests:
            if active.quest_card.get_current_data().get("Name") == quest_name:
                self.info_text.set_text(f"<font color='#FF0000'>Already have quest: {quest_name}</font>")
                return

        # Activate the quest
        success, msg = gc.game.current_quest_manager.activate_quest(quest_card, self.hex_grid, gc.game.current_player)

        if success:
            gc.game_screen.add_to_log(f"New quest accepted: {quest_name}")
            self.info_text.set_text(f"<font color='#00FF00'>Quest accepted: {quest_name}</font>")
            gc.game_screen.update_quest_button()
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

        # Save sell_state before purchase (shop item gets removed during purchase)
        shop_inv = self.hex_grid.get_shop_inventory(self.hex_pos[0], self.hex_pos[1])
        sell_state = None
        if self.selected_shop_item < len(shop_inv):
            sell_state = shop_inv[self.selected_shop_item].get("sell_state")

        # Get selected materials using the display name to card mapping
        selected_material_names = self.sell_materials_list.get_multi_selection() if self.sell_materials_list else []
        material_cards = [self.material_name_to_card[name] for name in selected_material_names
                         if name in self.material_name_to_card]

        purchased_card, msg = self.hex_grid.purchase_from_shop(
            self.hex_pos[0], self.hex_pos[1], self.selected_shop_item, gc.game.current_player.inventory, material_cards
        )

        if purchased_card:
            # Remove used materials
            for mat in material_cards:
                if mat in gc.game.current_player.inventory:
                    gc.game.current_player.inventory.remove(mat)

            # Route based on sell_state for mount NPCs
            is_mount_npc = (purchased_card.card_data.get("card_type") == "NPC Card" and
                           purchased_card.card_data.get("data", {}).get("Special Skill") == "Mount")

            if sell_state == 1 and is_mount_npc:
                # Wild purchase: spawn as neutral unit near stable
                from unit import Unit
                spawn_card = purchased_card.card_data.copy()
                spawn_card["data"] = spawn_card["data"].copy()
                wild_unit = Unit(spawn_card)
                spawn_pos = self.hex_grid.find_empty_hex_near(self.hex_pos, 3)
                if spawn_pos:
                    self.hex_grid.place_unit(wild_unit, spawn_pos[0], spawn_pos[1])
                    wild_name = purchased_card.get_current_data().get("Name", "Horse")
                    gc.game_screen.add_to_log(f"{wild_name} released near the stable!")
                    self.info_text.set_text(f"<font color='#00FF00'>{wild_name} released near the stable!</font>")
                else:
                    gc.game_screen.add_to_log("No space to release the horse nearby!")
                    self.info_text.set_text("<font color='#FF0000'>No space to release nearby!</font>")
            elif sell_state == 2 and is_mount_npc:
                # Tamed purchase: add to party (reset to state 1 for mount system compatibility)
                purchased_card.current_state = 1
                gc.game.current_party.append(purchased_card)
                tamed_name = purchased_card.card_data.get("data", {}).get("2nd_State_Name", "Horse")
                gc.game_screen.add_to_log(f"{tamed_name} joined your party!")
                self.info_text.set_text(f"<font color='#00FF00'>{tamed_name} joined your party!</font>")
            else:
                # Normal flow
                party_msg = gc.add_card_to_player(purchased_card)
                if party_msg:
                    gc.game_screen.add_to_log(party_msg)
                self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")

            gc.game_screen.add_to_log(msg)
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
        for card in gc.game.current_party:
            if card.get_current_data().get("Name") == selected_npc_name:
                npc_card = card
                break

        if not npc_card:
            self.info_text.set_text("<font color='#FF0000'>NPC not found!</font>")
            return

        success, msg = self.hex_grid.upgrade_location(self.hex_pos[0], self.hex_pos[1], npc_card)
        if success:
            # Remove NPC from party (they're now at the location)
            gc.game.current_party.remove(npc_card)
            gc.game_screen.add_to_log(msg)
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
                gc.game.current_party.remove(npc_card)
                gc.game_screen.add_to_log(msg)
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
            gc.game_screen.add_to_log(f"{unit_name} ordered to garrison location")

    def recruit_npc(self):
        """Recruit an NPC from the location to the player's party."""
        if self.selected_recruit_index is None:
            self.info_text.set_text("<font color='#FF0000'>Select an NPC to recruit!</font>")
            return

        # Check party size limit
        if len(gc.game.current_party) >= 5:
            self.info_text.set_text("<font color='#FF0000'>Party is full (max 5 members)!</font>")
            return

        # Get NPC data and remove from location
        npc_data, msg = self.hex_grid.recruit_npc_from_location(
            self.hex_pos[0], self.hex_pos[1], self.selected_recruit_index
        )

        if npc_data:
            # Try loading full card data to preserve Special Skill, heal fields, state 2, etc.
            full_card = load_card(npc_data.get("id"), silent=True)
            if full_card:
                full_card["data"]["Allegiance (Hostile, Neutral, Allied)"] = "Allied"
                if full_card.get("states", 1) >= 2 and "2nd_State_Allegiance (Hostile, Neutral, Allied)" in full_card.get("data", {}):
                    full_card["data"]["2nd_State_Allegiance (Hostile, Neutral, Allied)"] = "Allied"
                from inventory_card import InventoryCard
                npc_card = InventoryCard(full_card)
                # Restore state from stored data
                stored_state = npc_data.get("current_state", 1)
                if stored_state == 2:
                    npc_card.current_state = 2
            else:
                # Fallback: bare-bones card if card file can't be loaded
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
            gc.game.current_party.append(npc_card)

            gc.game_screen.add_to_log(msg)
            self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
            self.selected_recruit_index = None

            # Refresh the screen to update available NPCs list
            self.initialize_screen(self.location_card, self.hex_pos, self.hex_grid)
        else:
            self.info_text.set_text(f"<font color='#FF0000'>{msg}</font>")

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


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

        gc.manager.clear_and_reset()

        window_rect = pygame.Rect((gc.WINDOW_WIDTH - 800) // 2, (gc.WINDOW_HEIGHT - 600) // 2, 800, 600)
        self.window = pygame_gui.elements.UIWindow(window_rect, gc.manager, "Recruit NPC")

        # NPC info header
        npc_name = target_unit.name if target_unit else "Unknown"
        pygame_gui.elements.UILabel(
            pygame.Rect(10, 5, 780, 30), f"Recruit: {npc_name}", gc.manager, container=self.window
        )

        # Calculate recruitment cost
        recruitment_cost = self._calculate_recruitment_cost(target_unit)

        # NPC stats panel (left side)
        stats_text = self._get_npc_stats_text(target_unit)
        self.npc_info_text = pygame_gui.elements.UITextBox(
            f"<font color='#FFFFFF'>{stats_text}</font>",
            pygame.Rect(10, 40, 300, 200), gc.manager, container=self.window
        )

        # Cost label
        self.cost_label = pygame_gui.elements.UILabel(
            pygame.Rect(10, 250, 300, 30), f"Recruitment Cost: {recruitment_cost} material value",
            gc.manager, container=self.window
        )

        # Junk selection (right side)
        pygame_gui.elements.UILabel(
            pygame.Rect(320, 40, 460, 25), "Select junk to offer (multi-select):",
            gc.manager, container=self.window
        )

        # Build junk list with material values
        junk_items = []
        for card in gc.game.current_player.inventory:
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
            gc.manager, container=self.window,
            allow_multi_select=True
        )

        # Offered value label
        self.offered_label = pygame_gui.elements.UILabel(
            pygame.Rect(320, 380, 460, 30), "Total offered: 0 / " + str(recruitment_cost),
            gc.manager, container=self.window
        )

        # Info text at bottom
        self.info_text = pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select junk items with enough total value to meet the recruitment cost.</font>",
            pygame.Rect(10, 420, 780, 80), gc.manager, container=self.window
        )

        # Buttons
        self.recruit_button = pygame_gui.elements.UIButton(
            pygame.Rect(200, 510, 180, 40), "Recruit", gc.manager, container=self.window
        )
        self.cancel_button = pygame_gui.elements.UIButton(
            pygame.Rect(420, 510, 180, 40), "Cancel", gc.manager, container=self.window
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
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.cancel_button:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
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
        if len(gc.game.current_party) >= 5:
            self.info_text.set_text("<font color='#FF0000'>Party is full! (Max 5 members)</font>")
            return

        # Success! Remove junk from inventory
        for card in self.selected_junk:
            if card in gc.game.current_player.inventory:
                gc.game.current_player.inventory.remove(card)

        # Change NPC allegiance to Allied and set follow/carry behavior
        self.target_unit.set_allegiance("Allied")
        self.target_unit.carry_to_next_level = True
        self.target_unit.behavior_follow_target = f"player_{gc.game.current_player_index}"

        # Create party card for the NPC — use full card data to preserve Special Skill, heal fields, state 2, etc.
        full_card = load_card(self.target_unit.card_id, silent=True)
        if full_card:
            full_card["data"]["Allegiance (Hostile, Neutral, Allied)"] = "Allied"
            if full_card.get("states", 1) >= 2 and "2nd_State_Allegiance (Hostile, Neutral, Allied)" in full_card.get("data", {}):
                full_card["data"]["2nd_State_Allegiance (Hostile, Neutral, Allied)"] = "Allied"
            from inventory_card import InventoryCard
            npc_card = InventoryCard(full_card)
            # Match the unit's current state (e.g., Elder flipped to state 2 = Healer)
            if hasattr(self.target_unit, 'current_state') and self.target_unit.current_state == 2:
                npc_card.current_state = 2
        else:
            # Fallback: bare-bones card if card file can't be loaded
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
            from inventory_card import InventoryCard
            npc_card = InventoryCard(npc_card_data)
        gc.game.current_party.append(npc_card)

        # Log the recruitment
        gc.game_screen.add_to_log(f"{self.target_unit.name} joined your party!")

        # Return to game
        gc.game.current_screen = "game"
        gc.game_screen.initialize_screen()

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


class CardGivingScreen:
    """Screen for giving a card from current player to another player in multiplayer."""
    def __init__(self):
        self.window = None
        self.target_player = None
        self.card_list = None
        self.card_name_to_card = {}
        self.info_text = None
        self.give_button = None
        self.cancel_button = None

    def initialize_screen(self, target_player):
        """Initialize the card giving screen for a target player."""
        self.target_player = target_player
        self.card_name_to_card = {}

        gc.manager.clear_and_reset()

        window_rect = pygame.Rect((gc.WINDOW_WIDTH - 700) // 2, (gc.WINDOW_HEIGHT - 500) // 2, 700, 500)
        self.window = pygame_gui.elements.UIWindow(window_rect, gc.manager, "Give Card to Player")

        target_name = target_player.name or target_player.class_name
        pygame_gui.elements.UILabel(
            pygame.Rect(10, 5, 680, 30), f"Give a card to {target_name}", gc.manager, container=self.window
        )

        # Build list of all cards in current player's inventory
        card_items = []
        for card in gc.game.current_player.inventory:
            card_data = card.get_current_data()
            name = card_data.get("Name", "Unnamed")
            card_type = card.card_data.get("card_type", "")
            state_info = f" [State {card.current_state}]" if card.states == 2 else ""
            display = f"{name} ({card_type}){state_info}"
            card_items.append(display)
            self.card_name_to_card[display] = card

        self.card_list = pygame_gui.elements.UISelectionList(
            pygame.Rect(10, 40, 680, 320),
            card_items if card_items else ["No cards in inventory"],
            gc.manager, container=self.window,
            allow_multi_select=False
        )

        self.info_text = pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select a card to give.</font>",
            pygame.Rect(10, 370, 680, 50), gc.manager, container=self.window
        )

        self.give_button = pygame_gui.elements.UIButton(
            pygame.Rect(180, 430, 150, 40), "Give", gc.manager, container=self.window
        )
        self.cancel_button = pygame_gui.elements.UIButton(
            pygame.Rect(370, 430, 150, 40), "Cancel", gc.manager, container=self.window
        )

    def handle_event(self, event):
        if event.type == pygame_gui.UI_WINDOW_CLOSE:
            if event.ui_element == self.window:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.cancel_button:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
            elif event.ui_element == self.give_button:
                selected = self.card_list.get_single_selection()
                if selected and selected in self.card_name_to_card:
                    card = self.card_name_to_card[selected]
                    # Transfer card: remove from giver, add to receiver
                    gc.game.current_player.inventory.remove(card)
                    self.target_player.inventory.append(card)
                    # Log the transfer
                    giver_name = gc.game.current_player.name or gc.game.current_player.class_name
                    receiver_name = self.target_player.name or self.target_player.class_name
                    card_name = card.get_current_data().get("Name", "Unnamed")
                    gc.game_screen.add_to_log(f"{giver_name} gave {card_name} to {receiver_name}")
                    gc.game.current_screen = "game"
                    gc.game_screen.initialize_screen()
                else:
                    self.info_text.set_text("<font color='#FF0000'>Select a card first.</font>")

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)

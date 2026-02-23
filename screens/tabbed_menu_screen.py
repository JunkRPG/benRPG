import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UISelectionList, UILabel
import logging
from unit import Unit
import game_context as gc

logger = logging.getLogger("JunkRPG")


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
        gc.manager.clear_and_reset()
        self.content_elements = []
        self._build_tab_bar()
        self._build_active_content()

    def _build_tab_bar(self):
        """Build the persistent tab bar at the top."""
        total_width = len(self.TAB_NAMES) * self.TAB_WIDTH + (len(self.TAB_NAMES) - 1) * 10
        start_x = (gc.WINDOW_WIDTH - total_width) // 2
        self.tab_buttons = {}
        for i, name in enumerate(self.TAB_NAMES):
            x = start_x + i * (self.TAB_WIDTH + 10)
            btn = UIButton(pygame.Rect(x, 10, self.TAB_WIDTH, self.TAB_HEIGHT), name, gc.manager)
            self.tab_buttons[name] = btn
        # Close button at far right
        self.close_button = UIButton(pygame.Rect(gc.WINDOW_WIDTH - 120, 10, 100, self.TAB_HEIGHT), "Close", gc.manager)

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
        self._add(UILabel(pygame.Rect(10, y, column_width, 25), "Junk / Materials", gc.manager))
        self._add(UILabel(pygame.Rect(column_width + 20, y, column_width, 25), "Documents", gc.manager))
        self._add(UILabel(pygame.Rect(2 * column_width + 30, y, column_width, 25), "Weapons", gc.manager))
        self._add(UILabel(pygame.Rect(3 * column_width + 40, y, column_width, 25), "Consumables / Tools", gc.manager))

        list_y = y + 30

        # Junk cards (column 1)
        junk_cards = [card for card in gc.game.current_player.inventory if card.current_state == 1 and card.card_data["card_type"] == "Junk Card"]
        junk_names = []
        for card in junk_cards:
            name = card.get_current_data().get("Name", "Unnamed")
            if card.get_current_data().get("Use_HP") or card.card_data.get("subclass") == "Consumable":
                name += " [Usable]"
            junk_names.append(name)
        self.inv_junk_list = self._add(UISelectionList(pygame.Rect(10, list_y, column_width, column_height),
                                         junk_names if junk_names else ["No junk items"], gc.manager))
        self.inv_use_junk_button = self._add(UIButton(pygame.Rect(10, list_y + column_height + 10, column_width, 35), "Use Item", gc.manager))

        # Documents (column 2)
        documents_cards = [card for card in gc.game.current_player.inventory
                          if card.card_data["card_type"] == "Document Card"
                          and (card.current_state == 1 or card.card_data.get("subclass") == "Guide")]
        self.inv_documents_list = self._add(UISelectionList(pygame.Rect(column_width + 20, list_y, column_width, column_height - 45),
                                              [card.get_current_data().get("Name", "Unnamed") for card in documents_cards] or ["No documents"], gc.manager))
        self.inv_read_guide_button = self._add(UIButton(pygame.Rect(column_width + 20, list_y + column_height - 40, column_width, 35),
                                          "Read Guide", gc.manager))

        # Weapons (column 3)
        weapons_cards = [card for card in gc.game.current_player.inventory
                         if card.current_state == 2
                         and (card.get_current_data().get("Type") in ["Melee", "Projectile", "Both"]
                              or (not card.get_current_data().get("Type")
                                  and card.card_data.get("subclass") in ["Junk_to_Weapon", "Blueprint_to_Weapon"]))]
        self.inv_weapons_list = self._add(UISelectionList(pygame.Rect(2 * column_width + 30, list_y, column_width, column_height - 100),
                                            [card.get_current_data().get("Name", "Unnamed") for card in weapons_cards] or ["No weapons"], gc.manager))
        self.inv_equip_button = self._add(UIButton(pygame.Rect(2 * column_width + 30, list_y + column_height - 90, column_width, 35), "Equip Weapon", gc.manager))

        # Consumables, Tools, Ammunition (column 4)
        consumables_cards = [card for card in gc.game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Consumable"]
        tools_cards = [card for card in gc.game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Tool"]
        ammo_cards = [card for card in gc.game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Ammunition"]
        accessory_cards = [card for card in gc.game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") in ["Tool_Belt", "Accessory", "Belt", "Pouch"]]
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
                                                item_names if item_names else ["No consumables/tools"], gc.manager))
        self.inv_use_button = self._add(UIButton(pygame.Rect(3 * column_width + 40, list_y + column_height - 180, column_width, 35), "Use Consumable", gc.manager))
        self.inv_equip_tool_button = self._add(UIButton(pygame.Rect(3 * column_width + 40, list_y + column_height - 140, column_width, 35), "Equip as Tool/Ammo", gc.manager))
        self.inv_equip_accessory_button = self._add(UIButton(pygame.Rect(3 * column_width + 40, list_y + column_height - 100, column_width, 35), "Equip Accessory", gc.manager))

        # Item details panel (bottom)
        detail_y = list_y + column_height + 55
        self._add(UILabel(pygame.Rect(10, detail_y, 200, 25), "Item Details:", gc.manager))
        self.inv_info_text = self._add(UITextBox("<font color='#FFFFFF'>Select an item to view its stats and details</font>",
                                   pygame.Rect(10, detail_y + 25, 870, 120), gc.manager))

        # Creative mode button
        if gc.game.game_mode == "creative":
            self.inv_browse_cards_button = self._add(UIButton(pygame.Rect(900, detail_y + 25, 150, 35), "Browse Cards", gc.manager))
            self._add(UILabel(pygame.Rect(900, detail_y + 70, 150, 25), "[Creative Mode]", gc.manager))
        else:
            self.inv_browse_cards_button = None

    def _handle_inventory_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if self.inv_browse_cards_button and event.ui_element == self.inv_browse_cards_button:
                gc.game.current_screen = "card_browser"
                gc.card_browser_screen.initialize_screen()
                return
            elif event.ui_element == self.inv_equip_button and self.inv_selected_card and self.inv_selected_from_list == "weapons":
                gc.game.current_player.equip_weapon(self.inv_selected_card)
                gc.game_screen.player_info_label.set_text(gc.game_screen.get_player_info())
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
                        msg = gc.game.current_player.equip_tool(self.inv_selected_card)
                        self.inv_info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
                        self._refresh_current_tab()
                else:
                    self.inv_info_text.set_text("<font color='#FF0000'>Select a consumable, tool, or ammo to equip</font>")
            elif event.ui_element == self.inv_equip_accessory_button and self.inv_selected_card:
                if self.inv_selected_from_list == "consumables":
                    card_type = self.inv_selected_card.get_current_data().get("Type", "")
                    if card_type in ["Tool_Belt", "Accessory", "Belt", "Pouch"]:
                        msg = gc.game.current_player.equip_accessory(self.inv_selected_card)
                        self.inv_info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
                        self._refresh_current_tab()
                    else:
                        self.inv_info_text.set_text("<font color='#FF0000'>Select a tool belt or accessory to equip</font>")
                else:
                    self.inv_info_text.set_text("<font color='#FF0000'>Select a tool belt or accessory to equip</font>")
            elif self.inv_read_guide_button and event.ui_element == self.inv_read_guide_button:
                if self.inv_selected_card and self.inv_selected_from_list == "documents" and self.inv_selected_card.card_data.get("subclass") == "Guide":
                    message = gc.game.current_player.read_guide(self.inv_selected_card, gc.game.card_manager)
                    self.inv_info_text.set_text(f"<font color='#00FFFF'>{message}</font>")
                    gc.game_screen.add_to_log(message)
                    self._refresh_current_tab()
                else:
                    self.inv_info_text.set_text("<font color='#FF0000'>Select a Guide document to read</font>")

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            selected_name = event.text
            clean_name = selected_name.replace(" [Usable]", "")

            if event.ui_element == self.inv_junk_list:
                self.inv_selected_from_list = "junk"
                self.inv_selected_card = next((card for card in gc.game.current_player.inventory
                                          if card.current_state == 1
                                          and card.card_data["card_type"] == "Junk Card"
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.inv_documents_list:
                self.inv_selected_from_list = "documents"
                self.inv_selected_card = next((card for card in gc.game.current_player.inventory
                                          if card.card_data["card_type"] == "Document Card"
                                          and (card.current_state == 1 or card.card_data.get("subclass") == "Guide")
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.inv_weapons_list:
                self.inv_selected_from_list = "weapons"
                self.inv_selected_card = next((card for card in gc.game.current_player.inventory
                                          if card.current_state == 2
                                          and (card.get_current_data().get("Type") in ["Melee", "Projectile", "Both"]
                                               or (not card.get_current_data().get("Type")
                                                   and card.card_data.get("subclass") in ["Junk_to_Weapon", "Blueprint_to_Weapon"]))
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.inv_consumables_list:
                self.inv_selected_from_list = "consumables"
                match_name = clean_name.replace(" [Ammo]", "").replace(" [Accessory]", "")
                self.inv_selected_card = next((card for card in gc.game.current_player.inventory
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
                old_hp = gc.game.current_player.hp
                gc.game.current_player.hp = min(gc.game.current_player.max_hp, gc.game.current_player.hp + hp_change)
                actual_heal = gc.game.current_player.hp - old_hp
                gc.game_screen.add_to_log(f"Used {current_data.get('Name', 'Item')}: +{actual_heal} HP ({old_hp} -> {gc.game.current_player.hp})")
                gc.game.current_player.inventory.remove(self.inv_selected_card)
                self.inv_selected_card = None
                self._refresh_current_tab()
                gc.game_screen.player_info_label.set_text(gc.game_screen.get_player_info())
            elif hp_change < 0:
                gc.game.current_player.hp = max(0, gc.game.current_player.hp + hp_change)
                gc.game_screen.add_to_log(f"Used {current_data.get('Name', 'Item')}: {hp_change} HP")
                gc.game.current_player.inventory.remove(self.inv_selected_card)
                self.inv_selected_card = None
                self._refresh_current_tab()
                gc.game_screen.player_info_label.set_text(gc.game_screen.get_player_info())
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
        self._add(UILabel(pygame.Rect(col1_x, y, col_w, 25), "Junk Items (Craftable)", gc.manager))
        junk_cards = [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.is_two_state() and card.current_state == 1]
        self.craft_junk_list = self._add(UISelectionList(pygame.Rect(col1_x, y + 30, col_w, list_h),
                                         [card.get_current_data().get("Name", "Unnamed") for card in junk_cards], gc.manager))

        # Blueprints below junk
        self._add(UILabel(pygame.Rect(col1_x, y + list_h + 40, col_w, 25), "Blueprints", gc.manager))
        blueprint_cards = [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Document Card" and card.card_data.get("subclass", "") == "Blueprint" and card.is_two_state() and card.current_state == 1]
        self.craft_blueprint_list = self._add(UISelectionList(pygame.Rect(col1_x, y + list_h + 70, col_w, list_h),
                                              [card.get_current_data().get("Name", "Unnamed") for card in blueprint_cards], gc.manager))

        # Column 2: Materials (multi-select)
        self._add(UILabel(pygame.Rect(col2_x, y, col_w, 25), "Materials", gc.manager))
        self.craft_materials_list = self._add(UISelectionList(pygame.Rect(col2_x, y + 30, col_w, list_h * 2 + 40),
                                              [], gc.manager, allow_multi_select=True))
        self._craft_update_materials_list()

        # Column 3: Info panels
        self.craft_to_craft_info = self._add(UITextBox("<font color='#FFFFFF' size=4>To Craft</font>",
                                              pygame.Rect(col3_x, y + 30, col_w, 220), gc.manager))
        self.craft_selected_material_info = self._add(UITextBox("<font color='#FFFFFF' size=4>Selected Material</font>",
                                              pygame.Rect(col3_x, y + 260, col_w, 220), gc.manager))
        self.craft_state2_info = self._add(UITextBox("<font color='#FFFFFF' size=4>State 2 Info</font>",
                                              pygame.Rect(col3_x, y + 490, col_w, 220), gc.manager))

        # Column 4: Requirements + craft button
        self.craft_requirements_info = self._add(UITextBox("<font color='#FFFFFF' size=4>Requirements</font>",
                                              pygame.Rect(col4_x, y + 30, col_w, 300), gc.manager))
        self.craft_button = self._add(UIButton(pygame.Rect(col4_x, y + 340, 150, 30), "Craft", gc.manager))
        self.craft_success_label = self._add(UILabel(pygame.Rect(col4_x, y + 380, col_w, 30), "", gc.manager))
        self._craft_update_requirements_display()

    def _craft_update_materials_list(self):
        materials_cards = [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.current_state == 1]
        if self.craft_selected_to_craft and self.craft_selected_to_craft.card_data["card_type"] == "Junk Card":
            materials_cards = [card for card in materials_cards if card != self.craft_selected_to_craft]
        self.craft_materials_list.set_item_list([card.get_current_data().get("Name", "Unnamed") for card in materials_cards])

    def _craft_update_requirements_display(self):
        if not self.craft_selected_to_craft:
            self.craft_requirements_info.set_text("<font color='#FFFFFF' size=4>Requirements</font>")
            return
        state1_data = self.craft_selected_to_craft.get_state_data(1)
        builder_wood_perk = gc._check_builder_wood_perk()

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

            # Builder wood perk: show Wood as auto-fulfilled on forest terrain
            if builder_wood_perk and req_key == "Requirements: Wood" and required > 0:
                padded_type = material_type.ljust(18)
                requirements_text += f"{padded_type}<font color='#00CCFF'>AUTO</font>   <font color='#FFAA00'>{required:>3}</font><br>"
                continue

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
        builder_wood_perk = gc._check_builder_wood_perk()
        state1_data = self.craft_selected_to_craft.get_state_data(1)
        for req_key, val_key in self.REQUIREMENT_TO_VALUE.items():
            # Builder wood perk: skip Wood requirement on forest terrain
            if builder_wood_perk and req_key == "Requirements: Wood":
                continue
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
                        gc.game.current_player.inventory.remove(material)
                    self.craft_selected_to_craft.toggle_state()
                    crafted_name = self.craft_selected_to_craft.get_state_data(2).get("Name", "Unnamed Item")
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
                    [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.is_two_state() and card.current_state == 1]
                    if event.ui_element == self.craft_junk_list else
                    [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Document Card" and card.card_data.get("subclass", "") == "Blueprint" and card.is_two_state() and card.current_state == 1]
                )
                self.craft_selected_to_craft = next((card for card in cards if card.get_state_data(1).get("Name") == selected_name), None)
                self._craft_update_materials_list()
                if self.craft_selected_to_craft:
                    state1_data = self.craft_selected_to_craft.get_state_data(1)
                    info_text = f"<font color='#FFFFFF' size=4>To Craft: {state1_data.get('Name', 'Unnamed')}<br>" + "<br>".join(f"{k}: {v}" for k, v in state1_data.items() if k != "Name" and v) + "</font>"
                    self.craft_to_craft_info.set_text(info_text)
                    state2_data = self.craft_selected_to_craft.get_state_data(2)
                    state2_text = f"<font color='#FFFFFF' size=4>State 2: {state2_data.get('Name', 'Unnamed')}<br>" + "<br>".join(f"{k}: {v}" for k, v in state2_data.items() if k != 'Name' and v) + "</font>"
                    self.craft_state2_info.set_text(state2_text)
                    self._craft_update_requirements_display()
            elif event.ui_element == self.craft_materials_list:
                selected_names = self.craft_materials_list.get_multi_selection()
                materials_cards = [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.current_state == 1]
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

        column_width = (gc.WINDOW_WIDTH - 80) // 3
        list_height = gc.WINDOW_HEIGHT - 250

        # Column 1: Learnable Documents
        col1_x = 20
        self._add(UILabel(pygame.Rect(col1_x, y, column_width, 30), "Learnable Documents", gc.manager))
        learnable_items = self._skill_get_learnable_cards()
        self.skill_learnable_list = self._add(UISelectionList(
            pygame.Rect(col1_x, y + 35, column_width, list_height),
            learnable_items, gc.manager, allow_multi_select=False))
        self.skill_learn_button = self._add(UIButton(
            pygame.Rect(col1_x, y + list_height + 45, column_width, 40), "Learn Skill", gc.manager))

        # Column 2: Learned Skills
        col2_x = col1_x + column_width + 20
        self._add(UILabel(pygame.Rect(col2_x, y, column_width, 30), "Learned Skills", gc.manager))
        learned_items = self._skill_get_learned_skills()
        self.skill_learned_list = self._add(UISelectionList(
            pygame.Rect(col2_x, y + 35, column_width, list_height),
            learned_items, gc.manager, allow_multi_select=False))
        self.skill_equip_button = self._add(UIButton(
            pygame.Rect(col2_x, y + list_height + 45, column_width, 40), "Equip Skill", gc.manager))

        # Column 3: Equipped Skills
        col3_x = col2_x + column_width + 20
        self._add(UILabel(pygame.Rect(col3_x, y, column_width, 30),
            f"Equipped Skills ({len(gc.game.current_player.equipped_skills)}/{gc.game.current_player.active_skill_slots})", gc.manager))
        equipped_items = self._skill_get_equipped_skills()
        self.skill_equipped_list = self._add(UISelectionList(
            pygame.Rect(col3_x, y + 35, column_width, list_height),
            equipped_items, gc.manager, allow_multi_select=False))
        self.skill_unequip_button = self._add(UIButton(
            pygame.Rect(col3_x, y + list_height + 45, column_width, 40), "Unequip Skill", gc.manager))

    def _skill_get_learnable_cards(self):
        learnable = []
        for card in gc.game.current_player.inventory:
            card_type = card.card_data.get("card_type", "")
            if "Document/Skill" in card_type or card.card_data.get("subclass") == "Skill_Tome":
                if card.current_state == 1:
                    name = card.get_current_data().get("Name", "Unknown")
                    learnable.append(name)
        return learnable

    def _skill_get_learned_skills(self):
        skills = []
        for card in gc.game.current_player.skills:
            skill_data = card.get_current_data()
            name = skill_data.get("Name", "Unknown")
            skill_type = skill_data.get("Skill_Type", "Unknown")
            skills.append(f"{name} ({skill_type})")
        return skills

    def _skill_get_equipped_skills(self):
        equipped = []
        for card in gc.game.current_player.equipped_skills:
            skill_data = card.get_current_data()
            name = skill_data.get("Name", "Unknown")
            cooldown = gc.game.current_player.skill_cooldowns.get(name, 0)
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
                    for card in gc.game.current_player.inventory:
                        card_type = card.card_data.get("card_type", "")
                        if ("Document/Skill" in card_type or card.card_data.get("subclass") == "Skill_Tome"):
                            if card.current_state == 1:
                                name = card.get_current_data().get("Name", "")
                                if name == selections:
                                    gc.game.current_player.learn_skill(card)
                                    self._refresh_current_tab()
                                    break

            elif event.ui_element == self.skill_equip_button:
                selections = self.skill_learned_list.get_single_selection()
                if selections:
                    skill_name = selections.split(" (")[0]
                    for card in gc.game.current_player.skills:
                        if card.get_current_data().get("Name") == skill_name:
                            gc.game.current_player.equip_skill(card)
                            self._refresh_current_tab()
                            break

            elif event.ui_element == self.skill_unequip_button:
                selections = self.skill_equipped_list.get_single_selection()
                if selections:
                    skill_name = selections.split(" (")[0]
                    for card in gc.game.current_player.equipped_skills:
                        if card.get_current_data().get("Name") == skill_name:
                            gc.game.current_player.unequip_skill(card)
                            self._refresh_current_tab()
                            break

    # ========================
    # PARTY TAB
    # ========================
    def _build_party_content(self):
        self.party_selected_member = None
        y = self.CONTENT_Y

        # Header
        self._add(UILabel(pygame.Rect(10, y, 880, 30), "Your Party Members", gc.manager))

        # Party members list (left side)
        self._add(UILabel(pygame.Rect(10, y + 40, 300, 25), "Party Members:", gc.manager))

        party_names = []
        for card in gc.game.current_party:
            card_data = card.get_current_data()
            name = card_data.get("Name", "Unknown")
            deployed = any(u.card_id == card.card_data.get("id") for u in gc.game_screen.hex_grid.units if u.allegiance == "Allied")
            status = " [Deployed]" if deployed else ""
            party_names.append(f"{name}{status}")

        self.party_list = self._add(pygame_gui.elements.UISelectionList(
            pygame.Rect(10, y + 70, 300, 400),
            party_names if party_names else ["No party members"],
            gc.manager))
        self.party_member_names = party_names if party_names else []

        # Info panel (middle)
        self._add(UILabel(pygame.Rect(320, y + 40, 270, 25), "Member Details:", gc.manager))
        self.party_info_text = self._add(pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select a party member to view details</font>",
            pygame.Rect(320, y + 70, 270, 350), gc.manager))

        # Behavior tree panel (right side)
        bt_x = 600
        self._add(UILabel(pygame.Rect(bt_x, y + 40, 280, 25), "Behavior Priority:", gc.manager))
        self.party_bt_list = None
        self.party_bt_stubborn_label = None
        self.party_bt_move_up = None
        self.party_bt_move_down = None
        self.party_bt_add_dropdown = None
        self.party_bt_add_button = None
        self.party_bt_remove_button = None
        self.party_bt_set_target = None

        # Placeholder behavior panel (populated when member selected)
        self.party_bt_list = self._add(pygame_gui.elements.UISelectionList(
            pygame.Rect(bt_x, y + 70, 280, 200),
            ["Select a member"],
            gc.manager))

        # Behavior tree buttons (initially hidden, shown when non-stubborn member selected)
        self.party_bt_move_up = self._add(UIButton(pygame.Rect(bt_x, y + 275, 135, 30), "Move Up", gc.manager))
        self.party_bt_move_down = self._add(UIButton(pygame.Rect(bt_x + 145, y + 275, 135, 30), "Move Down", gc.manager))
        self.party_bt_remove_button = None
        self.party_bt_add_dropdown = None
        self.party_bt_add_button = None
        self.party_bt_set_target = self._add(UIButton(pygame.Rect(bt_x, y + 310, 280, 30), "Set Target on Map", gc.manager))
        self.party_bt_set_target.hide()

        # Action buttons
        self.party_deploy_button = self._add(UIButton(pygame.Rect(320, y + 430, 170, 35), "Deploy to Map", gc.manager))
        self.party_recall_button = self._add(UIButton(pygame.Rect(500, y + 430, 170, 35), "Recall to Party", gc.manager))
        self.party_dismiss_button = self._add(UIButton(pygame.Rect(320, y + 475, 350, 35), "Dismiss from Party", gc.manager))

        # Creative mode button (browse all NPCs)
        if gc.game.game_mode == "creative":
            self.party_browse_npcs_button = self._add(UIButton(pygame.Rect(320, y + 520, 170, 35), "Browse NPCs", gc.manager))
            self._add(UILabel(pygame.Rect(500, y + 520, 150, 35), "[Creative Mode]", gc.manager))
        else:
            self.party_browse_npcs_button = None

    def _get_party_member_behavior_tree(self, card):
        """Get the current behavior tree for a party member (from deployed unit or overrides)."""
        card_id = card.card_data.get("id")
        # Check if deployed — use live unit's tree
        for unit in gc.game_screen.hex_grid.units:
            if unit.card_id == card_id and unit.allegiance == "Allied":
                return list(unit.behavior_tree), unit.is_stubborn
        # Check overrides
        if card_id in gc.game.party_behavior_overrides:
            override = gc.game.party_behavior_overrides[card_id]
            return list(override.get("tree", ["attack_closest"])), False
        # Build default from card data
        card_data = card.get_current_data()
        dummy_data = {"id": card_id, "card_type": "NPC Card", "states": 1, "data": card_data}
        dummy = Unit(dummy_data)
        return list(dummy.behavior_tree), dummy.is_stubborn

    def _refresh_party_behavior_panel(self, card):
        """Refresh the behavior tree panel for the selected party member."""
        tree, is_stubborn = self._get_party_member_behavior_tree(card)

        # Build display labels from tree
        labels = []
        for b in tree:
            info = Unit.BEHAVIOR_REGISTRY.get(b, {})
            labels.append(info.get("label", b))

        if not labels:
            labels = ["(empty)"]

        if self.party_bt_list:
            self.party_bt_list.set_item_list(labels)

        # Show/hide controls based on stubborn
        if is_stubborn:
            if self.party_bt_move_up: self.party_bt_move_up.hide()
            if self.party_bt_move_down: self.party_bt_move_down.hide()
            if self.party_bt_set_target: self.party_bt_set_target.hide()
        else:
            if self.party_bt_move_up: self.party_bt_move_up.show()
            if self.party_bt_move_down: self.party_bt_move_down.show()
            # Show set target button if tree has follow_target or attack_target
            if "follow_target" in tree or "attack_target" in tree:
                if self.party_bt_set_target: self.party_bt_set_target.show()
            else:
                if self.party_bt_set_target: self.party_bt_set_target.hide()

    def _save_party_behavior_tree(self, card, tree, follow_target=None, attack_target=None):
        """Save a modified behavior tree to both the deployed unit and overrides."""
        card_id = card.card_data.get("id")
        # Update deployed unit if exists
        for unit in gc.game_screen.hex_grid.units:
            if unit.card_id == card_id and unit.allegiance == "Allied":
                unit.behavior_tree = list(tree)
                if follow_target is not None:
                    unit.behavior_follow_target = follow_target
                if attack_target is not None:
                    unit.behavior_attack_target = attack_target
                break
        # Always save to overrides
        if card_id not in gc.game.party_behavior_overrides:
            gc.game.party_behavior_overrides[card_id] = {}
        gc.game.party_behavior_overrides[card_id]["tree"] = list(tree)
        if follow_target is not None:
            gc.game.party_behavior_overrides[card_id]["follow_target"] = follow_target
        if attack_target is not None:
            gc.game.party_behavior_overrides[card_id]["attack_target"] = attack_target

    def _handle_party_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if self.party_browse_npcs_button and event.ui_element == self.party_browse_npcs_button:
                gc.game.current_screen = "npc_browser"
                gc.npc_browser_screen.initialize_screen()
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

            # Behavior tree controls
            if self.party_selected_member is not None and self.party_selected_member < len(gc.game.current_party):
                card = gc.game.current_party[self.party_selected_member]
                tree, is_stubborn = self._get_party_member_behavior_tree(card)
                if not is_stubborn:
                    if self.party_bt_move_up and event.ui_element == self.party_bt_move_up:
                        self._party_bt_move(card, tree, -1)
                        return
                    if self.party_bt_move_down and event.ui_element == self.party_bt_move_down:
                        self._party_bt_move(card, tree, 1)
                        return
                    if self.party_bt_set_target and event.ui_element == self.party_bt_set_target:
                        self._party_bt_enter_target_mode(card, tree)
                        return

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.party_list:
                selection = self.party_list.get_single_selection()
                if selection and selection != "No party members" and selection in self.party_member_names:
                    idx = self.party_member_names.index(selection)
                    if idx < len(gc.game.current_party):
                        self.party_selected_member = idx
                        card = gc.game.current_party[idx]
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

                        # Refresh behavior tree panel
                        self._refresh_party_behavior_panel(card)

    def _party_bt_move(self, card, tree, direction):
        """Move the selected behavior up or down in the tree."""
        if not self.party_bt_list:
            return
        selection = self.party_bt_list.get_single_selection()
        if not selection:
            return
        # Find index by matching label to tree
        for i, b in enumerate(tree):
            info = Unit.BEHAVIOR_REGISTRY.get(b, {})
            if info.get("label", b) == selection:
                new_idx = i + direction
                if 0 <= new_idx < len(tree):
                    tree[i], tree[new_idx] = tree[new_idx], tree[i]
                    self._save_party_behavior_tree(card, tree)
                    self._refresh_party_behavior_panel(card)
                return

    def _party_bt_enter_target_mode(self, card, tree):
        """Enter target selection mode on the map for follow_target/attack_target behaviors."""
        card_id = card.card_data.get("id")
        # Determine which target type is needed
        target_type = None
        if "follow_target" in tree:
            target_type = "follow_target"
        elif "attack_target" in tree:
            target_type = "attack_target"
        if not target_type:
            return
        # Close the menu and enter target selection mode on the game screen
        gc.game_screen.behavior_target_type = target_type
        gc.game_screen.behavior_target_npc_card_id = card_id
        gc.game_screen.player_mode = "behavior_target_select"
        gc.game.current_screen = "game"
        gc.game_screen.initialize_screen()

    def _party_deploy_member(self):
        if self.party_selected_member is None:
            self.party_info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = gc.game.current_party[self.party_selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        already_deployed = any(u.card_id == card.card_data.get("id") for u in gc.game_screen.hex_grid.units if u.allegiance == "Allied")
        if already_deployed:
            self.party_info_text.set_text(f"<font color='#FF0000'>{name} is already deployed!</font>")
            return

        player_pos = gc.game.current_player.position
        neighbors = gc.game_screen.hex_grid.get_neighbors(*player_pos)
        deploy_pos = None
        for n in neighbors:
            row, col = n
            if 0 <= row < gc.game_screen.hex_grid.rows and 0 <= col < gc.game_screen.hex_grid.cols:
                cell = gc.game_screen.hex_grid.grid[row][col]
                if cell["unit"] is None and cell.get("accessible", True):
                    deploy_pos = n
                    break

        if not deploy_pos:
            self.party_info_text.set_text(f"<font color='#FF0000'>No space near player to deploy {name}!</font>")
            return

        card_id = card.card_data.get("id")
        # Check for player-customized behavior tree override
        override = gc.game.party_behavior_overrides.get(card_id, {})
        custom_tree = override.get("tree", None)
        unit_data = {
            "id": card_id,
            "card_type": "NPC Card",
            "states": card.states,
            "data": card_data
        }
        if custom_tree:
            unit_data["custom_behavior_tree"] = custom_tree
        unit = Unit(unit_data)
        unit.set_allegiance("Allied")
        # Apply behavior target overrides (stubborn NPCs ignore overrides)
        if not unit.is_stubborn and override:
            if override.get("follow_target"):
                unit.behavior_follow_target = override["follow_target"]
            if override.get("attack_target"):
                unit.behavior_attack_target = override["attack_target"]
        gc.game_screen.hex_grid.place_unit(unit, deploy_pos[0], deploy_pos[1])

        gc.game_screen.add_to_log(f"{name} deployed to the battlefield!")
        self.party_info_text.set_text(f"<font color='#00FF00'>{name} deployed!</font>")
        self._refresh_current_tab()

    def _party_recall_member(self):
        if self.party_selected_member is None:
            self.party_info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = gc.game.current_party[self.party_selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        deployed_unit = None
        for unit in gc.game_screen.hex_grid.units:
            if unit.card_id == card.card_data.get("id") and unit.allegiance == "Allied":
                deployed_unit = unit
                break

        if not deployed_unit:
            self.party_info_text.set_text(f"<font color='#FF0000'>{name} is not deployed!</font>")
            return

        player_pos = gc.game.current_player.position
        unit_pos = deployed_unit.position
        distance = gc.game_screen.hex_grid.hex_distance(player_pos, unit_pos)
        if distance > 1:
            self.party_info_text.set_text(f"<font color='#FF0000'>{name} must be adjacent to recall!</font>")
            return

        # Save behavior state before removing (unless stubborn)
        if not getattr(deployed_unit, 'is_stubborn', False):
            card_id = card.card_data.get("id")
            gc.game.party_behavior_overrides[card_id] = {
                "tree": list(deployed_unit.behavior_tree),
                "follow_target": deployed_unit.behavior_follow_target,
                "attack_target": deployed_unit.behavior_attack_target,
            }

        gc.game_screen.hex_grid.grid[deployed_unit.position[0]][deployed_unit.position[1]]["unit"] = None
        gc.game_screen.hex_grid.units.remove(deployed_unit)

        gc.game_screen.add_to_log(f"{name} recalled to party.")
        self.party_info_text.set_text(f"<font color='#00FF00'>{name} recalled!</font>")
        self._refresh_current_tab()

    def _party_dismiss_member(self):
        if self.party_selected_member is None:
            self.party_info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = gc.game.current_party[self.party_selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        for unit in gc.game_screen.hex_grid.units[:]:
            if unit.card_id == card.card_data.get("id") and unit.allegiance == "Allied":
                gc.game_screen.hex_grid.grid[unit.position[0]][unit.position[1]]["unit"] = None
                gc.game_screen.hex_grid.units.remove(unit)
                break

        gc.game.current_party.remove(card)
        gc.game_screen.add_to_log(f"{name} dismissed from party.")
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

        active_count = len(gc.game.current_quest_manager.active_quests)
        completed_count = len(gc.game.current_quest_manager.completed_quests)
        failed_count = len(gc.game.current_quest_manager.failed_quests)

        active_btn = self._add(UIButton(pygame.Rect(10, tab_y, tab_width, 30), f"Active ({active_count})", gc.manager))
        self.quest_tab_buttons.append(("active", active_btn))

        completed_btn = self._add(UIButton(pygame.Rect(170, tab_y, tab_width, 30), f"Completed ({completed_count})", gc.manager))
        self.quest_tab_buttons.append(("completed", completed_btn))

        failed_btn = self._add(UIButton(pygame.Rect(330, tab_y, tab_width, 30), f"Failed ({failed_count})", gc.manager))
        self.quest_tab_buttons.append(("failed", failed_btn))

        # Quest list (left panel)
        self._add(UILabel(pygame.Rect(10, tab_y + 40, 350, 25), "Quests:", gc.manager))

        quest_names = self._quest_get_names_for_tab()
        self.quest_names = quest_names
        self.quest_list = self._add(pygame_gui.elements.UISelectionList(
            pygame.Rect(10, tab_y + 70, 350, 500),
            quest_names if quest_names else ["No quests"],
            gc.manager))

        # Quest details (right panel)
        self._add(UILabel(pygame.Rect(370, tab_y + 40, 600, 25), "Quest Details:", gc.manager))
        self.quest_details = self._add(pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select a quest to view details</font>",
            pygame.Rect(370, tab_y + 70, 600, 500), gc.manager))

        # Abandon button (only for active tab)
        if self.quest_current_tab == "active":
            self.quest_abandon_button = self._add(UIButton(
                pygame.Rect(370, tab_y + 580, 150, 35), "Abandon Quest", gc.manager))
        else:
            self.quest_abandon_button = None

    def _quest_get_names_for_tab(self):
        if self.quest_current_tab == "active":
            return [q.get_display_name() for q in gc.game.current_quest_manager.active_quests]
        elif self.quest_current_tab == "completed":
            return [q.get_display_name() for q in gc.game.current_quest_manager.completed_quests]
        elif self.quest_current_tab == "failed":
            return [q.get_display_name() for q in gc.game.current_quest_manager.failed_quests]
        return []

    def _quest_get_quests_for_tab(self):
        if self.quest_current_tab == "active":
            return gc.game.current_quest_manager.active_quests
        elif self.quest_current_tab == "completed":
            return gc.game.current_quest_manager.completed_quests
        elif self.quest_current_tab == "failed":
            return gc.game.current_quest_manager.failed_quests
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
                    success, msg = gc.game.current_quest_manager.abandon_quest(self.quest_selected_quest)
                    gc.game_screen.add_to_log(msg)
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
            gc.game.current_screen = "game"
            gc.game_screen.initialize_screen()
            return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            # Close button
            if event.ui_element == self.close_button:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
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
        gc.screen.fill(gc.DARK_CHARCOAL)
        # Draw active tab highlight (underline bar)
        if self.active_tab in self.tab_buttons:
            btn = self.tab_buttons[self.active_tab]
            rect = btn.relative_rect
            pygame.draw.rect(gc.screen, gc.GOLDEN_YELLOW, (rect.x, rect.y + rect.height, rect.width, 3))
        gc.manager.draw_ui(gc.screen)

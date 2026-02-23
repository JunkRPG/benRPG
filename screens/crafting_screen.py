import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UIWindow, UISelectionList, UILabel
import logging
import game_context as gc

logger = logging.getLogger("JunkRPG")


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
        gc.manager.clear_and_reset()
        self.window = UIWindow(pygame.Rect((gc.WINDOW_WIDTH - 1380) // 2, (gc.WINDOW_HEIGHT - 900) // 2, 1380, 900), gc.manager, "Crafting")
        junk_cards = [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.is_two_state() and card.current_state == 1]
        self.junk_list = UISelectionList(pygame.Rect(15, 75, 330, 300),
                                         [card.get_current_data().get("Name", "Unnamed") for card in junk_cards],
                                         gc.manager, container=self.window)
        blueprint_cards = [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Document Card" and card.card_data.get("subclass", "") == "Blueprint" and card.is_two_state() and card.current_state == 1]
        self.blueprint_list = UISelectionList(pygame.Rect(15, 390, 330, 300),
                                              [card.get_current_data().get("Name", "Unnamed") for card in blueprint_cards],
                                              gc.manager, container=self.window)
        self.materials_list = UISelectionList(pygame.Rect(360, 75, 330, 750),
                                              [], gc.manager, container=self.window, allow_multi_select=True)
        self.update_materials_list()
        self.to_craft_info = UITextBox("<font color='#FFFFFF' size=4>To Craft</font>", pygame.Rect(705, 75, 330, 250), gc.manager, container=self.window)
        self.selected_material_info = UITextBox("<font color='#FFFFFF' size=4>Selected Material</font>", pygame.Rect(705, 335, 330, 250), gc.manager, container=self.window)
        self.state2_info = UITextBox("<font color='#FFFFFF' size=4>State 2 Info</font>", pygame.Rect(705, 595, 330, 250), gc.manager, container=self.window)
        self.requirements_info = UITextBox("<font color='#FFFFFF' size=4>Requirements</font>", pygame.Rect(1050, 75, 330, 300), gc.manager, container=self.window)
        self.craft_button = UIButton(pygame.Rect(1060, 390, 100, 30), "Craft", gc.manager, container=self.window)
        self.close_button = UIButton(pygame.Rect(1170, 390, 100, 30), "Close", gc.manager, container=self.window)
        self.success_label = UILabel(pygame.Rect(1060, 430, 310, 30), "", gc.manager, container=self.window)
        self.update_requirements_display()

    def update_materials_list(self):
        materials_cards = [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.current_state == 1]
        if self.selected_to_craft and self.selected_to_craft.card_data["card_type"] == "Junk Card":
            materials_cards = [card for card in materials_cards if card != self.selected_to_craft]
        self.materials_list.set_item_list([card.get_current_data().get("Name", "Unnamed") for card in materials_cards])

    def update_requirements_display(self):
        if not self.selected_to_craft:
            self.requirements_info.set_text("<font color='#FFFFFF' size=4>Requirements</font>")
            return
        state1_data = self.selected_to_craft.get_state_data(1)
        builder_wood_perk = gc._check_builder_wood_perk()

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

            # Builder wood perk: show Wood as auto-fulfilled on forest terrain
            if builder_wood_perk and req_key == "Requirements: Wood" and required > 0:
                padded_type = material_type.ljust(18)
                requirements_text += f"{padded_type}<font color='#00CCFF'>AUTO</font>   <font color='#FFAA00'>{required:>3}</font><br>"
                continue

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
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
            elif event.ui_element == self.craft_button:
                if self.selected_to_craft and self.check_requirements():
                    for material in self.selected_materials:
                        gc.game.current_player.inventory.remove(material)
                    self.selected_to_craft.toggle_state()
                    crafted_name = self.selected_to_craft.get_state_data(2).get("Name", "Unnamed Item")
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
                    [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.is_two_state() and card.current_state == 1]
                    if event.ui_element == self.junk_list else
                    [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Document Card" and card.card_data.get("subclass", "") == "Blueprint" and card.is_two_state() and card.current_state == 1]
                )
                self.selected_to_craft = next((card for card in cards if card.get_state_data(1).get("Name") == selected_name), None)
                self.update_materials_list()
                if self.selected_to_craft:
                    state1_data = self.selected_to_craft.get_state_data(1)
                    info_text = f"<font color='#FFFFFF' size=4>To Craft: {state1_data.get('Name', 'Unnamed')}<br>" + "<br>".join(f"{k}: {v}" for k, v in state1_data.items() if k != "Name" and v) + "</font>"
                    self.to_craft_info.set_text(info_text)
                    state2_data = self.selected_to_craft.get_state_data(2)
                    state2_text = f"<font color='#FFFFFF' size=4>State 2: {state2_data.get('Name', 'Unnamed')}<br>" + "<br>".join(f"{k}: {v}" for k, v in state2_data.items() if k != 'Name' and v) + "</font>"
                    self.state2_info.set_text(state2_text)
                    self.update_requirements_display()
            elif event.ui_element == self.materials_list:
                selected_names = self.materials_list.get_multi_selection()
                materials_cards = [card for card in gc.game.current_player.inventory if card.card_data["card_type"] == "Junk Card" and card.current_state == 1]
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
        builder_wood_perk = gc._check_builder_wood_perk()
        state1_data = self.selected_to_craft.get_state_data(1)
        for req_key, val_key in self.REQUIREMENT_TO_VALUE.items():
            # Builder wood perk: skip Wood requirement on forest terrain
            if builder_wood_perk and req_key == "Requirements: Wood":
                continue
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
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)

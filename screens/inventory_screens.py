import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UIWindow, UISelectionList, UIDropDownMenu, UILabel, UITextEntryLine
import logging
from inventory_card import InventoryCard
from card_utils import load_card, load_card_index
import game_context as gc

logger = logging.getLogger("JunkRPG")


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
        gc.manager.clear_and_reset()
        window_rect = pygame.Rect((gc.WINDOW_WIDTH - 1200) // 2, (gc.WINDOW_HEIGHT - 800) // 2, 1200, 800)
        self.window = UIWindow(window_rect, gc.manager, "Inventory")
        self.header_label = UILabel(pygame.Rect(0, 0, 1200, 50), "Inventory", gc.manager, container=self.window)
        column_width = 280
        column_height = 500

        # Column labels
        UILabel(pygame.Rect(10, 35, column_width, 25), "Junk / Materials", gc.manager, container=self.window)
        UILabel(pygame.Rect(column_width + 10, 35, column_width, 25), "Documents", gc.manager, container=self.window)
        UILabel(pygame.Rect(2 * column_width + 10, 35, column_width, 25), "Weapons", gc.manager, container=self.window)
        UILabel(pygame.Rect(3 * column_width + 10, 35, column_width, 25), "Consumables / Tools", gc.manager, container=self.window)

        # Junk cards (column 1)
        junk_cards = [card for card in gc.game.current_player.inventory if card.current_state == 1 and card.card_data["card_type"] == "Junk Card"]
        junk_names = []
        for card in junk_cards:
            name = card.get_current_data().get("Name", "Unnamed")
            # Mark consumable junk items
            if card.get_current_data().get("Use_HP") or card.card_data.get("subclass") == "Consumable":
                name += " [Usable]"
            junk_names.append(name)
        self.junk_list = UISelectionList(pygame.Rect(10, 60, column_width, column_height),
                                         junk_names if junk_names else ["No junk items"],
                                         gc.manager, container=self.window)
        self.use_junk_button = UIButton(pygame.Rect(10, 565, column_width, 35), "Use Item", gc.manager, container=self.window)

        # Documents (column 2) - include Guide cards in both states
        documents_cards = [card for card in gc.game.current_player.inventory
                          if card.card_data["card_type"] == "Document Card"
                          and (card.current_state == 1 or card.card_data.get("subclass") == "Guide")]
        self.documents_list = UISelectionList(pygame.Rect(column_width + 10, 60, column_width, column_height - 45),
                                              [card.get_current_data().get("Name", "Unnamed") for card in documents_cards] or ["No documents"],
                                              gc.manager, container=self.window)
        self.read_guide_button = UIButton(pygame.Rect(column_width + 10, column_height + 20, column_width, 35),
                                          "Read Guide", gc.manager, container=self.window)

        # Weapons (column 3) — also match by subclass when Type is missing
        weapons_cards = [card for card in gc.game.current_player.inventory
                         if card.current_state == 2
                         and (card.get_current_data().get("Type") in ["Melee", "Projectile", "Both"]
                              or (not card.get_current_data().get("Type")
                                  and card.card_data.get("subclass") in ["Junk_to_Weapon", "Blueprint_to_Weapon"]))]
        self.weapons_list = UISelectionList(pygame.Rect(2 * column_width + 10, 60, column_width, column_height - 100),
                                            [card.get_current_data().get("Name", "Unnamed") for card in weapons_cards] or ["No weapons"],
                                            gc.manager, container=self.window)
        self.equip_button = UIButton(pygame.Rect(2 * column_width + 10, column_height - 30, column_width, 35), "Equip Weapon", gc.manager, container=self.window)

        # Consumables, Tools, and Ammunition (column 4)
        consumables_cards = [card for card in gc.game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Consumable"]
        tools_cards = [card for card in gc.game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Tool"]
        ammo_cards = [card for card in gc.game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") == "Ammunition"]
        accessory_cards = [card for card in gc.game.current_player.inventory if card.current_state == 2 and card.get_current_data().get("Type") in ["Tool_Belt", "Accessory", "Belt", "Pouch"]]
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
                                                gc.manager, container=self.window)
        self.use_button = UIButton(pygame.Rect(3 * column_width + 10, column_height - 120, column_width, 35), "Use Consumable", gc.manager, container=self.window)
        self.equip_tool_button = UIButton(pygame.Rect(3 * column_width + 10, column_height - 80, column_width, 35), "Equip as Tool/Ammo", gc.manager, container=self.window)
        self.equip_accessory_button = UIButton(pygame.Rect(3 * column_width + 10, column_height - 40, column_width, 35), "Equip Accessory", gc.manager, container=self.window)

        # Item details panel (bottom)
        UILabel(pygame.Rect(10, 610, 200, 25), "Item Details:", gc.manager, container=self.window)
        self.info_text = UITextBox("<font color='#FFFFFF'>Select an item to view its stats and details</font>",
                                   pygame.Rect(10, 635, 870, 120), gc.manager, container=self.window)

        # Creative mode button (browse all cards)
        if gc.game.game_mode == "creative":
            self.browse_cards_button = UIButton(pygame.Rect(900, 635, 150, 35), "Browse Cards", gc.manager, container=self.window)
            # Mode indicator
            UILabel(pygame.Rect(900, 680, 150, 25), "[Creative Mode]", gc.manager, container=self.window)
        else:
            self.browse_cards_button = None

        # Close button
        self.close_button = UIButton(pygame.Rect(1050, 720, 120, 35), "Close", gc.manager, container=self.window)
        self.selected_card = None
        self.selected_from_list = None

    def handle_event(self, event):
        # Handle window X button close
        if event.type == pygame_gui.UI_WINDOW_CLOSE:
            if event.ui_element == self.window:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
            elif self.browse_cards_button and event.ui_element == self.browse_cards_button:
                gc.game.current_screen = "card_browser"
                gc.card_browser_screen.initialize_screen()
            elif event.ui_element == self.equip_button and self.selected_card and self.selected_from_list == "weapons":
                gc.game.current_player.equip_weapon(self.selected_card)
                gc.game_screen.player_info_label.set_text(gc.game_screen.get_player_info())
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
                        msg = gc.game.current_player.equip_tool(self.selected_card)
                        self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
                        self.initialize_screen()  # Refresh to remove from list
                else:
                    self.info_text.set_text("<font color='#FF0000'>Select a consumable, tool, or ammo to equip</font>")
            elif hasattr(self, 'equip_accessory_button') and event.ui_element == self.equip_accessory_button and self.selected_card:
                # Equip accessory (tool belt, pouch, etc.)
                if self.selected_from_list == "consumables":
                    card_type = self.selected_card.get_current_data().get("Type", "")
                    if card_type in ["Tool_Belt", "Accessory", "Belt", "Pouch"]:
                        msg = gc.game.current_player.equip_accessory(self.selected_card)
                        self.info_text.set_text(f"<font color='#00FF00'>{msg}</font>")
                        self.initialize_screen()  # Refresh to remove from list
                    else:
                        self.info_text.set_text("<font color='#FF0000'>Select a tool belt or accessory to equip</font>")
                else:
                    self.info_text.set_text("<font color='#FF0000'>Select a tool belt or accessory to equip</font>")
            elif self.read_guide_button and event.ui_element == self.read_guide_button:
                # Read Guide document to learn a blueprint
                if self.selected_card and self.selected_from_list == "documents" and self.selected_card.card_data.get("subclass") == "Guide":
                    message = gc.game.current_player.read_guide(self.selected_card, gc.game.card_manager)
                    self.info_text.set_text(f"<font color='#00FFFF'>{message}</font>")
                    gc.game_screen.add_to_log(message)
                    self.initialize_screen()
                else:
                    self.info_text.set_text("<font color='#FF0000'>Select a Guide document to read</font>")

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            selected_name = event.text
            # Remove [Usable] suffix if present for matching
            clean_name = selected_name.replace(" [Usable]", "")

            if event.ui_element == self.junk_list:
                self.selected_from_list = "junk"
                self.selected_card = next((card for card in gc.game.current_player.inventory
                                          if card.current_state == 1
                                          and card.card_data["card_type"] == "Junk Card"
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.documents_list:
                self.selected_from_list = "documents"
                self.selected_card = next((card for card in gc.game.current_player.inventory
                                          if card.card_data["card_type"] == "Document Card"
                                          and (card.current_state == 1 or card.card_data.get("subclass") == "Guide")
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.weapons_list:
                self.selected_from_list = "weapons"
                self.selected_card = next((card for card in gc.game.current_player.inventory
                                          if card.current_state == 2
                                          and (card.get_current_data().get("Type") in ["Melee", "Projectile", "Both"]
                                               or (not card.get_current_data().get("Type")
                                                   and card.card_data.get("subclass") in ["Junk_to_Weapon", "Blueprint_to_Weapon"]))
                                          and card.get_current_data().get("Name") == clean_name), None)
            elif event.ui_element == self.consumables_list:
                self.selected_from_list = "consumables"
                # Remove type suffixes for matching
                match_name = clean_name.replace(" [Ammo]", "").replace(" [Accessory]", "")
                self.selected_card = next((card for card in gc.game.current_player.inventory
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
                old_hp = gc.game.current_player.hp
                gc.game.current_player.hp = min(gc.game.current_player.max_hp, gc.game.current_player.hp + hp_change)
                actual_heal = gc.game.current_player.hp - old_hp
                gc.game_screen.add_to_log(f"Used {current_data.get('Name', 'Item')}: +{actual_heal} HP ({old_hp} -> {gc.game.current_player.hp})")
                gc.game.current_player.inventory.remove(self.selected_card)
                self.selected_card = None
                self.initialize_screen()
                gc.game_screen.player_info_label.set_text(gc.game_screen.get_player_info())
            elif hp_change < 0:
                # Negative HP effect (poison, damage item, etc.)
                gc.game.current_player.hp = max(0, gc.game.current_player.hp + hp_change)
                gc.game_screen.add_to_log(f"Used {current_data.get('Name', 'Item')}: {hp_change} HP")
                gc.game.current_player.inventory.remove(self.selected_card)
                self.selected_card = None
                self.initialize_screen()
                gc.game_screen.player_info_label.set_text(gc.game_screen.get_player_info())
            else:
                self.info_text.set_text(f"<font color='#FF0000'>{current_data.get('Name', 'Item')} has no effect!</font>")
        except (ValueError, AttributeError) as e:
            self.info_text.set_text(f"<font color='#FF0000'>Cannot use {current_data.get('Name', 'Item')}: invalid effect</font>")

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


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
        gc.manager.clear_and_reset()
        window_rect = pygame.Rect((gc.WINDOW_WIDTH - 1000) // 2, (gc.WINDOW_HEIGHT - 700) // 2, 1000, 700)
        self.window = UIWindow(window_rect, gc.manager, "Card Browser (Creative Mode)")

        # Header
        UILabel(pygame.Rect(10, 5, 980, 30), "Browse and add cards to your inventory", gc.manager, container=self.window)

        # Filter controls row
        UILabel(pygame.Rect(10, 40, 80, 25), "Filter:", gc.manager, container=self.window)
        filter_options = ["All Cards", "Junk Cards", "Document Cards"]
        self.filter_dropdown = UIDropDownMenu(filter_options, "All Cards",
                                              pygame.Rect(90, 40, 180, 30), gc.manager, container=self.window)

        UILabel(pygame.Rect(290, 40, 60, 25), "Search:", gc.manager, container=self.window)
        self.search_entry = UITextEntryLine(pygame.Rect(350, 40, 200, 30), gc.manager, container=self.window)

        UILabel(pygame.Rect(570, 40, 80, 25), "Add as:", gc.manager, container=self.window)
        self.state_dropdown = UIDropDownMenu(["State 1 (Raw)", "State 2 (Crafted)"], "State 2 (Crafted)",
                                             pygame.Rect(650, 40, 150, 30), gc.manager, container=self.window)

        # Load all cards first
        self._load_all_cards()

        # Build initial display list
        self.filtered_cards = self.all_cards.copy()
        display_items = [f"[{card['type'][:4]}] {card['name']}" for card in self.filtered_cards]
        if not display_items:
            display_items = ["No cards available"]

        # Card list (left side)
        UILabel(pygame.Rect(10, 80, 200, 25), f"Available Cards ({len(self.all_cards)}):", gc.manager, container=self.window)
        self.card_list = UISelectionList(pygame.Rect(10, 105, 550, 400),
                                         display_items, gc.manager, container=self.window,
                                         allow_multi_select=True)

        # Selected cards info (right side)
        UILabel(pygame.Rect(580, 80, 200, 25), "Card Details:", gc.manager, container=self.window)
        self.info_text = UITextBox("<font color='#FFFFFF'>Select a card to view details</font>",
                                   pygame.Rect(580, 105, 390, 400), gc.manager, container=self.window)

        # Buttons at bottom
        self.add_button = UIButton(pygame.Rect(10, 520, 180, 40), "Add Selected", gc.manager, container=self.window)
        self.add_all_button = UIButton(pygame.Rect(200, 520, 180, 40), "Add All Filtered", gc.manager, container=self.window)
        self.clear_selection_button = UIButton(pygame.Rect(390, 520, 180, 40), "Clear Selection", gc.manager, container=self.window)
        self.close_button = UIButton(pygame.Rect(850, 620, 120, 35), "Close", gc.manager, container=self.window)

        # Status label
        self.status_label = UILabel(pygame.Rect(10, 570, 600, 25), "0 cards selected", gc.manager, container=self.window)

    # Card types that can be added to player inventory
    INVENTORY_CARD_TYPES = {"Junk Card", "Document Card"}

    def _load_all_cards(self):
        """Load all cards from card_index.json. Only includes inventory-compatible types (Junk, Document)."""
        self.all_cards = []
        try:
            # Use the existing load_card_index function from card_utils
            card_index = load_card_index()

            for card_id, card_info in card_index.items():
                # card_index uses "type" not "card_type"
                card_type = card_info.get("type", "Unknown")
                # Only include card types that can be added to inventory
                # Also allow compound types like "Document/Skill"
                if not any(t in card_type for t in self.INVENTORY_CARD_TYPES):
                    continue
                card_name = card_info.get("name", card_id)
                self.all_cards.append({
                    "id": card_id,
                    "name": card_name,
                    "type": card_type
                })

            # Sort by type then name
            self.all_cards.sort(key=lambda x: (x["type"], x["name"]))
            logger.debug(f"Card browser loaded {len(self.all_cards)} cards")
        except Exception as e:
            logger.error(f"Error loading card index: {e}")
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

        self.filtered_cards = []
        for card in self.all_cards:
            # Filter by type
            if filter_type != "All Cards":
                # Convert filter option to card type
                type_map = {
                    "Junk Cards": "Junk Card",
                    "Document Cards": "Document Card",
                }
                expected_type = type_map.get(filter_type, "")
                if expected_type not in card["type"]:
                    continue

            # Filter by search text
            if search_text and search_text not in card["name"].lower() and search_text not in card["id"].lower():
                continue

            self.filtered_cards.append(card)

        # Update list display
        display_items = [f"[{card['type'][:4]}] {card['name']}" for card in self.filtered_cards]
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
                if value and not key.startswith("2nd_state_") and not key.startswith("2nd_State_") and key not in ["id"]:
                    # Truncate long values
                    str_val = str(value)
                    if len(str_val) > 50:
                        str_val = str_val[:50] + "..."
                    lines.append(f"  {key}: {str_val}")

            # Show state 2 data if exists
            state2_fields = {k: v for k, v in data.items() if (k.startswith("2nd_state_") or k.startswith("2nd_State_")) and v}
            if state2_fields:
                lines.append("")
                lines.append("<b>State 2:</b>")
                for key, value in state2_fields.items():
                    display_key = key.replace("2nd_State_", "").replace("2nd_state_", "")
                    str_val = str(value)
                    if len(str_val) > 50:
                        str_val = str_val[:50] + "..."
                    lines.append(f"  {display_key}: {str_val}")

            return "<br>".join(lines)
        except Exception as e:
            return f"Error loading card: {e}"

    def _add_cards_to_inventory(self, card_infos):
        """Add selected cards to player inventory."""
        if not gc.game.current_player:
            return "No active player!"

        state = 2 if "State 2" in self.state_dropdown.selected_option else 1
        added_count = 0

        for card_info in card_infos:
            try:
                card_data = load_card(card_info["id"])
                if card_data:
                    inv_card = InventoryCard(card_data)
                    inv_card.current_state = state
                    gc.game.current_player.inventory.append(inv_card)
                    added_count += 1
            except Exception as e:
                logger.error(f"Error adding card {card_info['id']}: {e}")

        return f"Added {added_count} card(s) to inventory"

    def handle_event(self, event):
        if event.type == pygame_gui.UI_WINDOW_CLOSE:
            if event.ui_element == self.window:
                gc.game.current_screen = "tabbed_menu"
                gc.tabbed_menu_screen.active_tab = "Inventory"
                gc.tabbed_menu_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                gc.game.current_screen = "tabbed_menu"
                gc.tabbed_menu_screen.active_tab = "Inventory"
                gc.tabbed_menu_screen.initialize_screen()
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
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


# NPC Browser Screen (Creative Mode - browse and add NPCs to party)
class NpcBrowserScreen:
    def __init__(self):
        self.window = None
        self.npc_list = None
        self.search_entry = None
        self.info_text = None
        self.add_button = None
        self.add_all_button = None
        self.close_button = None
        self.clear_selection_button = None
        self.status_label = None
        self.selected_npcs = []
        self.all_npcs = []
        self.filtered_npcs = []

    def initialize_screen(self):
        gc.manager.clear_and_reset()
        window_rect = pygame.Rect((gc.WINDOW_WIDTH - 1000) // 2, (gc.WINDOW_HEIGHT - 700) // 2, 1000, 700)
        self.window = UIWindow(window_rect, gc.manager, "NPC Browser (Creative Mode)")

        # Header
        UILabel(pygame.Rect(10, 5, 980, 30), "Browse and add NPCs to your party", gc.manager, container=self.window)

        # Search controls row
        UILabel(pygame.Rect(10, 40, 60, 25), "Search:", gc.manager, container=self.window)
        self.search_entry = UITextEntryLine(pygame.Rect(70, 40, 250, 30), gc.manager, container=self.window)

        # Load NPC cards
        self._load_all_npcs()

        # Build initial display list
        self.filtered_npcs = self.all_npcs.copy()
        display_items = [npc['name'] for npc in self.filtered_npcs]
        if not display_items:
            display_items = ["No NPCs available"]

        # NPC list (left side)
        UILabel(pygame.Rect(10, 80, 300, 25), f"Available NPCs ({len(self.all_npcs)}):", gc.manager, container=self.window)
        self.npc_list = UISelectionList(pygame.Rect(10, 105, 550, 400),
                                         display_items, gc.manager, container=self.window,
                                         allow_multi_select=True)

        # NPC details (right side)
        UILabel(pygame.Rect(580, 80, 200, 25), "NPC Details:", gc.manager, container=self.window)
        self.info_text = UITextBox("<font color='#FFFFFF'>Select an NPC to view details</font>",
                                   pygame.Rect(580, 105, 390, 400), gc.manager, container=self.window)

        # Buttons at bottom
        self.add_button = UIButton(pygame.Rect(10, 520, 180, 40), "Add Selected", gc.manager, container=self.window)
        self.add_all_button = UIButton(pygame.Rect(200, 520, 180, 40), "Add All Filtered", gc.manager, container=self.window)
        self.clear_selection_button = UIButton(pygame.Rect(390, 520, 180, 40), "Clear Selection", gc.manager, container=self.window)
        self.close_button = UIButton(pygame.Rect(850, 620, 120, 35), "Close", gc.manager, container=self.window)

        # Status label
        self.status_label = UILabel(pygame.Rect(10, 570, 600, 25), "0 NPCs selected", gc.manager, container=self.window)

    def _load_all_npcs(self):
        """Load all NPC cards from card_index.json."""
        self.all_npcs = []
        try:
            card_index = load_card_index()
            for card_id, card_info in card_index.items():
                card_type = card_info.get("type", "Unknown")
                if card_type != "NPC Card":
                    continue
                card_name = card_info.get("name", card_id)
                self.all_npcs.append({
                    "id": card_id,
                    "name": card_name,
                    "type": card_type
                })
            self.all_npcs.sort(key=lambda x: x["name"])
            logger.debug(f"NPC browser loaded {len(self.all_npcs)} NPCs")
        except Exception as e:
            logger.error(f"Error loading NPC index: {e}")

    def _apply_filter(self):
        """Apply search filter to NPC list."""
        search_text = self.search_entry.get_text().lower().strip()
        self.filtered_npcs = []
        for npc in self.all_npcs:
            if search_text and search_text not in npc["name"].lower() and search_text not in npc["id"].lower():
                continue
            self.filtered_npcs.append(npc)
        display_items = [npc['name'] for npc in self.filtered_npcs]
        self.npc_list.set_item_list(display_items if display_items else ["No NPCs match filter"])

    def _get_npc_details(self, npc_info):
        """Get detailed info about an NPC card."""
        try:
            card_data = load_card(npc_info["id"])
            if not card_data:
                return f"<b>{npc_info['name']}</b><br>Card file not found"

            lines = [f"<b>{npc_info['name']}</b>"]
            lines.append(f"ID: {npc_info['id']}")
            lines.append("")

            data = card_data.get("data", {})
            for key, value in data.items():
                if value and not key.startswith("2nd_state_") and not key.startswith("2nd_State_") and key not in ["id"]:
                    str_val = str(value)
                    if len(str_val) > 50:
                        str_val = str_val[:50] + "..."
                    lines.append(f"{key}: {str_val}")

            return "<br>".join(lines)
        except Exception as e:
            return f"Error loading NPC: {e}"

    def _add_npcs_to_party(self, npc_infos):
        """Add selected NPCs to the player's party."""
        if not gc.game.current_player:
            return "No active player!"

        added_count = 0
        for npc_info in npc_infos:
            try:
                card_data = load_card(npc_info["id"])
                if card_data:
                    inv_card = InventoryCard(card_data)
                    gc.game.current_party.append(inv_card)
                    added_count += 1
            except Exception as e:
                logger.error(f"Error adding NPC {npc_info['id']}: {e}")

        return f"Added {added_count} NPC(s) to party"

    def handle_event(self, event):
        if event.type == pygame_gui.UI_WINDOW_CLOSE:
            if event.ui_element == self.window:
                gc.game.current_screen = "tabbed_menu"
                gc.tabbed_menu_screen.active_tab = "Party"
                gc.tabbed_menu_screen.initialize_screen()
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                gc.game.current_screen = "tabbed_menu"
                gc.tabbed_menu_screen.active_tab = "Party"
                gc.tabbed_menu_screen.initialize_screen()
            elif event.ui_element == self.add_button:
                if self.selected_npcs:
                    msg = self._add_npcs_to_party(self.selected_npcs)
                    self.status_label.set_text(msg)
                    self.selected_npcs = []
                else:
                    self.status_label.set_text("No NPCs selected!")
            elif event.ui_element == self.add_all_button:
                if self.filtered_npcs:
                    msg = self._add_npcs_to_party(self.filtered_npcs)
                    self.status_label.set_text(msg)
                else:
                    self.status_label.set_text("No NPCs to add!")
            elif event.ui_element == self.clear_selection_button:
                self.selected_npcs = []
                self.status_label.set_text("Selection cleared")

        elif event.type == pygame_gui.UI_TEXT_ENTRY_CHANGED:
            if event.ui_element == self.search_entry:
                self._apply_filter()
                self.selected_npcs = []
                self.status_label.set_text("0 NPCs selected")

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.npc_list:
                selected_text = event.text
                if selected_text and selected_text != "No NPCs available" and selected_text != "No NPCs match filter":
                    for npc in self.filtered_npcs:
                        if npc["name"] == selected_text:
                            if npc in self.selected_npcs:
                                self.selected_npcs.remove(npc)
                            else:
                                self.selected_npcs.append(npc)
                            self.info_text.set_text(f"<font color='#FFFFFF'>{self._get_npc_details(npc)}</font>")
                            break
                self.status_label.set_text(f"{len(self.selected_npcs)} NPC(s) selected")

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)

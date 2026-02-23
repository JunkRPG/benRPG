import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UITextBox, UILabel, UISelectionList
import logging
from unit import Unit
import game_context as gc

logger = logging.getLogger("JunkRPG")


class PartyScreen:
    def __init__(self):
        self.window = None
        self.party_list = None
        self.info_text = None
        self.close_button = None
        self.selected_member = None
        self.dismiss_button = None
        self.deploy_button = None
        self.recall_button = None

    def initialize_screen(self):
        gc.manager.clear_and_reset()
        self.selected_member = None

        window_rect = pygame.Rect((gc.WINDOW_WIDTH - 900) // 2, (gc.WINDOW_HEIGHT - 600) // 2, 900, 600)
        self.window = pygame_gui.elements.UIWindow(window_rect, gc.manager, "Party")

        # Header
        pygame_gui.elements.UILabel(
            pygame.Rect(10, 5, 880, 30), "Your Party Members", gc.manager, container=self.window
        )

        # Party members list (left side)
        pygame_gui.elements.UILabel(
            pygame.Rect(10, 40, 300, 25), "Party Members:", gc.manager, container=self.window
        )

        party_names = []
        for card in gc.game.current_party:
            card_data = card.get_current_data()
            name = card_data.get("Name", "Unknown")
            # Check if deployed on map
            deployed = any(u.card_id == card.card_data.get("id") for u in gc.game_screen.hex_grid.units if u.allegiance == "Allied")
            status = " [Deployed]" if deployed else ""
            party_names.append(f"{name}{status}")

        self.party_list = pygame_gui.elements.UISelectionList(
            pygame.Rect(10, 70, 300, 400),
            party_names if party_names else ["No party members"],
            gc.manager, container=self.window
        )
        self.party_member_names = party_names if party_names else []

        # Info panel (right side)
        pygame_gui.elements.UILabel(
            pygame.Rect(320, 40, 560, 25), "Member Details:", gc.manager, container=self.window
        )

        self.info_text = pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select a party member to view details</font>",
            pygame.Rect(320, 70, 560, 350), gc.manager, container=self.window
        )

        # Action buttons
        self.deploy_button = pygame_gui.elements.UIButton(
            pygame.Rect(320, 430, 170, 35), "Deploy to Map", gc.manager, container=self.window
        )

        self.recall_button = pygame_gui.elements.UIButton(
            pygame.Rect(500, 430, 170, 35), "Recall to Party", gc.manager, container=self.window
        )

        self.dismiss_button = pygame_gui.elements.UIButton(
            pygame.Rect(320, 475, 350, 35), "Dismiss from Party", gc.manager, container=self.window
        )

        # Close button
        self.close_button = pygame_gui.elements.UIButton(
            pygame.Rect(780, 5, 100, 30), "Close", gc.manager, container=self.window
        )

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
                return

            if event.ui_element == self.deploy_button:
                self.deploy_member()
                return

            if event.ui_element == self.recall_button:
                self.recall_member()
                return

            if event.ui_element == self.dismiss_button:
                self.dismiss_member()
                return

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.party_list:
                selection = self.party_list.get_single_selection()
                if selection and selection != "No party members" and selection in self.party_member_names:
                    idx = self.party_member_names.index(selection)
                    if idx < len(gc.game.current_party):
                        self.selected_member = idx
                        card = gc.game.current_party[idx]
                        card_data = card.get_current_data()

                        # Build info display
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

                        self.info_text.set_text(f"<font color='#FFFFFF'>{'<br>'.join(info_lines)}</font>")

    def deploy_member(self):
        if self.selected_member is None:
            self.info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = gc.game.current_party[self.selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        # Check if already deployed
        already_deployed = any(u.card_id == card.card_data.get("id") for u in gc.game_screen.hex_grid.units if u.allegiance == "Allied")
        if already_deployed:
            self.info_text.set_text(f"<font color='#FF0000'>{name} is already deployed!</font>")
            return

        # Find a spot near the player to deploy
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
            self.info_text.set_text(f"<font color='#FF0000'>No space near player to deploy {name}!</font>")
            return

        # Create unit from card and place on map
        unit_data = {
            "id": card.card_data.get("id"),
            "card_type": "NPC Card",
            "states": card.states,
            "data": card_data
        }
        unit = Unit(unit_data)
        unit.set_allegiance("Allied")  # Ensure allied
        gc.game_screen.hex_grid.place_unit(unit, deploy_pos[0], deploy_pos[1])

        gc.game_screen.add_to_log(f"{name} deployed to the battlefield!")
        self.info_text.set_text(f"<font color='#00FF00'>{name} deployed!</font>")
        self.initialize_screen()  # Refresh to show [Deployed] status

    def recall_member(self):
        """Recall a deployed NPC from the map back to the party (stays in party). Must be adjacent to player."""
        if self.selected_member is None:
            self.info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = gc.game.current_party[self.selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        # Check if deployed on map
        deployed_unit = None
        for unit in gc.game_screen.hex_grid.units:
            if unit.card_id == card.card_data.get("id") and unit.allegiance == "Allied":
                deployed_unit = unit
                break

        if not deployed_unit:
            self.info_text.set_text(f"<font color='#FF0000'>{name} is not deployed!</font>")
            return

        # Check if adjacent to player
        player_pos = gc.game.current_player.position
        unit_pos = deployed_unit.position
        distance = gc.game_screen.hex_grid.hex_distance(player_pos, unit_pos)
        if distance > 1:
            self.info_text.set_text(f"<font color='#FF0000'>{name} must be adjacent to recall!</font>")
            return

        # Remove from map but keep in party
        gc.game_screen.hex_grid.grid[deployed_unit.position[0]][deployed_unit.position[1]]["unit"] = None
        gc.game_screen.hex_grid.units.remove(deployed_unit)

        gc.game_screen.add_to_log(f"{name} recalled to party.")
        self.info_text.set_text(f"<font color='#00FF00'>{name} recalled!</font>")
        self.initialize_screen()  # Refresh to update [Deployed] status

    def dismiss_member(self):
        if self.selected_member is None:
            self.info_text.set_text("<font color='#FF0000'>Select a party member first!</font>")
            return

        card = gc.game.current_party[self.selected_member]
        card_data = card.get_current_data()
        name = card_data.get("Name", "Unknown")

        # Remove from map if deployed
        for unit in gc.game_screen.hex_grid.units[:]:
            if unit.card_id == card.card_data.get("id") and unit.allegiance == "Allied":
                gc.game_screen.hex_grid.grid[unit.position[0]][unit.position[1]]["unit"] = None
                gc.game_screen.hex_grid.units.remove(unit)
                break

        # Remove from party
        gc.game.current_party.remove(card)
        gc.game_screen.add_to_log(f"{name} dismissed from party.")
        self.selected_member = None
        self.initialize_screen()  # Refresh

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


# QuestScreen class for viewing and managing quests
class QuestScreen:
    def __init__(self):
        self.window = None
        self.tab_buttons = []
        self.quest_list = None
        self.quest_details = None
        self.abandon_button = None
        self.close_button = None
        self.current_tab = "active"  # "active", "completed", "failed"
        self.selected_quest = None
        self.quest_names = []

    def initialize_screen(self):
        gc.manager.clear_and_reset()
        self.selected_quest = None

        window_rect = pygame.Rect((gc.WINDOW_WIDTH - 1000) // 2, (gc.WINDOW_HEIGHT - 700) // 2, 1000, 700)
        self.window = pygame_gui.elements.UIWindow(window_rect, gc.manager, "Quest Journal")

        # Tab buttons
        tab_y = 5
        tab_width = 150
        self.tab_buttons = []

        active_count = len(gc.game.current_quest_manager.active_quests)
        completed_count = len(gc.game.current_quest_manager.completed_quests)
        failed_count = len(gc.game.current_quest_manager.failed_quests)

        active_btn = pygame_gui.elements.UIButton(
            pygame.Rect(10, tab_y, tab_width, 30),
            f"Active ({active_count})",
            gc.manager, container=self.window
        )
        self.tab_buttons.append(("active", active_btn))

        completed_btn = pygame_gui.elements.UIButton(
            pygame.Rect(170, tab_y, tab_width, 30),
            f"Completed ({completed_count})",
            gc.manager, container=self.window
        )
        self.tab_buttons.append(("completed", completed_btn))

        failed_btn = pygame_gui.elements.UIButton(
            pygame.Rect(330, tab_y, tab_width, 30),
            f"Failed ({failed_count})",
            gc.manager, container=self.window
        )
        self.tab_buttons.append(("failed", failed_btn))

        # Quest list (left panel)
        pygame_gui.elements.UILabel(
            pygame.Rect(10, 45, 350, 25), "Quests:", gc.manager, container=self.window
        )

        quest_names = self._get_quest_names_for_tab()
        self.quest_names = quest_names
        self.quest_list = pygame_gui.elements.UISelectionList(
            pygame.Rect(10, 75, 350, 500),
            quest_names if quest_names else ["No quests"],
            gc.manager, container=self.window
        )

        # Quest details (right panel)
        pygame_gui.elements.UILabel(
            pygame.Rect(370, 45, 600, 25), "Quest Details:", gc.manager, container=self.window
        )

        self.quest_details = pygame_gui.elements.UITextBox(
            "<font color='#FFFFFF'>Select a quest to view details</font>",
            pygame.Rect(370, 75, 600, 500), gc.manager, container=self.window
        )

        # Abandon button (only for active tab)
        if self.current_tab == "active":
            self.abandon_button = pygame_gui.elements.UIButton(
                pygame.Rect(370, 585, 150, 35), "Abandon Quest", gc.manager, container=self.window
            )
        else:
            self.abandon_button = None

        # Close button
        self.close_button = pygame_gui.elements.UIButton(
            pygame.Rect(870, 5, 100, 30), "Close", gc.manager, container=self.window
        )

    def _get_quest_names_for_tab(self):
        """Get quest names for the current tab."""
        if self.current_tab == "active":
            return [q.get_display_name() for q in gc.game.current_quest_manager.active_quests]
        elif self.current_tab == "completed":
            return [q.get_display_name() for q in gc.game.current_quest_manager.completed_quests]
        elif self.current_tab == "failed":
            return [q.get_display_name() for q in gc.game.current_quest_manager.failed_quests]
        return []

    def _get_quests_for_tab(self):
        """Get quest list for the current tab."""
        if self.current_tab == "active":
            return gc.game.current_quest_manager.active_quests
        elif self.current_tab == "completed":
            return gc.game.current_quest_manager.completed_quests
        elif self.current_tab == "failed":
            return gc.game.current_quest_manager.failed_quests
        return []

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.close_button:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()
                return

            # Tab buttons
            for tab_name, btn in self.tab_buttons:
                if event.ui_element == btn:
                    self.current_tab = tab_name
                    self.selected_quest = None
                    self.initialize_screen()
                    return

            # Abandon button
            if self.abandon_button and event.ui_element == self.abandon_button:
                if self.selected_quest:
                    success, msg = gc.game.current_quest_manager.abandon_quest(self.selected_quest)
                    gc.game_screen.add_to_log(msg)
                    self.selected_quest = None
                    self.initialize_screen()
                return

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.quest_list:
                selection = self.quest_list.get_single_selection()
                if selection and selection != "No quests" and selection in self.quest_names:
                    idx = self.quest_names.index(selection)
                    quests = self._get_quests_for_tab()
                    if idx < len(quests):
                        self.selected_quest = quests[idx]
                        self._update_quest_details()

    def _update_quest_details(self):
        """Update the quest details panel."""
        if not self.selected_quest:
            self.quest_details.set_text("<font color='#FFFFFF'>Select a quest to view details</font>")
            return

        quest = self.selected_quest
        lines = []

        # Quest name
        lines.append(f"<b>{quest.get_display_name()}</b>")
        lines.append("")

        # Status
        if quest.is_complete:
            lines.append("<font color='#00FF00'>Status: COMPLETED</font>")
        elif quest.is_failed:
            lines.append("<font color='#FF0000'>Status: FAILED</font>")
        else:
            lines.append("<font color='#FFFF00'>Status: IN PROGRESS</font>")
        lines.append("")

        # Description
        lines.append("<b>Description:</b>")
        lines.append(quest.get_filled_description())
        lines.append("")

        # Tracked units
        if quest.tracked_units:
            lines.append("<b>Tracked Characters:</b>")
            for pid, unit in quest.tracked_units.items():
                status = "Active" if unit.hp > 0 else "Defeated"
                lines.append(f"- {pid}: {unit.name} ({status})")
            lines.append("")

        # Tracked locations
        if quest.tracked_locations:
            lines.append("<b>Tracked Locations:</b>")
            for pid, pos in quest.tracked_locations.items():
                lines.append(f"- {pid}: Position {pos}")
            lines.append("")

        # Turn count
        lines.append(f"Turns elapsed: {quest.turn_count}")

        self.quest_details.set_text(f"<font color='#FFFFFF'>{'<br>'.join(lines)}</font>")

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)


# SkillsScreen class for managing learned and equipped skills
class SkillsScreen:
    def __init__(self):
        self.ui_elements = []
        self.learned_skills_list = None
        self.equipped_skills_list = None
        self.learnable_cards_list = None
        self.learn_button = None
        self.equip_button = None
        self.unequip_button = None
        self.back_button = None
        self.selected_learnable = None
        self.selected_learned = None
        self.selected_equipped = None
        # Flip animation tracking
        self.animating_card = None

    def initialize_screen(self):
        gc.manager.clear_and_reset()
        self.ui_elements = []
        self.selected_learnable = None
        self.selected_learned = None
        self.selected_equipped = None

        # Title
        title = UILabel(
            pygame.Rect(0, 20, gc.WINDOW_WIDTH, 40),
            "Skills Management",
            gc.manager,
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(title)

        # Back button
        self.back_button = UIButton(
            pygame.Rect(20, 20, 100, 40),
            "Back",
            gc.manager
        )
        self.ui_elements.append(self.back_button)

        # Three columns layout
        column_width = (gc.WINDOW_WIDTH - 80) // 3
        list_height = gc.WINDOW_HEIGHT - 250
        y_start = 80

        # Column 1: Learnable Cards (Document cards that can become skills)
        col1_x = 20
        learnable_label = UILabel(
            pygame.Rect(col1_x, y_start, column_width, 30),
            "Learnable Documents",
            gc.manager
        )
        self.ui_elements.append(learnable_label)

        learnable_items = self._get_learnable_cards()
        self.learnable_cards_list = UISelectionList(
            pygame.Rect(col1_x, y_start + 35, column_width, list_height),
            learnable_items,
            gc.manager,
            allow_multi_select=False
        )
        self.ui_elements.append(self.learnable_cards_list)

        self.learn_button = UIButton(
            pygame.Rect(col1_x, y_start + list_height + 45, column_width, 40),
            "Learn Skill",
            gc.manager
        )
        self.ui_elements.append(self.learn_button)

        # Column 2: Learned Skills
        col2_x = col1_x + column_width + 20
        learned_label = UILabel(
            pygame.Rect(col2_x, y_start, column_width, 30),
            "Learned Skills",
            gc.manager
        )
        self.ui_elements.append(learned_label)

        learned_items = self._get_learned_skills()
        self.learned_skills_list = UISelectionList(
            pygame.Rect(col2_x, y_start + 35, column_width, list_height),
            learned_items,
            gc.manager,
            allow_multi_select=False
        )
        self.ui_elements.append(self.learned_skills_list)

        self.equip_button = UIButton(
            pygame.Rect(col2_x, y_start + list_height + 45, column_width, 40),
            "Equip Skill",
            gc.manager
        )
        self.ui_elements.append(self.equip_button)

        # Column 3: Equipped Skills
        col3_x = col2_x + column_width + 20
        equipped_label = UILabel(
            pygame.Rect(col3_x, y_start, column_width, 30),
            f"Equipped Skills ({len(gc.game.current_player.equipped_skills)}/{gc.game.current_player.active_skill_slots})",
            gc.manager
        )
        self.ui_elements.append(equipped_label)

        equipped_items = self._get_equipped_skills()
        self.equipped_skills_list = UISelectionList(
            pygame.Rect(col3_x, y_start + 35, column_width, list_height),
            equipped_items,
            gc.manager,
            allow_multi_select=False
        )
        self.ui_elements.append(self.equipped_skills_list)

        self.unequip_button = UIButton(
            pygame.Rect(col3_x, y_start + list_height + 45, column_width, 40),
            "Unequip Skill",
            gc.manager
        )
        self.ui_elements.append(self.unequip_button)

    def _get_learnable_cards(self):
        """Get Document cards from inventory that can be transformed into skills."""
        learnable = []
        for card in gc.game.current_player.inventory:
            card_type = card.card_data.get("card_type", "")
            # Check for Document/Skill compound type or Skill_Tome subclass
            if "Document/Skill" in card_type or card.card_data.get("subclass") == "Skill_Tome":
                if card.current_state == 1:  # Still in Document state
                    name = card.get_current_data().get("Name", "Unknown")
                    learnable.append(name)
        return learnable

    def _get_learned_skills(self):
        """Get all learned skills."""
        skills = []
        for card in gc.game.current_player.skills:
            skill_data = card.get_current_data()
            name = skill_data.get("Name", "Unknown")
            skill_type = skill_data.get("Skill_Type", "Unknown")
            skills.append(f"{name} ({skill_type})")
        return skills

    def _get_equipped_skills(self):
        """Get equipped active skills."""
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

    def _find_card_by_name(self, name, card_list):
        """Find a card in a list by its name."""
        for card in card_list:
            card_name = card.get_current_data().get("Name", "")
            if card_name == name:
                return card
        return None

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                gc.game.current_screen = "game"
                gc.game_screen.initialize_screen()

            elif event.ui_element == self.learn_button:
                selections = self.learnable_cards_list.get_single_selection()
                if selections:
                    # Find the card in inventory
                    for card in gc.game.current_player.inventory:
                        card_type = card.card_data.get("card_type", "")
                        if ("Document/Skill" in card_type or card.card_data.get("subclass") == "Skill_Tome"):
                            if card.current_state == 1:
                                name = card.get_current_data().get("Name", "")
                                if name == selections:
                                    msg = gc.game.current_player.learn_skill(card)
                                    gc.game_screen.log.append(msg)
                                    self.initialize_screen()  # Refresh lists
                                    break

            elif event.ui_element == self.equip_button:
                selections = self.learned_skills_list.get_single_selection()
                if selections:
                    # Parse skill name from "Name (Type)" format
                    skill_name = selections.split(" (")[0]
                    for card in gc.game.current_player.skills:
                        if card.get_current_data().get("Name") == skill_name:
                            msg = gc.game.current_player.equip_skill(card)
                            gc.game_screen.log.append(msg)
                            self.initialize_screen()
                            break

            elif event.ui_element == self.unequip_button:
                selections = self.equipped_skills_list.get_single_selection()
                if selections:
                    # Parse skill name (may have cooldown suffix)
                    skill_name = selections.split(" (")[0]
                    for card in gc.game.current_player.equipped_skills:
                        if card.get_current_data().get("Name") == skill_name:
                            msg = gc.game.current_player.unequip_skill(card)
                            gc.game_screen.log.append(msg)
                            self.initialize_screen()
                            break

    def update(self):
        # Update flip animations
        if self.animating_card:
            if self.animating_card.update_flip_animation():
                self.animating_card = None
                self.initialize_screen()  # Refresh after animation complete

    def draw(self):
        gc.screen.fill(gc.DARK_CHARCOAL)
        gc.manager.draw_ui(gc.screen)

"""
Save/Load System for JunkRPG
Handles serialization and deserialization of game state to JSON files.
"""

import json
import os
import datetime
from inventory_card import InventoryCard
from unit import Unit
from card_utils import load_card


SAVE_DIR = "saves"
SAVE_VERSION = 1


class SaveManager:
    """Handles all save/load operations for the game."""

    def __init__(self):
        os.makedirs(SAVE_DIR, exist_ok=True)

    # ============================
    # Saving
    # ============================

    def save_game(self, game_ref, game_screen, save_type="manual", save_label="Manual Save"):
        """
        Save the current game state to a JSON file.

        Args:
            game_ref: The Game object
            game_screen: The GameScreen object
            save_type: "autosave" or "manual"
            save_label: Human-readable label like "Level Start" or "Turn 15"

        Returns:
            (success, filepath_or_message)
        """
        try:
            save_data = self._build_save_data(game_ref, game_screen, save_type, save_label)
            filepath = self._generate_filepath(save_type, game_screen.current_level_file)
            with open(filepath, 'w') as f:
                json.dump(save_data, f, indent=2)
            return True, filepath
        except Exception as e:
            print(f"Error saving game: {e}")
            import traceback
            traceback.print_exc()
            return False, str(e)

    def _build_save_data(self, game_ref, game_screen, save_type, save_label):
        """Build the complete save data dictionary."""
        timestamp = datetime.datetime.now().isoformat()

        save_data = {
            "version": SAVE_VERSION,
            "save_type": save_type,
            "save_label": save_label,
            "timestamp": timestamp,
            "level_file": game_screen.current_level_file,
            "campaign_file": game_screen.campaign_file,
            "current_level_idx": game_screen.current_level_idx,
            "multiplayer_mode": game_ref.multiplayer_mode,
            "game_mode": game_ref.game_mode,
        }

        # Serialize players
        if game_ref.multiplayer_mode and game_ref.players:
            save_data["players"] = [self._serialize_player(p) for p in game_ref.players]
            save_data["current_player_index"] = game_ref.current_player_index
        else:
            save_data["player"] = self._serialize_player(game_ref.player)

        # Serialize party (single-player party list)
        save_data["party"] = self._serialize_party(game_ref)

        # Serialize units on the grid
        save_data["units"] = self._serialize_units(game_screen.hex_grid)

        # Serialize location data mutations
        save_data["location_data"] = self._serialize_location_data(game_screen.hex_grid)

        # Serialize card_drawing_hex state
        save_data["card_drawing_hexes"] = game_screen.hex_grid.card_drawing_hexes
        save_data["teleport_pads"] = game_screen.hex_grid.teleport_pads

        # Serialize quest manager
        save_data["quest_manager"] = self._serialize_quest_manager(game_ref.quest_manager)
        if game_ref.multiplayer_mode and game_ref.quest_managers:
            save_data["quest_managers"] = [self._serialize_quest_manager(qm) for qm in game_ref.quest_managers]

        # Serialize instance manager
        save_data["instance_manager"] = self._serialize_instance_manager(game_ref.instance_manager)

        # Serialize transition manager
        save_data["transition_manager"] = self._serialize_transition_manager(game_ref.transition_manager)

        # Serialize game screen state
        save_data["game_screen"] = {
            "turn_phase": game_screen.turn_phase,
            "log": list(game_screen.log),
            "transition_target_cycle": game_screen.transition_target_cycle,
            "turn_cycle_count": getattr(game_screen, 'turn_cycle_count', 0),
            "player_class": game_screen.player_class,
        }

        # Campaign data
        if game_screen.campaign:
            save_data["campaign"] = game_screen.campaign

        # Party behavior overrides (player-customized behavior trees)
        save_data["party_behavior_overrides"] = getattr(game_ref, 'party_behavior_overrides', {})

        # Boss encounter state
        save_data["boss_encounter_phase"] = getattr(game_screen, 'boss_encounter_phase', 0)
        save_data["boss_encounter_phase2_tags"] = getattr(game_screen, 'boss_encounter_phase2_tags', [])
        save_data["level_completed"] = getattr(game_screen, 'level_completed', False)

        return save_data

    def _generate_filepath(self, save_type, level_file):
        """Generate a save file path."""
        level_name = "unknown"
        if level_file:
            level_name = os.path.splitext(os.path.basename(level_file))[0]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{save_type}_{level_name}_{timestamp}.json"
        return os.path.join(SAVE_DIR, filename)

    # ============================
    # Player Serialization
    # ============================

    def _serialize_player(self, player):
        """Serialize a Player object to a dict."""
        return {
            "class_name": player.class_name,
            "name": player.name,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "movement": player.movement,
            "projectile_range": player.projectile_range,
            "attacks": player.attacks,
            "special_attack": player.special_attack,
            "position": list(player.position) if player.position else None,
            "player_number": player.player_number,
            "player_color": list(player.player_color),
            # Inventory: store card_id + current_state for each card
            "inventory": [self._serialize_inventory_card(c) for c in player.inventory],
            # Equipped weapons (these stay in inventory, so just store identifiers)
            "melee_weapon": self._serialize_card_ref(player.melee_weapon),
            "projectile_weapon": self._serialize_card_ref(player.projectile_weapon),
            # Skills
            "skills": [self._serialize_inventory_card(c) for c in player.skills],
            "equipped_skills": [self._serialize_card_ref(c) for c in player.equipped_skills],
            "skill_cooldowns": dict(player.skill_cooldowns),
            "active_skill_slots": player.active_skill_slots,
            # Tools (removed from inventory when equipped)
            "equipped_tools": [self._serialize_inventory_card(t) if t else None for t in player.equipped_tools],
            "equipped_tool": self._serialize_inventory_card(player.equipped_tool) if player.equipped_tool else None,
            "tool_slots": player.tool_slots,
            # Accessory (removed from inventory when equipped)
            "equipped_accessory": self._serialize_inventory_card(player.equipped_accessory) if player.equipped_accessory else None,
            # Range properties
            "projectile_range_type": player.projectile_range_type,
            "projectile_include_pos": player.projectile_include_pos,
            "projectile_exclude_adj": player.projectile_exclude_adj,
            "piercing_projectile": player.piercing_projectile,
            # Combat state
            "movement_used": player.movement_used,
            "action_used": player.action_used,
            "warrior_attacks_remaining": player.warrior_attacks_remaining,
            "double_attack_active": player.double_attack_active,
            # Super charge
            "super_charge": player.super_charge,
            "super_charge_max": player.super_charge_max,
            "super_attack_ready": player.super_attack_ready,
            # Healer flag
            "is_healer": player.is_healer,
            # Per-player party (used in multiplayer)
            "party": [self._serialize_inventory_card(c) for c in player.party],
        }

    def _serialize_inventory_card(self, card):
        """Serialize an InventoryCard to a minimal dict."""
        if not card:
            return None
        data = {
            "card_id": card.card_data.get("id", ""),
            "current_state": card.current_state,
        }
        if hasattr(card, 'guide_drawn_ids') and card.guide_drawn_ids:
            data["guide_drawn_ids"] = card.guide_drawn_ids
        return data

    def _serialize_card_ref(self, card):
        """Serialize a reference to a card (for matching against inventory on load)."""
        if not card:
            return None
        return {
            "card_id": card.card_data.get("id", ""),
            "current_state": card.current_state,
        }

    # ============================
    # Party Serialization
    # ============================

    def _serialize_party(self, game_ref):
        """Serialize the party (list of InventoryCards for allied NPCs)."""
        party = game_ref.party if not game_ref.multiplayer_mode else []
        return [self._serialize_inventory_card(c) for c in party]

    # ============================
    # Unit Serialization
    # ============================

    def _serialize_units(self, hex_grid):
        """Serialize all units on the hex grid."""
        units = []
        for unit in hex_grid.units:
            units.append({
                "card_id": unit.card_id,
                "current_state": unit.current_state,
                "hp": unit.hp,
                "max_hp": unit.max_hp,
                "position": list(unit.position) if unit.position else None,
                "allegiance": unit.allegiance,
                "quest_target_position": list(unit.quest_target_position) if unit.quest_target_position else None,
                "quest_movement_priority": unit.quest_movement_priority if unit.quest_target_position else None,
                "name": unit.name,
                "movement": unit.movement,
                "melee_damage": unit.melee_damage,
                "projectile_damage": unit.projectile_damage,
                "projectile_range": unit.projectile_range,
                "garrison_target_location": list(unit.garrison_target_location) if getattr(unit, 'garrison_target_location', None) else None,
                "behavior_tree": getattr(unit, 'behavior_tree', []),
                "is_stubborn": getattr(unit, 'is_stubborn', False),
                "behavior_follow_target": getattr(unit, 'behavior_follow_target', None),
                "behavior_attack_target": getattr(unit, 'behavior_attack_target', None),
                "recruit_cooldown": getattr(unit, 'recruit_cooldown', 0),
                "boss_encounter_tag": getattr(unit, 'boss_encounter_tag', None),
                "dialogue_delivered": getattr(unit, 'dialogue_delivered', False),
                "_death_processed": getattr(unit, '_death_processed', False),
            })
        return units

    # ============================
    # Location Data Serialization
    # ============================

    def _serialize_location_data(self, hex_grid):
        """Serialize dynamic location data (shop contents, health, visited state, spawn state)."""
        serialized = {}
        for pos, loc_data in hex_grid.location_data.items():
            key = f"{pos[0]},{pos[1]}"
            entry = {
                "card_id": loc_data["card"].card_data.get("id", "") if loc_data.get("card") else None,
                "card_state": loc_data["card"].current_state if loc_data.get("card") else None,
                "shop": [self._serialize_inventory_card(c) for c in loc_data.get("shop", [])],
                "turns": loc_data.get("turns", 0),
                "visited": loc_data.get("visited", False),
            }
            # Spawn location fields
            if "health" in loc_data:
                entry["health"] = loc_data["health"]
            if "max_health" in loc_data:
                entry["max_health"] = loc_data["max_health"]
            if "spawn_active" in loc_data:
                entry["spawn_active"] = loc_data["spawn_active"]
            if "spawn_card_id" in loc_data:
                entry["spawn_card_id"] = loc_data["spawn_card_id"]
            if "spawn_timer" in loc_data:
                entry["spawn_timer"] = loc_data["spawn_timer"]
            if "spawn_interval" in loc_data:
                entry["spawn_interval"] = loc_data["spawn_interval"]
            # Garrison data
            garrison = loc_data.get("garrison_npcs", [])
            if garrison:
                entry["garrison_npcs"] = garrison
            serialized[key] = entry
        return serialized

    # ============================
    # Quest Manager Serialization
    # ============================

    def _serialize_quest_manager(self, quest_manager):
        """Serialize the quest manager state."""
        return {
            "active_quests": [self._serialize_active_quest(q) for q in quest_manager.active_quests],
            "completed_count": len(quest_manager.completed_quests),
            "failed_count": len(quest_manager.failed_quests),
        }

    def _serialize_active_quest(self, quest):
        """Serialize an active quest."""
        quest_data = quest.quest_card.get_current_data()
        return {
            "quest_card_id": quest.quest_card.card_data.get("id", ""),
            "quest_card_state": quest.quest_card.current_state,
            "turn_count": quest.turn_count,
            "is_complete": quest.is_complete,
            "is_failed": quest.is_failed,
            "tracked_units": {
                pid: {
                    "card_id": unit.card_id,
                    "position": list(unit.position) if unit.position else None,
                    "name": unit.name,
                }
                for pid, unit in quest.tracked_units.items()
            },
            "tracked_locations": {
                pid: list(pos) if pos else None
                for pid, pos in quest.tracked_locations.items()
            },
            "resolved_names": {
                pid: data.get("name", "")
                for pid, data in (quest.resolver.resolved.items() if quest.resolver else {})
            },
        }

    # ============================
    # Instance Manager Serialization
    # ============================

    def _serialize_instance_manager(self, instance_manager):
        """Serialize instance manager state."""
        return {
            "trigger_chance": instance_manager.trigger_chance,
            "deck_card_ids": [ic.card_id for ic in instance_manager.instance_deck],
        }

    # ============================
    # Transition Manager Serialization
    # ============================

    def _serialize_transition_manager(self, transition_manager):
        """Serialize transition manager state."""
        data = {
            "weather_effect": transition_manager.weather_effect,
            "weather_modifiers": transition_manager.weather_modifiers,
        }
        if transition_manager.active_transition:
            tc = transition_manager.active_transition
            data["active_card_id"] = tc.card_id
            data["active_card_state"] = tc.current_state
        else:
            data["active_card_id"] = None
            data["active_card_state"] = None
        return data

    # ============================
    # Loading
    # ============================

    def load_save_file(self, filepath):
        """Load and return save data from a file."""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading save file {filepath}: {e}")
            return None

    def get_all_saves(self):
        """Get a list of all save files with metadata, sorted newest first."""
        saves = []
        if not os.path.exists(SAVE_DIR):
            return saves
        for filename in os.listdir(SAVE_DIR):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(SAVE_DIR, filename)
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                saves.append({
                    "filepath": filepath,
                    "filename": filename,
                    "save_type": data.get("save_type", "unknown"),
                    "save_label": data.get("save_label", "Unknown"),
                    "timestamp": data.get("timestamp", ""),
                    "level_file": data.get("level_file", ""),
                    "campaign_file": data.get("campaign_file"),
                    "multiplayer_mode": data.get("multiplayer_mode", False),
                    "game_mode": data.get("game_mode", "survival"),
                })
            except Exception:
                continue
        # Sort by timestamp descending (newest first)
        saves.sort(key=lambda s: s["timestamp"], reverse=True)
        return saves

    def delete_save(self, filepath):
        """Delete a save file."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception as e:
            print(f"Error deleting save: {e}")
        return False

    def delete_saves_for_level(self, level_file):
        """Delete all saves matching a specific level file."""
        deleted = 0
        for save_info in self.get_all_saves():
            if save_info["level_file"] == level_file:
                if self.delete_save(save_info["filepath"]):
                    deleted += 1
        return deleted

    def get_most_recent_save(self, level_file=None, save_label=None):
        """Get the most recent save, optionally filtered by level and/or label."""
        for save_info in self.get_all_saves():
            if level_file and save_info["level_file"] != level_file:
                continue
            if save_label and save_info["save_label"] != save_label:
                continue
            return save_info
        return None

    def get_latest_level_start_save(self, level_file):
        """Get the most recent 'Level Start' autosave for a given level."""
        return self.get_most_recent_save(level_file=level_file, save_label="Level Start")

    # ============================
    # Deserialization (Rebuilding Game State)
    # ============================

    def rebuild_player(self, player_data):
        """Rebuild a Player object from save data.

        Returns:
            Player object with all state restored.
        """
        from player import Player

        player = Player(player_data["class_name"])
        player.name = player_data.get("name", "")
        player.hp = player_data["hp"]
        player.max_hp = player_data["max_hp"]
        player.movement = player_data["movement"]
        player.projectile_range = player_data["projectile_range"]
        player.attacks = player_data["attacks"]
        player.special_attack = player_data["special_attack"]
        player.player_number = player_data.get("player_number", 1)
        player.player_color = tuple(player_data.get("player_color", [0, 200, 0]))

        # Range properties
        player.projectile_range_type = player_data.get("projectile_range_type", "line_of_sight")
        player.projectile_include_pos = player_data.get("projectile_include_pos", False)
        player.projectile_exclude_adj = player_data.get("projectile_exclude_adj", False)
        player.piercing_projectile = player_data.get("piercing_projectile", False)

        # Combat state
        player.movement_used = player_data.get("movement_used", False)
        player.action_used = player_data.get("action_used", False)
        player.warrior_attacks_remaining = player_data.get("warrior_attacks_remaining", 0)
        player.double_attack_active = player_data.get("double_attack_active", False)

        # Super charge
        player.super_charge = player_data.get("super_charge", 0)
        player.super_charge_max = player_data.get("super_charge_max", 5)
        player.super_attack_ready = player_data.get("super_attack_ready", False)

        # Healer flag (backwards compatible: derive from special_attack if not saved)
        player.is_healer = player_data.get("is_healer", player.special_attack == "Heal")

        # Skill cooldowns
        player.skill_cooldowns = player_data.get("skill_cooldowns", {})
        player.active_skill_slots = player_data.get("active_skill_slots", 3)

        # Tool slots
        player.tool_slots = player_data.get("tool_slots", 1)

        # Rebuild inventory
        player.inventory = []
        for card_ref in player_data.get("inventory", []):
            card = self._rebuild_inventory_card(card_ref)
            if card:
                player.inventory.append(card)

        # Rebuild equipped weapons (match by card_id in inventory)
        melee_ref = player_data.get("melee_weapon")
        if melee_ref:
            player.melee_weapon = self._find_card_in_list(player.inventory, melee_ref)

        proj_ref = player_data.get("projectile_weapon")
        if proj_ref:
            player.projectile_weapon = self._find_card_in_list(player.inventory, proj_ref)

        # Rebuild skills (separate from inventory)
        player.skills = []
        for card_ref in player_data.get("skills", []):
            card = self._rebuild_inventory_card(card_ref)
            if card:
                player.skills.append(card)

        # Rebuild equipped skills (match by card_id in skills list)
        player.equipped_skills = []
        for skill_ref in player_data.get("equipped_skills", []):
            if skill_ref:
                match = self._find_card_in_list(player.skills, skill_ref)
                if match:
                    player.equipped_skills.append(match)

        # Rebuild equipped tools (these are NOT in inventory)
        player.equipped_tools = []
        for tool_ref in player_data.get("equipped_tools", []):
            if tool_ref:
                card = self._rebuild_inventory_card(tool_ref)
                player.equipped_tools.append(card)
            else:
                player.equipped_tools.append(None)

        # Legacy single tool slot
        legacy_tool_ref = player_data.get("equipped_tool")
        if legacy_tool_ref:
            player.equipped_tool = self._rebuild_inventory_card(legacy_tool_ref)
        else:
            player.equipped_tool = player.equipped_tools[0] if player.equipped_tools else None

        # Rebuild equipped accessory (NOT in inventory)
        accessory_ref = player_data.get("equipped_accessory")
        if accessory_ref:
            player.equipped_accessory = self._rebuild_inventory_card(accessory_ref)

        # Rebuild per-player party (used in multiplayer)
        player.party = []
        for card_ref in player_data.get("party", []):
            card = self._rebuild_inventory_card(card_ref)
            if card:
                player.party.append(card)

        return player

    def _rebuild_inventory_card(self, card_ref):
        """Rebuild an InventoryCard from a save reference."""
        if not card_ref:
            return None
        card_id = card_ref.get("card_id", "")
        if not card_id:
            return None
        card_data = load_card(card_id)
        if not card_data:
            print(f"Warning: Could not load card '{card_id}' for save restore")
            return None
        inv_card = InventoryCard(card_data)
        inv_card.current_state = card_ref.get("current_state", 1)
        if "guide_drawn_ids" in card_ref:
            inv_card.guide_drawn_ids = card_ref["guide_drawn_ids"]
        return inv_card

    def _find_card_in_list(self, card_list, card_ref):
        """Find a card in a list by matching card_id and current_state."""
        if not card_ref:
            return None
        target_id = card_ref.get("card_id", "")
        target_state = card_ref.get("current_state", 1)
        for card in card_list:
            if card.card_data.get("id", "") == target_id and card.current_state == target_state:
                return card
        # Fallback: match by card_id only
        for card in card_list:
            if card.card_data.get("id", "") == target_id:
                return card
        return None

    def rebuild_units(self, units_data, hex_grid):
        """Rebuild units from save data and place them on the grid."""
        for unit_info in units_data:
            card_id = unit_info.get("card_id", "")
            card_data = load_card(card_id)
            if not card_data:
                print(f"Warning: Could not load unit card '{card_id}'")
                continue

            unit = Unit(card_data)
            # Restore saved state (may differ from card defaults)
            unit.current_state = unit_info.get("current_state", 1)
            unit.hp = unit_info.get("hp", unit.hp)
            unit.max_hp = unit_info.get("max_hp", unit.max_hp)
            unit.allegiance = unit_info.get("allegiance", unit.allegiance)
            unit.name = unit_info.get("name", unit.name)
            unit.movement = unit_info.get("movement", unit.movement)
            unit.melee_damage = unit_info.get("melee_damage", unit.melee_damage)
            unit.projectile_damage = unit_info.get("projectile_damage", unit.projectile_damage)
            unit.projectile_range = unit_info.get("projectile_range", unit.projectile_range)

            pos = unit_info.get("position")
            if pos:
                quest_target = unit_info.get("quest_target_position")
                if quest_target:
                    unit.quest_target_position = tuple(quest_target)
                    unit.quest_movement_priority = unit_info.get("quest_movement_priority", "rush")
                garrison_target = unit_info.get("garrison_target_location")
                if garrison_target:
                    unit.garrison_target_location = tuple(garrison_target)
                # Restore behavior tree state
                saved_tree = unit_info.get("behavior_tree")
                if saved_tree and isinstance(saved_tree, list):
                    unit.behavior_tree = saved_tree
                unit.is_stubborn = unit_info.get("is_stubborn", False)
                unit.behavior_follow_target = unit_info.get("behavior_follow_target")
                unit.behavior_attack_target = unit_info.get("behavior_attack_target")
                unit.recruit_cooldown = unit_info.get("recruit_cooldown", 0)
                unit.boss_encounter_tag = unit_info.get("boss_encounter_tag")
                unit.dialogue_delivered = unit_info.get("dialogue_delivered", False)
                unit._death_processed = unit_info.get("_death_processed", False)
                if unit._death_processed:
                    # Dead unit: set position but don't occupy grid cell
                    unit.position = (pos[0], pos[1])
                    hex_grid.units.append(unit)
                else:
                    hex_grid.place_unit(unit, pos[0], pos[1])

    def rebuild_location_data(self, saved_loc_data, hex_grid):
        """Overlay saved location data onto the reloaded hex grid locations."""
        for key, entry in saved_loc_data.items():
            row, col = [int(x) for x in key.split(",")]
            pos = (row, col)
            if pos not in hex_grid.location_data:
                continue

            loc_data = hex_grid.location_data[pos]

            # Restore card state
            saved_state = entry.get("card_state", 1)
            if entry.get("card_id") and loc_data.get("card"):
                loc_data["card"].current_state = saved_state
                loc_data["state"] = saved_state
                # Re-parse spawn/defense data for the restored state
                if loc_data["card"].card_data:
                    hex_grid._init_spawn_location_data(pos, loc_data["card"].card_data, saved_state)

            # Restore shop contents
            loc_data["shop"] = []
            for shop_ref in entry.get("shop", []):
                card = self._rebuild_inventory_card(shop_ref)
                if card:
                    loc_data["shop"].append(card)

            # Restore simple fields
            loc_data["turns"] = entry.get("turns", 0)
            loc_data["visited"] = entry.get("visited", False)

            # Restore spawn location fields
            if "health" in entry:
                loc_data["health"] = entry["health"]
            if "max_health" in entry:
                loc_data["max_health"] = entry["max_health"]
            if "spawn_active" in entry:
                loc_data["spawn_active"] = entry["spawn_active"]
            if "spawn_timer" in entry:
                loc_data["spawn_timer"] = entry["spawn_timer"]
            # Restore garrison data
            if "garrison_npcs" in entry:
                loc_data["garrison_npcs"] = entry["garrison_npcs"]

    def rebuild_quest_manager(self, saved_qm, quest_manager, hex_grid, player, card_manager):
        """Rebuild quest manager state from save data."""
        quest_manager.active_quests = []
        for saved_quest in saved_qm.get("active_quests", []):
            quest_card_id = saved_quest.get("quest_card_id", "")
            card_data = load_card(quest_card_id)
            if not card_data:
                continue

            from quest_system import ActiveQuest, PlaceholderResolver
            quest_card = InventoryCard(card_data)
            quest_card.current_state = saved_quest.get("quest_card_state", 1)

            quest = ActiveQuest(quest_card, hex_grid, player, card_manager)
            quest.turn_count = saved_quest.get("turn_count", 0)
            quest.is_complete = saved_quest.get("is_complete", False)
            quest.is_failed = saved_quest.get("is_failed", False)

            # Rebuild tracked units by matching (card_id, position) on the grid
            quest.tracked_units = {}
            for pid, unit_info in saved_quest.get("tracked_units", {}).items():
                target_id = unit_info.get("card_id", "")
                target_pos = unit_info.get("position")
                if target_pos:
                    target_pos = tuple(target_pos)
                # Search hex_grid.units for a match
                for unit in hex_grid.units:
                    if unit.card_id == target_id and unit.position == target_pos:
                        quest.tracked_units[pid] = unit
                        break

            # Rebuild tracked locations
            quest.tracked_locations = {}
            for pid, pos in saved_quest.get("tracked_locations", {}).items():
                if pos:
                    quest.tracked_locations[pid] = tuple(pos)

            # Rebuild a stub resolver with resolved names for template filling
            quest.resolver = PlaceholderResolver(card_manager, hex_grid)
            for pid, name in saved_quest.get("resolved_names", {}).items():
                quest.resolver.resolved[pid] = {"name": name, "cards": [], "unit": None, "position": None}
                # Link tracked unit/location into resolver
                if pid in quest.tracked_units:
                    quest.resolver.resolved[pid]["unit"] = quest.tracked_units[pid]
                    quest.resolver.resolved[pid]["position"] = quest.tracked_units[pid].position
                if pid in quest.tracked_locations:
                    quest.resolver.resolved[pid]["position"] = quest.tracked_locations[pid]

            quest_manager.active_quests.append(quest)

    def rebuild_instance_manager(self, saved_im, instance_manager):
        """Rebuild instance manager state from save data."""
        instance_manager.trigger_chance = saved_im.get("trigger_chance", 0.0)
        # The deck itself is rebuilt from card IDs
        from instance_system import InstanceCard
        instance_manager.instance_deck = []
        for card_id in saved_im.get("deck_card_ids", []):
            card_data = load_card(card_id)
            if card_data and card_data.get("card_type") == "Instance Card":
                instance_manager.instance_deck.append(InstanceCard(card_data))

    def rebuild_transition_manager(self, saved_tm, transition_manager):
        """Rebuild transition manager state from save data."""
        transition_manager.weather_effect = saved_tm.get("weather_effect")
        transition_manager.weather_modifiers = saved_tm.get("weather_modifiers", {})

        card_id = saved_tm.get("active_card_id")
        if card_id:
            transition_manager.load_transition_card(card_id)
            if transition_manager.active_transition:
                saved_state = saved_tm.get("active_card_state", 1)
                if saved_state == 2 and transition_manager.active_transition.states == 2:
                    transition_manager.active_transition.current_state = 2

    # ============================
    # Display Helpers
    # ============================

    def format_save_display(self, save_info):
        """Format a save info dict for display in the UI list."""
        save_type = save_info.get("save_type", "unknown")
        label = save_info.get("save_label", "Unknown")
        level_file = save_info.get("level_file", "")
        level_name = os.path.splitext(os.path.basename(level_file))[0] if level_file else "Unknown"
        timestamp = save_info.get("timestamp", "")

        type_tag = "[AUTO]" if save_type == "autosave" else "[SAVE]"

        # Format timestamp
        time_str = ""
        if timestamp:
            try:
                dt = datetime.datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%b %d, %H:%M")
            except (ValueError, TypeError):
                time_str = timestamp[:16]

        return f"{type_tag} {label} - {level_name} - {time_str}"

    def format_save_details(self, save_info):
        """Format detailed info for a selected save."""
        filepath = save_info.get("filepath", "")
        data = self.load_save_file(filepath)
        if not data:
            return "Could not load save details."

        lines = []
        lines.append(f"Save Type: {data.get('save_type', 'unknown')}")
        lines.append(f"Label: {data.get('save_label', 'Unknown')}")

        level_file = data.get("level_file", "")
        level_name = os.path.splitext(os.path.basename(level_file))[0] if level_file else "Unknown"
        lines.append(f"Level: {level_name}")

        if data.get("campaign_file"):
            lines.append(f"Campaign: {os.path.basename(data['campaign_file'])}")
            lines.append(f"Stage: {data.get('current_level_idx', 0) + 1}")

        if data.get("multiplayer_mode"):
            lines.append("Mode: 2-Player Multiplayer")
            players = data.get("players", [])
            for i, p in enumerate(players):
                lines.append(f"  P{i+1}: {p.get('name', p.get('class_name', '?'))} - {p.get('class_name', '?')} HP:{p.get('hp', '?')}/{p.get('max_hp', '?')}")
        else:
            p = data.get("player", {})
            lines.append(f"Player: {p.get('name', p.get('class_name', '?'))}")
            lines.append(f"Class: {p.get('class_name', '?')}")
            lines.append(f"HP: {p.get('hp', '?')}/{p.get('max_hp', '?')}")

        gs = data.get("game_screen", {})
        turn = gs.get("turn_cycle_count", 0)
        lines.append(f"Turn: {turn}")

        timestamp = data.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.datetime.fromisoformat(timestamp)
                lines.append(f"Saved: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            except (ValueError, TypeError):
                lines.append(f"Saved: {timestamp}")

        return "\n".join(lines)

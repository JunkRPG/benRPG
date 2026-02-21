import pygame
import math
import random
import json
from deck_utils import resolve_deck_path
from card_utils import load_card

# Animation constants
MOVE_SPEED = 5
ATTACK_FLASH_DURATION = 500
DAMAGE_TEXT_DURATION = 1000  # 1 second

class Unit:
    def __init__(self, card_data):
        self.card_id = card_data.get("id", "")
        self.name = card_data["data"].get("Name", "Unnamed")
        self.hp = int(card_data["data"].get("Health", 10))
        self.max_hp = self.hp
        self.movement = int(card_data["data"].get("Movement", 3))
        self.melee_damage = int(card_data["data"].get("Melee Damage", 5))
        self.projectile_damage = int(card_data["data"].get("Projectile Damage", 0))
        self.projectile_range = int(card_data["data"].get("Projectile Range", 0))
        self.allegiance = card_data["data"].get("Allegiance (Hostile, Neutral, Allied)", "Hostile")
        self.special_skill = card_data["data"].get("Special Skill", None)
        self.spawn_deck = card_data["data"].get("Spawn_Deck", None)
        self.heal_amount = int(card_data["data"].get("Heal_Amount", 0) or 0)
        self.heal_range = int(card_data["data"].get("Heal_Range", 1) or 1)
        self.position = None
        self.card_type = card_data["card_type"]
        self.states = card_data.get("states", 1)
        self.current_state = 1
        self.animating = False
        self.target_pos = None
        self.render_pos = None
        self.attack_flash = False
        self.flash_start = 0
        self.second_state = {}
        # Damage feedback
        self.damage_text = None
        self.damage_time = 0
        self._hp_visual_offset = 0
        self._hp_visual_offset_until = 0
        self._pending_damage_anim = None
        # Quest-related: target position for escort quests
        self.quest_target_position = None
        # Quest movement priority: "rush" (head to destination, fight only if adjacent/blocking)
        # or "fight_first" (clear all enemies before moving to destination)
        self.quest_movement_priority = "rush"
        # Garrison target: location pos to pathfind to for garrison assignment
        self.garrison_target_location = None
        # Passthrough defense messages collected during movement animation
        self.passthrough_messages = []
        # Deferred attack (executed after movement animation completes)
        self.pending_attack = None
        # Path-based animation
        self.animation_path = []  # List of hex positions to animate through
        self.animation_path_index = 0  # Current target in the path
        # Death processing flag: True once death cleanup has run (body stays on board)
        self._death_processed = False

        self.is_stubborn = str(card_data["data"].get("Stubborn", "false")).lower() == "true"
        # Target references for follow/attack behaviors
        self.behavior_follow_target = None   # card_id or "player_0"/"player_1"
        self.behavior_attack_target = None   # card_id of hostile
        # Recruit cooldown (turns)
        self.recruit_cooldown = 0
        # Boss encounter: repair skill and aggro range
        self.repair_value = int(card_data["data"].get("Repair_Value", 0) or 0)
        self.aggro_range = int(card_data["data"].get("Aggro_Range", 0) or 0)  # 0 = unlimited
        # Boss encounter tag (set by boss encounter system for phase tracking)
        self.boss_encounter_tag = None
        # Messenger NPC dialogue
        self.dialogue_text = card_data["data"].get("Dialogue_Text", "")
        self.dialogue_delivered = False
        self.pending_dialogue = None
        # Gift cards given when dialogue is delivered
        gift_str = card_data["data"].get("Dialogue_Gift_Cards", "")
        self.dialogue_gift_cards = [c.strip() for c in gift_str.split(",") if c.strip()] if gift_str else []
        # Carry-over: if True, this NPC transfers to the next campaign level
        self.carry_to_next_level = False
        # Dual Strike: allows a second attack per turn (no movement)
        self.dual_strike = (self.special_skill == "Dual Strike")
        # Range flash: briefly highlight attack range at start of allied turn
        self.range_flash_start = 0
        # Attack proximity range: only engage enemies within this distance (0 = unlimited)
        self.attack_proximity_range = int(card_data["data"].get("Attack_Proximity_Range", 0) or 0)
        # Avoid location hexes: never stop on a location hex when following
        self.avoid_location_hexes = str(card_data["data"].get("Avoid_Location_Hexes", "false")).lower() == "true"
        # Skip turn: set by trip_fall, cleared after skipping one turn
        self.skip_turn = False
        # Planned move destination: set by plan_turn() for random-wander cases
        # so take_turn() moves to the same hex shown in the preview
        self._planned_move_dest = None
        # Quest giver: quest card to offer when adjacent to target
        self.quest_offer_card_id = None
        self.quest_offer_target = None  # "player_0" / "player_1"
        self.pending_quest_offer = None

        # Allegiance priority list (defines advancement order)
        self.allegiance_priority = self._parse_allegiance_priority(card_data)
        # Convert cooldown (turns remaining before convert_enemy can be used again)
        self.convert_cooldown = 0

        # Per-allegiance behavior trees (loaded after all attributes they depend on)
        self.hostile_behavior_tree = self._load_behavior_tree_field(card_data, "Hostile_Behavior_Tree")
        self.neutral_behavior_tree = self._load_behavior_tree_field(card_data, "Neutral_Behavior_Tree")
        self.allied_behavior_tree = self._load_behavior_tree_field(card_data, "Allied_Behavior_Tree")
        # Active behavior tree (selected based on current allegiance)
        self.behavior_tree = self._select_behavior_tree()

        if self.states == 2 and "2nd_State_Name" in card_data["data"]:
            self.second_state = {
                "name": card_data["data"]["2nd_State_Name"],
                "hp": int(card_data["data"].get("2nd_State_Health", self.hp)),
                "movement": int(card_data["data"].get("2nd_State_Movement", self.movement)),
                "melee_damage": int(card_data["data"].get("2nd_State_Melee Damage", self.melee_damage)),
                "projectile_damage": int(card_data["data"].get("2nd_State_Projectile Damage", self.projectile_damage)),
                "projectile_range": int(card_data["data"].get("2nd_State_Projectile Range", self.projectile_range)),
                "allegiance": card_data["data"].get("2nd_State_Allegiance (Hostile, Neutral, Allied)", self.allegiance),
                "special_skill": card_data["data"].get("2nd_State_Special Skill", self.special_skill),
                "heal_amount": int(card_data["data"].get("2nd_State_Heal_Amount", card_data["data"].get("Heal_Amount", 0)) or 0),
                "heal_range": int(card_data["data"].get("2nd_State_Heal_Range", card_data["data"].get("Heal_Range", 1)) or 1),
                "is_stubborn": str(card_data["data"].get("2nd_State_Stubborn", card_data["data"].get("Stubborn", "false"))).lower() == "true",
                "repair_value": int(card_data["data"].get("2nd_State_Repair_Value", card_data["data"].get("Repair_Value", 0)) or 0),
                "aggro_range": int(card_data["data"].get("2nd_State_Aggro_Range", card_data["data"].get("Aggro_Range", 0)) or 0),
                "behavior_tree_str": card_data["data"].get("2nd_State_Default_Behavior_Tree", ""),
                "hostile_bt_str": card_data["data"].get("2nd_State_Hostile_Behavior_Tree", ""),
                "neutral_bt_str": card_data["data"].get("2nd_State_Neutral_Behavior_Tree", ""),
                "allied_bt_str": card_data["data"].get("2nd_State_Allied_Behavior_Tree", ""),
                "allegiance_priority_str": card_data["data"].get("2nd_State_Allegiance_Priority", ""),
            }

    # Behavior registry: defines available behaviors with labels and restrictions
    BEHAVIOR_REGISTRY = {
        "revive_ally":        {"label": "Revive Ally",         "restrict_skill": "Healer"},
        "healing":            {"label": "Heal Allies",         "restrict_skill": "Healer"},
        "patrol":             {"label": "Patrol (Wander)"},
        "guard":              {"label": "Guard Position"},
        "recruit":            {"label": "Recruit Neutrals"},
        "follow_target":      {"label": "Follow Target",       "needs_target": "follow"},
        "attack_target":      {"label": "Attack Target",       "needs_target": "attack"},
        "attack_closest":     {"label": "Attack Closest"},
        "attack_weakest":     {"label": "Attack Weakest"},
        "flee":               {"label": "Flee from Enemies"},
        "graze":              {"label": "Graze (Recover HP)",  "restrict_skill": "Mount"},
        "garrison_tower":     {"label": "Garrison Tower"},
        "repair_location":    {"label": "Repair Location",     "restrict_skill": "Repair"},
        "aggro_gate":         {"label": "Aggro Range Gate"},
        "attack_tower":       {"label": "Attack Tower"},
        "attack_player":      {"label": "Attack Player"},
        "attack_locations":   {"label": "Attack Locations"},
        "summon_minion":      {"label": "Summon Minion",       "restrict_skill": "Summon Minion"},
        "messenger_deliver":  {"label": "Deliver Message",     "restrict_skill": "Messenger"},
        "quest_offer":        {"label": "Offer Quest"},
        "wild_mount_wander":  {"label": "Wild Mount Wander",   "restrict_skill": "Mount"},
        "convert_enemy":      {"label": "Convert Enemy",       "restrict_skill": "Healer"},
    }

    def _load_behavior_tree_field(self, card_data, field_name):
        """Load a per-allegiance behavior tree from card data.
        Returns parsed list or None (meaning 'use default')."""
        # Runtime custom override applies to allied tree only
        if field_name == "Allied_Behavior_Tree":
            custom_tree = card_data.get("custom_behavior_tree", None)
            if custom_tree and isinstance(custom_tree, list):
                return list(custom_tree)
        # Try the per-allegiance field first
        bt_str = card_data["data"].get(field_name, "")
        if bt_str:
            try:
                tree = json.loads(bt_str)
                if isinstance(tree, list) and len(tree) > 0:
                    return tree
            except (json.JSONDecodeError, TypeError):
                pass
        # For Allied tree, fall back to legacy Default_Behavior_Tree
        if field_name == "Allied_Behavior_Tree":
            legacy_str = card_data["data"].get("Default_Behavior_Tree", "")
            if legacy_str:
                try:
                    tree = json.loads(legacy_str)
                    if isinstance(tree, list) and len(tree) > 0:
                        return tree
                except (json.JSONDecodeError, TypeError):
                    pass
        return None  # Will use smart default

    def _parse_allegiance_priority(self, card_data):
        """Parse Allegiance_Priority from card data. Returns ordered list."""
        raw = card_data["data"].get("Allegiance_Priority", "")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list) and len(parsed) >= 1:
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        # Smart defaults based on starting allegiance
        if self.allegiance == "Hostile":
            return ["Hostile", "Neutral", "Allied"]
        elif self.allegiance == "Neutral":
            return ["Neutral", "Allied"]
        else:
            return ["Allied"]

    def _select_behavior_tree(self):
        """Select the active behavior tree based on current allegiance."""
        if self.allegiance == "Hostile":
            if self.hostile_behavior_tree:
                return list(self.hostile_behavior_tree)
            return self._default_hostile_tree()
        elif self.allegiance == "Neutral":
            if self.neutral_behavior_tree:
                return list(self.neutral_behavior_tree)
            return self._default_neutral_tree()
        else:  # Allied
            if self.allied_behavior_tree:
                return list(self.allied_behavior_tree)
            return self._default_allied_tree()

    def _default_hostile_tree(self):
        """Smart default behavior tree for hostile units."""
        tree = []
        if self.special_skill == "Repair" and self.repair_value > 0:
            tree.append("repair_location")
        if self.aggro_range > 0:
            tree.append("aggro_gate")
        if self.special_skill == "Healer" and self.heal_amount > 0:
            tree.append("healing")
        tree.append("attack_tower")
        tree.append("attack_player")
        tree.append("attack_closest")
        tree.append("attack_locations")
        if self.special_skill == "Summon Minion" and self.spawn_deck:
            tree.append("summon_minion")
        tree.append("patrol")
        return tree

    def _default_neutral_tree(self):
        """Smart default behavior tree for neutral units."""
        if self.special_skill == "Messenger" and self.dialogue_text:
            return ["messenger_deliver", "patrol"]
        if self.quest_offer_card_id:
            return ["quest_offer", "patrol"]
        if self.states == 2 and self.current_state == 1 and self.special_skill == "Mount":
            return ["wild_mount_wander"]
        return ["patrol"]

    def _default_allied_tree(self):
        """Smart default behavior tree for allied units."""
        default = []
        if self.special_skill == "Healer" and self.heal_amount > 0:
            default.append("revive_ally")
            default.append("healing")
        if self.special_skill == "Mount":
            default.append("graze")
        default.append("attack_closest")
        return default

    def set_allegiance(self, new_allegiance):
        """Change allegiance and activate the corresponding behavior tree."""
        self.allegiance = new_allegiance
        self.behavior_tree = self._select_behavior_tree()

    def advance_allegiance(self):
        """Advance to next allegiance in priority list. Returns (old, new, changed)."""
        old = self.allegiance
        if old not in self.allegiance_priority:
            return (old, old, False)
        idx = self.allegiance_priority.index(old)
        if idx >= len(self.allegiance_priority) - 1:
            return (old, old, False)  # Already at end
        new = self.allegiance_priority[idx + 1]
        self.set_allegiance(new)
        return (old, new, True)

    def _get_enemies(self, grid):
        """Units hostile to me based on my allegiance."""
        if self.allegiance == "Hostile":
            enemies = [u for u in grid.units if u.allegiance == "Allied" and u.hp > 0 and u.position]
            # Also include players as enemies
            players = grid.players if hasattr(grid, 'players') and grid.players else []
            if not players and hasattr(grid, 'player') and grid.player:
                players = [grid.player]
            enemies.extend([p for p in players if p.hp > 0 and p.position])
            return enemies
        elif self.allegiance == "Allied":
            return [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0 and u.position]
        return []  # Neutral has no automatic enemies

    def _get_friendlies(self, grid):
        """Units friendly to me based on my allegiance."""
        friendlies = [u for u in grid.units if u.allegiance == self.allegiance and u.hp > 0 and u.position and u is not self]
        # Allied units also consider players as friendlies
        if self.allegiance == "Allied":
            players = grid.players if hasattr(grid, 'players') and grid.players else []
            if not players and hasattr(grid, 'player') and grid.player:
                players = [grid.player]
            friendlies.extend([p for p in players if p.hp > 0 and p.position])
        return friendlies

    def _get_dead_enemies(self, grid):
        """Dead units hostile to me (for convert_enemy)."""
        if self.allegiance == "Allied":
            return [u for u in grid.units if u.allegiance == "Hostile" and u.hp <= 0
                    and getattr(u, '_death_processed', False) and u.position]
        elif self.allegiance == "Hostile":
            return [u for u in grid.units if u.allegiance == "Allied" and u.hp <= 0
                    and getattr(u, '_death_processed', False) and u.position]
        return []

    def get_available_behaviors(self):
        """Return list of behavior keys this unit can use."""
        available = []
        for key, info in self.BEHAVIOR_REGISTRY.items():
            skill_req = info.get("restrict_skill")
            if skill_req and self.special_skill != skill_req:
                continue
            available.append(key)
        return available

    def take_turn(self, grid):
        log = []
        if not self.position:
            return log

        # Skip turn if stunned (e.g. from trip_fall)
        if self.skip_turn:
            self.skip_turn = False
            return [f"{self.name} is stunned and loses their turn!"]

        # Recruit cooldown tick
        if self.recruit_cooldown > 0:
            self.recruit_cooldown -= 1
        # Convert cooldown tick
        if self.convert_cooldown > 0:
            self.convert_cooldown -= 1

        # Quest-driven override (Allied with quest target)
        if self.allegiance == "Allied" and self.quest_target_position:
            hostile_units = [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0]
            use_rush = (self.quest_movement_priority == "rush" and hostile_units)
            if use_rush:
                log = self._allied_rush_turn(grid, hostile_units)
            elif hostile_units:
                log = self._allied_fight_turn(grid, hostile_units)
            else:
                log = self._allied_idle_turn(grid)
        elif self.garrison_target_location:
            # Garrison override
            loc = grid.location_data.get(self.garrison_target_location)
            if not loc or loc.get("state", 1) != 2 or len(loc.get("garrison_npcs", [])) >= 3:
                self.garrison_target_location = None
            if self.garrison_target_location:
                log = self._allied_idle_turn(grid)
            else:
                for behavior in self.behavior_tree:
                    result = self._execute_behavior(behavior, grid)
                    if result is not None:
                        log.extend(result)
                        break
        else:
            # Universal behavior tree execution
            for behavior in self.behavior_tree:
                result = self._execute_behavior(behavior, grid)
                if result is not None:
                    log.extend(result)
                    break

        # Dual Strike second attack
        if self.dual_strike and log:
            second_log = self._dual_strike_second_attack(grid)
            if second_log:
                log.extend(second_log)

        return log

    def _wild_mount_wander(self, grid):
        """Wild mount wander: pick a random direction and walk in a line up to movement range."""
        log = []
        DIRECTIONS = [
            (1, 0, -1), (1, -1, 0), (0, -1, 1),
            (-1, 0, 1), (-1, 1, 0), (0, 1, -1)
        ]
        dir_idx = random.randint(0, 5)
        direction = DIRECTIONS[dir_idx]
        distance = random.randint(1, self.movement)
        row, col = self.position
        line = grid.get_line(row, col, direction, distance)

        # Walk the line, stopping at first inaccessible or occupied hex
        furthest = None
        for hex_pos in line:
            r, c = hex_pos
            if (0 <= r < grid.rows and 0 <= c < grid.cols and
                    grid.grid[r][c]["accessible"] and
                    grid.grid[r][c]["unit"] is None):
                furthest = hex_pos
            else:
                break

        if furthest:
            success, msg = grid.move_unit(self, furthest[0], furthest[1])
            if success:
                log.append(msg)
        return log

    def _allied_rush_turn(self, grid, hostile_units):
        """Rush mode: NPC prioritizes reaching quest_target_position.
        Attacks adjacent enemies or enemies in projectile range, but otherwise
        moves toward the destination instead of chasing enemies."""
        log = []

        # 1. Check for adjacent enemies - can't ignore something right next to you
        adjacent_enemies = [u for u in hostile_units if grid.hex_distance(self.position, u.position) == 1]
        if adjacent_enemies:
            target = random.choice(adjacent_enemies)
            damage = self.melee_damage
            target.hp -= damage
            target.set_damage_text(damage)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks()
            log.append(f"{self.name} attacked {target.name} for {damage} damage")
            return log

        # 2. Check for enemies in projectile range - shoot them opportunistically
        if self.projectile_damage > 0:
            in_range_enemies = [u for u in hostile_units if
                                1 < grid.hex_distance(self.position, u.position) <= self.projectile_range and
                                grid.is_aligned(self.position, u.position, self.projectile_range) and
                                grid.has_clear_line_of_sight(self.position, u.position)]
            if in_range_enemies:
                target = min(in_range_enemies, key=lambda u: grid.hex_distance(self.position, u.position))
                damage = self.projectile_damage
                target.hp -= damage
                target.set_damage_text(damage)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks()
                log.append(f"{self.name} attacked {target.name} with projectile for {damage} damage")
                return log

        # 3. Move toward quest target destination
        distance_to_target = grid.hex_distance(self.position, self.quest_target_position)
        if distance_to_target > 0:
            path = grid.find_path(self.position, self.quest_target_position)
            if path and len(path) > 1:
                max_steps = min(self.movement, len(path) - 1)
                for steps in range(max_steps, 0, -1):
                    new_pos = path[steps]
                    if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                        success, msg = grid.move_unit(self, *new_pos)
                        if success:
                            log.append(f"{self.name} moves toward destination")
                            # 4. After moving, check if now adjacent to an enemy - defer melee
                            for enemy in hostile_units:
                                if enemy.hp > 0 and grid.hex_distance(self.position, enemy.position) == 1:
                                    self.pending_attack = {
                                        "target": enemy,
                                        "damage": self.melee_damage,
                                        "type": "melee",
                                        "is_player": False
                                    }
                                    break
                        break

        return log

    def _allied_fight_turn(self, grid, hostile_units):
        """Fight mode: NPC chases and attacks the nearest hostile unit.
        This is the standard Allied combat behavior."""
        log = []
        target = min(hostile_units, key=lambda u: grid.hex_distance(self.position, u.position))
        distance = grid.hex_distance(self.position, target.position)
        melee_possible = distance == 1
        projectile_possible = (self.projectile_damage > 0 and
                               1 < distance <= self.projectile_range and
                               grid.is_aligned(self.position, target.position, self.projectile_range) and
                               grid.has_clear_line_of_sight(self.position, target.position))
        if projectile_possible:
            damage = self.projectile_damage
            target.hp -= damage
            target.set_damage_text(damage)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks()
            log.append(f"{self.name} attacked {target.name} with projectile for {damage} damage")
            return log
        elif melee_possible:
            damage = self.melee_damage
            target.hp -= damage
            target.set_damage_text(damage)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks()
            log.append(f"{self.name} attacked {target.name} for {damage} damage")
            return log
        path = grid.find_path(self.position, target.position)
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                    success, msg = grid.move_unit(self, *new_pos)
                    if success:
                        log.append(msg)
                        distance_after = grid.hex_distance(self.position, target.position)
                        if distance_after == 1:
                            self.pending_attack = {
                                "target": target,
                                "damage": self.melee_damage,
                                "type": "melee",
                                "is_player": False
                            }
                        elif (self.projectile_damage > 0 and
                              1 < distance_after <= self.projectile_range and
                              grid.is_aligned(self.position, target.position, self.projectile_range) and
                              grid.has_clear_line_of_sight(self.position, target.position)):
                            self.pending_attack = {
                                "target": target,
                                "damage": self.projectile_damage,
                                "type": "projectile",
                                "is_player": False
                            }
                    break
        return log

    def _allied_idle_turn(self, grid):
        """Idle mode: no enemies. Move toward quest target, garrison, or do nothing."""
        log = []
        if self.quest_target_position:
            distance_to_target = grid.hex_distance(self.position, self.quest_target_position)
            if distance_to_target > 0:
                path = grid.find_path(self.position, self.quest_target_position)
                if path and len(path) > 1:
                    max_steps = min(self.movement, len(path) - 1)
                    for steps in range(max_steps, 0, -1):
                        new_pos = path[steps]
                        if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                            success, msg = grid.move_unit(self, *new_pos)
                            if success:
                                log.append(f"{self.name} moves toward destination")
                            break
        elif self.garrison_target_location:
            distance_to_garrison = grid.hex_distance(self.position, self.garrison_target_location)
            if distance_to_garrison <= 1:
                log.append(f"{self.name} arrived at garrison location")
            elif distance_to_garrison > 0:
                path = grid.find_path(self.position, self.garrison_target_location)
                if path and len(path) > 1:
                    max_steps = min(self.movement, len(path) - 1)
                    for steps in range(max_steps, 0, -1):
                        new_pos = path[steps]
                        if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                            success, msg = grid.move_unit(self, *new_pos)
                            if success:
                                log.append(f"{self.name} moves toward garrison")
                            break
        return log

    def _perform_healing(self, grid):
        """Healer skill: revive dead allies or heal the most damaged friendly unit in range."""
        log = []
        if self.heal_amount <= 0:
            return log

        # --- Revive phase: check for dead friendlies in range ---
        revive_candidates = []
        friendlies = self._get_friendlies(grid)
        for u in friendlies:
            if (u.hp <= 0 and getattr(u, '_death_processed', False)
                    and u.position
                    and grid.hex_distance(self.position, u.position) <= self.heal_range):
                revive_candidates.append(u)

            if revive_candidates:
                target = revive_candidates[0]
                revive_hp = max(1, target.max_hp // 4)
                target.hp = revive_hp
                target._death_processed = False
                if hasattr(target, '_death_logged'):
                    target._death_logged = False
                target_name = getattr(target, 'class_name', None) or getattr(target, 'name', 'Unknown')
                # Re-occupy grid cell if empty, else find nearby empty hex
                if target.position:
                    tr, tc = target.position
                    if grid.grid[tr][tc]["unit"] is None:
                        grid.grid[tr][tc]["unit"] = target
                    else:
                        # Find a nearby empty accessible hex
                        neighbors = grid.get_neighbors(tr, tc)
                        for nr, nc in neighbors:
                            if grid.grid[nr][nc]["accessible"] and grid.grid[nr][nc]["unit"] is None:
                                target.position = (nr, nc)
                                grid.grid[nr][nc]["unit"] = target
                                break
                target.set_damage_text(0, text=f"+{revive_hp}")
                log.append(f"{self.name} revived {target_name} with {revive_hp} HP!")
                return log  # Don't also heal on same turn

        # --- Heal phase: heal the most damaged friendly unit in range ---
        candidates = []
        friendlies = self._get_friendlies(grid)
        for u in friendlies:
            if (u.hp > 0 and u.hp < u.max_hp and u.position
                    and grid.hex_distance(self.position, u.position) <= self.heal_range):
                candidates.append(u)

        if not candidates:
            return log

        # Pick the most damaged (lowest HP ratio)
        target = min(candidates, key=lambda u: u.hp / u.max_hp)
        old_hp = target.hp
        target.hp = min(target.max_hp, target.hp + self.heal_amount)
        healed = target.hp - old_hp

        if healed > 0:
            target_name = getattr(target, 'class_name', None) or getattr(target, 'name', 'Unknown')
            target.set_damage_text(0, text=f"+{healed}")
            log.append(f"{self.name} healed {target_name} for {healed} HP")

        return log

    # ============================
    # Behavior Tree System
    # ============================

    def _execute_behavior(self, behavior, grid):
        """Try to execute a behavior. Returns log list if executed, None if conditions not met."""
        dispatch = {
            "revive_ally": self._behavior_revive_ally,
            "healing": self._behavior_healing,
            "patrol": self._behavior_patrol,
            "guard": self._behavior_guard,
            "recruit": self._behavior_recruit,
            "follow_target": self._behavior_follow_target,
            "attack_target": self._behavior_attack_target,
            "attack_closest": self._behavior_attack_closest,
            "attack_weakest": self._behavior_attack_weakest,
            "flee": self._behavior_flee,
            "graze": self._behavior_graze,
            "garrison_tower": self._behavior_garrison_tower,
            "repair_location": self._behavior_repair_location,
            "aggro_gate": self._behavior_aggro_gate,
            "attack_tower": self._behavior_attack_tower,
            "attack_player": self._behavior_attack_player,
            "attack_locations": self._behavior_attack_locations,
            "summon_minion": self._behavior_summon_minion,
            "messenger_deliver": self._behavior_messenger_deliver,
            "quest_offer": self._behavior_quest_offer,
            "wild_mount_wander": self._behavior_wild_mount_wander,
            "convert_enemy": self._behavior_convert_enemy,
        }
        handler = dispatch.get(behavior)
        if handler:
            return handler(grid)
        return None

    def _chase_and_attack(self, grid, target):
        """Shared helper: chase a target and attack if possible.
        Returns log list if action taken, None if couldn't path to target."""
        log = []
        distance = grid.hex_distance(self.position, target.position)

        # Try projectile attack first (longer range)
        if (self.projectile_damage > 0 and
                1 < distance <= self.projectile_range and
                grid.is_aligned(self.position, target.position, self.projectile_range) and
                grid.has_clear_line_of_sight(self.position, target.position)):
            damage = self.projectile_damage
            target.hp -= damage
            target.set_damage_text(damage)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks()
            log.append(f"{self.name} attacked {target.name} with projectile for {damage} damage")
            return log

        # Try melee attack
        if distance == 1:
            damage = self.melee_damage
            target.hp -= damage
            target.set_damage_text(damage)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks()
            log.append(f"{self.name} attacked {target.name} for {damage} damage")
            return log

        # Move toward target
        path = grid.find_path(self.position, target.position)
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                    success, msg = grid.move_unit(self, *new_pos)
                    if success:
                        log.append(msg)
                        distance_after = grid.hex_distance(self.position, target.position)
                        if distance_after == 1:
                            self.pending_attack = {
                                "target": target,
                                "damage": self.melee_damage,
                                "type": "melee",
                                "is_player": False
                            }
                        elif (self.projectile_damage > 0 and
                              1 < distance_after <= self.projectile_range and
                              grid.is_aligned(self.position, target.position, self.projectile_range) and
                              grid.has_clear_line_of_sight(self.position, target.position)):
                            self.pending_attack = {
                                "target": target,
                                "damage": self.projectile_damage,
                                "type": "projectile",
                                "is_player": False
                            }
                    return log
        # Couldn't path — let tree try next behavior
        return None

    def _do_revive(self, grid, target):
        """Revive a dead ally/player. Returns log list."""
        log = []
        revive_hp = max(1, target.max_hp // 4)
        target.hp = revive_hp
        target._death_processed = False
        if hasattr(target, '_death_logged'):
            target._death_logged = False
        target_name = getattr(target, 'class_name', None) or getattr(target, 'name', 'Unknown')
        # Re-occupy grid cell if empty, else find nearby empty hex
        if target.position:
            tr, tc = target.position
            if grid.grid[tr][tc]["unit"] is None:
                grid.grid[tr][tc]["unit"] = target
            else:
                neighbors = grid.get_neighbors(tr, tc)
                for nr, nc in neighbors:
                    if grid.grid[nr][nc]["accessible"] and grid.grid[nr][nc]["unit"] is None:
                        target.position = (nr, nc)
                        grid.grid[nr][nc]["unit"] = target
                        break
        target.set_damage_text(0, text=f"+{revive_hp}")
        log.append(f"{self.name} revived {target_name} with {revive_hp} HP!")
        return log

    def _behavior_revive_ally(self, grid):
        """Find and revive dead friendlies, pathfinding toward them if needed (allegiance-aware)."""
        if self.special_skill != "Healer" or self.heal_amount <= 0:
            return None

        # Find all dead friendlies on the board
        dead_targets = []
        friendlies = self._get_friendlies(grid)
        for u in friendlies:
            if (u.hp <= 0 and getattr(u, '_death_processed', False)
                    and u.position):
                dead_targets.append(u)

        if not dead_targets:
            return None  # No dead allies — fall through to next behavior

        # Sort by distance
        dead_targets.sort(key=lambda t: grid.hex_distance(self.position, t.position))
        nearest = dead_targets[0]
        dist = grid.hex_distance(self.position, nearest.position)

        # In range — revive immediately
        if dist <= self.heal_range:
            return self._do_revive(grid, nearest)

        # Out of range — pathfind toward nearest dead ally
        path = grid.find_path(self.position, nearest.position)
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                    success, msg = grid.move_unit(self, *new_pos)
                    if success:
                        log = [f"{self.name} moves toward fallen ally"]
                        # Check if now in range after moving
                        new_dist = grid.hex_distance(self.position, nearest.position)
                        if new_dist <= self.heal_range:
                            log.extend(self._do_revive(grid, nearest))
                        return log
                    break

        # Can't pathfind but dead allies exist — consume action, don't fall through
        return []

    def _behavior_convert_enemy(self, grid):
        """Find dead enemies, revive them, then advance their allegiance. 4-turn cooldown."""
        if self.special_skill != "Healer" or self.heal_amount <= 0:
            return None
        if self.convert_cooldown > 0:
            return None

        dead_enemies = self._get_dead_enemies(grid)
        if not dead_enemies:
            return None

        # Sort by distance
        dead_enemies.sort(key=lambda t: grid.hex_distance(self.position, t.position))
        nearest = dead_enemies[0]
        dist = grid.hex_distance(self.position, nearest.position)

        # In range — revive and convert
        if dist <= self.heal_range:
            log = self._do_revive(grid, nearest)
            old, new, changed = nearest.advance_allegiance()
            if changed:
                log.append(f"{nearest.name}'s allegiance changed from {old} to {new}!")
            self.convert_cooldown = 4
            return log

        # Out of range — pathfind toward nearest dead enemy
        path = grid.find_path(self.position, nearest.position)
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                    success, msg = grid.move_unit(self, *new_pos)
                    if success:
                        log = [f"{self.name} moves toward fallen enemy to convert"]
                        new_dist = grid.hex_distance(self.position, nearest.position)
                        if new_dist <= self.heal_range:
                            log.extend(self._do_revive(grid, nearest))
                            old, new_alleg, changed = nearest.advance_allegiance()
                            if changed:
                                log.append(f"{nearest.name}'s allegiance changed from {old} to {new_alleg}!")
                            self.convert_cooldown = 4
                        return log
                    break

        return []  # Dead enemies exist but can't reach — consume action

    def _behavior_healing(self, grid):
        """Heal the most damaged alive friendly unit, pathfinding toward them if needed (allegiance-aware)."""
        if self.special_skill != "Healer" or self.heal_amount <= 0:
            return None

        # Find all damaged (alive) friendlies anywhere on board
        friendlies = self._get_friendlies(grid)
        candidates = [u for u in friendlies if u.hp > 0 and u.hp < u.max_hp and u.position]

        if not candidates:
            return None  # No damaged allies — fall through to next behavior

        # Pick the most damaged (lowest HP ratio)
        most_damaged = min(candidates, key=lambda u: u.hp / u.max_hp)
        dist = grid.hex_distance(self.position, most_damaged.position)

        # In range — heal immediately
        if dist <= self.heal_range:
            old_hp = most_damaged.hp
            most_damaged.hp = min(most_damaged.max_hp, most_damaged.hp + self.heal_amount)
            healed = most_damaged.hp - old_hp
            if healed > 0:
                target_name = getattr(most_damaged, 'class_name', None) or getattr(most_damaged, 'name', 'Unknown')
                most_damaged.set_damage_text(0, text=f"+{healed}")
                return [f"{self.name} healed {target_name} for {healed} HP"]
            return []

        # Out of range — pathfind toward nearest damaged ally
        nearest = min(candidates, key=lambda u: grid.hex_distance(self.position, u.position))
        path = grid.find_path(self.position, nearest.position)
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                    success, msg = grid.move_unit(self, *new_pos)
                    if success:
                        log = [f"{self.name} moves toward wounded ally"]
                        # Re-check: heal most damaged ally now in range
                        in_range_now = [c for c in candidates if
                                        grid.hex_distance(self.position, c.position) <= self.heal_range]
                        if in_range_now:
                            target = min(in_range_now, key=lambda u: u.hp / u.max_hp)
                            old_hp = target.hp
                            target.hp = min(target.max_hp, target.hp + self.heal_amount)
                            healed = target.hp - old_hp
                            if healed > 0:
                                target_name = getattr(target, 'class_name', None) or getattr(target, 'name', 'Unknown')
                                target.set_damage_text(0, text=f"+{healed}")
                                log.append(f"{self.name} healed {target_name} for {healed} HP")
                        return log
                    break

        # Can't pathfind but damaged allies exist — consume action
        return []

    def _behavior_attack_closest(self, grid):
        """Chase and attack the nearest enemy unit (allegiance-aware)."""
        enemies = self._get_enemies(grid)
        if not enemies:
            return None
        target = min(enemies, key=lambda u: grid.hex_distance(self.position, u.position))
        # If proximity range is set, only engage if nearest enemy is within range
        if self.attack_proximity_range > 0:
            if grid.hex_distance(self.position, target.position) > self.attack_proximity_range:
                return None  # Too far — skip to next behavior
        return self._chase_and_attack(grid, target)

    def _behavior_attack_weakest(self, grid):
        """Chase and attack the lowest-HP enemy unit (allegiance-aware)."""
        enemies = self._get_enemies(grid)
        if not enemies:
            return None
        target = min(enemies, key=lambda u: u.hp)
        return self._chase_and_attack(grid, target)

    def _behavior_attack_target(self, grid):
        """Chase and attack a specific assigned hostile."""
        if not self.behavior_attack_target:
            return None
        target = None
        for u in grid.units:
            if u.card_id == self.behavior_attack_target and u.hp > 0 and u.position:
                target = u
                break
        if not target:
            return None
        return self._chase_and_attack(grid, target)

    def _behavior_follow_target(self, grid):
        """Stay within 2 hexes of a target, fight adjacent threats opportunistically."""
        target_entity = self._resolve_follow_target(grid)
        if not target_entity or not target_entity.position:
            return None

        distance = grid.hex_distance(self.position, target_entity.position)

        # If currently standing on a location hex and should avoid them, move off first
        if self.avoid_location_hexes and self.position in grid.location_data:
            neighbors = grid.get_neighbors(*self.position)
            best = None
            best_dist = float('inf')
            for pos in neighbors:
                if (grid.grid[pos[0]][pos[1]]["unit"] is None and
                        grid.grid[pos[0]][pos[1]].get("accessible", True) and
                        pos not in grid.location_data):
                    d = grid.hex_distance(pos, target_entity.position)
                    if d < best_dist:
                        best_dist = d
                        best = pos
            if best:
                success, msg = grid.move_unit(self, *best)
                if success:
                    return [f"{self.name} steps aside"]
            return []

        # Within 2 hexes — opportunistically attack adjacent enemies
        if distance <= 2:
            enemies = self._get_enemies(grid)
            adjacent = [u for u in enemies if grid.hex_distance(self.position, u.position) == 1]
            if adjacent:
                enemy = random.choice(adjacent)
                damage = self.melee_damage
                enemy.hp -= damage
                enemy.set_damage_text(damage)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks()
                return [f"{self.name} attacked {enemy.name} for {damage} damage"]
            return []  # Staying near target, nothing to do

        # Too far — move toward target, avoiding location hexes
        path = grid.find_path(self.position, target_entity.position)
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                    # Skip location hexes if avoiding them
                    if self.avoid_location_hexes and new_pos in grid.location_data:
                        continue
                    success, msg = grid.move_unit(self, *new_pos)
                    if success:
                        return [f"{self.name} follows toward {getattr(target_entity, 'name', getattr(target_entity, 'class_name', 'target'))}"]
                    break
        return []

    def _resolve_follow_target(self, grid):
        """Resolve the follow target to a player or unit entity."""
        if not self.behavior_follow_target:
            return None
        # Player references: "player_0", "player_1", etc.
        if self.behavior_follow_target.startswith("player_"):
            try:
                idx = int(self.behavior_follow_target.split("_")[1])
                players = grid.players if hasattr(grid, 'players') and grid.players else []
                if not players and hasattr(grid, 'player') and grid.player:
                    players = [grid.player]
                if idx < len(players) and players[idx].hp > 0:
                    return players[idx]
            except (ValueError, IndexError):
                pass
            return None
        # Unit reference by card_id
        for u in grid.units:
            if u.card_id == self.behavior_follow_target and u.hp > 0 and u.position:
                return u
        return None

    def _behavior_guard(self, grid):
        """Stay in place, attack adjacent/ranged enemies only. Never skips."""
        log = []
        enemies = self._get_enemies(grid)

        # Melee: attack a random adjacent enemy
        adjacent = [u for u in enemies if grid.hex_distance(self.position, u.position) == 1]
        if adjacent:
            target = random.choice(adjacent)
            damage = self.melee_damage
            target.hp -= damage
            target.set_damage_text(damage)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks()
            log.append(f"{self.name} attacked {target.name} for {damage} damage")
            return log

        # Projectile: shoot nearest in-range enemy
        if self.projectile_damage > 0:
            in_range = [u for u in enemies if
                        1 < grid.hex_distance(self.position, u.position) <= self.projectile_range and
                        grid.is_aligned(self.position, u.position, self.projectile_range) and
                        grid.has_clear_line_of_sight(self.position, u.position)]
            if in_range:
                target = min(in_range, key=lambda u: grid.hex_distance(self.position, u.position))
                damage = self.projectile_damage
                target.hp -= damage
                target.set_damage_text(damage)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks()
                log.append(f"{self.name} attacked {target.name} with projectile for {damage} damage")
                return log

        return log  # Always executes (never None)

    def _behavior_patrol(self, grid):
        """Wander randomly to an adjacent hex. Never skips."""
        if self._planned_move_dest:
            dest = self._planned_move_dest
            self._planned_move_dest = None
            if (grid.grid[dest[0]][dest[1]]["unit"] is None and
                    grid.grid[dest[0]][dest[1]].get("accessible", True)):
                success, msg = grid.move_unit(self, *dest)
                if success:
                    return [msg]
        neighbors = grid.get_neighbors(*self.position)
        empty = [pos for pos in neighbors if grid.grid[pos[0]][pos[1]]["unit"] is None
                 and grid.grid[pos[0]][pos[1]].get("accessible", True)]
        if empty:
            new_pos = random.choice(empty)
            success, msg = grid.move_unit(self, *new_pos)
            if success:
                return [msg]
        return []  # Always executes

    def _behavior_flee(self, grid):
        """Move away from the nearest enemy, don't attack (allegiance-aware)."""
        enemies = self._get_enemies(grid)
        if not enemies:
            return None
        nearest = min(enemies, key=lambda u: grid.hex_distance(self.position, u.position))
        neighbors = grid.get_neighbors(*self.position)
        empty = [pos for pos in neighbors if grid.grid[pos[0]][pos[1]]["unit"] is None
                 and grid.grid[pos[0]][pos[1]].get("accessible", True)]
        if empty:
            # Pick the neighbor that maximizes distance from nearest hostile
            best = max(empty, key=lambda pos: grid.hex_distance(pos, nearest.position))
            success, msg = grid.move_unit(self, *best)
            if success:
                return [f"{self.name} flees from {nearest.name}"]
        return []

    def _behavior_recruit(self, grid):
        """Move toward nearest neutral NPC and attempt persuasion roll."""
        if self.recruit_cooldown > 0:
            return None
        neutrals = [u for u in grid.units if u.allegiance == "Neutral" and u.hp > 0 and u.position]
        if not neutrals:
            return None
        target = min(neutrals, key=lambda u: grid.hex_distance(self.position, u.position))
        distance = grid.hex_distance(self.position, target.position)

        if distance == 1:
            # Adjacent: attempt persuasion
            chance = max(10, min(70, 30 + self.max_hp - target.max_hp))
            roll = random.randint(1, 100)
            if roll <= chance:
                target.set_allegiance("Allied")
                self.recruit_cooldown = 3
                return [f"{self.name} recruited {target.name}! (rolled {roll} vs {chance}%)"]
            else:
                self.recruit_cooldown = 2
                return [f"{self.name} failed to recruit {target.name} (rolled {roll} vs {chance}%)"]

        # Not adjacent: move toward neutral
        path = grid.find_path(self.position, target.position)
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                    success, msg = grid.move_unit(self, *new_pos)
                    if success:
                        return [f"{self.name} moves toward {target.name} to recruit"]
                    break
        return []

    def _behavior_graze(self, grid):
        """Mount behavior: move to grass hex and heal 10hp/turn while on grass."""
        if self.special_skill != "Mount":
            return None
        if self.hp >= self.max_hp:
            return None

        # Check if currently on grass
        row, col = self.position
        terrain = grid.grid[row][col].get("terrain", "")
        if terrain == "grass":
            heal = min(10, self.max_hp - self.hp)
            self.hp += heal
            self.set_damage_text(0, text=f"+{heal}")
            return [f"{self.name} grazes on grass (+{heal} HP)"]

        # Find nearest grass hex
        best_grass = None
        best_dist = float('inf')
        for r in range(grid.rows):
            for c in range(grid.cols):
                if (grid.grid[r][c].get("terrain", "") == "grass" and
                        grid.grid[r][c].get("accessible", True) and
                        grid.grid[r][c]["unit"] is None):
                    d = grid.hex_distance(self.position, (r, c))
                    if d < best_dist:
                        best_dist = d
                        best_grass = (r, c)

        if not best_grass:
            return None  # No grass reachable

        path = grid.find_path(self.position, best_grass)
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                    success, msg = grid.move_unit(self, *new_pos)
                    if success:
                        log = [f"{self.name} moves toward grass to graze"]
                        # Heal if arrived at grass this turn
                        nr, nc = self.position
                        if grid.grid[nr][nc].get("terrain", "") == "grass":
                            heal = min(10, self.max_hp - self.hp)
                            self.hp += heal
                            self.set_damage_text(0, text=f"+{heal}")
                            log.append(f"{self.name} grazes on grass (+{heal} HP)")
                        return log
                    break
        return None

    def _behavior_garrison_tower(self, grid):
        """Garrison tower behavior: find a defensive location that needs NPCs and pathfind to it."""
        # If already assigned a garrison target, let the garrison override handle it
        if self.garrison_target_location:
            return None

        # Find all defensive locations in state 2 with requires_npc defenses and room
        candidates = []
        # Get positions where players are manning (exclude those)
        player_manning = set()
        players = grid.players if hasattr(grid, 'players') and grid.players else []
        if not players and hasattr(grid, 'player') and grid.player:
            players = [grid.player]
        for p in players:
            if hasattr(p, 'manning_location') and p.manning_location:
                player_manning.add(tuple(p.manning_location))

        for pos, loc_data in grid.location_data.items():
            if loc_data.get("state", 1) != 2:
                continue
            if pos in player_manning:
                continue
            defenses = loc_data.get("defenses", [])
            has_npc_defense = any(d.get("requires_npc") for d in defenses)
            if not has_npc_defense:
                continue
            garrison = loc_data.get("garrison_npcs", [])
            if len(garrison) >= 3:
                continue
            # Check no other allied unit is already targeting this tower
            already_targeted = False
            for u in grid.units:
                if u is not self and u.hp > 0 and getattr(u, 'garrison_target_location', None) == pos:
                    already_targeted = True
                    break
            # Still allow if tower has room for more (count existing + targeting)
            targeting_count = sum(1 for u in grid.units if u is not self and u.hp > 0 and getattr(u, 'garrison_target_location', None) == pos)
            if len(garrison) + targeting_count >= 3:
                continue
            candidates.append(pos)

        if not candidates:
            return None  # Fall through to next behavior

        # Pick closest tower
        closest = min(candidates, key=lambda p: grid.hex_distance(self.position, p))
        self.garrison_target_location = closest
        return []  # Action consumed — garrison override handles pathfinding next turn

    # ============================
    # Hostile/Neutral Behavior Handlers
    # ============================

    def _behavior_repair_location(self, grid):
        """Boss repair: prioritize repairing enemy spawn locations."""
        if self.special_skill != "Repair" or self.repair_value <= 0:
            return None
        damaged_locations = grid.get_damaged_spawn_locations()
        if not damaged_locations:
            return None
        nearest_loc = min(damaged_locations, key=lambda x: grid.hex_distance(self.position, x[0]))
        dist_to_loc = grid.hex_distance(self.position, nearest_loc[0])
        if dist_to_loc <= 1:
            success, healed, rebuilt, msg = grid.repair_spawn_location(
                nearest_loc[0][0], nearest_loc[0][1], self.repair_value)
            if success:
                delay = 0
                if hasattr(grid, 'attack_anims'):
                    src = grid.get_hex_center(*self.position)
                    tgt = grid.get_hex_center(*nearest_loc[0])
                    grid.attack_anims.create_melee(src, tgt)
                    delay = grid.attack_anims.get_max_remaining_ms()
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks() + delay
                return [msg]
            return []
        # Pathfind toward damaged location
        path = grid.find_path(self.position, nearest_loc[0])
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                    loc_card = nearest_loc[1].get("card")
                    loc_name = loc_card.get_current_data().get("Name", "location") if loc_card else "location"
                    success, move_msg = grid.move_unit(self, *new_pos)
                    if success:
                        log = [f"{self.name} moves to repair {loc_name}"]
                        new_dist = grid.hex_distance(self.position, nearest_loc[0])
                        if new_dist <= 1:
                            self.pending_attack = {
                                "type": "repair",
                                "target_pos": nearest_loc[0],
                                "repair_value": self.repair_value
                            }
                        return log
                    break
        return []

    def _behavior_aggro_gate(self, grid):
        """Aggro range gate: skip turn if no targets in aggro_range. Returns [] to idle, None to fall through."""
        if self.aggro_range <= 0:
            return None  # No aggro range set, fall through
        enemies = self._get_enemies(grid)
        # Check units (excluding players which are in _get_enemies for Hostile)
        for e in enemies:
            if grid.hex_distance(self.position, e.position) <= self.aggro_range:
                return None  # Target in range, fall through to next behavior
        return []  # No targets in aggro range — idle

    def _behavior_attack_tower(self, grid):
        """Attack tower that player is manning."""
        player = grid.player
        if not (hasattr(player, 'manning_location') and player.manning_location is not None):
            return None
        tower_pos = player.manning_location
        dist_to_tower = grid.hex_distance(self.position, tower_pos)
        log = []
        tower_attacked = False
        # Try melee attack on tower
        if dist_to_tower == 1:
            damage = self.melee_damage
            if grid.is_attackable_npc_location(tower_pos[0], tower_pos[1]):
                damage_dealt, destroyed, msg = grid.damage_npc_location(tower_pos[0], tower_pos[1], damage)
            elif grid.is_attackable_location(tower_pos[0], tower_pos[1]):
                damage_dealt, destroyed, msg = grid.damage_location(tower_pos[0], tower_pos[1], damage)
            else:
                damage_dealt, destroyed, msg = 0, False, ""
            if damage_dealt > 0:
                delay = 0
                if hasattr(grid, 'attack_anims'):
                    src = grid.get_hex_center(*self.position)
                    tgt = grid.get_hex_center(*tower_pos)
                    grid.attack_anims.create_melee(src, tgt)
                    delay = grid.attack_anims.get_max_remaining_ms()
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks() + delay
                log.append(msg)
                if destroyed:
                    player.leave_manning()
                    log.append(f"{player.name or player.class_name} ejected from destroyed tower!")
                return log
            tower_attacked = True
        # Try projectile attack on tower
        elif (self.projectile_damage > 0 and
              1 < dist_to_tower <= self.projectile_range and
              grid.is_aligned(self.position, tower_pos, self.projectile_range) and
              grid.has_clear_line_of_sight(self.position, tower_pos)):
            damage = self.projectile_damage
            if grid.is_attackable_npc_location(tower_pos[0], tower_pos[1]):
                damage_dealt, destroyed, msg = grid.damage_npc_location(tower_pos[0], tower_pos[1], damage)
            elif grid.is_attackable_location(tower_pos[0], tower_pos[1]):
                damage_dealt, destroyed, msg = grid.damage_location(tower_pos[0], tower_pos[1], damage)
            else:
                damage_dealt, destroyed, msg = 0, False, ""
            if damage_dealt > 0:
                delay = 0
                if hasattr(grid, 'attack_anims'):
                    src = grid.get_hex_center(*self.position)
                    tgt = grid.get_hex_center(*tower_pos)
                    grid.attack_anims.create_projectile(src, tgt)
                    delay = grid.attack_anims.get_max_remaining_ms()
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks() + delay
                log.append(msg)
                if destroyed:
                    player.leave_manning()
                    log.append(f"{player.name or player.class_name} ejected from destroyed tower!")
                return log
            tower_attacked = True
        # Can't attack tower - pathfind toward it
        if not tower_attacked:
            path = grid.find_path(self.position, tower_pos)
            if path and len(path) > 1:
                max_steps = min(self.movement, len(path) - 1)
                for steps in range(max_steps, 0, -1):
                    new_pos = path[steps]
                    if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                        success, move_msg = grid.move_unit(self, *new_pos)
                        if success:
                            log.append(move_msg)
                        break
        # Also try attacking adjacent allied units while near tower
        allied_units = [u for u in grid.units if u.allegiance == "Allied" and u.hp > 0]
        allied_melee = [u for u in allied_units if grid.hex_distance(self.position, u.position) == 1]
        if allied_melee:
            target = random.choice(allied_melee)
            damage = self.melee_damage
            anim = None
            delay = 0
            if hasattr(grid, 'attack_anims'):
                src = grid.get_hex_center(*self.position)
                tgt = grid.get_hex_center(*target.position)
                anim = grid.attack_anims.create_melee(src, tgt)
                delay = grid.attack_anims.get_max_remaining_ms()
            target.hp -= damage
            target.set_damage_text(damage, delay, anim=anim)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks() + delay
            log.append(f"{self.name} attacked {target.name} for {damage} damage")
        return log

    def _behavior_attack_player(self, grid):
        """Attack the player with melee/projectile, or pathfind toward them."""
        player = grid.player
        # Skip if player is manning a tower (attack_tower handles that)
        if hasattr(player, 'manning_location') and player.manning_location is not None:
            return None
        distance_to_player = grid.hex_distance(self.position, player.position)
        melee_possible = distance_to_player == 1
        projectile_possible = (self.projectile_damage > 0 and
                               1 < distance_to_player <= self.projectile_range and
                               grid.is_aligned(self.position, player.position, self.projectile_range) and
                               grid.has_clear_line_of_sight(self.position, player.position))

        if melee_possible:
            damage = self.melee_damage
            anim = None
            delay = 0
            if hasattr(grid, 'attack_anims'):
                src = grid.get_hex_center(*self.position)
                tgt = grid.get_hex_center(*player.position)
                anim = grid.attack_anims.create_melee(src, tgt)
                delay = grid.attack_anims.get_max_remaining_ms()
            actual_damage, blocked, shield_broken = player.take_damage(damage, self.position, grid)
            log = []
            if blocked:
                player.set_damage_text(0, delay, anim=anim, text="BLOCKED")
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks() + delay
                log.append(f"{self.name} attacked {player.class_name} — blocked by defense!")
                return log
            if shield_broken:
                absorbed = damage - actual_damage
                log.append(f"{player.class_name}'s shield broke! (absorbed {absorbed} damage)")
            player.set_damage_text(actual_damage, delay, anim=anim)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks() + delay
            log.append(f"{self.name} attacked {player.class_name} for {actual_damage} damage")
            if self.special_skill == "Life Drain":
                heal = actual_damage // 2
                self.hp = min(self.hp + heal, self.max_hp)
                log.append(f"{self.name} drained {heal} HP!")
            if player.hp <= 0:
                all_players = grid.players if grid.players else [grid.player]
                if all(p.hp <= 0 for p in all_players):
                    grid.game_over = True
            return log
        elif projectile_possible:
            damage = self.projectile_damage
            anim = None
            delay = 0
            if hasattr(grid, 'attack_anims'):
                src = grid.get_hex_center(*self.position)
                tgt = grid.get_hex_center(*player.position)
                anim = grid.attack_anims.create_projectile(src, tgt)
                delay = grid.attack_anims.get_max_remaining_ms()
            actual_damage, blocked, shield_broken = player.take_damage(damage, self.position, grid)
            log = []
            if blocked:
                player.set_damage_text(0, delay, anim=anim, text="BLOCKED")
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks() + delay
                log.append(f"{self.name} attacked {player.class_name} with projectile — blocked by defense!")
                return log
            if shield_broken:
                absorbed = damage - actual_damage
                log.append(f"{player.class_name}'s shield broke! (absorbed {absorbed} damage)")
            player.set_damage_text(actual_damage, delay, anim=anim)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks() + delay
            log.append(f"{self.name} attacked {player.class_name} with projectile for {actual_damage} damage")
            if player.hp <= 0:
                all_players = grid.players if grid.players else [grid.player]
                if all(p.hp <= 0 for p in all_players):
                    grid.game_over = True
            return log
        else:
            # Try attacking adjacent allied units
            allied_units = [u for u in grid.units if u.allegiance == "Allied" and u.hp > 0]
            allied_melee = [u for u in allied_units if grid.hex_distance(self.position, u.position) == 1]
            if allied_melee:
                target = random.choice(allied_melee)
                damage = self.melee_damage
                anim = None
                delay = 0
                if hasattr(grid, 'attack_anims'):
                    src = grid.get_hex_center(*self.position)
                    tgt = grid.get_hex_center(*target.position)
                    anim = grid.attack_anims.create_melee(src, tgt)
                    delay = grid.attack_anims.get_max_remaining_ms()
                target.hp -= damage
                target.set_damage_text(damage, delay, anim=anim)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks() + delay
                log = [f"{self.name} attacked {target.name} for {damage} damage"]
                if self.special_skill == "Life Drain":
                    heal = damage // 2
                    self.hp = min(self.hp + heal, self.max_hp)
                    log.append(f"{self.name} drained {heal} HP!")
                return log

            allied_projectile = [u for u in allied_units if
                                 self.projectile_damage > 0 and
                                 1 < grid.hex_distance(self.position, u.position) <= self.projectile_range and
                                 grid.is_aligned(self.position, u.position, self.projectile_range) and
                                 grid.has_clear_line_of_sight(self.position, u.position)]
            if allied_projectile:
                target = min(allied_projectile, key=lambda u: grid.hex_distance(self.position, u.position))
                damage = self.projectile_damage
                anim = None
                delay = 0
                if hasattr(grid, 'attack_anims'):
                    src = grid.get_hex_center(*self.position)
                    tgt = grid.get_hex_center(*target.position)
                    anim = grid.attack_anims.create_projectile(src, tgt)
                    delay = grid.attack_anims.get_max_remaining_ms()
                target.hp -= damage
                target.set_damage_text(damage, delay, anim=anim)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks() + delay
                return [f"{self.name} attacked {target.name} with projectile for {damage} damage"]

            # Pathfind toward player
            path = grid.find_path(self.position, player.position)
            if path and len(path) > 1:
                max_steps = min(self.movement, len(path) - 1)
                for steps in range(max_steps, 0, -1):
                    new_pos = path[steps]
                    if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                        success, msg = grid.move_unit(self, *new_pos)
                        if success:
                            log = [msg]
                            distance_after = grid.hex_distance(self.position, player.position)
                            if distance_after == 1:
                                self.pending_attack = {
                                    "target": player,
                                    "damage": self.melee_damage,
                                    "type": "melee",
                                    "is_player": True
                                }
                            elif (self.projectile_damage > 0 and
                                  1 < distance_after <= self.projectile_range and
                                  grid.is_aligned(self.position, player.position, self.projectile_range) and
                                  grid.has_clear_line_of_sight(self.position, player.position)):
                                self.pending_attack = {
                                    "target": player,
                                    "damage": self.projectile_damage,
                                    "type": "projectile",
                                    "is_player": True
                                }
                            return log
                        break
        return None  # Couldn't do anything — fall through

    def _behavior_attack_locations(self, grid):
        """Attack NPC spawn locations (churches)."""
        npc_spawn_locations = grid.get_active_npc_spawn_locations()
        if not npc_spawn_locations:
            return None
        for loc_pos, loc_data in npc_spawn_locations:
            distance_to_loc = grid.hex_distance(self.position, loc_pos)
            if distance_to_loc == 1:
                damage = self.melee_damage
                damage_dealt, destroyed, msg = grid.damage_npc_location(loc_pos[0], loc_pos[1], damage)
                if damage_dealt > 0:
                    delay = 0
                    if hasattr(grid, 'attack_anims'):
                        src = grid.get_hex_center(*self.position)
                        tgt = grid.get_hex_center(*loc_pos)
                        grid.attack_anims.create_melee(src, tgt)
                        delay = grid.attack_anims.get_max_remaining_ms()
                    self.attack_flash = True
                    self.flash_start = pygame.time.get_ticks() + delay
                    return [msg]
            elif (self.projectile_damage > 0 and
                  1 < distance_to_loc <= self.projectile_range and
                  grid.is_aligned(self.position, loc_pos, self.projectile_range) and
                  grid.has_clear_line_of_sight(self.position, loc_pos)):
                damage = self.projectile_damage
                damage_dealt, destroyed, msg = grid.damage_npc_location(loc_pos[0], loc_pos[1], damage)
                if damage_dealt > 0:
                    delay = 0
                    if hasattr(grid, 'attack_anims'):
                        src = grid.get_hex_center(*self.position)
                        tgt = grid.get_hex_center(*loc_pos)
                        grid.attack_anims.create_projectile(src, tgt)
                        delay = grid.attack_anims.get_max_remaining_ms()
                    self.attack_flash = True
                    self.flash_start = pygame.time.get_ticks() + delay
                    return [msg]
        return None  # No locations attackable — fall through

    def _behavior_summon_minion(self, grid):
        """Boss ability: summon a minion from spawn deck."""
        if self.special_skill != "Summon Minion" or not self.spawn_deck:
            return None
        neighbors = grid.get_neighbors(*self.position)
        empty = [p for p in neighbors if grid.grid[p[0]][p[1]]["unit"] is None]
        if not empty:
            return None
        deck_path = resolve_deck_path(self.spawn_deck)
        try:
            with open(deck_path) as f:
                deck_data = json.load(f)
            card_ids = deck_data.get("cards", [])
            if card_ids:
                card_id = random.choice(card_ids)
                card_data = load_card(card_id)
                if card_data:
                    minion = Unit(card_data)
                    spawn_pos = random.choice(empty)
                    grid.place_unit(minion, *spawn_pos)
                    return [f"{self.name} summoned {minion.name}!"]
        except Exception:
            pass
        return None

    def _behavior_messenger_deliver(self, grid):
        """Messenger NPC: approach player and deliver dialogue."""
        if self.special_skill != "Messenger" or not self.dialogue_text or self.dialogue_delivered:
            return None
        targets = [grid.player]
        if hasattr(grid, 'players') and grid.players:
            targets = [p for p in grid.players if p.hp > 0]
        nearest_player = min(targets, key=lambda p: grid.hex_distance(self.position, p.position))
        dist = grid.hex_distance(self.position, nearest_player.position)

        if dist <= 1:
            self.pending_dialogue = {
                "text": self.dialogue_text,
                "speaker": self.name,
                "gift_card_ids": list(self.dialogue_gift_cards)
            }
            self.dialogue_delivered = True
            if self.states == 2:
                self.switch_state()
                self.set_allegiance("Allied")
            return []
        else:
            path = grid.find_path(self.position, nearest_player.position)
            if path and len(path) > 1:
                max_steps = min(self.movement, len(path) - 1)
                for steps in range(max_steps, 0, -1):
                    new_pos = path[steps]
                    if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                        if new_pos != nearest_player.position:
                            success, msg = grid.move_unit(self, *new_pos)
                            if success:
                                log = [f"{self.name} approaches"]
                                if grid.hex_distance(self.position, nearest_player.position) <= 1:
                                    self.pending_dialogue = {
                                        "text": self.dialogue_text,
                                        "speaker": self.name,
                                        "gift_card_ids": list(self.dialogue_gift_cards)
                                    }
                                    self.dialogue_delivered = True
                                    if self.states == 2:
                                        self.switch_state()
                                        self.set_allegiance("Allied")
                                return log
                        break
            return []

    def _behavior_quest_offer(self, grid):
        """Quest giver NPC: approach target player and offer quest."""
        if not self.quest_offer_card_id or not self.quest_offer_target:
            return None
        targets = [grid.player]
        if hasattr(grid, 'players') and grid.players:
            targets = [p for p in grid.players if p.hp > 0]
        target_player = None
        if self.quest_offer_target.startswith("player_"):
            try:
                idx = int(self.quest_offer_target.split("_")[1])
                players = grid.players if hasattr(grid, 'players') and grid.players else []
                if not players and hasattr(grid, 'player') and grid.player:
                    players = [grid.player]
                if idx < len(players) and players[idx].hp > 0:
                    target_player = players[idx]
            except (ValueError, IndexError):
                pass
        if not target_player:
            target_player = targets[0] if targets else None
        if not target_player or not target_player.position:
            return None
        dist = grid.hex_distance(self.position, target_player.position)
        if dist <= 1:
            self.pending_quest_offer = {
                "quest_card_id": self.quest_offer_card_id,
                "speaker": self.name
            }
            return []
        else:
            path = grid.find_path(self.position, target_player.position)
            if path and len(path) > 1:
                max_steps = min(self.movement, len(path) - 1)
                for steps in range(max_steps, 0, -1):
                    new_pos = path[steps]
                    if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                        if new_pos != target_player.position:
                            if self.avoid_location_hexes and new_pos in grid.location_data:
                                continue
                            success, msg = grid.move_unit(self, *new_pos)
                            if success:
                                log = [f"{self.name} approaches"]
                                if grid.hex_distance(self.position, target_player.position) <= 1:
                                    self.pending_quest_offer = {
                                        "quest_card_id": self.quest_offer_card_id,
                                        "speaker": self.name
                                    }
                                return log
                        break
            return []

    def _behavior_wild_mount_wander(self, grid):
        """Wild mount wander: multi-hex directional wander."""
        if not (self.states == 2 and self.current_state == 1 and self.special_skill == "Mount"):
            return None
        if self._planned_move_dest:
            dest = self._planned_move_dest
            self._planned_move_dest = None
            r, c = dest
            if (0 <= r < grid.rows and 0 <= c < grid.cols and
                    grid.grid[r][c]["accessible"] and
                    grid.grid[r][c]["unit"] is None):
                success, msg = grid.move_unit(self, r, c)
                if success:
                    return [msg]
                return []
            return self._wild_mount_wander(grid)
        return self._wild_mount_wander(grid)

    # ============================
    # Turn Planning (Read-only Preview)
    # ============================

    def plan_turn(self, grid):
        """Read-only preview of what this unit will do on its turn.
        Returns a dict: {"action": str, "move_dest": tuple|None, "target_pos": tuple|None}"""
        idle = {"action": "idle", "move_dest": None, "target_pos": None}

        if not self.position:
            return idle
        if self.skip_turn:
            return idle

        # Route based on behavior tree content rather than allegiance name
        hostile_behaviors = {"attack_player", "attack_tower", "attack_locations", "repair_location", "summon_minion", "aggro_gate"}
        neutral_behaviors = {"messenger_deliver", "quest_offer", "wild_mount_wander"}

        tree_set = set(self.behavior_tree)
        if tree_set & hostile_behaviors:
            # Has hostile-specific behaviors — use hostile plan
            return self._plan_hostile(grid)
        elif tree_set & neutral_behaviors:
            # Has neutral-specific behaviors — use neutral plan
            return self._plan_neutral(grid)
        else:
            # Default: use allied plan (behavior tree preview)
            return self._plan_allied(grid)

    def _find_move_dest(self, grid, path):
        """Find the furthest reachable empty hex along a path (read-only)."""
        max_steps = min(self.movement, len(path) - 1)
        for steps in range(max_steps, 0, -1):
            new_pos = path[steps]
            if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                return new_pos
        return None

    def _plan_healing_action(self, grid):
        """Read-only: check if healer would heal or revive (allegiance-aware). Returns plan dict or None."""
        if self.heal_amount <= 0:
            return None

        # Revive phase
        friendlies = self._get_friendlies(grid)
        for u in friendlies:
            if (u.hp <= 0 and getattr(u, '_death_processed', False)
                    and u.position
                    and grid.hex_distance(self.position, u.position) <= self.heal_range):
                return {"action": "revive", "move_dest": None, "target_pos": u.position}

        # Heal phase
        candidates = [u for u in friendlies
                      if u.hp > 0 and u.hp < u.max_hp and u.position
                      and grid.hex_distance(self.position, u.position) <= self.heal_range]

        if candidates:
            target = min(candidates, key=lambda u: u.hp / u.max_hp)
            return {"action": "heal", "move_dest": None, "target_pos": target.position}

        return None

    def _plan_hostile(self, grid):
        """Read-only preview of hostile unit decision tree."""
        idle = {"action": "idle", "move_dest": None, "target_pos": None}

        # Repair boss
        if self.special_skill == "Repair" and self.repair_value > 0:
            damaged_locations = grid.get_damaged_spawn_locations()
            if damaged_locations:
                nearest_loc = min(damaged_locations, key=lambda x: grid.hex_distance(self.position, x[0]))
                dist_to_loc = grid.hex_distance(self.position, nearest_loc[0])
                if dist_to_loc <= 1:
                    return {"action": "repair", "move_dest": None, "target_pos": nearest_loc[0]}
                path = grid.find_path(self.position, nearest_loc[0])
                if path and len(path) > 1:
                    dest = self._find_move_dest(grid, path)
                    if dest:
                        if grid.hex_distance(dest, nearest_loc[0]) <= 1:
                            return {"action": "move_repair", "move_dest": dest, "target_pos": nearest_loc[0]}
                        return {"action": "move", "move_dest": dest, "target_pos": None}
                return idle

        # Aggro range gate
        player = grid.player
        distance_to_player = grid.hex_distance(self.position, player.position)

        if self.aggro_range > 0:
            targets_in_range = distance_to_player <= self.aggro_range
            if not targets_in_range:
                allied_units = [u for u in grid.units if u.allegiance == "Allied" and u.hp > 0]
                targets_in_range = any(grid.hex_distance(self.position, u.position) <= self.aggro_range for u in allied_units)
            if not targets_in_range:
                return idle

        # If player is manning a tower, redirect attacks to tower
        if hasattr(player, 'manning_location') and player.manning_location is not None:
            tower_pos = player.manning_location
            dist_to_tower = grid.hex_distance(self.position, tower_pos)
            if dist_to_tower == 1:
                return {"action": "melee", "move_dest": None, "target_pos": tower_pos}
            if (self.projectile_damage > 0 and
                    1 < dist_to_tower <= self.projectile_range and
                    grid.is_aligned(self.position, tower_pos, self.projectile_range) and
                    grid.has_clear_line_of_sight(self.position, tower_pos)):
                return {"action": "projectile", "move_dest": None, "target_pos": tower_pos}
            # Can't attack tower - pathfind toward it
            path = grid.find_path(self.position, tower_pos)
            if path and len(path) > 1:
                dest = self._find_move_dest(grid, path)
                if dest:
                    return {"action": "move", "move_dest": dest, "target_pos": tower_pos}
            # Fall through to allied unit targeting
            allied_units = [u for u in grid.units if u.allegiance == "Allied" and u.hp > 0]
            allied_melee = [u for u in allied_units if grid.hex_distance(self.position, u.position) == 1]
            if allied_melee:
                return {"action": "melee", "move_dest": None, "target_pos": allied_melee[0].position}
            return idle

        # Can melee player?
        if distance_to_player == 1:
            return {"action": "melee", "move_dest": None, "target_pos": player.position}

        # Can projectile player?
        if (self.projectile_damage > 0 and
                1 < distance_to_player <= self.projectile_range and
                grid.is_aligned(self.position, player.position, self.projectile_range) and
                grid.has_clear_line_of_sight(self.position, player.position)):
            return {"action": "projectile", "move_dest": None, "target_pos": player.position}

        # Allied units - melee
        allied_units = [u for u in grid.units if u.allegiance == "Allied" and u.hp > 0]
        allied_melee = [u for u in allied_units if grid.hex_distance(self.position, u.position) == 1]
        if allied_melee:
            return {"action": "melee", "move_dest": None, "target_pos": allied_melee[0].position}

        # Allied units - projectile
        if self.projectile_damage > 0:
            allied_proj = [u for u in allied_units if
                           1 < grid.hex_distance(self.position, u.position) <= self.projectile_range and
                           grid.is_aligned(self.position, u.position, self.projectile_range) and
                           grid.has_clear_line_of_sight(self.position, u.position)]
            if allied_proj:
                target = min(allied_proj, key=lambda u: grid.hex_distance(self.position, u.position))
                return {"action": "projectile", "move_dest": None, "target_pos": target.position}

        # NPC spawn locations
        npc_spawn_locations = grid.get_active_npc_spawn_locations()
        for loc_pos, loc_data in npc_spawn_locations:
            dist = grid.hex_distance(self.position, loc_pos)
            if dist == 1:
                return {"action": "melee", "move_dest": None, "target_pos": loc_pos}
            if (self.projectile_damage > 0 and
                    1 < dist <= self.projectile_range and
                    grid.is_aligned(self.position, loc_pos, self.projectile_range) and
                    grid.has_clear_line_of_sight(self.position, loc_pos)):
                return {"action": "projectile", "move_dest": None, "target_pos": loc_pos}

        # Pathfind toward player
        path = grid.find_path(self.position, player.position)
        if path and len(path) > 1:
            dest = self._find_move_dest(grid, path)
            if dest:
                dist_after = grid.hex_distance(dest, player.position)
                if dist_after == 1:
                    return {"action": "move_melee", "move_dest": dest, "target_pos": player.position}
                if (self.projectile_damage > 0 and
                        1 < dist_after <= self.projectile_range and
                        grid.is_aligned(dest, player.position, self.projectile_range) and
                        grid.has_clear_line_of_sight(dest, player.position)):
                    return {"action": "move_projectile", "move_dest": dest, "target_pos": player.position}
                return {"action": "move", "move_dest": dest, "target_pos": None}

        # Summon Minion or no action
        return idle

    def _plan_allied(self, grid):
        """Read-only preview of allied unit decision tree."""
        idle = {"action": "idle", "move_dest": None, "target_pos": None}

        # Quest-driven behavior
        if self.quest_target_position:
            hostile_units = [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0]
            use_rush = (self.quest_movement_priority == "rush" and hostile_units)
            if use_rush:
                return self._plan_allied_rush(grid, hostile_units)
            elif hostile_units:
                return self._plan_allied_fight(grid, hostile_units)
            else:
                return self._plan_allied_idle(grid)

        # Garrison (validate target is still valid)
        if self.garrison_target_location:
            loc = grid.location_data.get(self.garrison_target_location)
            if loc and loc.get("state", 1) == 2 and len(loc.get("garrison_npcs", [])) < 3:
                return self._plan_allied_idle(grid)
            # Target invalid — fall through to behavior tree

        # Behavior tree
        for behavior in self.behavior_tree:
            result = self._plan_behavior(behavior, grid)
            if result is not None:
                return result

        return idle

    def _plan_allied_rush(self, grid, hostile_units):
        """Read-only preview of rush mode."""
        idle = {"action": "idle", "move_dest": None, "target_pos": None}

        # Adjacent enemies
        adjacent = [u for u in hostile_units if grid.hex_distance(self.position, u.position) == 1]
        if adjacent:
            return {"action": "melee", "move_dest": None, "target_pos": adjacent[0].position}

        # Projectile
        if self.projectile_damage > 0:
            in_range = [u for u in hostile_units if
                        1 < grid.hex_distance(self.position, u.position) <= self.projectile_range and
                        grid.is_aligned(self.position, u.position, self.projectile_range) and
                        grid.has_clear_line_of_sight(self.position, u.position)]
            if in_range:
                target = min(in_range, key=lambda u: grid.hex_distance(self.position, u.position))
                return {"action": "projectile", "move_dest": None, "target_pos": target.position}

        # Move toward quest target
        dist = grid.hex_distance(self.position, self.quest_target_position)
        if dist > 0:
            path = grid.find_path(self.position, self.quest_target_position)
            if path and len(path) > 1:
                dest = self._find_move_dest(grid, path)
                if dest:
                    for enemy in hostile_units:
                        if enemy.hp > 0 and grid.hex_distance(dest, enemy.position) == 1:
                            return {"action": "move_melee", "move_dest": dest, "target_pos": enemy.position}
                    return {"action": "move", "move_dest": dest, "target_pos": None}

        return idle

    def _plan_allied_fight(self, grid, hostile_units):
        """Read-only preview of fight mode."""
        target = min(hostile_units, key=lambda u: grid.hex_distance(self.position, u.position))
        return self._plan_chase_and_attack(grid, target)

    def _plan_allied_idle(self, grid):
        """Read-only preview of idle mode (no enemies, move toward target/garrison)."""
        idle = {"action": "idle", "move_dest": None, "target_pos": None}

        dest_pos = self.quest_target_position or self.garrison_target_location
        if dest_pos:
            dist = grid.hex_distance(self.position, dest_pos)
            if dist > 0:
                path = grid.find_path(self.position, dest_pos)
                if path and len(path) > 1:
                    move_dest = self._find_move_dest(grid, path)
                    if move_dest:
                        return {"action": "move", "move_dest": move_dest, "target_pos": None}

        return idle

    def _plan_chase_and_attack(self, grid, target):
        """Read-only preview of chase-and-attack logic."""
        idle = {"action": "idle", "move_dest": None, "target_pos": None}
        distance = grid.hex_distance(self.position, target.position)

        # Projectile
        if (self.projectile_damage > 0 and
                1 < distance <= self.projectile_range and
                grid.is_aligned(self.position, target.position, self.projectile_range) and
                grid.has_clear_line_of_sight(self.position, target.position)):
            return {"action": "projectile", "move_dest": None, "target_pos": target.position}

        # Melee
        if distance == 1:
            return {"action": "melee", "move_dest": None, "target_pos": target.position}

        # Pathfind
        path = grid.find_path(self.position, target.position)
        if path and len(path) > 1:
            dest = self._find_move_dest(grid, path)
            if dest:
                dist_after = grid.hex_distance(dest, target.position)
                if dist_after == 1:
                    return {"action": "move_melee", "move_dest": dest, "target_pos": target.position}
                if (self.projectile_damage > 0 and
                        1 < dist_after <= self.projectile_range and
                        grid.is_aligned(dest, target.position, self.projectile_range) and
                        grid.has_clear_line_of_sight(dest, target.position)):
                    return {"action": "move_projectile", "move_dest": dest, "target_pos": target.position}
                return {"action": "move", "move_dest": dest, "target_pos": None}

        return idle

    def _plan_behavior(self, behavior, grid):
        """Read-only preview of a behavior tree entry. Returns plan dict or None."""
        dispatch = {
            "revive_ally": self._plan_behavior_revive,
            "healing": self._plan_behavior_healing,
            "patrol": self._plan_behavior_patrol,
            "guard": self._plan_behavior_guard,
            "recruit": self._plan_behavior_recruit,
            "follow_target": self._plan_behavior_follow,
            "attack_target": self._plan_behavior_attack_target,
            "attack_closest": self._plan_behavior_attack_closest,
            "attack_weakest": self._plan_behavior_attack_weakest,
            "flee": self._plan_behavior_flee,
            "graze": self._plan_behavior_graze,
            "garrison_tower": self._plan_behavior_garrison_tower,
            "convert_enemy": self._plan_behavior_convert_enemy,
        }
        handler = dispatch.get(behavior)
        if handler:
            return handler(grid)
        return None

    def _plan_behavior_revive(self, grid):
        if self.special_skill != "Healer" or self.heal_amount <= 0:
            return None
        dead_targets = []
        friendlies = self._get_friendlies(grid)
        for u in friendlies:
            if (u.hp <= 0 and getattr(u, '_death_processed', False)
                    and u.position):
                dead_targets.append(u)
        if not dead_targets:
            return None
        dead_targets.sort(key=lambda t: grid.hex_distance(self.position, t.position))
        nearest = dead_targets[0]
        dist = grid.hex_distance(self.position, nearest.position)
        if dist <= self.heal_range:
            return {"action": "revive", "move_dest": None, "target_pos": nearest.position}
        path = grid.find_path(self.position, nearest.position)
        if path and len(path) > 1:
            dest = self._find_move_dest(grid, path)
            if dest:
                return {"action": "move", "move_dest": dest, "target_pos": None}
        return {"action": "idle", "move_dest": None, "target_pos": None}

    def _plan_behavior_convert_enemy(self, grid):
        """Preview: find dead enemies to convert."""
        if self.special_skill != "Healer" or self.heal_amount <= 0:
            return None
        if self.convert_cooldown > 0:
            return None
        dead_enemies = self._get_dead_enemies(grid)
        if not dead_enemies:
            return None
        dead_enemies.sort(key=lambda t: grid.hex_distance(self.position, t.position))
        nearest = dead_enemies[0]
        dist = grid.hex_distance(self.position, nearest.position)
        if dist <= self.heal_range:
            return {"action": "convert_enemy", "move_dest": None, "target_pos": nearest.position}
        path = grid.find_path(self.position, nearest.position)
        if path and len(path) > 1:
            dest = self._find_move_dest(grid, path)
            if dest:
                return {"action": "move", "move_dest": dest, "target_pos": None}
        return {"action": "idle", "move_dest": None, "target_pos": None}

    def _plan_behavior_healing(self, grid):
        if self.special_skill != "Healer" or self.heal_amount <= 0:
            return None
        friendlies = self._get_friendlies(grid)
        candidates = [u for u in friendlies if u.hp > 0 and u.hp < u.max_hp and u.position]
        if not candidates:
            return None
        most_damaged = min(candidates, key=lambda u: u.hp / u.max_hp)
        dist = grid.hex_distance(self.position, most_damaged.position)
        if dist <= self.heal_range:
            return {"action": "heal", "move_dest": None, "target_pos": most_damaged.position}
        nearest = min(candidates, key=lambda u: grid.hex_distance(self.position, u.position))
        path = grid.find_path(self.position, nearest.position)
        if path and len(path) > 1:
            dest = self._find_move_dest(grid, path)
            if dest:
                return {"action": "move", "move_dest": dest, "target_pos": None}
        return {"action": "idle", "move_dest": None, "target_pos": None}

    def _plan_behavior_attack_closest(self, grid):
        enemies = self._get_enemies(grid)
        if not enemies:
            return None
        target = min(enemies, key=lambda u: grid.hex_distance(self.position, u.position))
        if self.attack_proximity_range > 0:
            if grid.hex_distance(self.position, target.position) > self.attack_proximity_range:
                return None
        return self._plan_chase_and_attack(grid, target)

    def _plan_behavior_attack_weakest(self, grid):
        enemies = self._get_enemies(grid)
        if not enemies:
            return None
        target = min(enemies, key=lambda u: u.hp)
        return self._plan_chase_and_attack(grid, target)

    def _plan_behavior_attack_target(self, grid):
        if not self.behavior_attack_target:
            return None
        target = None
        for u in grid.units:
            if u.card_id == self.behavior_attack_target and u.hp > 0 and u.position:
                target = u
                break
        if not target:
            return None
        return self._plan_chase_and_attack(grid, target)

    def _plan_behavior_follow(self, grid):
        target_entity = self._resolve_follow_target(grid)
        if not target_entity or not target_entity.position:
            return None
        distance = grid.hex_distance(self.position, target_entity.position)

        # On location hex and avoiding — move off
        if self.avoid_location_hexes and self.position in grid.location_data:
            neighbors = grid.get_neighbors(*self.position)
            for pos in neighbors:
                if (grid.grid[pos[0]][pos[1]]["unit"] is None and
                        grid.grid[pos[0]][pos[1]].get("accessible", True) and
                        pos not in grid.location_data):
                    return {"action": "move", "move_dest": pos, "target_pos": None}
            return {"action": "idle", "move_dest": None, "target_pos": None}

        # Within 2 hexes — attack adjacent enemies
        if distance <= 2:
            enemies = self._get_enemies(grid)
            adjacent = [u for u in enemies if grid.hex_distance(self.position, u.position) == 1]
            if adjacent:
                return {"action": "melee", "move_dest": None, "target_pos": adjacent[0].position}
            return {"action": "idle", "move_dest": None, "target_pos": None}

        # Too far — move toward target
        path = grid.find_path(self.position, target_entity.position)
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                    if self.avoid_location_hexes and new_pos in grid.location_data:
                        continue
                    return {"action": "move", "move_dest": new_pos, "target_pos": None}
        return {"action": "idle", "move_dest": None, "target_pos": None}

    def _plan_behavior_guard(self, grid):
        enemies = self._get_enemies(grid)
        adjacent = [u for u in enemies if grid.hex_distance(self.position, u.position) == 1]
        if adjacent:
            return {"action": "melee", "move_dest": None, "target_pos": adjacent[0].position}
        if self.projectile_damage > 0:
            in_range = [u for u in enemies if
                        1 < grid.hex_distance(self.position, u.position) <= self.projectile_range and
                        grid.is_aligned(self.position, u.position, self.projectile_range) and
                        grid.has_clear_line_of_sight(self.position, u.position)]
            if in_range:
                target = min(in_range, key=lambda u: grid.hex_distance(self.position, u.position))
                return {"action": "projectile", "move_dest": None, "target_pos": target.position}
        return {"action": "idle", "move_dest": None, "target_pos": None}

    def _plan_behavior_patrol(self, grid):
        neighbors = grid.get_neighbors(*self.position)
        empty = [pos for pos in neighbors if grid.grid[pos[0]][pos[1]]["unit"] is None
                 and grid.grid[pos[0]][pos[1]].get("accessible", True)]
        if empty:
            dest = random.choice(empty)
            self._planned_move_dest = dest
            return {"action": "move", "move_dest": dest, "target_pos": None}
        return {"action": "idle", "move_dest": None, "target_pos": None}

    def _plan_behavior_flee(self, grid):
        enemies = self._get_enemies(grid)
        if not enemies:
            return None
        nearest = min(enemies, key=lambda u: grid.hex_distance(self.position, u.position))
        neighbors = grid.get_neighbors(*self.position)
        empty = [pos for pos in neighbors if grid.grid[pos[0]][pos[1]]["unit"] is None
                 and grid.grid[pos[0]][pos[1]].get("accessible", True)]
        if empty:
            best = max(empty, key=lambda pos: grid.hex_distance(pos, nearest.position))
            return {"action": "move", "move_dest": best, "target_pos": None}
        return {"action": "idle", "move_dest": None, "target_pos": None}

    def _plan_behavior_recruit(self, grid):
        if self.recruit_cooldown > 0:
            return None
        neutrals = [u for u in grid.units if u.allegiance == "Neutral" and u.hp > 0 and u.position]
        if not neutrals:
            return None
        target = min(neutrals, key=lambda u: grid.hex_distance(self.position, u.position))
        distance = grid.hex_distance(self.position, target.position)
        if distance == 1:
            return {"action": "idle", "move_dest": None, "target_pos": target.position}
        path = grid.find_path(self.position, target.position)
        if path and len(path) > 1:
            dest = self._find_move_dest(grid, path)
            if dest:
                return {"action": "move", "move_dest": dest, "target_pos": None}
        return {"action": "idle", "move_dest": None, "target_pos": None}

    def _plan_behavior_graze(self, grid):
        if self.special_skill != "Mount":
            return None
        if self.hp >= self.max_hp:
            return None
        row, col = self.position
        terrain = grid.grid[row][col].get("terrain", "")
        if terrain == "grass":
            return {"action": "heal", "move_dest": None, "target_pos": self.position}
        best_grass = None
        best_dist = float('inf')
        for r in range(grid.rows):
            for c in range(grid.cols):
                if (grid.grid[r][c].get("terrain", "") == "grass" and
                        grid.grid[r][c].get("accessible", True) and
                        grid.grid[r][c]["unit"] is None):
                    d = grid.hex_distance(self.position, (r, c))
                    if d < best_dist:
                        best_dist = d
                        best_grass = (r, c)
        if not best_grass:
            return None
        path = grid.find_path(self.position, best_grass)
        if path and len(path) > 1:
            dest = self._find_move_dest(grid, path)
            if dest:
                return {"action": "move", "move_dest": dest, "target_pos": None}
        return None

    def _plan_behavior_garrison_tower(self, grid):
        """Plan preview for garrison tower behavior."""
        if self.garrison_target_location:
            return None  # Already assigned, garrison override handles it

        # Same search logic as _behavior_garrison_tower
        player_manning = set()
        players = grid.players if hasattr(grid, 'players') and grid.players else []
        if not players and hasattr(grid, 'player') and grid.player:
            players = [grid.player]
        for p in players:
            if hasattr(p, 'manning_location') and p.manning_location:
                player_manning.add(tuple(p.manning_location))

        candidates = []
        for pos, loc_data in grid.location_data.items():
            if loc_data.get("state", 1) != 2:
                continue
            if pos in player_manning:
                continue
            defenses = loc_data.get("defenses", [])
            if not any(d.get("requires_npc") for d in defenses):
                continue
            garrison = loc_data.get("garrison_npcs", [])
            targeting_count = sum(1 for u in grid.units if u is not self and u.hp > 0 and getattr(u, 'garrison_target_location', None) == pos)
            if len(garrison) + targeting_count >= 3:
                continue
            candidates.append(pos)

        if not candidates:
            return None

        closest = min(candidates, key=lambda p: grid.hex_distance(self.position, p))
        return {"action": "move", "move_dest": closest, "target_pos": None}

    def _plan_neutral(self, grid):
        """Read-only preview of neutral unit decision tree."""
        idle = {"action": "idle", "move_dest": None, "target_pos": None}

        # Messenger NPC
        if self.special_skill == "Messenger" and self.dialogue_text and not self.dialogue_delivered:
            targets = [grid.player]
            if hasattr(grid, 'players') and grid.players:
                targets = [p for p in grid.players if p.hp > 0]
            nearest_player = min(targets, key=lambda p: grid.hex_distance(self.position, p.position))
            dist = grid.hex_distance(self.position, nearest_player.position)
            if dist <= 1:
                return idle
            path = grid.find_path(self.position, nearest_player.position)
            if path and len(path) > 1:
                max_steps = min(self.movement, len(path) - 1)
                for steps in range(max_steps, 0, -1):
                    new_pos = path[steps]
                    if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                        if new_pos != nearest_player.position:
                            return {"action": "move", "move_dest": new_pos, "target_pos": None}
                        break
            return idle

        # Quest giver NPC
        if self.quest_offer_card_id and self.quest_offer_target:
            targets = [grid.player]
            if hasattr(grid, 'players') and grid.players:
                targets = [p for p in grid.players if p.hp > 0]
            target_player = None
            if self.quest_offer_target.startswith("player_"):
                try:
                    idx = int(self.quest_offer_target.split("_")[1])
                    players = grid.players if hasattr(grid, 'players') and grid.players else []
                    if not players and hasattr(grid, 'player') and grid.player:
                        players = [grid.player]
                    if idx < len(players) and players[idx].hp > 0:
                        target_player = players[idx]
                except (ValueError, IndexError):
                    pass
            if not target_player:
                target_player = targets[0] if targets else None
            if target_player and target_player.position:
                dist = grid.hex_distance(self.position, target_player.position)
                if dist <= 1:
                    return idle
                path = grid.find_path(self.position, target_player.position)
                if path and len(path) > 1:
                    max_steps = min(self.movement, len(path) - 1)
                    for steps in range(max_steps, 0, -1):
                        new_pos = path[steps]
                        if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                            if new_pos != target_player.position:
                                if self.avoid_location_hexes and new_pos in grid.location_data:
                                    continue
                                return {"action": "move", "move_dest": new_pos, "target_pos": None}
                            break
            return idle

        # Wild mount — replicate actual wander logic so preview matches execution
        if (self.states == 2 and self.current_state == 1 and self.special_skill == "Mount"):
            DIRECTIONS = [
                (1, 0, -1), (1, -1, 0), (0, -1, 1),
                (-1, 0, 1), (-1, 1, 0), (0, 1, -1)
            ]
            dir_idx = random.randint(0, 5)
            direction = DIRECTIONS[dir_idx]
            distance = random.randint(1, self.movement)
            row, col = self.position
            line = grid.get_line(row, col, direction, distance)
            furthest = None
            for hex_pos in line:
                r, c = hex_pos
                if (0 <= r < grid.rows and 0 <= c < grid.cols and
                        grid.grid[r][c]["accessible"] and
                        grid.grid[r][c]["unit"] is None):
                    furthest = hex_pos
                else:
                    break
            if furthest:
                self._planned_move_dest = furthest
                return {"action": "move", "move_dest": furthest, "target_pos": None}
            return idle

        # Default neutral wander — use random.choice and store for take_turn()
        neighbors = grid.get_neighbors(*self.position)
        empty = [pos for pos in neighbors if grid.grid[pos[0]][pos[1]]["unit"] is None]
        if empty:
            dest = random.choice(empty)
            self._planned_move_dest = dest
            return {"action": "move", "move_dest": dest, "target_pos": None}

        return idle

    def _dual_strike_second_attack(self, grid):
        """Dual Strike: attempt a second attack from current position (no movement)."""
        log = []
        enemies = self._get_enemies(grid)
        if not enemies:
            return log

        # Prefer projectile attack on nearest in-range enemy
        if self.projectile_damage > 0:
            in_range = [u for u in enemies if
                        1 < grid.hex_distance(self.position, u.position) <= self.projectile_range and
                        grid.is_aligned(self.position, u.position, self.projectile_range) and
                        grid.has_clear_line_of_sight(self.position, u.position)]
            if in_range:
                target = min(in_range, key=lambda u: grid.hex_distance(self.position, u.position))
                damage = self.projectile_damage
                anim = None
                delay = 0
                if hasattr(grid, 'attack_anims'):
                    src = grid.get_hex_center(*self.position)
                    tgt = grid.get_hex_center(*target.position)
                    anim = grid.attack_anims.create_projectile(src, tgt)
                    delay = grid.attack_anims.get_max_remaining_ms()
                target.hp -= damage
                target.set_damage_text(damage, delay, anim=anim)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks() + delay
                log.append(f"{self.name} (Dual Strike) attacked {target.name} with projectile for {damage} damage")
                return log

        # Melee attack on adjacent enemy
        adjacent = [u for u in enemies if grid.hex_distance(self.position, u.position) == 1]
        if adjacent:
            target = random.choice(adjacent)
            damage = self.melee_damage
            anim = None
            delay = 0
            if hasattr(grid, 'attack_anims'):
                src = grid.get_hex_center(*self.position)
                tgt = grid.get_hex_center(*target.position)
                anim = grid.attack_anims.create_melee(src, tgt)
                delay = grid.attack_anims.get_max_remaining_ms()
            target.hp -= damage
            target.set_damage_text(damage, delay, anim=anim)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks() + delay
            log.append(f"{self.name} (Dual Strike) attacked {target.name} for {damage} damage")
            return log

        return log

    def execute_pending_attack(self, grid):
        """Execute a deferred attack after movement animation completes.
        Returns list of log entries."""
        if not self.pending_attack:
            return []

        attack = self.pending_attack
        self.pending_attack = None

        # Handle repair type (boss repairing spawn locations)
        if attack.get("type") == "repair":
            target_pos = attack["target_pos"]
            repair_val = attack["repair_value"]
            log = []
            success, healed, rebuilt, msg = grid.repair_spawn_location(target_pos[0], target_pos[1], repair_val)
            if success:
                delay = 0
                if hasattr(grid, 'attack_anims'):
                    src = grid.get_hex_center(*self.position)
                    tgt = grid.get_hex_center(*target_pos)
                    grid.attack_anims.create_melee(src, tgt)
                    delay = grid.attack_anims.get_max_remaining_ms()
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks() + delay
                log.append(msg)
            return log

        target = attack["target"]
        damage = attack["damage"]
        attack_type = attack["type"]
        is_player = attack.get("is_player", False)

        # Check target is still valid
        if is_player:
            if target.hp <= 0:
                return []
        else:
            if target not in grid.units or target.hp <= 0:
                return []

        # Trigger attack animation
        anim = None
        delay = 0
        if hasattr(grid, 'attack_anims') and self.position and target.position:
            src = grid.get_hex_center(*self.position)
            tgt = grid.get_hex_center(*target.position)
            if attack_type == "projectile":
                anim = grid.attack_anims.create_projectile(src, tgt)
            else:
                anim = grid.attack_anims.create_melee(src, tgt)
            delay = grid.attack_anims.get_max_remaining_ms()

        log = []
        if is_player:
            target_name = target.class_name
            actual_damage, blocked, shield_broken = target.take_damage(damage, self.position, grid)
            if blocked:
                target.set_damage_text(0, delay, anim=anim, text="BLOCKED")
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks() + delay
                log.append(f"{self.name} attacked {target_name} — blocked by defense!")
                return log
            if shield_broken:
                absorbed = damage - actual_damage
                log.append(f"{target_name}'s shield broke! (absorbed {absorbed} damage)")
            target.set_damage_text(actual_damage, delay, anim=anim)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks() + delay
            if attack_type == "projectile":
                log.append(f"{self.name} attacked {target_name} with projectile for {actual_damage} damage")
            else:
                log.append(f"{self.name} attacked {target_name} for {actual_damage} damage")
                if self.special_skill == "Life Drain":
                    heal = actual_damage // 2
                    self.hp = min(self.hp + heal, self.max_hp)
                    log.append(f"{self.name} drained {heal} HP!")
        else:
            target_name = target.name
            target.hp -= damage
            target.set_damage_text(damage, delay, anim=anim)
            self.attack_flash = True
            self.flash_start = pygame.time.get_ticks() + delay
            if attack_type == "projectile":
                log.append(f"{self.name} attacked {target_name} with projectile for {damage} damage")
            else:
                log.append(f"{self.name} attacked {target_name} for {damage} damage")
                if self.special_skill == "Life Drain":
                    heal = damage // 2
                    self.hp = min(self.hp + heal, self.max_hp)
                    log.append(f"{self.name} drained {heal} HP!")

        if is_player and target.hp <= 0:
            # Only game over if ALL players are dead (multiplayer support)
            all_players = grid.players if grid.players else [grid.player]
            if all(p.hp <= 0 for p in all_players):
                grid.game_over = True

        return log

    def switch_state(self):
        if self.states == 2 and self.current_state == 1:
            self.current_state = 2
            state_data = self.second_state
            self.name = state_data["name"]
            self.hp = state_data["hp"]
            self.max_hp = self.hp
            self.movement = state_data["movement"]
            self.melee_damage = state_data["melee_damage"]
            self.projectile_damage = state_data["projectile_damage"]
            self.projectile_range = state_data["projectile_range"]
            # Allegiance is NOT changed by state switch — use set_allegiance() explicitly
            self.special_skill = state_data["special_skill"]
            self.dual_strike = (self.special_skill == "Dual Strike")
            self.heal_amount = state_data.get("heal_amount", self.heal_amount)
            self.heal_range = state_data.get("heal_range", self.heal_range)
            self.is_stubborn = state_data.get("is_stubborn", self.is_stubborn)
            self.repair_value = state_data.get("repair_value", self.repair_value)
            self.aggro_range = state_data.get("aggro_range", self.aggro_range)
            # Update per-allegiance trees from state 2 data
            for key, attr in [("hostile_bt_str", "hostile_behavior_tree"),
                              ("neutral_bt_str", "neutral_behavior_tree"),
                              ("allied_bt_str", "allied_behavior_tree")]:
                bt_str = state_data.get(key, "")
                if bt_str:
                    try:
                        tree = json.loads(bt_str)
                        if isinstance(tree, list) and tree:
                            setattr(self, attr, tree)
                    except (json.JSONDecodeError, TypeError):
                        pass
            # Also check legacy behavior_tree_str for Allied tree
            bt_str = state_data.get("behavior_tree_str", "")
            if bt_str and not state_data.get("allied_bt_str", ""):
                try:
                    tree = json.loads(bt_str)
                    if isinstance(tree, list) and tree:
                        self.allied_behavior_tree = tree
                except (json.JSONDecodeError, TypeError):
                    pass
            # Update allegiance priority if state 2 has one
            ap_str = state_data.get("allegiance_priority_str", "")
            if ap_str:
                try:
                    parsed = json.loads(ap_str)
                    if isinstance(parsed, list) and len(parsed) >= 1:
                        self.allegiance_priority = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            # Re-select active tree based on current allegiance (unchanged)
            self.behavior_tree = self._select_behavior_tree()
            return f"{self.name} switched to second state"
        return ""

    def get_stats(self):
        stats = f"Name: {self.name}\nHP: {self.hp}/{self.max_hp}\nMovement: {self.movement}\nMelee Damage: {self.melee_damage}"
        if self.projectile_damage > 0:
            stats += f"\nProjectile Damage: {self.projectile_damage}\nRange: {self.projectile_range}"
        stats += f"\nAllegiance: {self.allegiance}"
        if self.special_skill:
            stats += f"\nSpecial Skill: {self.special_skill}"
        if self.states == 2:
            stats += f"\nState: {self.current_state}/2"
        return stats

    def set_damage_text(self, damage, delay=0, anim=None, text=None):
        """Set the damage text and timestamp when damage is taken.
        delay: ms to wait before showing the text (syncs with attack animations).
        anim: AttackAnimation object to tie health bar offset to actual animation state.
        text: custom text override (e.g. '+8' for healing, 'BLOCKED')."""
        self.damage_text = text if text else f"-{damage}"
        self.damage_time = pygame.time.get_ticks() + delay
        if anim:
            self._pending_damage_anim = anim
            self._hp_visual_offset = damage
        elif delay > 0:
            self._hp_visual_offset = damage
            self._hp_visual_offset_until = pygame.time.get_ticks() + delay

    def animate_move(self, grid, new_row, new_col):
        """Start path-based movement animation from current position to new position."""
        old_pos = self.position

        # Find path from old position to new position
        path = grid.find_path(old_pos, (new_row, new_col))

        if path and len(path) > 1:
            # Store the path (excluding starting position)
            self.animation_path = path[1:]  # Skip the starting hex
            self.animation_path_index = 0
        else:
            # Fallback: direct path if pathfinding fails
            self.animation_path = [(new_row, new_col)]
            self.animation_path_index = 0

        # Set initial render position at old location
        old_x, old_y = grid.get_hex_center(*old_pos)
        self.render_pos = (old_x, old_y)
        self.animating = True

        # Update grid to show unit at final position (for collision detection)
        grid.grid[old_pos[0]][old_pos[1]]["unit"] = None
        grid.grid[new_row][new_col]["unit"] = self
        self.position = (new_row, new_col)

    def update_animation(self, grid):
        """Update path-based movement animation, moving hex by hex."""
        if self.animating and self.render_pos and self.animation_path:
            # Get current target hex in the path
            target_hex = self.animation_path[self.animation_path_index]
            target_x, target_y = grid.get_hex_center(*target_hex)

            dx = target_x - self.render_pos[0]
            dy = target_y - self.render_pos[1]
            dist = math.sqrt(dx**2 + dy**2)

            if dist <= MOVE_SPEED:
                # Reached current target hex
                self.render_pos = (target_x, target_y)
                self.animation_path_index += 1

                # Check passthrough defenses when hostile unit enters a new hex
                if self.allegiance == "Hostile":
                    self._check_passthrough_defenses(grid, target_hex)

                # Check if we've completed the path
                if self.animation_path_index >= len(self.animation_path):
                    self.render_pos = None
                    self.animating = False
                    self.animation_path = []
                    self.animation_path_index = 0
            else:
                # Move toward current target hex
                move_x = dx / dist * MOVE_SPEED
                move_y = dy / dist * MOVE_SPEED
                self.render_pos = (self.render_pos[0] + move_x, self.render_pos[1] + move_y)
        if self.attack_flash and pygame.time.get_ticks() - self.flash_start > ATTACK_FLASH_DURATION:
            self.attack_flash = False
        if self.damage_text and pygame.time.get_ticks() - self.damage_time > DAMAGE_TEXT_DURATION:
            self.damage_text = None  # Clear damage text after duration

    def _check_passthrough_defenses(self, grid, current_hex):
        """Check if this hostile unit passes through any active defensive location ranges.
        Deals half damage on successful hit based on passthrough_chance."""
        for pos, loc_data in grid.location_data.items():
            if loc_data.get("state", 1) != 2:
                continue
            garrison = loc_data.get("garrison_npcs", [])
            if not garrison:
                continue
            for defense in loc_data.get("defenses", []):
                if not defense.get("requires_npc"):
                    continue
                passthrough_chance = defense.get("passthrough_chance", 0)
                if passthrough_chance <= 0:
                    continue
                damage = defense.get("damage", 0)
                if damage <= 0:
                    continue

                # Calculate defense range each time (position-dependent, not safe to cache)
                cached = grid.calculate_range(
                    pos, defense["range_distance"], defense["range_type"],
                    defense.get("include_position", False), defense.get("exclude_adjacent", False)
                )

                if current_hex in cached:
                    # Roll passthrough chance
                    if random.randint(1, 100) <= passthrough_chance:
                        pt_damage = max(1, damage // 2)
                        self.hp -= pt_damage
                        self.set_damage_text(pt_damage)
                        loc_name = loc_data.get("card").get_current_data().get("Name", "Defense") if loc_data.get("card") else "Defense"
                        self.passthrough_messages.append(
                            f"{loc_name} passthrough hits {self.name} for {pt_damage} damage"
                        )

    def draw_health_bar(self, surface, pos):
        if self.hp > 0:
            bar_width, bar_height = 28, 4
            bar_x, bar_y = int(pos[0] - bar_width / 2), int(pos[1] - 15)
            # Dark outline
            pygame.draw.rect(surface, (10, 10, 20), (bar_x - 1, bar_y - 1, bar_width + 2, bar_height + 2))
            # Red background (missing health)
            pygame.draw.rect(surface, (120, 20, 20), (bar_x, bar_y, bar_width, bar_height))
            # Health fill - color shifts from green to yellow to red
            visual_hp = self.hp
            if self._pending_damage_anim:
                if not self._pending_damage_anim.done:
                    visual_hp = min(self.max_hp, self.hp + self._hp_visual_offset)
                else:
                    self._hp_visual_offset = 0
                    self._pending_damage_anim = None
            elif self._hp_visual_offset > 0 and pygame.time.get_ticks() < self._hp_visual_offset_until:
                visual_hp = min(self.max_hp, self.hp + self._hp_visual_offset)
            elif self._hp_visual_offset > 0:
                self._hp_visual_offset = 0
            hp_ratio = visual_hp / self.max_hp
            health_width = max(1, int(bar_width * hp_ratio))
            if hp_ratio > 0.5:
                r = int(255 * (1 - hp_ratio) * 2)
                g = 220
            else:
                r = 220
                g = int(220 * hp_ratio * 2)
            pygame.draw.rect(surface, (r, g, 30), (bar_x, bar_y, health_width, bar_height))

    def teleport(self, grid, new_row, new_col):
        grid.grid[self.position[0]][self.position[1]]["unit"] = None
        self.position = (new_row, new_col)
        grid.grid[new_row][new_col]["unit"] = self
        self.animating = False
        self.render_pos = None

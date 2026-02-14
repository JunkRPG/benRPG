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

        # Behavior tree: ordered list of behavior names for Allied units
        self.behavior_tree = self._init_behavior_tree(card_data)
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
            }

    # Behavior registry: defines available behaviors with labels and restrictions
    BEHAVIOR_REGISTRY = {
        "healing":        {"label": "Heal Allies",       "restrict_skill": "Healer"},
        "patrol":         {"label": "Patrol (Wander)"},
        "guard":          {"label": "Guard Position"},
        "recruit":        {"label": "Recruit Neutrals"},
        "follow_target":  {"label": "Follow Target",     "needs_target": "follow"},
        "attack_target":  {"label": "Attack Target",     "needs_target": "attack"},
        "attack_closest": {"label": "Attack Closest"},
        "attack_weakest": {"label": "Attack Weakest"},
        "flee":           {"label": "Flee from Enemies"},
        "graze":          {"label": "Graze (Recover HP)", "restrict_skill": "Mount"},
    }

    def _init_behavior_tree(self, card_data):
        """Initialize behavior tree from card data or build smart default."""
        # Runtime custom override (set by player via party screen, passed at deploy)
        custom_tree = card_data.get("custom_behavior_tree", None)
        if custom_tree and isinstance(custom_tree, list):
            return list(custom_tree)
        # Card's Default_Behavior_Tree (JSON string)
        default_str = card_data["data"].get("Default_Behavior_Tree", "")
        if default_str:
            try:
                tree = json.loads(default_str)
                if isinstance(tree, list) and len(tree) > 0:
                    return tree
            except (json.JSONDecodeError, TypeError):
                pass
        # Smart fallback based on unit properties
        default = []
        if card_data["data"].get("Special Skill") == "Healer" and int(card_data["data"].get("Heal_Amount", 0) or 0) > 0:
            default.append("healing")
        if card_data["data"].get("Special Skill") == "Mount":
            default.append("graze")
        default.append("attack_closest")
        return default

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

        # Healer: heal friendly units before taking other actions (non-Allied only;
        # Allied healers are handled by their behavior tree)
        if self.special_skill == "Healer" and self.heal_amount > 0 and self.allegiance != "Allied":
            heal_log = self._perform_healing(grid)
            log.extend(heal_log)

        if self.allegiance == "Hostile":
            # === Repair Boss: prioritize repairing enemy spawn locations ===
            if self.special_skill == "Repair" and self.repair_value > 0:
                damaged_locations = grid.get_damaged_spawn_locations()
                if damaged_locations:
                    # Find nearest damaged location
                    nearest_loc = min(damaged_locations, key=lambda x: grid.hex_distance(self.position, x[0]))
                    dist_to_loc = grid.hex_distance(self.position, nearest_loc[0])
                    if dist_to_loc <= 1:
                        # Adjacent — repair it
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
                            log.append(msg)
                            return log
                    else:
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
                                        log.append(f"{self.name} moves to repair {loc_name}")
                                        # Check if now adjacent after move
                                        new_dist = grid.hex_distance(self.position, nearest_loc[0])
                                        if new_dist <= 1:
                                            self.pending_attack = {
                                                "type": "repair",
                                                "target_pos": nearest_loc[0],
                                                "repair_value": self.repair_value
                                            }
                                    break
                            return log

            # === Aggro range check: skip attack if no targets in range ===
            player = grid.player
            distance_to_player = grid.hex_distance(self.position, player.position)

            if self.aggro_range > 0:
                # Check if any valid target is within aggro range
                targets_in_range = distance_to_player <= self.aggro_range
                if not targets_in_range:
                    allied_units = [u for u in grid.units if u.allegiance == "Allied" and u.hp > 0]
                    targets_in_range = any(grid.hex_distance(self.position, u.position) <= self.aggro_range for u in allied_units)
                if not targets_in_range:
                    return log  # No targets in aggro range — idle

            melee_possible_player = distance_to_player == 1
            projectile_possible_player = (self.projectile_damage > 0 and
                                          1 < distance_to_player <= self.projectile_range and
                                          grid.is_aligned(self.position, player.position, self.projectile_range) and
                                          grid.has_clear_line_of_sight(self.position, player.position))

            if melee_possible_player:
                damage = self.melee_damage
                # Trigger melee animation
                anim = None
                delay = 0
                if hasattr(grid, 'attack_anims'):
                    src = grid.get_hex_center(*self.position)
                    tgt = grid.get_hex_center(*player.position)
                    anim = grid.attack_anims.create_melee(src, tgt)
                    delay = grid.attack_anims.get_max_remaining_ms()
                actual_damage, blocked, shield_broken = player.take_damage(damage, self.position, grid)
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
                    # Only game over if ALL players are dead (multiplayer support)
                    all_players = grid.players if grid.players else [grid.player]
                    if all(p.hp <= 0 for p in all_players):
                        grid.game_over = True
                return log
            elif projectile_possible_player:
                damage = self.projectile_damage
                # Trigger projectile animation
                anim = None
                delay = 0
                if hasattr(grid, 'attack_anims'):
                    src = grid.get_hex_center(*self.position)
                    tgt = grid.get_hex_center(*player.position)
                    anim = grid.attack_anims.create_projectile(src, tgt)
                    delay = grid.attack_anims.get_max_remaining_ms()
                actual_damage, blocked, shield_broken = player.take_damage(damage, self.position, grid)
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
                allied_units = [u for u in grid.units if u.allegiance == "Allied" and u.hp > 0]
                allied_melee = [u for u in allied_units if grid.hex_distance(self.position, u.position) == 1]
                if allied_melee:
                    target = random.choice(allied_melee)
                    damage = self.melee_damage
                    # Trigger melee animation
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
                    # Trigger projectile animation
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
                    log.append(f"{self.name} attacked {target.name} with projectile for {damage} damage")
                    return log

                # Check for NPC spawn locations (churches) to attack
                npc_spawn_locations = grid.get_active_npc_spawn_locations()
                for loc_pos, loc_data in npc_spawn_locations:
                    distance_to_loc = grid.hex_distance(self.position, loc_pos)
                    # Check melee attack on church
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
                            log.append(msg)
                            return log
                    # Check projectile attack on church
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
                            log.append(msg)
                            return log

                path = grid.find_path(self.position, player.position)
                if path and len(path) > 1:
                    max_steps = min(self.movement, len(path) - 1)
                    for steps in range(max_steps, 0, -1):
                        new_pos = path[steps]
                        if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                            success, msg = grid.move_unit(self, *new_pos)
                            if success:
                                log.append(msg)
                                distance_after = grid.hex_distance(self.position, player.position)
                                if distance_after == 1:
                                    # Defer melee attack until after movement animation
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
                                    # Defer projectile attack until after movement animation
                                    self.pending_attack = {
                                        "target": player,
                                        "damage": self.projectile_damage,
                                        "type": "projectile",
                                        "is_player": True
                                    }
                            break

                # Boss ability: Summon Minion when no other action taken
                if not log and self.special_skill == "Summon Minion" and self.spawn_deck:
                    neighbors = grid.get_neighbors(*self.position)
                    empty = [p for p in neighbors if grid.grid[p[0]][p[1]]["unit"] is None]
                    if empty:
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
                                    log.append(f"{self.name} summoned {minion.name}!")
                        except Exception:
                            pass

        elif self.allegiance == "Allied":
            if self.recruit_cooldown > 0:
                self.recruit_cooldown -= 1

            # Quest-driven behavior overrides behavior tree
            if self.quest_target_position:
                hostile_units = [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0]
                use_rush = (self.quest_movement_priority == "rush" and hostile_units)
                if use_rush:
                    log = self._allied_rush_turn(grid, hostile_units)
                elif hostile_units:
                    log = self._allied_fight_turn(grid, hostile_units)
                else:
                    log = self._allied_idle_turn(grid)
            elif self.garrison_target_location:
                log = self._allied_idle_turn(grid)
            else:
                # Behavior tree execution
                for behavior in self.behavior_tree:
                    result = self._execute_behavior(behavior, grid)
                    if result is not None:
                        log.extend(result)
                        break

        elif self.allegiance == "Neutral":
            # Messenger NPC: approach player and deliver dialogue
            if self.special_skill == "Messenger" and self.dialogue_text and not self.dialogue_delivered:
                targets = [grid.player]
                if hasattr(grid, 'players') and grid.players:
                    targets = [p for p in grid.players if p.hp > 0]
                nearest_player = min(targets, key=lambda p: grid.hex_distance(self.position, p.position))
                dist = grid.hex_distance(self.position, nearest_player.position)

                if dist <= 1:
                    # Adjacent — trigger dialogue
                    self.pending_dialogue = {
                        "text": self.dialogue_text,
                        "speaker": self.name,
                        "gift_card_ids": list(self.dialogue_gift_cards)
                    }
                    self.dialogue_delivered = True
                    return log
                else:
                    # Pathfind toward nearest player
                    path = grid.find_path(self.position, nearest_player.position)
                    if path and len(path) > 1:
                        max_steps = min(self.movement, len(path) - 1)
                        for steps in range(max_steps, 0, -1):
                            new_pos = path[steps]
                            if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
                                if new_pos != nearest_player.position:
                                    success, msg = grid.move_unit(self, *new_pos)
                                    if success:
                                        log.append(f"{self.name} approaches")
                                        if grid.hex_distance(self.position, nearest_player.position) <= 1:
                                            self.pending_dialogue = {
                                                "text": self.dialogue_text,
                                                "speaker": self.name,
                                                "gift_card_ids": list(self.dialogue_gift_cards)
                                            }
                                            self.dialogue_delivered = True
                                break
                    return log

            # Wild mounts wander multiple hexes in a random direction
            elif (self.states == 2 and self.current_state == 1 and
                    self.special_skill == "Mount"):
                log = self._wild_mount_wander(grid)
            else:
                neighbors = grid.get_neighbors(*self.position)
                empty_neighbors = [pos for pos in neighbors if grid.grid[pos[0]][pos[1]]["unit"] is None]
                if empty_neighbors:
                    new_pos = random.choice(empty_neighbors)
                    success, msg = grid.move_unit(self, *new_pos)
                    if success:
                        log.append(msg)

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
        """Healer skill: heal the most damaged friendly unit in range."""
        log = []
        if self.heal_amount <= 0:
            return log

        # Build candidate list based on allegiance
        candidates = []
        if self.allegiance == "Hostile":
            for u in grid.units:
                if (u.allegiance == "Hostile" and u.hp > 0 and u.hp < u.max_hp
                        and u is not self and u.position
                        and grid.hex_distance(self.position, u.position) <= self.heal_range):
                    candidates.append(u)
        elif self.allegiance == "Allied":
            for u in grid.units:
                if (u.allegiance == "Allied" and u.hp > 0 and u.hp < u.max_hp
                        and u is not self and u.position
                        and grid.hex_distance(self.position, u.position) <= self.heal_range):
                    candidates.append(u)
            # Also consider healing player(s)
            players = grid.players if hasattr(grid, 'players') and grid.players else []
            if not players and hasattr(grid, 'player') and grid.player:
                players = [grid.player]
            for p in players:
                if (p.hp > 0 and p.hp < p.max_hp and p.position
                        and grid.hex_distance(self.position, p.position) <= self.heal_range):
                    candidates.append(p)

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

    def _behavior_healing(self, grid):
        """Heal the most damaged friendly unit in range."""
        if self.special_skill != "Healer" or self.heal_amount <= 0:
            return None
        result = self._perform_healing(grid)
        return result if result else None

    def _behavior_attack_closest(self, grid):
        """Chase and attack the nearest hostile unit."""
        hostiles = [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0 and u.position]
        if not hostiles:
            return None
        target = min(hostiles, key=lambda u: grid.hex_distance(self.position, u.position))
        return self._chase_and_attack(grid, target)

    def _behavior_attack_weakest(self, grid):
        """Chase and attack the lowest-HP hostile unit."""
        hostiles = [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0 and u.position]
        if not hostiles:
            return None
        target = min(hostiles, key=lambda u: u.hp)
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

        # Within 2 hexes — opportunistically attack adjacent enemies
        if distance <= 2:
            hostiles = [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0 and u.position]
            adjacent = [u for u in hostiles if grid.hex_distance(self.position, u.position) == 1]
            if adjacent:
                enemy = random.choice(adjacent)
                damage = self.melee_damage
                enemy.hp -= damage
                enemy.set_damage_text(damage)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks()
                return [f"{self.name} attacked {enemy.name} for {damage} damage"]
            return []  # Staying near target, nothing to do

        # Too far — move toward target
        path = grid.find_path(self.position, target_entity.position)
        if path and len(path) > 1:
            max_steps = min(self.movement, len(path) - 1)
            for steps in range(max_steps, 0, -1):
                new_pos = path[steps]
                if grid.grid[new_pos[0]][new_pos[1]]["unit"] is None:
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
        hostiles = [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0 and u.position]

        # Melee: attack a random adjacent enemy
        adjacent = [u for u in hostiles if grid.hex_distance(self.position, u.position) == 1]
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
            in_range = [u for u in hostiles if
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
        """Move away from the nearest hostile, don't attack."""
        hostiles = [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0 and u.position]
        if not hostiles:
            return None
        nearest = min(hostiles, key=lambda u: grid.hex_distance(self.position, u.position))
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
                target.allegiance = "Allied"
                target.behavior_tree = ["attack_closest"]
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
            self.allegiance = state_data["allegiance"]
            self.special_skill = state_data["special_skill"]
            self.heal_amount = state_data.get("heal_amount", self.heal_amount)
            self.heal_range = state_data.get("heal_range", self.heal_range)
            self.is_stubborn = state_data.get("is_stubborn", self.is_stubborn)
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

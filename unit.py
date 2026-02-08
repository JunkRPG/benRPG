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

        if self.states == 2 and "2nd_State_Name" in card_data["data"]:
            self.second_state = {
                "name": card_data["data"]["2nd_State_Name"],
                "hp": int(card_data["data"].get("2nd_State_Health", self.hp)),
                "movement": int(card_data["data"].get("2nd_State_Movement", self.movement)),
                "melee_damage": int(card_data["data"].get("2nd_State_Melee Damage", self.melee_damage)),
                "projectile_damage": int(card_data["data"].get("2nd_State_Projectile Damage", self.projectile_damage)),
                "projectile_range": int(card_data["data"].get("2nd_State_Projectile Range", self.projectile_range)),
                "allegiance": card_data["data"].get("2nd_State_Allegiance (Hostile, Neutral, Allied)", self.allegiance),
                "special_skill": card_data["data"].get("2nd_State_Special Skill", self.special_skill)
            }

    def take_turn(self, grid):
        log = []
        if not self.position:
            return log
        
        if self.allegiance == "Hostile":
            player = grid.player
            distance_to_player = grid.hex_distance(self.position, player.position)
            melee_possible_player = distance_to_player == 1
            projectile_possible_player = (self.projectile_damage > 0 and
                                          1 < distance_to_player <= self.projectile_range and
                                          grid.is_aligned(self.position, player.position, self.projectile_range) and
                                          grid.has_clear_line_of_sight(self.position, player.position))
            
            if melee_possible_player:
                damage = self.melee_damage
                player.hp -= damage
                player.set_damage_text(damage)  # Set damage feedback for player
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks()
                log.append(f"{self.name} attacked {player.class_name} for {damage} damage")
                if self.special_skill == "Life Drain":
                    heal = damage // 2
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
                player.hp -= damage
                player.set_damage_text(damage)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks()
                log.append(f"{self.name} attacked {player.class_name} with projectile for {damage} damage")
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
                    target.hp -= damage
                    target.set_damage_text(damage)  # Set damage feedback for allied unit
                    self.attack_flash = True
                    self.flash_start = pygame.time.get_ticks()
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
                    target.hp -= damage
                    target.set_damage_text(damage)
                    self.attack_flash = True
                    self.flash_start = pygame.time.get_ticks()
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
                            self.attack_flash = True
                            self.flash_start = pygame.time.get_ticks()
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
                            self.attack_flash = True
                            self.flash_start = pygame.time.get_ticks()
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
            hostile_units = [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0]

            # Determine behavior based on quest target and movement priority
            use_rush = (self.quest_target_position and
                        self.quest_movement_priority == "rush" and
                        hostile_units)

            if use_rush:
                # Rush mode: prioritize reaching destination, only fight adjacent/in-range threats
                log = self._allied_rush_turn(grid, hostile_units)
            elif hostile_units:
                # Fight first (default combat): chase and attack enemies
                log = self._allied_fight_turn(grid, hostile_units)
            else:
                # No enemies: move toward quest target, garrison, or idle
                log = self._allied_idle_turn(grid)

        elif self.allegiance == "Neutral":
            neighbors = grid.get_neighbors(*self.position)
            empty_neighbors = [pos for pos in neighbors if grid.grid[pos[0]][pos[1]]["unit"] is None]
            if empty_neighbors:
                new_pos = random.choice(empty_neighbors)
                success, msg = grid.move_unit(self, *new_pos)
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

    def execute_pending_attack(self, grid):
        """Execute a deferred attack after movement animation completes.
        Returns list of log entries."""
        if not self.pending_attack:
            return []

        attack = self.pending_attack
        self.pending_attack = None

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

        target.hp -= damage
        target.set_damage_text(damage)
        self.attack_flash = True
        self.flash_start = pygame.time.get_ticks()

        log = []
        if is_player:
            target_name = target.class_name
        else:
            target_name = target.name

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

    def set_damage_text(self, damage):
        """Set the damage text and timestamp when damage is taken."""
        self.damage_text = f"-{damage}"
        self.damage_time = pygame.time.get_ticks()

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

                # Use cached range if available, otherwise calculate
                cache_key = "_cached_range"
                cached = defense.get(cache_key)
                if cached is None:
                    cached = grid.calculate_range(
                        pos, defense["range_distance"], defense["range_type"],
                        defense.get("include_position", False), defense.get("exclude_adjacent", False)
                    )
                    defense[cache_key] = cached

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
            bar_width, bar_height = 20, 5
            bar_x, bar_y = int(pos[0] - bar_width / 2), int(pos[1] - 15)
            pygame.draw.rect(surface, (255, 0, 0), (bar_x, bar_y, bar_width, bar_height))
            health_width = int(bar_width * (self.hp / self.max_hp))
            pygame.draw.rect(surface, (0, 255, 0), (bar_x, bar_y, health_width, bar_height))

    def teleport(self, grid, new_row, new_col):
        grid.grid[self.position[0]][self.position[1]]["unit"] = None
        self.position = (new_row, new_col)
        grid.grid[new_row][new_col]["unit"] = self
        self.animating = False
        self.render_pos = None

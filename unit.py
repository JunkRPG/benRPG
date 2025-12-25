import pygame
import math
import random

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
                if player.hp <= 0:
                    grid.game_over = True  # Signal game over
                return log
            elif projectile_possible_player:
                damage = self.projectile_damage
                player.hp -= damage
                player.set_damage_text(damage)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks()
                log.append(f"{self.name} attacked {player.class_name} with projectile for {damage} damage")
                if player.hp <= 0:
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
                                    damage = self.melee_damage
                                    player.hp -= damage
                                    player.set_damage_text(damage)
                                    self.attack_flash = True
                                    self.flash_start = pygame.time.get_ticks()
                                    log.append(f"{self.name} attacked {player.class_name} for {damage} damage")
                                    if player.hp <= 0:
                                        grid.game_over = True
                                elif (self.projectile_damage > 0 and
                                      1 < distance_after <= self.projectile_range and
                                      grid.is_aligned(self.position, player.position, self.projectile_range) and
                                      grid.has_clear_line_of_sight(self.position, player.position)):
                                    damage = self.projectile_damage
                                    player.hp -= damage
                                    player.set_damage_text(damage)
                                    self.attack_flash = True
                                    self.flash_start = pygame.time.get_ticks()
                                    log.append(f"{self.name} attacked {player.class_name} with projectile for {damage} damage")
                                    if player.hp <= 0:
                                        grid.game_over = True
                            break
        
        elif self.allegiance == "Allied":
            hostile_units = [u for u in grid.units if u.allegiance == "Hostile" and u.hp > 0]
            if hostile_units:
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
                    target.set_damage_text(damage)  # Set damage feedback for hostile unit
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
                                    damage = self.melee_damage
                                    target.hp -= damage
                                    target.set_damage_text(damage)
                                    self.attack_flash = True
                                    self.flash_start = pygame.time.get_ticks()
                                    log.append(f"{self.name} attacked {target.name} for {damage} damage")
                                elif (self.projectile_damage > 0 and
                                      1 < distance_after <= self.projectile_range and
                                      grid.is_aligned(self.position, target.position, self.projectile_range) and
                                      grid.has_clear_line_of_sight(self.position, target.position)):
                                    damage = self.projectile_damage
                                    target.hp -= damage
                                    target.set_damage_text(damage)
                                    self.attack_flash = True
                                    self.flash_start = pygame.time.get_ticks()
                                    log.append(f"{self.name} attacked {target.name} with projectile for {damage} damage")
                            break
        
        elif self.allegiance == "Neutral":
            neighbors = grid.get_neighbors(*self.position)
            empty_neighbors = [pos for pos in neighbors if grid.grid[pos[0]][pos[1]]["unit"] is None]
            if empty_neighbors:
                new_pos = random.choice(empty_neighbors)
                success, msg = grid.move_unit(self, *new_pos)
                if success:
                    log.append(msg)
        
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
        self.animating = True
        old_x, old_y = grid.get_hex_center(*self.position)
        new_x, new_y = grid.get_hex_center(new_row, new_col)
        self.render_pos = (old_x, old_y)
        grid.grid[self.position[0]][self.position[1]]["unit"] = None
        grid.grid[new_row][new_col]["unit"] = self
        self.position = (new_row, new_col)

    def update_animation(self, grid):  # Add grid parameter
        if self.animating and self.render_pos:
            target_x, target_y = grid.get_hex_center(*self.position)
            dx = target_x - self.render_pos[0]
            dy = target_y - self.render_pos[1]
            dist = math.sqrt(dx**2 + dy**2)
            if dist <= MOVE_SPEED:
                self.render_pos = None
                self.animating = False
            else:
                move_x = dx / dist * MOVE_SPEED
                move_y = dy / dist * MOVE_SPEED
                self.render_pos = (self.render_pos[0] + move_x, self.render_pos[1] + move_y)
        if self.attack_flash and pygame.time.get_ticks() - self.flash_start > ATTACK_FLASH_DURATION:
            self.attack_flash = False
        if self.damage_text and pygame.time.get_ticks() - self.damage_time > DAMAGE_TEXT_DURATION:
            self.damage_text = None  # Clear damage text after duration

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

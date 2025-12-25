import pygame
import os
import math

# Character classes
CHARACTER_CLASSES = {
    "Ranger": {"hp": 50, "movement": 5, "projectile_range": 5, "attacks": {"Sling": 8, "Punch": 4}, "special_attack": "Multi-target Projectile"},
    "Warrior": {"hp": 100, "movement": 4, "projectile_range": 4, "attacks": {"Throw Rock": 6, "Kick": 6}, "special_attack": "Double Attack"},
    "Tank": {"hp": 150, "movement": 3, "projectile_range": 3, "attacks": {"Spit": 4, "Head-butt": 8}, "special_attack": "Spin Punch"}
}

# Animation constants
MOVE_SPEED = 5
ATTACK_FLASH_DURATION = 500
DAMAGE_TEXT_DURATION = 1000  # 1 second

class Player:
    def __init__(self, class_name):
        stats = CHARACTER_CLASSES[class_name]
        self.class_name = class_name
        self.hp = stats["hp"]
        self.max_hp = stats["hp"]
        self.movement = stats["movement"]
        self.projectile_range = stats["projectile_range"]
        self.attacks = {
            "projectile": {"name": list(stats["attacks"].keys())[0], "damage": list(stats["attacks"].values())[0]},
            "melee": {"name": list(stats["attacks"].keys())[1], "damage": list(stats["attacks"].values())[1]}
        }
        self.special_attack = stats["special_attack"]
        self.movement_used = False
        self.action_used = False
        self.position = (0, 0)
        self.animating = False
        self.render_pos = None
        self.attack_flash = False
        self.flash_start = 0
        self.inventory = []
        self.melee_weapon = None
        self.projectile_weapon = None
        self.damage_text = None
        self.damage_time = 0
        try:
            self.image = pygame.image.load(os.path.join(os.path.dirname(__file__), "images", "player.png")).convert_alpha()
        except FileNotFoundError:
            print("Player image not found, using default circle")
            self.image = None
        self.image_scale_factor = 1.2

    def attack(self, enemy, attack_name, grid):
        if not self.action_used:
            if attack_name == self.attacks["projectile"]["name"]:
                damage = self.attacks["projectile"]["damage"]
                max_range = self.projectile_range
                distance = grid.hex_distance(self.position, enemy.position)
                if (1 < distance <= max_range and 
                    grid.is_aligned(self.position, enemy.position, max_range) and 
                    grid.has_clear_line_of_sight(self.position, enemy.position)):
                    enemy.hp -= damage
                    enemy.set_damage_text(damage)  # Set damage feedback for enemy
                    self.action_used = True
                    self.attack_flash = True
                    self.flash_start = pygame.time.get_ticks()
                    return f"{self.class_name} used {attack_name} on {enemy.name} for {damage} damage", enemy.hp <= 0
            elif attack_name == self.attacks["melee"]["name"]:
                damage = self.attacks["melee"]["damage"]
                distance = grid.hex_distance(self.position, enemy.position)
                if distance == 1:
                    enemy.hp -= damage
                    enemy.set_damage_text(damage)
                    self.action_used = True
                    self.attack_flash = True
                    self.flash_start = pygame.time.get_ticks()
                    return f"{self.class_name} used {attack_name} on {enemy.name} for {damage} damage", enemy.hp <= 0
        return "", False

    def equip_weapon(self, weapon_card):
        weapon_data = weapon_card.get_current_data()
        weapon_type = weapon_data.get("Type")
        if weapon_type == "Melee" and "Melee Damage" in weapon_data:
            try:
                damage = int(weapon_data["Melee Damage"])
                self.melee_weapon = weapon_card
                self.attacks["melee"] = {"name": weapon_data["Name"], "damage": damage}
            except ValueError:
                print(f"Error: Invalid 'Melee Damage' for {weapon_data.get('Name', 'Unknown')}")
        elif weapon_type == "Projectile" and "Projectile Damage" in weapon_data:
            try:
                damage = int(weapon_data["Projectile Damage"])
                self.projectile_weapon = weapon_card
                self.attacks["projectile"] = {"name": weapon_data["Name"], "damage": damage}
            except ValueError:
                print(f"Error: Invalid 'Projectile Damage' for {weapon_data.get('Name', 'Unknown')}")

    def get_stats(self):
        attacks_str = ', '.join([f"{attack['name']} ({attack['damage']})" for attack in self.attacks.values()])
        melee = self.melee_weapon.get_current_data().get("Name", "None") if self.melee_weapon else "None"
        proj = self.projectile_weapon.get_current_data().get("Name", "None") if self.projectile_weapon else "None"
        return (f"Class: {self.class_name}\nHP: {self.hp}/{self.max_hp}\nMovement: {self.movement}\nRange: {self.projectile_range}\n"
                f"Attacks: {attacks_str}\nSpecial: {self.special_attack}\nMelee Weapon: {melee}\nProjectile Weapon: {proj}")

    def set_damage_text(self, damage):
        """Set the damage text and timestamp when damage is taken."""
        self.damage_text = f"-{damage}"
        self.damage_time = pygame.time.get_ticks()

    def animate_move(self, grid, new_row, new_col):
        if not self.animating:
            self.animating = True
            old_x, old_y = grid.get_hex_center(*self.position)
            self.render_pos = (old_x, old_y)
            grid.grid[self.position[0]][self.position[1]]["unit"] = None
            grid.grid[new_row][new_col]["unit"] = self
            self.position = (new_row, new_col)

    def update_animation(self, grid):
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
            self.damage_text = None

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
        self.animating = False  # Ensure no animation
        self.render_pos = None

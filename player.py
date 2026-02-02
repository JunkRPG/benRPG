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
        # Double Attack mode (Warrior special) - allows both melee and projectile in one turn
        self.double_attack_active = False
        self.double_attack_melee_used = False
        self.double_attack_projectile_used = False
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
        # Path-based animation
        self.animation_path = []  # List of hex positions to animate through
        self.animation_path_index = 0  # Current target in the path
        # Skill system attributes
        self.skills = []                # Learned skill cards (in state 2)
        self.active_skill_slots = 3     # Max equipped active skills
        self.equipped_skills = []       # Currently equipped Attack/Buff skills
        self.skill_cooldowns = {}       # {"skill_name": turns_remaining}
        try:
            self.image = pygame.image.load(os.path.join(os.path.dirname(__file__), "images", "player.png")).convert_alpha()
        except FileNotFoundError:
            print("Player image not found, using default circle")
            self.image = None
        self.image_scale_factor = 1.2

    def attack(self, enemy, attack_name, grid):
        is_projectile = attack_name == self.attacks["projectile"]["name"]
        is_melee = attack_name == self.attacks["melee"]["name"]

        # Check if this attack type can be used
        if self.double_attack_active:
            # In Double Attack mode, check type-specific flags
            if is_projectile and self.double_attack_projectile_used:
                return "", False
            if is_melee and self.double_attack_melee_used:
                return "", False
        else:
            # Normal mode - check action_used
            if self.action_used:
                return "", False

        if is_projectile:
            damage = self.attacks["projectile"]["damage"]
            max_range = self.projectile_range
            distance = grid.hex_distance(self.position, enemy.position)
            if (1 < distance <= max_range and
                grid.is_aligned(self.position, enemy.position, max_range) and
                grid.has_clear_line_of_sight(self.position, enemy.position)):
                enemy.hp -= damage
                enemy.set_damage_text(damage)
                self._mark_attack_used(is_projectile=True)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks()
                return f"{self.class_name} used {attack_name} on {enemy.name} for {damage} damage", enemy.hp <= 0
        elif is_melee:
            damage = self.attacks["melee"]["damage"]
            distance = grid.hex_distance(self.position, enemy.position)
            if distance == 1:
                enemy.hp -= damage
                enemy.set_damage_text(damage)
                self._mark_attack_used(is_projectile=False)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks()
                return f"{self.class_name} used {attack_name} on {enemy.name} for {damage} damage", enemy.hp <= 0
        return "", False

    def _mark_attack_used(self, is_projectile):
        """Mark an attack as used, handling Double Attack mode."""
        if self.double_attack_active:
            if is_projectile:
                self.double_attack_projectile_used = True
            else:
                self.double_attack_melee_used = True
            # If both attacks used, mark action as fully used
            if self.double_attack_melee_used and self.double_attack_projectile_used:
                self.action_used = True
        else:
            self.action_used = True

    def reset_double_attack(self):
        """Reset Double Attack mode at end of turn."""
        self.double_attack_active = False
        self.double_attack_melee_used = False
        self.double_attack_projectile_used = False

    def use_special_attack(self, target, grid):
        """
        Execute the player's class-specific special attack.

        Args:
            target: Target unit for targeted specials (can be None for AoE)
            grid: The HexGrid instance

        Returns:
            tuple: (message, list of defeated units)
        """
        if self.special_attack == "Multi-target Projectile":
            if self.action_used:
                return "Action already used this turn", []
            return self._multi_target_projectile(target, grid)
        elif self.special_attack == "Double Attack":
            # Double Attack is a mode activation, not a direct attack
            return self._activate_double_attack()
        elif self.special_attack == "Spin Punch":
            if self.action_used:
                return "Action already used this turn", []
            return self._spin_punch(grid)
        else:
            return f"Unknown special attack: {self.special_attack}", []

    def _multi_target_projectile(self, primary_target, grid):
        """
        Ranger special: Piercing shot that hits all enemies along a line
        in the direction of the target (up to 3 enemies total).
        """
        if not primary_target:
            return "Select a target for Multi-target Projectile", []

        # Check if primary target is in range and aligned (on a hex line)
        distance = grid.hex_distance(self.position, primary_target.position)
        if distance < 1 or distance > self.projectile_range:
            return "Target out of range", []
        if not grid.is_aligned(self.position, primary_target.position, self.projectile_range):
            return "Target must be in a straight line", []

        # Get the full line in the direction of the target
        player_row, player_col = self.position
        target_row, target_col = primary_target.position

        # Find which direction the target is in and get the full line
        from hexgrid import DIRECTIONS
        attack_line = []
        for direction in DIRECTIONS:
            line = grid.get_line(player_row, player_col, direction, self.projectile_range)
            if (target_row, target_col) in line:
                attack_line = line
                break

        if not attack_line:
            return "Cannot determine attack line", []

        damage = self.attacks["projectile"]["damage"]
        messages = []
        defeated = []
        hits = 0
        max_hits = 3

        # Hit all enemies along the line (up to 3)
        for hex_pos in attack_line:
            if hits >= max_hits:
                break
            row, col = hex_pos
            if 0 <= row < grid.rows and 0 <= col < grid.cols:
                unit = grid.grid[row][col].get("unit")
                if unit and hasattr(unit, 'allegiance') and unit.allegiance == "Hostile" and unit.hp > 0:
                    unit.hp -= damage
                    unit.set_damage_text(damage)
                    unit.attack_flash = True
                    unit.flash_start = pygame.time.get_ticks()
                    messages.append(f"{unit.name} ({damage} dmg)")
                    hits += 1
                    if unit.hp <= 0:
                        defeated.append(unit)

        if hits == 0:
            return "No enemies hit", []

        self.action_used = True
        self.attack_flash = True
        self.flash_start = pygame.time.get_ticks()

        result = f"{self.class_name} used Multi-target Projectile! Pierced through: {', '.join(messages)}"
        return result, defeated

    def _activate_double_attack(self):
        """
        Warrior special: Activates Double Attack mode, allowing both a melee
        attack AND a projectile attack this turn.
        """
        if self.double_attack_active:
            return "Double Attack already active", []

        if self.action_used:
            return "Action already used this turn", []

        self.double_attack_active = True
        self.double_attack_melee_used = False
        self.double_attack_projectile_used = False

        return f"{self.class_name} activated Double Attack! Can use both melee and projectile this turn.", []

    def _double_attack(self, target, grid):
        """Legacy method - use _activate_double_attack instead."""
        return self._activate_double_attack()

    def _spin_punch(self, grid):
        """
        Tank special: Hit all adjacent enemies with melee damage.
        No target selection needed - automatically hits all adjacent hostiles.
        """
        damage = self.attacks["melee"]["damage"]
        messages = []
        defeated = []

        # Get all adjacent hexes (distance 1)
        adjacent_hexes = grid.get_hexes_at_distance(self.position, 1)

        targets_hit = 0
        for hex_pos in adjacent_hexes:
            row, col = hex_pos
            if 0 <= row < grid.rows and 0 <= col < grid.cols:
                unit = grid.grid[row][col].get("unit")
                if unit and hasattr(unit, 'allegiance') and unit.allegiance == "Hostile" and unit.hp > 0:
                    unit.hp -= damage
                    unit.set_damage_text(damage)
                    unit.attack_flash = True
                    unit.flash_start = pygame.time.get_ticks()
                    targets_hit += 1
                    messages.append(f"{unit.name} ({damage} dmg)")
                    if unit.hp <= 0:
                        defeated.append(unit)

        if targets_hit == 0:
            return "No adjacent enemies to hit with Spin Punch", []

        self.action_used = True
        self.attack_flash = True
        self.flash_start = pygame.time.get_ticks()

        result = f"{self.class_name} used Spin Punch! Hit: {', '.join(messages)}"
        return result, defeated

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
        """Start path-based movement animation from current position to new position."""
        if not self.animating:
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

    # ===== SKILL SYSTEM METHODS =====

    def learn_skill(self, card):
        """Transform a Document card into a Skill card, add to skills, remove from inventory."""
        if card in self.inventory:
            self.inventory.remove(card)
        # Start flip animation and toggle state to 2
        card.start_flip_animation()
        card.current_state = 2
        self.skills.append(card)
        skill_name = card.get_current_data().get("Name", "Unknown Skill")
        return f"Learned skill: {skill_name}"

    def equip_skill(self, card):
        """Add an active skill (Attack/Buff_Heal) to equipped slots."""
        if card not in self.skills:
            return "Skill not learned"
        skill_data = card.get_current_data()
        skill_type = skill_data.get("Skill_Type", "")
        if skill_type == "Passive":
            return "Passive skills are always active"
        if len(self.equipped_skills) >= self.active_skill_slots:
            return "No available skill slots"
        if card in self.equipped_skills:
            return "Skill already equipped"
        self.equipped_skills.append(card)
        skill_name = skill_data.get("Name", "Unknown")
        return f"Equipped skill: {skill_name}"

    def unequip_skill(self, card):
        """Remove skill from equipped slots."""
        if card in self.equipped_skills:
            self.equipped_skills.remove(card)
            skill_name = card.get_current_data().get("Name", "Unknown")
            return f"Unequipped skill: {skill_name}"
        return "Skill not equipped"

    def use_skill(self, card, target, grid):
        """Execute an Attack or Buff_Heal skill."""
        if self.action_used:
            return "", False

        skill_data = card.get_current_data()
        skill_name = skill_data.get("Name", "Unknown Skill")
        skill_type = skill_data.get("Skill_Type", "")

        # Check cooldown
        if self.skill_cooldowns.get(skill_name, 0) > 0:
            return f"{skill_name} is on cooldown ({self.skill_cooldowns[skill_name]} turns)", False

        if skill_type == "Attack":
            return self._use_attack_skill(card, target, grid)
        elif skill_type == "Buff_Heal":
            return self._use_buff_heal_skill(card, target, grid)

        return "", False

    def _use_attack_skill(self, card, target, grid):
        """Execute an attack skill on target."""
        skill_data = card.get_current_data()
        skill_name = skill_data.get("Name", "Unknown")
        try:
            damage = int(skill_data.get("Damage", 0))
            attack_range = int(skill_data.get("Attack_Range", 1))
            cooldown = int(skill_data.get("Cooldown", 0))
        except ValueError:
            return "Invalid skill data", False

        attack_type = skill_data.get("Attack_Type", "Melee")
        distance = grid.hex_distance(self.position, target.position)

        # Check range based on attack type
        if attack_type == "Melee" and distance != 1:
            return "Target out of melee range", False
        elif attack_type == "Projectile":
            if distance > attack_range or distance < 1:
                return "Target out of range", False
            if not grid.has_clear_line_of_sight(self.position, target.position):
                return "No line of sight", False
        elif attack_type == "AOE":
            if distance > attack_range:
                return "Target out of range", False

        # Apply damage
        target.hp -= damage
        target.set_damage_text(damage)
        self.action_used = True
        self.attack_flash = True
        self.flash_start = pygame.time.get_ticks()

        # Set cooldown
        if cooldown > 0:
            self.skill_cooldowns[skill_name] = cooldown

        killed = target.hp <= 0
        return f"{self.class_name} used {skill_name} on {target.name} for {damage} damage", killed

    def _use_buff_heal_skill(self, card, target, grid):
        """Execute a buff/heal skill."""
        skill_data = card.get_current_data()
        skill_name = skill_data.get("Name", "Unknown")
        try:
            effect_value = int(skill_data.get("Effect_Value", 0))
            cooldown = int(skill_data.get("Cooldown", 0))
        except ValueError:
            return "Invalid skill data", False

        effect_type = skill_data.get("Effect_Type", "Heal")
        target_type = skill_data.get("Target", "Self")

        # Determine actual target
        if target_type == "Self":
            actual_target = self
        else:
            actual_target = target

        # Apply effect
        message = ""
        if effect_type == "Heal":
            old_hp = actual_target.hp
            if hasattr(actual_target, 'max_hp'):
                actual_target.hp = min(actual_target.max_hp, actual_target.hp + effect_value)
            else:
                actual_target.hp += effect_value
            healed = actual_target.hp - old_hp
            target_name = "self" if actual_target == self else actual_target.name
            message = f"{self.class_name} healed {target_name} for {healed} HP"
        elif effect_type == "Buff_Attack":
            # Temporarily increase attack damage (would need buff tracking system)
            message = f"{self.class_name} buffed attack by {effect_value}"
        elif effect_type == "Buff_Defense":
            message = f"{self.class_name} buffed defense by {effect_value}"

        self.action_used = True

        # Set cooldown
        if cooldown > 0:
            self.skill_cooldowns[skill_name] = cooldown

        return message, False

    def apply_passive_skills(self, grid, trigger):
        """Apply all passive skills with the matching trigger. Returns list of log messages."""
        messages = []
        for skill in self.skills:
            skill_data = skill.get_current_data()
            skill_type = skill_data.get("Skill_Type", "")

            if skill_type != "Passive":
                continue

            skill_trigger = skill_data.get("Trigger", "")
            if skill_trigger != trigger:
                continue

            effect_type = skill_data.get("Effect_Type", "")
            try:
                effect_value = int(skill_data.get("Effect_Value", 0))
                effect_range = int(skill_data.get("Range", 1))
            except ValueError:
                continue

            skill_name = skill_data.get("Name", "Unknown")

            if effect_type == "Heal_Adjacent":
                # Heal adjacent allies and neutrals
                neighbors = grid.get_neighbors(*self.position)
                for neighbor in neighbors:
                    row, col = neighbor
                    if 0 <= row < grid.rows and 0 <= col < grid.cols:
                        unit = grid.grid[row][col].get("unit")
                        if unit and hasattr(unit, 'allegiance'):
                            if unit.allegiance in ["Allied", "Neutral"]:
                                old_hp = unit.hp
                                unit.hp = min(unit.max_hp, unit.hp + effect_value)
                                healed = unit.hp - old_hp
                                if healed > 0:
                                    messages.append(f"{skill_name}: Healed {unit.name} for {healed} HP")
            elif effect_type == "Heal":
                # Heal self
                old_hp = self.hp
                self.hp = min(self.max_hp, self.hp + effect_value)
                healed = self.hp - old_hp
                if healed > 0:
                    messages.append(f"{skill_name}: Healed self for {healed} HP")

        return messages

    def tick_cooldowns(self):
        """Reduce all skill cooldowns by 1 at end of turn."""
        for skill_name in list(self.skill_cooldowns.keys()):
            self.skill_cooldowns[skill_name] -= 1
            if self.skill_cooldowns[skill_name] <= 0:
                del self.skill_cooldowns[skill_name]

    def get_passive_skills(self):
        """Return list of learned passive skills."""
        return [s for s in self.skills if s.get_current_data().get("Skill_Type") == "Passive"]

    def get_active_skills(self):
        """Return list of learned active skills (Attack and Buff_Heal)."""
        return [s for s in self.skills if s.get_current_data().get("Skill_Type") in ["Attack", "Buff_Heal"]]

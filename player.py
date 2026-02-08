import pygame
import os
import math
import random

# Character classes
CHARACTER_CLASSES = {
    "Ranger": {
        "hp": 50, "movement": 5, "projectile_range": 5,
        "attacks": {"Sling": 8, "Punch": 4},
        "special_attack": "Piercing Shot",
        "starting_kit": [
            {"card_id": "starter_ranger_bow", "state": 1},
            {"card_id": "starter_ranger_bowstring", "state": 1},
            {"card_id": "starter_ranger_curved_branch", "state": 1},
            {"card_id": "win_guide", "state": 1}
        ]
    },
    "Warrior": {
        "hp": 100, "movement": 4, "projectile_range": 4,
        "attacks": {"Throw Rock": 6, "Kick": 6},
        "special_attack": "Dual Strike",
        "starting_kit": [
            {"card_id": "starter_warrior_combat_bow", "state": 1},
            {"card_id": "starter_warrior_bowstring", "state": 1},
            {"card_id": "starter_warrior_metal_wraps", "state": 1},
            {"card_id": "starter_warrior_arrows", "state": 2},
            {"card_id": "win_guide", "state": 1}
        ]
    },
    "Tank": {
        "hp": 150, "movement": 3, "projectile_range": 3,
        "attacks": {"Spit": 4, "Head-butt": 8},
        "special_attack": "Spin Punch",
        "starting_kit": [
            {"card_id": "starter_tank_sledgehammer_plans", "state": 1},
            {"card_id": "starter_tank_hammer_head", "state": 1},
            {"card_id": "starter_tank_branch", "state": 1},
            {"card_id": "win_guide", "state": 1}
        ]
    }
}

# Animation constants
MOVE_SPEED = 5
ATTACK_FLASH_DURATION = 500
DAMAGE_TEXT_DURATION = 1000  # 1 second

class Player:
    def __init__(self, class_name):
        stats = CHARACTER_CLASSES[class_name]
        self.class_name = class_name
        self.name = ""  # Set during character creation; defaults to class_name
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
        # Warrior passive: always gets 2 attacks per turn (any combination of melee/projectile)
        self.warrior_attacks_remaining = 2 if class_name == "Warrior" else 0
        self.double_attack_active = (class_name == "Warrior")  # Always active for Warriors
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
        # Tool equipment slot (multi-slot system with tool belt support)
        self.equipped_tool = None       # Legacy: single equipped tool (kept for backwards compatibility)
        self.tool_slots = 1             # Number of available tool slots (expandable via tool belt)
        self.equipped_tools = []        # List of equipped tool cards (multi-slot)
        self.equipped_accessory = None  # Tool belt or other accessory in accessory slot

        # Range properties (set by equipped projectile weapon)
        self.projectile_range_type = "line_of_sight"  # Pattern: line_of_sight, area_effect, echo, perimeter
        self.projectile_include_pos = False           # Include caster's hex in range
        self.projectile_exclude_adj = False           # Exclude adjacent hexes (for sniper-type weapons)
        # Ranger passive: piercing projectile shots go through units
        self.piercing_projectile = (class_name == "Ranger")

        # Multiplayer attributes
        self.player_number = 1  # 1 or 2 (for multiplayer mode)
        self.player_color = (0, 200, 0)  # Default green, customized per player
        self.party = []  # This player's recruited allied NPCs (for multiplayer independence)
        try:
            self.image = pygame.image.load(os.path.join(os.path.dirname(__file__), "images", "player.png")).convert_alpha()
        except FileNotFoundError:
            print("Player image not found, using default circle")
            self.image = None
        self.image_scale_factor = 1.2

    def get_effective_movement(self, party):
        """Return movement, boosted by Mount_Movement if a Mount is in the party."""
        for card in party:
            data = card.get_current_data()
            if data.get("Special Skill") == "Mount":
                mount_movement = int(data.get("Mount_Movement", 10) or 10)
                return max(self.movement, mount_movement)
        return self.movement

    def get_mount_melee_bonus(self, party):
        """Return bonus melee damage from a Mount in the party (e.g. War Bear)."""
        for card in party:
            data = card.get_current_data()
            if data.get("Special Skill") == "Mount":
                return int(data.get("Mount_Melee_Damage", 0) or 0)
        return 0

    def get_mount_range_bonus(self, party):
        """Return bonus projectile range from a Mount in the party (e.g. Giant Hawk)."""
        for card in party:
            data = card.get_current_data()
            if data.get("Special Skill") == "Mount":
                return int(data.get("Mount_Projectile_Range", 0) or 0)
        return 0

    def get_effective_projectile_range(self, party):
        """Return projectile range including mount bonus."""
        return self.projectile_range + self.get_mount_range_bonus(party)

    def attack(self, enemy, attack_name, grid, party=None):
        is_projectile = attack_name == self.attacks["projectile"]["name"]
        is_melee = attack_name == self.attacks["melee"]["name"]
        if party is None:
            party = []

        # Check if this attack type can be used
        if self.double_attack_active:
            # Warrior passive: check attacks remaining counter
            if self.warrior_attacks_remaining <= 0:
                return "", False
        else:
            # Normal mode - check action_used
            if self.action_used:
                return "", False

        if is_projectile:
            return self._execute_projectile_attack(enemy, attack_name, grid, party)
        elif is_melee:
            damage = self.attacks["melee"]["damage"] + self.get_mount_melee_bonus(party)
            distance = grid.hex_distance(self.position, enemy.position)
            if distance == 1:
                enemy.hp -= damage
                enemy.set_damage_text(damage)
                self._mark_attack_used(is_projectile=False)
                self.attack_flash = True
                self.flash_start = pygame.time.get_ticks()
                return f"{self.class_name} used {attack_name} on {enemy.name} for {damage} damage", enemy.hp <= 0
        return "", False

    def _execute_projectile_attack(self, enemy, attack_name, grid, party=None):
        """Execute a projectile attack, handling ammunition requirements.

        For piercing projectile (Ranger), returns (message, list_of_hit_units) where
        each entry is (unit, damage, defeated). For non-piercing, returns (message, defeated_bool).
        """
        if party is None:
            party = []
        weapon_data = self.projectile_weapon.get_current_data() if self.projectile_weapon else {}
        attack_info = self.attacks.get("projectile", {})
        requires_ammo = attack_info.get("requires_ammo", False)

        # Get ammunition if required
        ammo_card = None
        ammo_data = {}
        damage = attack_info.get("damage", 0)

        if requires_ammo:
            # Find equipped ammunition - check multi-slot system first, then legacy single slot
            ammo_card = self._get_equipped_ammunition()

            if not ammo_card:
                return "No ammunition equipped - cannot fire!", False

            ammo_data = ammo_card.get_current_data()

            # Check ammo compatibility with weapon
            compatible_weapons = ammo_data.get("Compatible_Weapons", "")
            weapon_name = weapon_data.get("Name", "")

            if compatible_weapons:
                compatible_list = [w.strip() for w in compatible_weapons.split(",")]
                if weapon_name not in compatible_list:
                    return f"{ammo_data.get('Name', 'Ammunition')} not compatible with {weapon_name}", False

            # ALL damage comes from ammunition
            damage = int(ammo_data.get("Ammo_Damage", 0))

        # Calculate effective range with mount bonus
        effective_range = self.projectile_range + self.get_mount_range_bonus(party)

        # Use the unified range system to check if target is valid
        if not self._is_valid_projectile_target(enemy.position, grid, effective_range):
            # Provide more specific error messages
            distance = grid.hex_distance(self.position, enemy.position)
            if self.projectile_exclude_adj and distance == 1:
                return "Target too close for this weapon", False
            elif distance < 2 and self.projectile_range_type == "line_of_sight":
                return "Target too close for projectile attack", False
            elif distance > effective_range:
                return "Target out of range", False
            else:
                return "Target not in valid range pattern", False

        # Piercing projectile: hit all entities along the line up to and including the target
        if self.piercing_projectile and self.projectile_range_type == "line_of_sight":
            return self._execute_piercing_attack(enemy, attack_name, damage, ammo_card, ammo_data, requires_ammo, grid)

        # Standard single-target attack
        enemy.hp -= damage
        enemy.set_damage_text(damage)
        self._mark_attack_used(is_projectile=True)
        self.attack_flash = True
        self.flash_start = pygame.time.get_ticks()

        base_msg = f"{self.class_name} used {attack_name} on {enemy.name} for {damage} damage"
        killed = enemy.hp <= 0

        # Handle ammunition runout after successful attack
        if requires_ammo and ammo_card:
            runout_msg = self._check_ammo_runout(ammo_card, ammo_data)
            if runout_msg:
                base_msg += f" {runout_msg}"

        return base_msg, killed

    def _execute_piercing_attack(self, primary_target, attack_name, damage, ammo_card, ammo_data, requires_ammo, grid):
        """Ranger piercing shot: hits all entities along the line from player to clicked target."""
        from hexgrid import DIRECTIONS

        player_row, player_col = self.position
        target_row, target_col = primary_target.position

        # Find the direction line that contains the target
        attack_line = []
        for direction in DIRECTIONS:
            line = grid.get_line(player_row, player_col, direction, self.projectile_range)
            if (target_row, target_col) in line:
                attack_line = line
                break

        if not attack_line:
            return "Cannot determine attack line", False

        # Collect all entities along the line up to and including the clicked target
        hit_units = []
        messages = []
        for hex_pos in attack_line:
            row, col = hex_pos
            if not (0 <= row < grid.rows and 0 <= col < grid.cols):
                continue
            # Stop if we've passed the clicked target
            target_dist = grid.hex_distance(self.position, primary_target.position)
            hex_dist = grid.hex_distance(self.position, hex_pos)
            if hex_dist > target_dist:
                break
            unit = grid.grid[row][col].get("unit")
            if unit and hasattr(unit, 'hp') and unit.hp > 0:
                unit.hp -= damage
                unit.set_damage_text(damage)
                unit.attack_flash = True
                unit.flash_start = pygame.time.get_ticks()
                defeated = unit.hp <= 0
                hit_units.append((unit, damage, defeated))
                messages.append(f"{unit.name} ({damage} dmg{'- defeated' if defeated else ''})")

        if not hit_units:
            return "No targets hit", False

        self._mark_attack_used(is_projectile=True)
        self.attack_flash = True
        self.flash_start = pygame.time.get_ticks()

        # Handle ammunition runout
        ammo_msg = ""
        if requires_ammo and ammo_card:
            runout_msg = self._check_ammo_runout(ammo_card, ammo_data)
            if runout_msg:
                ammo_msg = f" {runout_msg}"

        if len(hit_units) == 1:
            unit, dmg, killed = hit_units[0]
            base_msg = f"{self.class_name} used {attack_name} on {unit.name} for {dmg} damage{ammo_msg}"
            return base_msg, hit_units
        else:
            base_msg = f"{self.class_name} piercing shot! Hit: {', '.join(messages)}{ammo_msg}"
            return base_msg, hit_units

    def _get_equipped_ammunition(self):
        """Find equipped ammunition card from tool slots."""
        # Check multi-slot system first
        for tool in self.equipped_tools:
            if tool:
                tool_data = tool.get_current_data()
                if tool_data.get("Type") == "Ammunition":
                    return tool

        # Fall back to legacy single tool slot
        if self.equipped_tool:
            tool_data = self.equipped_tool.get_current_data()
            if tool_data.get("Type") == "Ammunition":
                return self.equipped_tool

        return None

    def _is_valid_projectile_target(self, target_pos, grid, effective_range=None):
        """Check if target position is valid for projectile attack based on range type."""
        if effective_range is None:
            effective_range = self.projectile_range
        # Use the grid's calculate_range method for full pattern support
        return grid.is_in_range(
            self.position,
            target_pos,
            effective_range,
            self.projectile_range_type,
            self.projectile_include_pos,
            self.projectile_exclude_adj,
            piercing=self.piercing_projectile
        )

    def _check_ammo_runout(self, ammo_card, ammo_data):
        """Check if ammunition runs out after use, return message if it does."""
        runout_chance = int(ammo_data.get("Runout_Chance", 0) or 0)

        if runout_chance > 0 and random.randint(1, 100) <= runout_chance:
            # Revert ammo card back to state 1 (document/raw material form)
            ammo_card.current_state = 1

            # Remove from equipped slot and return to inventory
            if ammo_card in self.equipped_tools:
                idx = self.equipped_tools.index(ammo_card)
                self.equipped_tools[idx] = None
            elif ammo_card == self.equipped_tool:
                self.equipped_tool = None

            self.inventory.append(ammo_card)
            return "Your ammunition has run out!"

        return None

    def _mark_attack_used(self, is_projectile):
        """Mark an attack as used, handling Warrior's passive double attack."""
        if self.double_attack_active:
            self.warrior_attacks_remaining -= 1
            if self.warrior_attacks_remaining <= 0:
                self.action_used = True
        else:
            self.action_used = True

    def get_projectile_attack_range(self, grid, party=None):
        """
        Get the set of valid hexes for projectile attack based on equipped weapon's range pattern.

        Args:
            grid: The HexGrid instance
            party: Optional party list for mount range bonuses

        Returns:
            set: Set of (row, col) positions that can be targeted
        """
        effective_range = self.projectile_range + self.get_mount_range_bonus(party or [])
        return grid.calculate_range(
            self.position,
            effective_range,
            self.projectile_range_type,
            self.projectile_include_pos,
            self.projectile_exclude_adj,
            piercing=self.piercing_projectile
        )

    def get_melee_attack_range(self, grid):
        """
        Get the set of valid hexes for melee attack (adjacent hexes).

        Args:
            grid: The HexGrid instance

        Returns:
            set: Set of (row, col) positions that can be targeted
        """
        return grid.calculate_range(
            self.position,
            1,
            "melee",
            include_pos=False,
            exclude_adj=False
        )

    def reset_double_attack(self):
        """Reset attack state at end of turn. Warriors always have 2 attacks."""
        if self.class_name == "Warrior":
            self.double_attack_active = True
            self.warrior_attacks_remaining = 2
        else:
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
        elif self.special_attack == "Dual Strike":
            # Dual Strike is passive - Warrior always gets 2 attacks per turn
            return "Dual Strike is a passive ability - attack normally to use both attacks", []
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

        # Calculate damage - handle ammunition system like normal projectile attacks
        attack_info = self.attacks.get("projectile", {})
        requires_ammo = attack_info.get("requires_ammo", False)
        ammo_card = None
        ammo_data = {}
        damage = attack_info.get("damage", 0)

        if requires_ammo:
            ammo_card = self._get_equipped_ammunition()
            if not ammo_card:
                return "No ammunition equipped - cannot fire!", []
            ammo_data = ammo_card.get_current_data()
            # ALL damage comes from ammunition
            damage = int(ammo_data.get("Ammo_Damage", 0))

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

        # Check ammo runout after successful attack
        if requires_ammo and ammo_card:
            runout_msg = self._check_ammo_runout(ammo_card, ammo_data)
            if runout_msg:
                messages.append(runout_msg)

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
        """Equip a weapon card, updating attack stats and range properties."""
        weapon_data = weapon_card.get_current_data()
        weapon_type = weapon_data.get("Type")

        if weapon_type == "Both":
            # Dual-slot weapon (e.g., Combat Bow) - occupies both melee and projectile slots
            try:
                # Melee slot
                melee_damage = int(weapon_data.get("Melee Damage", 0))
                self.melee_weapon = weapon_card
                self.attacks["melee"] = {"name": weapon_data["Name"], "damage": melee_damage}

                # Projectile slot
                self.projectile_weapon = weapon_card
                self.projectile_range = int(weapon_data.get("Range_Distance", weapon_data.get("Projectile Range", 5)))
                self.projectile_range_type = weapon_data.get("Range_Type", "line_of_sight")
                self.projectile_include_pos = str(weapon_data.get("Include_Position", "false")).lower() == "true"
                self.projectile_exclude_adj = str(weapon_data.get("Exclude_Adjacent", "false")).lower() == "true"

                requires_ammo = str(weapon_data.get("Requires_Ammo", "false")).lower() == "true"
                if requires_ammo:
                    self.attacks["projectile"] = {
                        "name": weapon_data["Name"],
                        "damage": 0,
                        "requires_ammo": True,
                        "compatible_ammo": weapon_data.get("Compatible_Ammo", "")
                    }
                else:
                    proj_damage = int(weapon_data.get("Projectile Damage", 0))
                    self.attacks["projectile"] = {
                        "name": weapon_data["Name"],
                        "damage": proj_damage,
                        "requires_ammo": False
                    }
            except ValueError as e:
                print(f"Error: Invalid dual-slot weapon data for {weapon_data.get('Name', 'Unknown')}: {e}")

        elif weapon_type == "Melee" and "Melee Damage" in weapon_data:
            try:
                damage = int(weapon_data["Melee Damage"])
                self.melee_weapon = weapon_card
                self.attacks["melee"] = {"name": weapon_data["Name"], "damage": damage}
            except ValueError:
                print(f"Error: Invalid 'Melee Damage' for {weapon_data.get('Name', 'Unknown')}")

        elif weapon_type == "Projectile":
            try:
                self.projectile_weapon = weapon_card

                # Load full range properties from weapon
                self.projectile_range = int(weapon_data.get("Range_Distance", weapon_data.get("Projectile Range", 5)))
                self.projectile_range_type = weapon_data.get("Range_Type", "line_of_sight")
                self.projectile_include_pos = str(weapon_data.get("Include_Position", "false")).lower() == "true"
                self.projectile_exclude_adj = str(weapon_data.get("Exclude_Adjacent", "false")).lower() == "true"

                # Check if weapon requires ammunition
                requires_ammo = str(weapon_data.get("Requires_Ammo", "false")).lower() == "true"

                if requires_ammo:
                    # Bow-type weapon: has NO damage alone, damage comes from ammo
                    self.attacks["projectile"] = {
                        "name": weapon_data["Name"],
                        "damage": 0,
                        "requires_ammo": True,
                        "compatible_ammo": weapon_data.get("Compatible_Ammo", "")  # e.g., "Arrow,Bolt"
                    }
                else:
                    # Standard projectile weapon with built-in damage
                    damage = int(weapon_data.get("Projectile Damage", 0))
                    self.attacks["projectile"] = {
                        "name": weapon_data["Name"],
                        "damage": damage,
                        "requires_ammo": False
                    }
            except ValueError as e:
                print(f"Error: Invalid projectile weapon data for {weapon_data.get('Name', 'Unknown')}: {e}")

    def get_stats(self):
        attacks_str = ', '.join([f"{attack['name']} ({attack['damage']})" for attack in self.attacks.values()])
        melee = self.melee_weapon.get_current_data().get("Name", "None") if self.melee_weapon else "None"
        proj = self.projectile_weapon.get_current_data().get("Name", "None") if self.projectile_weapon else "None"

        # Tool slot display (supports multi-slot)
        if self.equipped_tools:
            tool_names = [t.get_current_data().get("Name", "Empty") if t else "Empty" for t in self.equipped_tools]
            tool = ", ".join(tool_names)
        elif self.equipped_tool:
            tool = self.equipped_tool.get_current_data().get("Name", "None")
        else:
            tool = "None"

        # Accessory slot display
        accessory = self.equipped_accessory.get_current_data().get("Name", "None") if self.equipped_accessory else "None"

        # Check if projectile weapon requires ammo
        proj_info = proj
        if self.projectile_weapon and self.attacks.get("projectile", {}).get("requires_ammo"):
            proj_info = f"{proj} (Needs Ammo)"

        return (f"Class: {self.class_name}\nHP: {self.hp}/{self.max_hp}\nMovement: {self.movement}\nRange: {self.projectile_range}\n"
                f"Attacks: {attacks_str}\nSpecial: {self.special_attack}\nMelee Weapon: {melee}\nProjectile Weapon: {proj_info}\n"
                f"Tool: {tool} (Slots: {self.tool_slots})\nAccessory: {accessory}")

    # ===== TOOL EQUIPMENT METHODS =====

    def equip_tool(self, card, slot_index=None):
        """
        Equip a tool, consumable, or ammunition card to a tool slot.

        Args:
            card: The card to equip
            slot_index: Optional specific slot index (0-based). If None, uses first available slot.

        Returns:
            str: Result message
        """
        card_data = card.get_current_data()
        card_type = card_data.get("Type", "")
        card_subclass = card.card_data.get("subclass", "")

        # Determine if card can be equipped as a tool
        valid_types = ["Consumable", "Tool", "Ammunition"]
        is_valid = (card_type in valid_types or
                    card_subclass == "Consumable" or
                    card_data.get("Use_HP") or
                    card_data.get("Ammo_Damage"))

        if not is_valid:
            return "Cannot equip this item as a tool"

        # Ensure equipped_tools list is properly sized
        while len(self.equipped_tools) < self.tool_slots:
            self.equipped_tools.append(None)

        # Find slot to use
        if slot_index is not None:
            if slot_index >= self.tool_slots:
                return f"Invalid tool slot (max: {self.tool_slots})"
            target_slot = slot_index
        else:
            # Find first empty slot, or use slot 0 if all full
            target_slot = 0
            for i, slot in enumerate(self.equipped_tools):
                if slot is None:
                    target_slot = i
                    break

        # Unequip existing item in that slot if any
        if target_slot < len(self.equipped_tools) and self.equipped_tools[target_slot]:
            old_card = self.equipped_tools[target_slot]
            self.inventory.append(old_card)

        # Equip new card
        self.equipped_tools[target_slot] = card
        if card in self.inventory:
            self.inventory.remove(card)

        # Also update legacy single slot for backwards compatibility
        if target_slot == 0:
            self.equipped_tool = card

        return f"Equipped {card_data.get('Name', 'Unknown')} to tool slot {target_slot + 1}"

    def unequip_tool(self, slot_index=0):
        """
        Unequip tool from specified slot.

        Args:
            slot_index: The slot to unequip from (0-based)

        Returns:
            str: Result message
        """
        if slot_index >= len(self.equipped_tools) or self.equipped_tools[slot_index] is None:
            # Check legacy single slot
            if slot_index == 0 and self.equipped_tool:
                name = self.equipped_tool.get_current_data().get("Name", "Unknown")
                self.inventory.append(self.equipped_tool)
                self.equipped_tool = None
                return f"Unequipped tool: {name}"
            return "No tool in this slot"

        card = self.equipped_tools[slot_index]
        name = card.get_current_data().get("Name", "Unknown")
        self.inventory.append(card)
        self.equipped_tools[slot_index] = None

        # Update legacy single slot
        if slot_index == 0:
            self.equipped_tool = None

        return f"Unequipped tool: {name}"

    # ===== ACCESSORY/TOOL BELT METHODS =====

    def equip_accessory(self, card):
        """
        Equip an accessory (tool belt, pouch, etc.) to the accessory slot.
        Tool belts increase available tool slots.

        Args:
            card: The accessory card to equip

        Returns:
            str: Result message
        """
        card_data = card.get_current_data()
        card_type = card_data.get("Type", "")

        # Check if this is a valid accessory
        valid_accessory_types = ["Tool_Belt", "Accessory", "Belt", "Pouch"]
        if card_type not in valid_accessory_types:
            return "This item cannot be equipped as an accessory"

        # Unequip current accessory if any
        if self.equipped_accessory:
            old_accessory = self.equipped_accessory
            old_name = old_accessory.get_current_data().get("Name", "Unknown")
            self.inventory.append(old_accessory)

            # Reset tool slots to base
            self.tool_slots = 1

        # Equip new accessory
        self.equipped_accessory = card
        if card in self.inventory:
            self.inventory.remove(card)

        # Apply tool slot bonus from tool belt
        extra_slots = int(card_data.get("Extra_Tool_Slots", 0) or 0)
        self.tool_slots = 1 + extra_slots

        # Resize equipped_tools list if needed
        while len(self.equipped_tools) < self.tool_slots:
            self.equipped_tools.append(None)

        return f"Equipped {card_data.get('Name', 'Unknown')}. Tool slots: {self.tool_slots}"

    def unequip_accessory(self):
        """
        Unequip the current accessory.

        Returns:
            str: Result message
        """
        if not self.equipped_accessory:
            return "No accessory equipped"

        accessory = self.equipped_accessory
        name = accessory.get_current_data().get("Name", "Unknown")

        # Move any tools beyond slot 0 back to inventory
        for i in range(1, len(self.equipped_tools)):
            if self.equipped_tools[i]:
                self.inventory.append(self.equipped_tools[i])
                self.equipped_tools[i] = None

        # Resize to single slot
        self.tool_slots = 1
        self.equipped_tools = self.equipped_tools[:1] if self.equipped_tools else [None]

        # Return accessory to inventory
        self.inventory.append(accessory)
        self.equipped_accessory = None

        return f"Unequipped accessory: {name}. Tool slots reset to 1."

    def get_tool_in_slot(self, slot_index):
        """Get the tool card in a specific slot."""
        if slot_index < len(self.equipped_tools):
            return self.equipped_tools[slot_index]
        if slot_index == 0:
            return self.equipped_tool  # Legacy fallback
        return None

    def use_tool(self, slot_index=0, target=None, grid=None):
        """
        Use the tool in the specified slot. Returns (success, message).
        Dispatches based on tool type:
        - Healing: parse Use_HP, heal player or target at range
        - Building: placeholder for future building interaction
        - Other: extensible for future tool types

        Args:
            slot_index: Which tool slot to use (0-based)
            target: Optional target unit/player for ranged effects
            grid: HexGrid for range validation (required for ranged effects)

        Returns:
            tuple: (success: bool, message: str)
        """
        # Get tool from specified slot
        tool = self.get_tool_in_slot(slot_index)

        if not tool:
            return False, f"No tool in slot {slot_index + 1}"

        if self.action_used:
            return False, "Action already used this turn"

        tool_data = tool.get_current_data()
        tool_name = tool_data.get("Name", "Unknown")
        tool_type = tool_data.get("Type", "")
        tool_subtype = tool_data.get("Subtype", "")
        hp_effect = tool_data.get("Use_HP", "")

        # Healing tool (has Use_HP field)
        if hp_effect:
            try:
                # Handle case where hp_effect is a list
                if isinstance(hp_effect, list):
                    hp_effect = next((effect for effect in hp_effect if effect and "HP" in str(effect)), "+0HP")

                # Parse HP value (handles +15HP, -10HP, etc.)
                hp_str = str(hp_effect).replace("HP", "").replace("+", "")
                hp_change = int(hp_str)

                # Determine target (self or ranged target)
                heal_target = self  # Default: heal self
                target_name = "self"

                # Check if this is a ranged tool with a specified target
                effect_range = int(tool_data.get("Effect_Range_Distance", 0) or 0)

                # Check if this is a revival item
                is_revival = str(tool_data.get("Revival", "false")).lower() == "true"

                if effect_range > 0 and target and grid and target != self:
                    # Validate target is in range
                    range_type = tool_data.get("Effect_Range_Type", "line_of_sight")
                    include_pos = str(tool_data.get("Effect_Include_Position", "true")).lower() == "true"
                    exclude_adj = str(tool_data.get("Effect_Exclude_Adjacent", "false")).lower() == "true"

                    if grid.is_in_range(self.position, target.position, effect_range, range_type, include_pos, exclude_adj):
                        heal_target = target
                        target_name = target.name if hasattr(target, 'name') else target.class_name
                    else:
                        return False, f"Target is not in range for {tool_name}"

                # Block non-revival items from targeting dead players
                if heal_target.hp <= 0 and not is_revival:
                    return False, f"{tool_name} cannot be used on a defeated player"

                if hp_change > 0:
                    was_dead = heal_target.hp <= 0
                    old_hp = heal_target.hp
                    max_hp = heal_target.max_hp if hasattr(heal_target, 'max_hp') else heal_target.hp + hp_change
                    heal_target.hp = min(max_hp, heal_target.hp + hp_change)
                    actual_heal = heal_target.hp - old_hp
                    self.action_used = True

                    # Clear death log flag if revived
                    if was_dead and heal_target.hp > 0 and hasattr(heal_target, '_death_logged'):
                        heal_target._death_logged = False

                    # Check for revert chance (consumable may revert to document form)
                    revert_chance = int(tool_data.get("Revert_Chance", 0) or 0)
                    if revert_chance > 0 and random.randint(1, 100) <= revert_chance:
                        # Revert the card back to state 1 (document form) and return to inventory
                        tool.current_state = 1
                        self.inventory.append(tool)

                        # Clear from multi-slot system
                        if slot_index < len(self.equipped_tools):
                            self.equipped_tools[slot_index] = None
                        # Clear legacy slot if it was slot 0
                        if slot_index == 0:
                            self.equipped_tool = None

                        if was_dead and heal_target.hp > 0:
                            return True, f"Used {tool_name}: REVIVED {target_name}! (+{actual_heal} HP). Item reverted to materials!"
                        return True, f"Used {tool_name} on {target_name}: +{actual_heal} HP. Item reverted to document form!"

                    if was_dead and heal_target.hp > 0:
                        return True, f"Used {tool_name}: REVIVED {target_name}! (+{actual_heal} HP, now at {heal_target.hp})"
                    return True, f"Used {tool_name} on {target_name}: +{actual_heal} HP ({old_hp} -> {heal_target.hp})"
                elif hp_change < 0:
                    heal_target.hp = max(0, heal_target.hp + hp_change)
                    self.action_used = True
                    return True, f"Used {tool_name} on {target_name}: {hp_change} HP"
                else:
                    return False, f"{tool_name} has no effect"
            except (ValueError, AttributeError) as e:
                return False, f"Cannot use {tool_name}: invalid effect"

        # Building tool (future feature)
        if tool_type == "Tool" and tool_subtype == "Building":
            return False, "Building tools require a buildable target"

        # Other tool types - placeholder for future mechanics
        return False, f"{tool_name} cannot be used directly"

    def get_tool_effect_text(self, slot_index=0):
        """
        Get a short description of the equipped tool's effect for UI display.

        Args:
            slot_index: Which tool slot to get effect text for (0-based)

        Returns:
            str: Effect text for display
        """
        tool = self.get_tool_in_slot(slot_index)

        if not tool:
            return ""

        tool_data = tool.get_current_data()
        tool_type = tool_data.get("Type", "")

        # Ammunition shows damage
        if tool_type == "Ammunition":
            ammo_damage = tool_data.get("Ammo_Damage", "?")
            runout = tool_data.get("Runout_Chance", "0")
            return f"({ammo_damage} dmg, {runout}% runout)"

        # Healing shows HP effect
        hp_effect = tool_data.get("Use_HP", "")
        if hp_effect:
            # Handle case where hp_effect is a list
            if isinstance(hp_effect, list):
                hp_effect = next((effect for effect in hp_effect if effect and "HP" in str(effect)), "")
            if hp_effect:
                # Check if it's a ranged tool
                effect_range = int(tool_data.get("Effect_Range_Distance", 0) or 0)
                if effect_range > 0:
                    return f"({hp_effect}, Range: {effect_range})"
                return f"({hp_effect})"

        tool_subtype = tool_data.get("Subtype", "")
        if tool_subtype:
            return f"({tool_subtype})"

        return ""

    def get_tool_effect_range(self, grid, slot_index=0):
        """
        Get the set of valid hexes for tool effect based on range properties.

        Args:
            grid: The HexGrid instance
            slot_index: Which tool slot to get range for (0-based)

        Returns:
            set: Set of (row, col) positions that can be targeted, or None if no range
        """
        tool = self.get_tool_in_slot(slot_index)

        if not tool:
            return None

        tool_data = tool.get_current_data()
        effect_range = int(tool_data.get("Effect_Range_Distance", 0) or 0)

        if effect_range <= 0:
            return None

        range_type = tool_data.get("Effect_Range_Type", "line_of_sight")
        include_pos = str(tool_data.get("Effect_Include_Position", "true")).lower() == "true"
        exclude_adj = str(tool_data.get("Effect_Exclude_Adjacent", "false")).lower() == "true"

        return grid.calculate_range(
            self.position,
            effect_range,
            range_type,
            include_pos,
            exclude_adj
        )

    def is_tool_ranged(self, slot_index=0):
        """
        Check if the tool in the specified slot has range (for UI purposes).

        Args:
            slot_index: Which tool slot to check (0-based)

        Returns:
            bool: True if the tool has an effect range > 0
        """
        tool = self.get_tool_in_slot(slot_index)

        if not tool:
            return False

        tool_data = tool.get_current_data()
        effect_range = int(tool_data.get("Effect_Range_Distance", 0) or 0)

        return effect_range > 0

    def search(self, terrain_type, location_name=None):
        """
        Search for items at the current location using Searchable documents in inventory.

        Args:
            terrain_type: The terrain type at the current hex (e.g., "forest", "grass")
            location_name: Optional name of a location hex the player is on

        Returns:
            tuple: (success, message, flipped_card or None)
        """
        if self.action_used:
            return False, "Action already used this turn", None

        # Find Searchable documents in inventory that match current terrain/location
        searchable_cards = []
        for card in self.inventory:
            card_data = card.card_data
            subclass = card_data.get("subclass", "")
            if subclass != "Searchable":
                continue
            # Only search with cards in state 1 (the document side)
            if card.current_state != 1:
                continue

            current_data = card.get_current_data()
            search_terrain = current_data.get("Search_Terrain", "")
            search_location = current_data.get("Search_Location", "")

            # Check if this card matches the current terrain or location
            match = False

            # Location-based search (if card specifies a location)
            if search_location and location_name:
                if search_location.lower() == location_name.lower():
                    match = True

            # Terrain-based search (if card specifies terrains)
            if search_terrain and not match:
                allowed_terrains = [t.strip().lower() for t in search_terrain.split(",")]
                if "any" in allowed_terrains or terrain_type.lower() in allowed_terrains:
                    match = True

            if match:
                searchable_cards.append(card)

        if not searchable_cards:
            return False, "No matching searchable documents for this location", None

        # Use the first matching searchable document
        card = searchable_cards[0]
        current_data = card.get_current_data()
        card_name = current_data.get("Name", "Unknown")

        # Roll against success chance
        success_chance = int(current_data.get("Search_Success_Chance", 50) or 50)
        roll = random.randint(1, 100)

        if roll <= success_chance:
            # Success! Flip the card to state 2
            card.current_state = 2
            found_item = card.get_current_data().get("Name", "something")
            self.action_used = True
            return True, f"Found {found_item}! (Searched using {card_name})", card
        else:
            # Failed search
            self.action_used = True
            return False, f"Searched but found nothing. (Used {card_name}, rolled {roll} vs {success_chance}%)", None

    def read_guide(self, guide_card, card_manager):
        """
        Read a Guide document to learn a blueprint. Costs the player's action.

        Args:
            guide_card: The Guide InventoryCard to read
            card_manager: The CardManager instance for loading cards

        Returns:
            str: Result message
        """
        import json

        if self.action_used:
            return "Action already used this turn"

        if guide_card.card_data.get("subclass") != "Guide":
            return "This is not a guide"

        current_data = guide_card.get_current_data()
        deck_path = current_data.get("Guide_Deck", "")
        draw_chance = int(current_data.get("Guide_Draw_Chance", 50) or 50)

        if not deck_path:
            return "Guide has no associated deck"

        # Load the deck file
        try:
            from deck_utils import resolve_deck_path
            resolved_path = resolve_deck_path(deck_path)
            with open(resolved_path, 'r') as f:
                deck_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            return f"Could not load guide deck: {e}"

        all_card_ids = deck_data.get("cards", [])
        if not all_card_ids:
            return "Guide deck is empty"

        # Filter out already-drawn cards (no duplicates)
        available_ids = [cid for cid in all_card_ids if cid not in guide_card.guide_drawn_ids]

        if not available_ids:
            return "You have already mastered this volume"

        # Costs action regardless of success
        self.action_used = True

        # Roll against draw chance
        roll = random.randint(1, 100)
        if roll > draw_chance:
            remaining = len(available_ids)
            return f"You studied the guide but didn't learn anything new. ({remaining} pages remain)"

        # Success - draw a random card from available
        drawn_id = random.choice(available_ids)
        guide_card.guide_drawn_ids.append(drawn_id)

        # Load the drawn card and add to inventory
        from card_utils import load_card
        from inventory_card import InventoryCard
        card_data = load_card(drawn_id)
        if not card_data:
            return f"Error: Could not load blueprint card '{drawn_id}'"

        new_card = InventoryCard(card_data)
        new_card.current_state = 1  # Blueprint state
        self.inventory.append(new_card)

        drawn_name = new_card.get_current_data().get("Name", "Unknown Blueprint")
        remaining = len(all_card_ids) - len(guide_card.guide_drawn_ids)

        # Check if this volume is complete
        if remaining <= 0:
            if guide_card.current_state == 1:
                # Vol. I complete - flip to Vol. II
                guide_card.guide_drawn_ids = []
                guide_card.current_state = 2
                return f"Learned: {drawn_name}! Vol. I complete - guide upgraded to Vol. II!"
            else:
                # Vol. II complete - guide fully mastered
                return f"Learned: {drawn_name}! You have fully mastered the WIN Guide!"

        return f"Learned: {drawn_name}! ({remaining} pages remain)"

    def get_location_plans(self):
        """Get all Location_Plan documents in inventory that are still in state 1."""
        plans = []
        for card in self.inventory:
            subclass = card.card_data.get("subclass", "")
            if subclass == "Location_Plan" and card.current_state == 1:
                plans.append(card)
        return plans

    def has_building_tool(self):
        """Check if player has a building tool (hammer) equipped."""
        # Check multi-slot tool system first
        if self.equipped_tools:
            for tool in self.equipped_tools:
                if tool and self._is_building_tool(tool):
                    return True
        # Fall back to legacy single tool slot
        if self.equipped_tool and self._is_building_tool(self.equipped_tool):
            return True
        return False

    def _is_building_tool(self, tool):
        """Check if a tool is a building tool (hammer)."""
        tool_data = tool.get_current_data()
        tool_type = tool_data.get("Type", "")
        tool_subtype = tool_data.get("Subtype", "")
        # Check for Building type tools or hammers
        if tool_type == "Tool" and tool_subtype == "Building":
            return True
        # Also check name for hammer-like tools
        tool_name = tool_data.get("Name", "").lower()
        if "hammer" in tool_name:
            return True
        return False

    def can_build(self, location_plan_card):
        """
        Check if player can build a location from a Location_Plan card.

        Args:
            location_plan_card: The Location_Plan card to check

        Returns:
            tuple: (can_build: bool, missing_requirements: list of strings)
        """
        missing = []

        # Check if card is a Location_Plan in state 1
        if location_plan_card.card_data.get("subclass") != "Location_Plan":
            missing.append("Not a Location Plan")
            return False, missing
        if location_plan_card.current_state != 1:
            missing.append("Plan already used")
            return False, missing

        # Check for building tool
        if not self.has_building_tool():
            missing.append("Need a hammer/building tool equipped")

        # Get requirements from the plan
        plan_data = location_plan_card.get_current_data()
        req_materials_str = plan_data.get("Requirements_Materials", "{}")

        try:
            import json
            req_materials = json.loads(req_materials_str) if isinstance(req_materials_str, str) else (req_materials_str or {})
        except (json.JSONDecodeError, TypeError):
            req_materials = {}

        # Calculate total materials from inventory
        totals = {"Metal": 0, "Wood": 0, "Raw": 0, "Refined": 0}
        for card in self.inventory:
            card_data = card.get_current_data()
            totals["Metal"] += int(card_data.get("Metal Value", 0) or 0)
            totals["Wood"] += int(card_data.get("Wood Value", 0) or 0)
            totals["Raw"] += int(card_data.get("Raw Material Value", 0) or 0)
            totals["Refined"] += int(card_data.get("Refined Material Value", 0) or 0)

        # Check each requirement
        for material, required in req_materials.items():
            required = int(required or 0)
            if required <= 0:
                continue
            available = totals.get(material, 0)
            if available < required:
                missing.append(f"Need {required} {material} (have {available})")

        return len(missing) == 0, missing

    def build(self, location_plan_card, material_cards):
        """
        Build a location from a Location_Plan card.

        Args:
            location_plan_card: The Location_Plan card to build
            material_cards: List of inventory cards to consume for materials

        Returns:
            tuple: (success: bool, message: str, built_card: InventoryCard or None)
        """
        can, missing = self.can_build(location_plan_card)
        if not can:
            return False, f"Cannot build: {', '.join(missing)}", None

        # Consume material cards
        for card in material_cards:
            if card in self.inventory:
                self.inventory.remove(card)

        # Flip the plan card to state 2 (the actual location)
        location_plan_card.current_state = 2
        location_name = location_plan_card.get_current_data().get("Name", "Built Location")

        return True, f"Built {location_name}!", location_plan_card

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

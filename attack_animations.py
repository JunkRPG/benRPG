import pygame
import math


class AttackAnimation:
    """A single in-flight attack animation (projectile arrow or melee slash)."""

    def __init__(self, anim_type, source_pos, target_pos, color=None):
        """
        anim_type: "projectile" or "melee"
        source_pos: (x, y) screen pixel coords of attacker
        target_pos: (x, y) screen pixel coords of target
        color: optional override color
        """
        self.anim_type = anim_type
        self.source = source_pos
        self.target = target_pos
        self.start_time = pygame.time.get_ticks()

        dx = target_pos[0] - source_pos[0]
        dy = target_pos[1] - source_pos[1]
        self.total_dist = math.hypot(dx, dy)
        self.angle = math.atan2(dy, dx)

        if anim_type == "projectile":
            self.color = color or (255, 240, 100)
            self.trail_color = (255, 200, 50)
            self.speed = 12  # pixels per frame
            self.traveled = 0.0
            self.trail = []  # past positions for fading trail
            self.done = False
            # Duration estimate in ms (at ~60fps)
            self.duration_ms = int((self.total_dist / self.speed) * (1000 / 60)) if self.total_dist > 0 else 100
        else:  # melee
            self.color = color or (255, 255, 255)
            self.duration_ms = 300
            # Arc center is 70% toward target from attacker
            self.arc_center = (
                source_pos[0] + dx * 0.7,
                source_pos[1] + dy * 0.7
            )
            self.arc_radius = max(20, self.total_dist * 0.6)
            # Sweep 120 degrees (pi/3 on each side of the attack angle)
            self.arc_start_angle = self.angle - math.pi / 3
            self.arc_end_angle = self.angle + math.pi / 3
            self.done = False

    def update(self):
        """Advance one frame. Returns True if still active, False when done."""
        if self.done:
            return False

        if self.anim_type == "projectile":
            self.traveled += self.speed
            # Calculate current position
            if self.total_dist > 0:
                progress = min(1.0, self.traveled / self.total_dist)
            else:
                progress = 1.0
            cx = self.source[0] + (self.target[0] - self.source[0]) * progress
            cy = self.source[1] + (self.target[1] - self.source[1]) * progress
            self.trail.append((cx, cy))
            if len(self.trail) > 5:
                self.trail.pop(0)
            if self.traveled >= self.total_dist:
                self.done = True
                return False
            return True
        else:  # melee
            elapsed = pygame.time.get_ticks() - self.start_time
            if elapsed >= self.duration_ms:
                self.done = True
                return False
            return True

    def draw(self, surface):
        """Render onto the given surface."""
        if self.done:
            return

        if self.anim_type == "projectile":
            self._draw_projectile(surface)
        else:
            self._draw_melee(surface)

    def _draw_projectile(self, surface):
        """Draw a golden arrowhead with fading trail."""
        if self.total_dist <= 0:
            return

        progress = min(1.0, self.traveled / self.total_dist)
        cx = self.source[0] + (self.target[0] - self.source[0]) * progress
        cy = self.source[1] + (self.target[1] - self.source[1]) * progress

        # Draw fading trail
        if len(self.trail) > 1:
            trail_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            for i in range(len(self.trail) - 1):
                alpha = int(40 + (i / len(self.trail)) * 120)
                t_color = (self.trail_color[0], self.trail_color[1], self.trail_color[2], alpha)
                p1 = (int(self.trail[i][0]), int(self.trail[i][1]))
                p2 = (int(self.trail[i + 1][0]), int(self.trail[i + 1][1]))
                pygame.draw.line(trail_surf, t_color, p1, p2, 2)
            surface.blit(trail_surf, (0, 0))

        # Draw arrowhead triangle pointing in travel direction
        arrow_len = 10
        arrow_width = 5
        tip = (cx + math.cos(self.angle) * arrow_len,
               cy + math.sin(self.angle) * arrow_len)
        left = (cx + math.cos(self.angle + 2.5) * arrow_width,
                cy + math.sin(self.angle + 2.5) * arrow_width)
        right = (cx + math.cos(self.angle - 2.5) * arrow_width,
                 cy + math.sin(self.angle - 2.5) * arrow_width)

        points = [(int(tip[0]), int(tip[1])),
                  (int(left[0]), int(left[1])),
                  (int(right[0]), int(right[1]))]
        pygame.draw.polygon(surface, self.color, points)

        # Bright glow at the tip
        glow_surf = pygame.Surface((16, 16), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (255, 255, 200, 100), (8, 8), 8)
        surface.blit(glow_surf, (int(tip[0]) - 8, int(tip[1]) - 8))

    def _draw_melee(self, surface):
        """Draw a swinging stick with a swoosh trail behind it."""
        elapsed = pygame.time.get_ticks() - self.start_time
        progress = min(1.0, elapsed / self.duration_ms)

        # Current sweep angle of the stick
        current_angle = self.arc_start_angle + (self.arc_end_angle - self.arc_start_angle) * progress

        arc_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        cx, cy = self.arc_center
        stick_len = self.arc_radius

        # --- Swoosh trail: filled wedge of past stick positions ---
        num_trail = 12
        for i in range(num_trail):
            t = max(0.0, progress - (num_trail - i) * 0.035)
            if t <= 0:
                continue
            t_next = max(0.0, progress - (num_trail - i - 1) * 0.035)
            t_next = min(t_next, progress)

            a1 = self.arc_start_angle + (self.arc_end_angle - self.arc_start_angle) * t
            a2 = self.arc_start_angle + (self.arc_end_angle - self.arc_start_angle) * t_next

            # Swoosh is a thin quad between two stick tip positions
            alpha = int((i / num_trail) * 140)
            # Inner edge (near pivot) and outer edge (tip) for both angles
            inner_ratio = 0.3  # swoosh starts 30% along the stick
            p1_inner = (cx + math.cos(a1) * stick_len * inner_ratio,
                        cy + math.sin(a1) * stick_len * inner_ratio)
            p1_outer = (cx + math.cos(a1) * stick_len,
                        cy + math.sin(a1) * stick_len)
            p2_inner = (cx + math.cos(a2) * stick_len * inner_ratio,
                        cy + math.sin(a2) * stick_len * inner_ratio)
            p2_outer = (cx + math.cos(a2) * stick_len,
                        cy + math.sin(a2) * stick_len)

            points = [
                (int(p1_inner[0]), int(p1_inner[1])),
                (int(p1_outer[0]), int(p1_outer[1])),
                (int(p2_outer[0]), int(p2_outer[1])),
                (int(p2_inner[0]), int(p2_inner[1])),
            ]
            swoosh_color = (200, 220, 255, alpha)
            pygame.draw.polygon(arc_surf, swoosh_color, points)

        # --- The stick itself: a thick line from pivot to tip ---
        stick_base = (int(cx), int(cy))
        stick_tip = (int(cx + math.cos(current_angle) * stick_len),
                     int(cy + math.sin(current_angle) * stick_len))

        # Dark outline for the stick
        pygame.draw.line(arc_surf, (40, 30, 20, 230), stick_base, stick_tip, 5)
        # Light wood-colored stick
        pygame.draw.line(arc_surf, (190, 160, 110, 240), stick_base, stick_tip, 3)
        # Bright highlight along the leading edge
        highlight_offset = 1
        hx = math.cos(current_angle + 0.15) * highlight_offset
        hy = math.sin(current_angle + 0.15) * highlight_offset
        h_base = (int(cx + hx), int(cy + hy))
        h_tip = (int(cx + math.cos(current_angle) * stick_len + hx),
                 int(cy + math.sin(current_angle) * stick_len + hy))
        pygame.draw.line(arc_surf, (230, 210, 170, 150), h_base, h_tip, 1)

        # --- Bright impact glow at the tip ---
        glow_alpha = int(180 * (0.5 + 0.5 * math.sin(progress * math.pi)))
        pygame.draw.circle(arc_surf, (255, 255, 230, glow_alpha), stick_tip, 6)

        surface.blit(arc_surf, (0, 0))


class AttackAnimationManager:
    """Manages all active attack animations."""

    def __init__(self, sound_mgr=None):
        self.active_animations = []
        self.sound_mgr = sound_mgr

    def create_projectile(self, source_pos, target_pos, color=None):
        """Create a projectile (arrow) animation from source to target pixel coords."""
        anim = AttackAnimation("projectile", source_pos, target_pos, color)
        self.active_animations.append(anim)
        if self.sound_mgr:
            self.sound_mgr.play("projectile_shot")
        return anim

    def create_melee(self, source_pos, target_pos, color=None):
        """Create a melee slash arc animation."""
        anim = AttackAnimation("melee", source_pos, target_pos, color)
        self.active_animations.append(anim)
        if self.sound_mgr:
            self.sound_mgr.play("melee_swing")
        return anim

    def update(self):
        """Advance all animations, remove finished ones."""
        self.active_animations = [a for a in self.active_animations if a.update()]

    def draw(self, surface):
        """Render all active animations."""
        for anim in self.active_animations:
            anim.draw(surface)

    def is_animating(self):
        """Returns True if any animations are currently playing."""
        return len(self.active_animations) > 0

    def get_max_remaining_ms(self):
        """Returns the longest remaining animation time in milliseconds."""
        if not self.active_animations:
            return 0
        now = pygame.time.get_ticks()
        max_remaining = 0
        for anim in self.active_animations:
            if anim.anim_type == "projectile":
                # Estimate remaining time based on distance left
                remaining_dist = max(0, anim.total_dist - anim.traveled)
                remaining_ms = int((remaining_dist / anim.speed) * (1000 / 60)) if anim.speed > 0 else 0
            else:
                elapsed = now - anim.start_time
                remaining_ms = max(0, anim.duration_ms - elapsed)
            max_remaining = max(max_remaining, remaining_ms)
        return max_remaining

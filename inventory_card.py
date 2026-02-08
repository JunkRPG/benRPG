import pygame

class InventoryCard:
    def __init__(self, card_data):
        self.card_data = card_data
        self.states = card_data.get("states", 1)
        self.current_state = 1 if self.states >= 1 else None
        self.guide_drawn_ids = []  # Track card IDs drawn from Guide decks
        # Flip animation attributes
        self.flip_animation_active = False
        self.flip_progress = 0.0  # 0 to 1
        self.flip_start_time = 0
        self.flip_duration = 500  # milliseconds

    def get_current_data(self):
        return self.get_state_data(self.current_state)

    def get_state_data(self, state):
        if state == 1:
            return {k: v for k, v in self.card_data["data"].items() if not k.startswith("2nd_state_")}
        elif state == 2:
            return {k.replace("2nd_state_", ""): v for k, v in self.card_data["data"].items() if k.startswith("2nd_state_")}
        return {}

    def toggle_state(self):
        if self.states == 2:
            self.current_state = 3 - self.current_state

    def is_two_state(self):
        return self.states == 2

    def get_current_type(self):
        """Returns the card type for the current state from compound card_type (e.g., 'Document/Skill')."""
        card_type = self.card_data.get("card_type", "")
        if "/" in card_type:
            types = card_type.split("/")
            return types[0] if self.current_state == 1 else types[1]
        return card_type  # Single-state card

    def start_flip_animation(self):
        """Start the flip animation to transition between states."""
        if self.states == 2:
            self.flip_animation_active = True
            self.flip_progress = 0.0
            self.flip_start_time = pygame.time.get_ticks()

    def update_flip_animation(self):
        """Update flip animation progress. Returns True when complete."""
        if not self.flip_animation_active:
            return False

        current_time = pygame.time.get_ticks()
        elapsed = current_time - self.flip_start_time
        self.flip_progress = min(1.0, elapsed / self.flip_duration)

        # At midpoint (0.5), toggle the state
        if self.flip_progress >= 0.5 and self.current_state == 1:
            self.current_state = 2
        elif self.flip_progress >= 0.5 and self.current_state == 2:
            # Already toggled, do nothing
            pass

        # Animation complete
        if self.flip_progress >= 1.0:
            self.flip_animation_active = False
            self.flip_progress = 0.0
            return True

        return False

    def get_flip_scale(self):
        """Returns horizontal scale factor for flip animation (1.0 -> 0.0 -> 1.0)."""
        if not self.flip_animation_active:
            return 1.0

        # First half: 1.0 -> 0.0, Second half: 0.0 -> 1.0
        if self.flip_progress <= 0.5:
            return 1.0 - (self.flip_progress * 2)
        else:
            return (self.flip_progress - 0.5) * 2

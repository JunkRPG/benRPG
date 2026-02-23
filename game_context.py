"""
Shared mutable namespace for JunkRPG game globals.

Screen modules use `import game_context as gc` and access globals as
`gc.screen`, `gc.manager`, `gc.game`, etc.  Python resolves `gc.screen`
at call time, not import time, so even though these are None at import
they are populated by the time any method executes.
"""
from sound_manager import play_card_acquired_sound

# ── Pygame display objects (set by JunkRPG34.py after pygame.init) ──────
screen = None
manager = None
WINDOW_WIDTH = 0
WINDOW_HEIGHT = 0

# ── Color constants ─────────────────────────────────────────────────────
DARK_CHARCOAL = (35, 35, 40)
GRAY = (200, 200, 200)
YELLOW = (255, 255, 0)
GOLDEN_YELLOW = (255, 215, 0)
BLUE = (0, 0, 255)
RED = (255, 0, 0)
DARK_RED_ALPHA = (100, 0, 0, 128)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
LIGHT_GREEN = (144, 238, 144)
PURPLE = (128, 0, 128)
ORANGE = (255, 165, 0)

# ── Multiplayer constants ──────────────────────────────────────────────
PLAYER_COLORS = [
    (0, 200, 0),
    (100, 150, 255),
    (255, 100, 100),
    (255, 200, 50),
]
PLAYER_COLOR_NAMES = ["Green", "Blue", "Red", "Gold"]
PLAYER_COLOR_HEX = ["#66DD66", "#6688FF", "#FF6666", "#FFD744"]

# ── Animation constants ────────────────────────────────────────────────
MOVE_SPEED = 5
ATTACK_FLASH_DURATION = 500

# ── Game + screen singletons (all set by JunkRPG34.py after instantiation) ──
game = None
game_screen = None
main_menu = None
player_count_screen = None
character_creation_screen = None
multiplayer_character_creation_screen = None
settings_screen = None
game_settings_screen = None
crafting_screen = None
inventory_screen = None
location_screen = None
recruitment_screen = None
card_giving_screen = None
party_screen = None
skills_screen = None
quest_screen = None
pause_menu_screen = None
confirmation_screen = None
teleport_party_screen = None
save_load_screen = None
defeat_screen = None
card_browser_screen = None
tabbed_menu_screen = None
npc_browser_screen = None


# ── Relocated helper functions (used by multiple screen modules) ────────
def _check_builder_wood_perk():
    """Returns True if current player is a Master Builder standing on forest terrain."""
    player = game.current_player
    if player.special_attack != "Master Builder":
        return False
    pos = player.position
    if pos is None:
        return False
    terrain = game_screen.hex_grid.grid[pos[0]][pos[1]].get("terrain", "grass")
    return terrain == "forest"


def add_card_to_player(card):
    """Add a card to inventory or party depending on type. Returns message about where it went."""
    play_card_acquired_sound(card)
    card_type = card.card_data.get("card_type", "")
    if card_type == "NPC Card":
        allegiance = card.get_current_data().get("Allegiance (Hostile, Neutral, Allied)", "")
        if "Allied" in allegiance:
            game.current_party.append(card)
            name = card.get_current_data().get("Name", "Unknown")
            return f"{name} joined your party!"
    game.current_player.inventory.append(card)
    return None

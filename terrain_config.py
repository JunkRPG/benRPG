"""
Terrain configuration - Single source of truth for terrain types.

This module defines all terrain types and their properties used by both
the game engine (hexgrid.py) and the level editor (Level_Maker19.py).
"""

# Terrain types configuration
# Each terrain has: color, accessible (can units walk on it), blocks_los (does it block line of sight)
TERRAIN_CONFIG = {
    "grass": {"color": (76, 153, 0), "accessible": True, "blocks_los": False},
    "dirt": {"color": (139, 90, 43), "accessible": True, "blocks_los": False},
    "sand": {"color": (238, 214, 175), "accessible": True, "blocks_los": False},
    "stone": {"color": (128, 128, 128), "accessible": True, "blocks_los": False},
    "wood": {"color": (139, 69, 19), "accessible": True, "blocks_los": False},
    "water": {"color": (30, 144, 255), "accessible": False, "blocks_los": False},
    "deep_water": {"color": (0, 0, 139), "accessible": False, "blocks_los": False},
    "lava": {"color": (255, 69, 0), "accessible": False, "blocks_los": False},
    "mountain": {"color": (105, 105, 105), "accessible": False, "blocks_los": True},
    "cliff": {"color": (70, 70, 70), "accessible": False, "blocks_los": True},
    "forest": {"color": (34, 100, 34), "accessible": True, "blocks_los": True},
    "swamp": {"color": (85, 107, 47), "accessible": True, "blocks_los": False},
    "ice": {"color": (173, 216, 230), "accessible": True, "blocks_los": False},
    "void": {"color": (20, 20, 30), "accessible": False, "blocks_los": True},
}

# Convenience lists derived from config
TERRAIN_TYPES = list(TERRAIN_CONFIG.keys())
TERRAIN_COLORS = {k: v["color"] for k, v in TERRAIN_CONFIG.items()}


def get_terrain_color(terrain_type):
    """Get the color for a terrain type."""
    return TERRAIN_CONFIG.get(terrain_type, TERRAIN_CONFIG["grass"])["color"]


def is_terrain_accessible(terrain_type):
    """Check if a terrain type is walkable."""
    return TERRAIN_CONFIG.get(terrain_type, TERRAIN_CONFIG["grass"])["accessible"]


def does_terrain_block_los(terrain_type):
    """Check if a terrain type blocks line of sight."""
    return TERRAIN_CONFIG.get(terrain_type, TERRAIN_CONFIG["grass"])["blocks_los"]

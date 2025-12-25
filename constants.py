# constants.py
DARK_INDIGO = (25, 25, 112)      # Background
LIGHT_GOLDEN = (238, 221, 130)   # Text on background
LIGHT_TEAL = (127, 255, 212)     # Text box background
DARK_BRONZE = (139, 69, 19)      # Text inside text boxes
DARK_BRASS = (184, 134, 11)      # Button background
LIGHT_CREAM = (245, 245, 220)    # Button text
LIGHT_GREEN = (144, 238, 144)    # Card-drawing hex border
YELLOW = (255, 255, 0)           # Selected hex border
GRAY = (200, 200, 200)           # Default hex border

WINDOW_WIDTH = 1920  # Default, will be overridden by display info
WINDOW_HEIGHT = 1080

CARD_WIDTH = 750
CARD_HEIGHT = 1050

TERRAIN_TYPES = ["grass", "water", "mountain"]
TERRAIN_COLORS = {
    "grass": (76, 153, 0),
    "water": (0, 0, 255),
    "mountain": (100, 100, 100)
}

SUPPORTED_IMAGE_FORMATS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
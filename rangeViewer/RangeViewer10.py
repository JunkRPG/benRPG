# RangeViewer.py

import pygame
import pygame_gui
from pygame_gui.elements import UIDropDownMenu, UILabel
import math
from hexgrid import HexGrid  # Assuming hexgrid.py is in the same directory

# Initialize Pygame
pygame.init()

# Set up fullscreen display
display_info = pygame.display.Info()
WINDOW_WIDTH = display_info.current_w
WINDOW_HEIGHT = display_info.current_h
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Range Viewer")

# Colors
DARK_INDIGO = (25, 25, 112)  # Background
BLUE = (0, 0, 255)           # Movement range
RED = (255, 0, 0)            # Attack range
GREEN = (0, 255, 0)          # Healing range
YELLOW = (255, 255, 0)       # Selected hex
GOLDEN_YELLOW = (255, 215, 0)  # Hex border
PURPLE = (128, 0, 128)       # Special effect range
ORANGE = (255, 165, 0)       # Echo pattern color
CYAN = (0, 255, 255)        # Inverted LOS pattern color
MAGENTA = (255, 0, 255)      # New combined pattern color

# Initialize UIManager
manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT))

# Define range types with their patterns and descriptions
RANGE_TYPES = {
    "Short Melee (Adjacent)": {
        "description": "Basic melee attack hitting adjacent hexes.",
        "range_func": lambda grid, pos: grid.get_attack_range(pos, 1, is_projectile=False)
    },
    "Spear Melee (2 Hexes)": {
        "description": "Extended melee attack reaching 2 hexes in all directions.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 2) if hex_pos != pos and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    },
    "Standard Projectile (5 Hexes)": {
        "description": "Typical projectile range up to 5 hexes with LOS.",
        "range_func": lambda grid, pos: grid.get_attack_range(pos, 5, is_projectile=True)
    },
    "Longbow Projectile (8 Hexes)": {
        "description": "Long-range projectile up to 8 hexes with LOS.",
        "range_func": lambda grid, pos: grid.get_attack_range(pos, 8, is_projectile=True)
    },
    "Healing Aura (3 Hexes)": {
        "description": "Healing effect in a 3-hex radius around the caster.",
        "range_func": lambda grid, pos: grid.get_movement_range(pos, 3)
    },
    "Grenade Blast (2 Hexes Radius)": {
        "description": "Explosive area effect within 2 hexes of impact.",
        "range_func": lambda grid, pos: grid.get_movement_range(pos, 2)
    },
    "Chain Lightning (4 Hexes Bounce)": {
        "description": "Hits a target up to 4 hexes away, then bounces to nearby targets.",
        "range_func": lambda grid, pos: grid.get_attack_range(pos, 4, is_projectile=True)  # Simplified
    },
    "Whirlwind Spin (1 Hex Around)": {
        "description": "Melee attack hitting all adjacent hexes.",
        "range_func": lambda grid, pos: grid.get_attack_range(pos, 1, is_projectile=False)
    },
    "Sniper Shot (10 Hexes Precise)": {
        "description": "Ultra-long-range shot up to 10 hexes with LOS.",
        "range_func": lambda grid, pos: grid.get_attack_range(pos, 10, is_projectile=True)
    },
    "Poison Cloud (3 Hexes Spread)": {
        "description": "Area effect poisoning within 3 hexes.",
        "range_func": lambda grid, pos: grid.get_movement_range(pos, 3)
    },
    "Echo Wave (3 Hexes Alternating)": {
        "description": "A wave that affects hexes at distances 1 and 3, skipping 2.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 3) if grid.hex_distance(pos, hex_pos) in (1, 3) and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    },
    "Pulse Echo (4 Hexes Even)": {
        "description": "A pulsing wave hitting even distances (2 and 4) up to 4 hexes.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 4) if grid.hex_distance(pos, hex_pos) in (2, 4) and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    },
    "Ripple Echo (5 Hexes Outer)": {
        "description": "A ripple effect targeting only the outer edge at 5 hexes.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 5) if grid.hex_distance(pos, hex_pos) == 5 and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    },
    "Dual Echo (3-5 Hexes Split)": {
        "description": "A split wave affecting hexes at 3 and 5 hexes, skipping others.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 5) if grid.hex_distance(pos, hex_pos) in (3, 5) and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    },
    "Mist Strike (5 Hexes Obscured)": {
        "description": "A misty attack within 5 hexes targeting hexes blocked by obstacles, beyond 1 hex.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 5) if hex_pos != pos and not grid.has_clear_line_of_sight(pos, hex_pos) and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"] and grid.hex_distance(pos, hex_pos) > 1}
    },
    "Echo Shadow (5 Hexes Hidden)": {
        "description": "A shadowy strike hitting hexes at 2 and 4 hexes without LOS.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 5) if grid.hex_distance(pos, hex_pos) in (2, 4) and not grid.has_clear_line_of_sight(pos, hex_pos) and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    },
    # New Combined Patterns
    "Echo Grenade (3 Hexes Burst)": {
        "description": "A grenade that bursts at 1 and 3 hexes, creating explosive rings.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 3) if grid.hex_distance(pos, hex_pos) in (1, 3) and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    },
    "Mist Ripple (6 Hexes Edge)": {
        "description": "A mist that ripples to the 6-hex edge, targeting obscured hexes only.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 6) if grid.hex_distance(pos, hex_pos) == 6 and not grid.has_clear_line_of_sight(pos, hex_pos) and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    },
    "Poison Echo (4 Hexes Toxic)": {
        "description": "A toxic wave poisoning hexes at 2 and 4 hexes in all directions.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 4) if grid.hex_distance(pos, hex_pos) in (2, 4) and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    },
    "Chain Mist (5 Hexes Bounce)": {
        "description": "A misty chain that bounces to obscured hexes within 5 hexes.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 5) if hex_pos != pos and not grid.has_clear_line_of_sight(pos, hex_pos) and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"] and grid.hex_distance(pos, hex_pos) > 1}
    },
    "Healing Ripple (5 Hexes Outer Heal)": {
        "description": "A healing ripple that restores allies only at the 5-hex outer edge.",
        "range_func": lambda grid, pos: {hex_pos for hex_pos in grid.get_movement_range(pos, 5) if grid.hex_distance(pos, hex_pos) == 5 and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    }
}

# Hex grid setup
hex_grid = HexGrid(16, 24, 30, WINDOW_WIDTH, WINDOW_HEIGHT)
center_pos = (hex_grid.rows // 2, hex_grid.cols // 2)  # Center of the grid as origin

# UI setup
dropdown_options = list(RANGE_TYPES.keys())
dropdown = UIDropDownMenu(options_list=dropdown_options,
                         starting_option=dropdown_options[0],
                         relative_rect=pygame.Rect(10, 50, 250, 30),
                         manager=manager)
description_label = UILabel(relative_rect=pygame.Rect(10, 90, 250, 200),
                           text=RANGE_TYPES[dropdown_options[0]]["description"],
                           manager=manager)

# Interaction variables
dragging = False
drag_start_x = drag_start_y = start_view_offset_x = start_view_offset_y = 0
current_range = RANGE_TYPES[dropdown_options[0]]["range_func"](hex_grid, center_pos)
range_color = RED  # Default color, will be updated based on range type

# Main loop
clock = pygame.time.Clock()
running = True
while running:
    time_delta = clock.tick(60) / 1000.0
    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            running = False
        # Process UI events first
        consumed_event = manager.process_events(event)
        
        # Only process game logic if the UI didn't consume the event
        if not consumed_event:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click to select hex
                    pos = event.pos
                    hex_pos = hex_grid.get_hex_at_pixel(pos[0], pos[1])
                    if hex_pos:
                        hex_grid.selected_hex = hex_pos
                        selected_key = dropdown.selected_option
                        if isinstance(selected_key, tuple):
                            selected_key = selected_key[0]
                        current_range = RANGE_TYPES[selected_key]["range_func"](hex_grid, hex_pos)
                elif event.button == 3:  # Right click to drag
                    dragging = True
                    drag_start_x, drag_start_y = event.pos
                    start_view_offset_x, start_view_offset_y = hex_grid.view_offset_x, hex_grid.view_offset_y
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 3:
                    dragging = False
            elif event.type == pygame.MOUSEMOTION:
                if dragging:
                    dx = event.pos[0] - drag_start_x
                    dy = event.pos[1] - drag_start_y
                    hex_grid.view_offset_x = start_view_offset_x + dx
                    hex_grid.view_offset_y = start_view_offset_y + dy
                    grid_width = hex_grid.cols * hex_grid.hex_size * 1.5
                    grid_height = hex_grid.rows * hex_grid.hex_size * 1.732
                    min_offset_x = WINDOW_WIDTH - grid_width if grid_width > WINDOW_WIDTH else 0
                    max_offset_x = 0 if grid_width > WINDOW_WIDTH else WINDOW_WIDTH - grid_width
                    min_offset_y = WINDOW_HEIGHT - grid_height if grid_height > WINDOW_HEIGHT else 0
                    max_offset_y = 0 if grid_height > WINDOW_HEIGHT else WINDOW_HEIGHT - grid_height
                    hex_grid.view_offset_x = max(min(hex_grid.view_offset_x, max_offset_x), min_offset_x)
                    hex_grid.view_offset_y = max(min(hex_grid.view_offset_y, max_offset_y), min_offset_y)
            elif event.type == pygame.MOUSEWHEEL:
                zoom_factor = 1.1 if event.y > 0 else 0.9
                mx, my = pygame.mouse.get_pos()
                ox, oy = hex_grid.view_offset_x, hex_grid.view_offset_y
                s = hex_grid.hex_size
                new_s = s * zoom_factor
                if 10 <= new_s <= 100:  # Limit zoom range
                    hex_grid.hex_size = new_s
                    hex_grid.view_offset_x = mx - zoom_factor * (mx - ox)
                    hex_grid.view_offset_y = my - zoom_factor * (my - oy)
                    grid_width = hex_grid.cols * hex_grid.hex_size * 1.5
                    grid_height = hex_grid.rows * hex_grid.hex_size * 1.732
                    min_offset_x = WINDOW_WIDTH - grid_width if grid_width > WINDOW_WIDTH else 0
                    max_offset_x = 0 if grid_width > WINDOW_WIDTH else WINDOW_WIDTH - grid_width
                    min_offset_y = WINDOW_HEIGHT - grid_height if grid_height > WINDOW_HEIGHT else 0
                    max_offset_y = 0 if grid_height > WINDOW_HEIGHT else WINDOW_HEIGHT - grid_height
                    hex_grid.view_offset_x = max(min(hex_grid.view_offset_x, max_offset_x), min_offset_x)
                    hex_grid.view_offset_y = max(min(hex_grid.view_offset_y, max_offset_y), min_offset_y)
                    # Update range with new scale
                    selected_key = dropdown.selected_option
                    if isinstance(selected_key, tuple):
                        selected_key = selected_key[0]
                    current_range = RANGE_TYPES[selected_key]["range_func"](hex_grid, hex_grid.selected_hex or center_pos)
        
        # Handle UI-specific events regardless of consumption
        if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            selected_key = event.text
            if isinstance(selected_key, tuple):
                selected_key = selected_key[0]
            selected_range = RANGE_TYPES[selected_key]
            hex_pos = hex_grid.selected_hex or center_pos
            current_range = selected_range["range_func"](hex_grid, hex_pos)
            description_label.set_text(selected_range["description"])
            # Assign color based on range type
            if "Melee" in selected_key or "Whirlwind" in selected_key:
                range_color = RED
            elif "Projectile" in selected_key or "Sniper" in selected_key:
                range_color = RED
            elif "Healing" in selected_key and "Ripple" not in selected_key:
                range_color = GREEN
            elif "Grenade" in selected_key or "Cloud" in selected_key or "Chain" in selected_key and "Mist" not in selected_key:
                range_color = PURPLE
            elif "Echo" in selected_key and "Shadow" not in selected_key:
                range_color = ORANGE
            elif "Mist" in selected_key or "Shadow" in selected_key:
                range_color = CYAN
            elif "Echo Grenade" in selected_key or "Mist Ripple" in selected_key or "Poison Echo" in selected_key or "Chain Mist" in selected_key or "Healing Ripple" in selected_key:
                range_color = MAGENTA  # New combined patterns use magenta
            else:
                range_color = BLUE

    manager.update(time_delta)
    screen.fill(DARK_INDIGO)

    # Draw the hex grid with the selected range
    selected_key = dropdown.selected_option
    if isinstance(selected_key, tuple):
        selected_key = selected_key[0]
    range_name = selected_key.lower()
    movement_range = current_range if "movement" in range_name else None
    attack_range = current_range if "melee" in range_name or "projectile" in range_name or "sniper" in range_name or "whirlwind" in range_name or "echo" in range_name or "mist" in range_name or "shadow" in range_name or "grenade" in range_name or "poison" in range_name or "chain" in range_name or "ripple" in range_name else None
    special_range = current_range if "healing" in range_name else None
    
    colors = {
        'BLUE': BLUE,
        'DARK_RED_ALPHA': (range_color[0], range_color[1], range_color[2], 128),
        'LIGHT_GREEN': GREEN,
        'YELLOW': YELLOW,
        'GOLDEN_YELLOW': GOLDEN_YELLOW,
        'GREEN': GREEN,
        'RED': RED,
        'GRAY': (128, 128, 128),
        'WHITE': (255, 255, 255),
        'PURPLE': PURPLE
    }
    
    # Draw grid with appropriate range highlighted
    if movement_range:
        hex_grid.draw(screen, movement_range=movement_range, colors=colors)
    elif attack_range:
        hex_grid.draw(screen, attack_range=attack_range, colors=colors)
    elif special_range:
        hex_grid.draw(screen, attack_range=special_range, colors=colors)  # Using attack_range for simplicity
    else:
        hex_grid.draw(screen, colors=colors)

    # Draw UI
    manager.draw_ui(screen)
    pygame.display.flip()

pygame.quit()

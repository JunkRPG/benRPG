# RangeViewer.py

import pygame
import pygame_gui
from pygame_gui.elements import UIDropDownMenu, UILabel, UITextEntryLine, UIButton
import math
from hexgrid import HexGrid, DIRECTIONS

pygame.init()

display_info = pygame.display.Info()
WINDOW_WIDTH = display_info.current_w
WINDOW_HEIGHT = display_info.current_h
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Range Viewer")

DARK_CHARCOAL = (35, 35, 40)
BLUE = (0, 0, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)
GOLDEN_YELLOW = (255, 215, 0)
PURPLE = (128, 0, 128)
ORANGE = (255, 165, 0)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)

manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT), "theme.json")

hex_grid = HexGrid(16, 24, 30, WINDOW_WIDTH, WINDOW_HEIGHT)
center_pos = (hex_grid.rows // 2, hex_grid.cols // 2)
hex_grid.selected_hex = center_pos

hex_grid.grid[7][11]["accessible"] = False
hex_grid.grid[8][12]["accessible"] = False
hex_grid.grid[9][11]["accessible"] = False

range_distance_entry = UITextEntryLine(relative_rect=pygame.Rect(10, 50, 100, 30), manager=manager, initial_text="9")
range_distance_label = UILabel(relative_rect=pygame.Rect(120, 50, 150, 30), text="Range Distance", manager=manager)

pattern_options = ["Line of Sight", "Melee", "Area Effect", "Echo", "Multi Echo", "Perimeter", "Mist/Shadow"]
pattern_dropdown = UIDropDownMenu(options_list=pattern_options, starting_option="Line of Sight",
                                  relative_rect=pygame.Rect(10, 90, 150, 30), manager=manager)
pattern_label = UILabel(relative_rect=pygame.Rect(170, 90, 100, 30), text="Pattern", manager=manager)

include_pos_button = UIButton(relative_rect=pygame.Rect(10, 130, 150, 30), text="Include Position: OFF", manager=manager)
exclude_adj_button = UIButton(relative_rect=pygame.Rect(10, 160, 150, 30), text="Exclude Adjacent: OFF", manager=manager)
include_pos_state = False
exclude_adj_state = False

# Range 2 controls
range2_enabled = False
range2_toggle_button = UIButton(relative_rect=pygame.Rect(10, 200, 150, 30), text="Range 2: OFF", manager=manager)
range2_distance_entry = UITextEntryLine(relative_rect=pygame.Rect(10, 230, 100, 30), manager=manager, initial_text="3")
range2_distance_label = UILabel(relative_rect=pygame.Rect(120, 230, 150, 30), text="Range 2 Distance", manager=manager)
range2_pattern_dropdown = UIDropDownMenu(options_list=pattern_options, starting_option="Area Effect",
                                         relative_rect=pygame.Rect(10, 270, 150, 30), manager=manager)
range2_pattern_label = UILabel(relative_rect=pygame.Rect(170, 270, 120, 30), text="Range 2 Pattern", manager=manager)
range2_include_pos_button = UIButton(relative_rect=pygame.Rect(10, 310, 150, 30), text="R2 Include Pos: OFF", manager=manager)
range2_exclude_adj_button = UIButton(relative_rect=pygame.Rect(10, 340, 150, 30), text="R2 Exclude Adj: OFF", manager=manager)
range2_include_pos_state = False
range2_exclude_adj_state = False
current_range2 = set()
range2_color = GREEN

instructions_label = UILabel(relative_rect=pygame.Rect(10, 400, 450, 30),
                             text="Left: Move Center, Right: Toggle Obstacle, Middle: Clear Obstacle",
                             manager=manager)

dragging = False
drag_start_x = drag_start_y = start_view_offset_x = start_view_offset_y = 0
current_range = set()
range_color = RED

# Bisecting directions with exact (row, col) deltas (kept for reference, not used in new Mist/Shadow)
BISECTING_DIRECTIONS = [
    (-1, 1),  # 30°
    (0, 2),   # 90°
    (2, 1),   # 150°
    (2, -1),  # 210°
    (0, -2),  # 270°
    (-1, -1), # 330°
]

def get_hex_direction(pos, target):
    """Calculate the exact direction from pos to target in hex grid."""
    r1, c1 = pos
    r2, c2 = target
    dr = r2 - r1
    dc = c2 - c1
    
    if dr == 0 and dc == 0:
        return DIRECTIONS[0]  # Shouldn’t happen
    
    # Hex grid directions (assuming DIRECTIONS = [(0, 1), (1, 1), (1, 0), (0, -1), (-1, -1), (-1, 0)])
    # Map to 30°, 90°, 150°, 210°, 270°, 330°
    if dr == 0:
        return DIRECTIONS[1] if dc > 0 else DIRECTIONS[4]  # 90° or 270°
    elif dc == 0:
        return DIRECTIONS[0] if dr < 0 else DIRECTIONS[3]  # 30° or 210° approx
    elif dr > 0 and dc > 0:
        return DIRECTIONS[2]  # 150°
    elif dr > 0 and dc < 0:
        return DIRECTIONS[3]  # 210°
    elif dr < 0 and dc < 0:
        return DIRECTIONS[5]  # 330°
    elif dr < 0 and dc > 0:
        return DIRECTIONS[0]  # 30°
    return DIRECTIONS[0]  # Fallback

PATTERN_NAME_MAP = {
    "Line of Sight": "line_of_sight",
    "Melee": "melee",
    "Area Effect": "area_effect",
    "Echo": "echo",
    "Multi Echo": "multi_echo",
    "Perimeter": "perimeter",
    "Mist/Shadow": "mist_shadow",
}

def calculate_range(grid, pos, distance, pattern, include_pos, exclude_adj):
    if not distance.isdigit() or int(distance) < 0:
        print(f"Invalid distance: {distance}")
        return set()
    dist = int(distance)

    if isinstance(pattern, tuple):
        pattern = pattern[0]

    # Map display name to internal name and delegate to HexGrid.calculate_range()
    internal_pattern = PATTERN_NAME_MAP.get(pattern, pattern)
    return grid.calculate_range(pos, dist, internal_pattern, include_pos, exclude_adj)

def recalc_range2():
    """Recalculate Range 2 if enabled."""
    if range2_enabled:
        return calculate_range(hex_grid, hex_grid.selected_hex or center_pos,
                               range2_distance_entry.get_text(),
                               range2_pattern_dropdown.selected_option,
                               range2_include_pos_state, range2_exclude_adj_state)
    return set()

current_range = calculate_range(hex_grid, center_pos, range_distance_entry.get_text(),
                                pattern_dropdown.selected_option, include_pos_state, exclude_adj_state)
current_range2 = recalc_range2()

clock = pygame.time.Clock()
running = True
while running:
    time_delta = clock.tick(60) / 1000.0
    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            running = False
        consumed_event = manager.process_events(event)
        
        if not consumed_event:
            if event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos
                hex_pos = hex_grid.get_hex_at_pixel(pos[0], pos[1])
                if hex_pos:
                    if event.button == 1:
                        hex_grid.selected_hex = hex_pos
                        current_range = calculate_range(hex_grid, hex_pos, range_distance_entry.get_text(),
                                                        pattern_dropdown.selected_option,
                                                        include_pos_state, exclude_adj_state)
                        current_range2 = recalc_range2()
                    elif event.button == 2:
                        hex_grid.grid[hex_pos[0]][hex_pos[1]]["accessible"] = True
                        current_range = calculate_range(hex_grid, hex_grid.selected_hex or center_pos,
                                                        range_distance_entry.get_text(),
                                                        pattern_dropdown.selected_option,
                                                        include_pos_state, exclude_adj_state)
                        current_range2 = recalc_range2()
                    elif event.button == 3:
                        if not dragging:
                            current_state = hex_grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]
                            hex_grid.grid[hex_pos[0]][hex_pos[1]]["accessible"] = not current_state
                            current_range = calculate_range(hex_grid, hex_grid.selected_hex or center_pos,
                                                            range_distance_entry.get_text(),
                                                            pattern_dropdown.selected_option,
                                                            include_pos_state, exclude_adj_state)
                            current_range2 = recalc_range2()
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
                if 10 <= new_s <= 100:
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
                    current_range = calculate_range(hex_grid, hex_grid.selected_hex or center_pos,
                                                    range_distance_entry.get_text(),
                                                    pattern_dropdown.selected_option,
                                                    include_pos_state, exclude_adj_state)
                    current_range2 = recalc_range2()

        if event.type == pygame_gui.UI_TEXT_ENTRY_FINISHED:
            if event.ui_element == range_distance_entry:
                current_range = calculate_range(hex_grid, hex_grid.selected_hex or center_pos,
                                                range_distance_entry.get_text(),
                                                pattern_dropdown.selected_option,
                                                include_pos_state, exclude_adj_state)
            elif event.ui_element == range2_distance_entry:
                current_range2 = recalc_range2()
        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            if event.ui_element == pattern_dropdown:
                pattern = event.text if isinstance(event.text, str) else event.text[0]
                current_range = calculate_range(hex_grid, hex_grid.selected_hex or center_pos,
                                                range_distance_entry.get_text(),
                                                pattern,
                                                include_pos_state, exclude_adj_state)
                range_color = (RED if pattern in ("Line of Sight", "Melee") else
                              GREEN if pattern == "Area Effect" else
                              ORANGE if pattern in ("Echo", "Multi Echo") else
                              MAGENTA if pattern == "Perimeter" else
                              CYAN if pattern == "Mist/Shadow" else BLUE)
            elif event.ui_element == range2_pattern_dropdown:
                r2_pattern = event.text if isinstance(event.text, str) else event.text[0]
                range2_color = (RED if r2_pattern in ("Line of Sight", "Melee") else
                                GREEN if r2_pattern == "Area Effect" else
                                ORANGE if r2_pattern in ("Echo", "Multi Echo") else
                                MAGENTA if r2_pattern == "Perimeter" else
                                CYAN if r2_pattern == "Mist/Shadow" else BLUE)
                current_range2 = recalc_range2()
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == include_pos_button:
                include_pos_state = not include_pos_state
                include_pos_button.set_text(f"Include Position: {'ON' if include_pos_state else 'OFF'}")
                current_range = calculate_range(hex_grid, hex_grid.selected_hex or center_pos,
                                                range_distance_entry.get_text(),
                                                pattern_dropdown.selected_option,
                                                include_pos_state, exclude_adj_state)
            elif event.ui_element == exclude_adj_button:
                exclude_adj_state = not exclude_adj_state
                exclude_adj_button.set_text(f"Exclude Adjacent: {'ON' if exclude_adj_state else 'OFF'}")
                current_range = calculate_range(hex_grid, hex_grid.selected_hex or center_pos,
                                                range_distance_entry.get_text(),
                                                pattern_dropdown.selected_option,
                                                include_pos_state, exclude_adj_state)
            elif event.ui_element == range2_toggle_button:
                range2_enabled = not range2_enabled
                range2_toggle_button.set_text(f"Range 2: {'ON' if range2_enabled else 'OFF'}")
                current_range2 = recalc_range2()
            elif event.ui_element == range2_include_pos_button:
                range2_include_pos_state = not range2_include_pos_state
                range2_include_pos_button.set_text(f"R2 Include Pos: {'ON' if range2_include_pos_state else 'OFF'}")
                current_range2 = recalc_range2()
            elif event.ui_element == range2_exclude_adj_button:
                range2_exclude_adj_state = not range2_exclude_adj_state
                range2_exclude_adj_button.set_text(f"R2 Exclude Adj: {'ON' if range2_exclude_adj_state else 'OFF'}")
                current_range2 = recalc_range2()

    manager.update(time_delta)
    screen.fill(DARK_CHARCOAL)

    colors = {
        'BLUE': BLUE,
        'DARK_RED_ALPHA': (range_color[0], range_color[1], range_color[2], 128),
        'YELLOW': YELLOW,
        'GOLDEN_YELLOW': GOLDEN_YELLOW,
        'GRAY': (128, 128, 128),
        'WHITE': (255, 255, 255),
        'RED': RED,
        'GREEN': GREEN,
        'LIGHT_GREEN': (144, 238, 144),
        'PURPLE': PURPLE,
        'ORANGE': ORANGE,
    }

    # Build attack_ranges list for drawing
    attack_ranges = []
    pattern = pattern_dropdown.selected_option
    if isinstance(pattern, tuple):
        pattern = pattern[0]
    pattern_lower = pattern.lower()
    movement_range = current_range if "area" in pattern_lower else None
    attack_range = current_range if movement_range is None and current_range else None

    if attack_range:
        rc = range_color
        attack_ranges.append({"range": attack_range, "color": (rc[0], rc[1], rc[2], 220), "outline": (rc[0]//2, rc[1]//2, rc[2]//2, 220), "inset": 0.65})

    if range2_enabled and current_range2:
        r2c = range2_color
        attack_ranges.append({"range": current_range2, "color": (r2c[0], r2c[1], r2c[2], 140), "outline": (r2c[0]//2, r2c[1]//2, r2c[2]//2, 220), "inset": 0.50})

    if movement_range:
        hex_grid.draw(screen, movement_range=movement_range, attack_ranges=attack_ranges if attack_ranges else None, colors=colors)
    elif attack_ranges:
        hex_grid.draw(screen, attack_ranges=attack_ranges, colors=colors)
    else:
        hex_grid.draw(screen, colors=colors)

    manager.draw_ui(screen)
    pygame.display.flip()

pygame.quit()

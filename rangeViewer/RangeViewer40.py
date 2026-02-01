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

DARK_INDIGO = (25, 25, 112)
BLUE = (0, 0, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)
GOLDEN_YELLOW = (255, 215, 0)
PURPLE = (128, 0, 128)
ORANGE = (255, 165, 0)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)

manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT))

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

def calculate_range(grid, pos, distance, pattern, include_pos, exclude_adj):
    if not distance.isdigit() or int(distance) < 0:
        print(f"Invalid distance: {distance}")
        return set()
    dist = int(distance)
    
    if isinstance(pattern, tuple):
        pattern = pattern[0]
    print(f"Calculating range: pattern={pattern}, distance={dist}, include_pos={include_pos}, exclude_adj={exclude_adj}")
    
    if pattern == "Line of Sight":
        range_set = grid.get_attack_range(pos, dist, is_projectile=True)
    elif pattern == "Melee":
        range_set = grid.get_attack_range(pos, dist, is_projectile=False)
    elif pattern == "Area Effect":
        range_set = grid.get_movement_range(pos, dist)
    elif pattern == "Echo":
        range_set = {hex_pos for hex_pos in grid.get_movement_range(pos, dist) 
                     if grid.hex_distance(pos, hex_pos) % 2 == 1 and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    elif pattern == "Multi Echo":
        range_set = {hex_pos for hex_pos in grid.get_movement_range(pos, dist) 
                     if grid.hex_distance(pos, hex_pos) % 2 == 0 and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    elif pattern == "Perimeter":
        range_set = {hex_pos for hex_pos in grid.get_movement_range(pos, dist) 
                     if grid.hex_distance(pos, hex_pos) == dist and grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]}
    elif pattern == "Mist/Shadow":
        range_set = set()
        angles = [30, 90, 150, 210, 270, 330]
        row, col = pos
        is_odd_col = col % 2 != 0
        
        # Define target offsets based on column parity
        step_offsets = {
            30: [(-1, 1), (-3, 2), (-4, 3), (-6, 4)] if is_odd_col else [(-2, 1), (-3, 2), (-5, 3), (-6, 4)],
            150: [(2, 1), (3, 2), (5, 3), (6, 4)] if is_odd_col else [(1, 1), (3, 2), (4, 3), (6, 4)],
            210: [(2, -1), (3, -2), (5, -3), (6, -4)] if is_odd_col else [(1, -1), (3, -2), (4, -3), (6, -4)],
            330: [(-1, -1), (-3, -2), (-4, -3), (-6, -4)] if is_odd_col else [(-2, -1), (-3, -2), (-5, -3), (-6, -4)]
        }
        
        for angle in angles:
            line = []
            r, c = row, col
            if angle in [90, 270]:
                # Horizontal directions: step by 2 columns
                steps = min(4, dist)
                for step in range(1, steps + 1):
                    new_r, new_c = r, c + (2 * step if angle == 90 else -2 * step)
                    new_pos = (new_r, new_c)
                    if (0 <= new_r < grid.rows and 0 <= new_c < grid.cols and 
                        grid.hex_distance(pos, new_pos) <= dist):
                        if grid.grid[new_r][new_c]["accessible"]:
                            line.append(new_pos)
                        else:
                            break  # Stop at the first obstruction
                    else:
                        break
            else:
                # Diagonal directions: use predefined offsets
                offsets = step_offsets[angle]
                for dr, dc in offsets[:min(4, dist)]:
                    new_r, new_c = r + dr, c + dc
                    new_pos = (new_r, new_c)
                    if (0 <= new_r < grid.rows and 0 <= new_c < grid.cols and 
                        grid.hex_distance(pos, new_pos) <= dist):
                        if grid.grid[new_r][new_c]["accessible"]:
                            line.append(new_pos)
                        else:
                            break  # Stop at the first obstruction
                    else:
                        break
            range_set.update(line)
    
    # Apply include_pos and exclude_adjacent filters
    if not include_pos and pos in range_set:
        range_set.remove(pos)
    if exclude_adj:
        adj = set(grid.get_neighbors(*pos))
        range_set -= adj
    
    return range_set

current_range = calculate_range(hex_grid, center_pos, range_distance_entry.get_text(), 
                                pattern_dropdown.selected_option, include_pos_state, exclude_adj_state)

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
                    elif event.button == 2:
                        hex_grid.grid[hex_pos[0]][hex_pos[1]]["accessible"] = True
                        current_range = calculate_range(hex_grid, hex_grid.selected_hex or center_pos, 
                                                        range_distance_entry.get_text(), 
                                                        pattern_dropdown.selected_option, 
                                                        include_pos_state, exclude_adj_state)
                    elif event.button == 3:
                        if not dragging:
                            current_state = hex_grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]
                            hex_grid.grid[hex_pos[0]][hex_pos[1]]["accessible"] = not current_state
                            current_range = calculate_range(hex_grid, hex_grid.selected_hex or center_pos, 
                                                            range_distance_entry.get_text(), 
                                                            pattern_dropdown.selected_option, 
                                                            include_pos_state, exclude_adj_state)
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
        
        if event.type == pygame_gui.UI_TEXT_ENTRY_FINISHED:
            current_range = calculate_range(hex_grid, hex_grid.selected_hex or center_pos, 
                                            range_distance_entry.get_text(), 
                                            pattern_dropdown.selected_option, 
                                            include_pos_state, exclude_adj_state)
        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
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

    manager.update(time_delta)
    screen.fill(DARK_INDIGO)

    colors = {
        'BLUE': BLUE,
        'DARK_RED_ALPHA': (range_color[0], range_color[1], range_color[2], 128),
        'YELLOW': YELLOW,
        'GOLDEN_YELLOW': GOLDEN_YELLOW,
        'GRAY': (128, 128, 128),
    }

    pattern = pattern_dropdown.selected_option
    if isinstance(pattern, tuple):
        pattern = pattern[0]
    pattern = pattern.lower()
    movement_range = current_range if "area" in pattern else None
    attack_range = current_range if "sight" in pattern or "melee" in pattern or "echo" in pattern or "perimeter" in pattern or "mist" in pattern else None
    
    print(f"Drawing: movement_range={len(movement_range) if movement_range else 0}, attack_range={len(attack_range) if attack_range else 0}")
    if movement_range:
        hex_grid.draw(screen, movement_range=movement_range, colors=colors)
    elif attack_range:
        hex_grid.draw(screen, attack_range=attack_range, colors=colors)
    else:
        hex_grid.draw(screen, colors=colors)

    manager.draw_ui(screen)
    pygame.display.flip()

pygame.quit()

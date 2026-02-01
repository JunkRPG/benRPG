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
pattern_dropdown = UIDropDownMenu(options_list=pattern_options, starting_option="Mist/Shadow",
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
        # Exclude the six LOS lines
        los_hexes = set()
        row, col = pos
        for dir in DIRECTIONS:
            line = grid.get_line(row, col, dir, dist)
            for hex_pos in line:
                if grid.hex_distance(pos, hex_pos) <= dist:
                    los_hexes.add(hex_pos)
        # Build range from all six bisecting lines
        range_set = set()
        angles = [30, 90, 150, 210, 270, 330]
        for i, angle in enumerate(angles):
            line = []
            r, c = row, col
            if angle == 90:  # Straight east
                for step in range(1, dist + 1):
                    new_r, new_c = r, c + 2 * step
                    new_pos = (new_r, new_c)
                    if (0 <= new_r < grid.rows and 0 <= new_c < grid.cols and 
                        grid.hex_distance(pos, new_pos) <= dist):
                        line.append(new_pos)
                    else:
                        break
            elif angle == 270:  # Straight west
                for step in range(1, dist + 1):
                    new_r, new_c = r, c - 2 * step
                    new_pos = (new_r, new_c)
                    if (0 <= new_r < grid.rows and 0 <= new_c < grid.cols and 
                        grid.hex_distance(pos, new_pos) <= dist):
                        line.append(new_pos)
                    else:
                        break
            elif angle == 30:  # NE, alternating
                steps = [(6, 13), (5, 14), (3, 15), (2, 16), (0, 17)]
                for dr, dc in steps:
                    new_r, new_c = dr + (row - 8), dc + (col - 12)
                    new_pos = (new_r, new_c)
                    if (0 <= new_r < grid.rows and 0 <= new_c < grid.cols and 
                        grid.hex_distance(pos, new_pos) <= dist):
                        line.append(new_pos)
                    else:
                        break
            elif angle == 150:  # SE, alternating
                steps = [(9, 13), (11, 14), (12, 15), (14, 16)]
                for dr, dc in steps:
                    new_r, new_c = dr + (row - 8), dc + (col - 12)
                    new_pos = (new_r, new_c)
                    if (0 <= new_r < grid.rows and 0 <= new_c < grid.cols and 
                        grid.hex_distance(pos, new_pos) <= dist):
                        line.append(new_pos)
                    else:
                        break
            elif angle == 210:  # SW, alternating
                steps = [(9, 11), (11, 10), (12, 9), (14, 8)]
                for dr, dc in steps:
                    new_r, new_c = dr + (row - 8), dc + (col - 12)
                    new_pos = (new_r, new_c)
                    if (0 <= new_r < grid.rows and 0 <= new_c < grid.cols and 
                        grid.hex_distance(pos, new_pos) <= dist):
                        line.append(new_pos)
                    else:
                        break
            elif angle == 330:  # NW, alternating
                steps = [(6, 11), (5, 10), (3, 9), (2, 8)]
                for dr, dc in steps:
                    new_r, new_c = dr + (row - 8), dc + (col - 12)
                    new_pos = (new_r, new_c)
                    if (0 <= new_r < grid.rows and 0 <= new_c < grid.cols and 
                        grid.hex_distance(pos, new_pos) <= dist):
                        line.append(new_pos)
                    else:
                        break
            print(f"Direction {angle}°: {line}")
            for hex_pos in line:
                if not grid.grid[hex_pos[0]][hex_pos[1]]["accessible"]:
                    break  # Stop at obstruction
                range_set.add(hex_pos)
        print(f"LOS hexes excluded: {los_hexes}")
        print(f"Range before LOS filter: {range_set}")
        # Final exclusion of LOS hexes
        range_set = {hex_pos for hex_pos in range_set if hex_pos not in los_hexes}
        print(f"Range after LOS filter: {range_set}")
    else:
        range_set = set()

    if not include_pos and pos in range_set:
        range_set.remove(pos)
    if exclude_adj:
        range_set = {hex_pos for hex_pos in range_set if grid.hex_distance(pos, hex_pos) > 1}
    
    print(f"Range calculated: {len(range_set)} hexes - {range_set}")
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

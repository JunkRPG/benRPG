# hexgrid.py

import pygame
import math

# Hexagonal directions for LOS
DIRECTIONS = [
    (1, 0, -1), (1, -1, 0), (0, -1, 1),
    (-1, 0, 1), (-1, 1, 0), (0, 1, -1)
]

class HexGrid:
    def __init__(self, rows, cols, hex_size, window_width, window_height):
        self.rows = rows
        self.cols = cols
        self.hex_size = hex_size
        self.grid = [[{"accessible": True} for _ in range(cols)] for _ in range(rows)]
        self.selected_hex = None
        grid_width = self.cols * self.hex_size * 1.5
        grid_height = self.rows * self.hex_size * 1.732
        self.view_offset_x = (window_width - grid_width) / 2 if grid_width < window_width else 0
        self.view_offset_y = (window_height - grid_height) / 2 if grid_height < window_height else 0

    def get_hex_center(self, row, col):
        x = self.view_offset_x + col * self.hex_size * 1.5
        y = self.view_offset_y + row * self.hex_size * 1.732 + (col % 2) * self.hex_size * 0.866
        return x, y

    def get_hex_at_pixel(self, x, y):
        grid_left = self.view_offset_x
        grid_right = self.view_offset_x + (self.cols * self.hex_size * 1.5)
        grid_top = self.view_offset_y
        grid_bottom = self.view_offset_y + (self.rows * self.hex_size * 1.732)
        padding = self.hex_size
        if not (grid_left - padding <= x <= grid_right + padding and grid_top - padding <= y <= grid_bottom + padding):
            return None
        min_dist = float('inf')
        selected_hex = None
        for row in range(self.rows):
            for col in range(self.cols):
                center_x, center_y = self.get_hex_center(row, col)
                dist = (x - center_x) ** 2 + (y - center_y) ** 2
                if dist < min_dist and dist < (self.hex_size ** 2):
                    min_dist = dist
                    selected_hex = (row, col)
        return selected_hex

    def offset_to_cube(self, col, row):
        x = col
        z = row - (col // 2)
        y = -x - z
        return x, y, z

    def cube_to_offset(self, x, z):
        col = x
        row = z + (x // 2)
        return row, col

    def hex_distance(self, pos1, pos2):
        row1, col1 = pos1
        row2, col2 = pos2
        x1, y1, z1 = self.offset_to_cube(col1, row1)
        x2, y2, z2 = self.offset_to_cube(col2, row2)
        return max(abs(x1 - x2), abs(y1 - y2), abs(z1 - z2))

    def get_line(self, start_row, start_col, direction, max_distance):
        start_x, start_y, start_z = self.offset_to_cube(start_col, start_row)
        dir_x, dir_y, dir_z = direction
        line = []
        for k in range(1, max_distance + 1):
            x = start_x + k * dir_x
            y = start_y + k * dir_y
            z = start_z + k * dir_z
            row, col = self.cube_to_offset(x, z)
            if 0 <= row < self.rows and 0 <= col < self.cols:
                line.append((row, col))
            else:
                break
        return line

    def get_line_between(self, start_row, start_col, end_row, end_col):
        distance = self.hex_distance((start_row, start_col), (end_row, end_col))
        for dir in DIRECTIONS:
            line = self.get_line(start_row, start_col, dir, distance)
            if (end_row, end_col) in line:
                idx = line.index((end_row, end_col))
                return line[:idx + 1]
        return []

    def has_clear_line_of_sight(self, start_pos, target_pos):
        start_row, start_col = start_pos
        end_row, end_col = target_pos
        line = self.get_line_between(start_row, start_col, end_row, end_col)
        if not line:
            return False
        # Check all hexes up to (but not including) the target
        for row, col in line[1:]:
            if not self.grid[row][col]["accessible"]:
                return False
        return True

    def get_neighbors(self, row, col):
        if col % 2 == 0:
            offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1)]
        else:
            offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (1, -1), (1, 1)]
        neighbors = [(row + dr, col + dc) for dr, dc in offsets]
        return [(r, c) for r, c in neighbors if 0 <= r < self.rows and 0 <= c < self.cols and self.grid[r][c]["accessible"]]

    def get_movement_range(self, start, movement):
        from collections import deque
        reachable = set()
        frontier = deque([(0, start)])
        visited = set([start])
        while frontier:
            cost, current = frontier.popleft()
            if cost > movement:
                continue
            reachable.add(current)
            for neighbor in self.get_neighbors(*current):
                if neighbor not in visited:
                    visited.add(neighbor)
                    frontier.append((cost + 1, neighbor))
        return reachable

    def get_attack_range(self, start, range_limit, is_projectile=False):
        if is_projectile:
            attack_hexes = set()
            row, col = start
            for dir in DIRECTIONS:
                line = self.get_line(row, col, dir, range_limit)
                for hex_pos in line:
                    distance = self.hex_distance(start, hex_pos)
                    if distance > range_limit:
                        break
                    # Stop adding hexes if we hit an obstruction
                    if not self.grid[hex_pos[0]][hex_pos[1]]["accessible"]:
                        break
                    attack_hexes.add(hex_pos)
            return attack_hexes
        else:
            return {(r, c) for r, c in self.get_neighbors(*start) if self.hex_distance(start, (r, c)) <= range_limit}

    def draw(self, surface, movement_range=None, attack_range=None, colors=None):
        if colors is None:
            colors = {
                'BLUE': (0, 0, 255),
                'DARK_RED_ALPHA': (100, 0, 0, 128),
                'YELLOW': (255, 255, 0),
                'GOLDEN_YELLOW': (255, 215, 0),
                'GRAY': (128, 128, 128),
            }
        hex_surface = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
        for row in range(self.rows):
            for col in range(self.cols):
                x, y = self.get_hex_center(row, col)
                points = [(x + self.hex_size * math.cos(math.radians(60 * i)), 
                           y + self.hex_size * math.sin(math.radians(60 * i))) for i in range(6)]
                if not self.grid[row][col]["accessible"]:
                    pygame.draw.polygon(hex_surface, colors['GRAY'], points, 0)
                elif movement_range and (row, col) in movement_range:
                    pygame.draw.polygon(hex_surface, colors['BLUE'], points, 0)
                elif attack_range and (row, col) in attack_range:
                    pygame.draw.polygon(hex_surface, colors['DARK_RED_ALPHA'], points, 0)
                if self.selected_hex == (row, col):
                    pygame.draw.polygon(hex_surface, colors['YELLOW'], points, 0)
                pygame.draw.polygon(hex_surface, colors['GOLDEN_YELLOW'], points, 1)
        surface.blit(hex_surface, (0, 0))

import json, random, math, os

random.seed(42)

ROWS = 24
COLS = 42

grid = {}
for r in range(ROWS):
    for c in range(COLS):
        grid[(r, c)] = "grass"

for c in range(COLS):
    grid[(0, c)] = "cliff"
    grid[(ROWS - 1, c)] = "cliff"
for r in range(ROWS):
    grid[(r, 0)] = "cliff"
    grid[(r, COLS - 1)] = "cliff"

pond_center = (12, 28)
pond_hexes = set()
pond_candidates = []
for r in range(8, 17):
    for c in range(24, 34):
        dr = r - pond_center[0]
        dc = c - pond_center[1]
        dist = math.sqrt(dr * dr + dc * dc)
        if dist <= 3.5:
            pond_candidates.append((r, c))

for pos in pond_candidates:
    dr = pos[0] - pond_center[0]
    dc = pos[1] - pond_center[1]
    dist = math.sqrt(dr * dr + dc * dc)
    if dist <= 2.0:
        pond_hexes.add(pos)
    elif dist <= 3.0 and random.random() < 0.7:
        pond_hexes.add(pos)
    elif dist <= 3.5 and random.random() < 0.35:
        pond_hexes.add(pos)

extensions = [(10, 26), (11, 26), (13, 30), (14, 30), (11, 30), (12, 31)]
for ext in extensions:
    if random.random() < 0.6:
        pond_hexes.add(ext)

for pos in pond_hexes:
    grid[pos] = "water"

for pos in list(pond_hexes):
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            nr, nc = pos[0] + dr, pos[1] + dc
            if (nr, nc) in grid and grid[(nr, nc)] == "grass":
                dist = abs(dr) + abs(dc)
                if dist <= 1:
                    if random.random() < 0.7:
                        grid[(nr, nc)] = "dirt"
                elif dist <= 2:
                    if random.random() < 0.3:
                        grid[(nr, nc)] = "dirt"

player_start = (10, 5)
assigned_locations = [(7, 6), (16, 5), (4, 10), (5, 34), (12, 38), (18, 34), (21, 39)]
deck_locations = [(2, 8), (4, 20), (7, 30), (9, 37), (11, 13), (13, 22), (15, 32), (17, 10), (19, 25), (20, 15), (22, 35), (22, 7)]

protected_positions = set()
protected_positions.add(player_start)
for pos in assigned_locations:
    protected_positions.add(pos)
for pos in deck_locations:
    protected_positions.add(pos)

# Forest clusters
forest_seeds = []
attempts = 0
while len(forest_seeds) < 18 and attempts < 200:
    r = random.randint(2, ROWS - 3)
    c = random.randint(2, COLS - 3)
    if grid[(r, c)] in ("water", "cliff"):
        attempts += 1
        continue
    dist_to_pond = math.sqrt((r - pond_center[0])**2 + (c - pond_center[1])**2)
    if dist_to_pond < 5:
        attempts += 1
        continue
    too_close = False
    for sr, sc in forest_seeds:
        if abs(r - sr) + abs(c - sc) < 4:
            too_close = True
            break
    if too_close:
        attempts += 1
        continue
    forest_seeds.append((r, c))
    attempts += 1

for seed_r, seed_c in forest_seeds:
    cluster_size = random.randint(3, 8)
    cluster = [(seed_r, seed_c)]
    for _ in range(cluster_size - 1):
        base = random.choice(cluster)
        dr = random.choice([-1, 0, 0, 1])
        dc = random.choice([-1, 0, 0, 1])
        nr, nc = base[0] + dr, base[1] + dc
        if 1 <= nr < ROWS - 1 and 1 <= nc < COLS - 1:
            if grid[(nr, nc)] not in ("water", "cliff"):
                cluster.append((nr, nc))
    for pos in cluster:
        if pos not in protected_positions:
            grid[pos] = "forest"

for _ in range(40):
    r = random.randint(1, ROWS - 2)
    c = random.randint(1, COLS - 2)
    if grid[(r, c)] == "grass" and (r, c) not in protected_positions:
        dist_to_pond = math.sqrt((r - pond_center[0])**2 + (c - pond_center[1])**2)
        if dist_to_pond > 4:
            grid[(r, c)] = "forest"

# Stone patches
stone_seeds = []
attempts = 0
while len(stone_seeds) < 12 and attempts < 200:
    r = random.randint(2, ROWS - 3)
    c = random.randint(2, COLS - 3)
    if grid[(r, c)] in ("water", "cliff", "forest"):
        attempts += 1
        continue
    if (r, c) in protected_positions:
        attempts += 1
        continue
    stone_seeds.append((r, c))
    attempts += 1

for seed_r, seed_c in stone_seeds:
    cluster_size = random.randint(2, 5)
    cluster = [(seed_r, seed_c)]
    for _ in range(cluster_size - 1):
        base = random.choice(cluster)
        dr = random.choice([-1, 0, 1])
        dc = random.choice([-1, 0, 1])
        nr, nc = base[0] + dr, base[1] + dc
        if 1 <= nr < ROWS - 1 and 1 <= nc < COLS - 1:
            if grid[(nr, nc)] not in ("water", "cliff"):
                if (nr, nc) not in protected_positions:
                    cluster.append((nr, nc))
    for pos in cluster:
        if pos not in protected_positions:
            grid[pos] = "stone"

for _ in range(50):
    r = random.randint(1, ROWS - 2)
    c = random.randint(1, COLS - 2)
    if grid[(r, c)] == "grass" and (r, c) not in protected_positions:
        grid[(r, c)] = "stone"

# Dirt paths
def draw_path(grid, start, end, terrain="dirt", width=1, protected=set()):
    r, c = start
    er, ec = end
    path_hexes = []
    max_steps = 200
    steps = 0
    while (r, c) != (er, ec) and steps < max_steps:
        path_hexes.append((r, c))
        dr = 0 if r == er else (1 if er > r else -1)
        dc = 0 if c == ec else (1 if ec > c else -1)
        if random.random() < 0.3 and dr != 0 and dc != 0:
            if random.random() < 0.5:
                dr = 0
            else:
                dc = 0
        r += dr
        c += dc
        r = max(1, min(ROWS - 2, r))
        c = max(1, min(COLS - 2, c))
        steps += 1
    path_hexes.append((er, ec))
    for pr, pc in path_hexes:
        for ddr in range(-width + 1, width):
            for ddc in range(-width + 1, width):
                nr, nc = pr + ddr, pc + ddc
                if 1 <= nr < ROWS - 1 and 1 <= nc < COLS - 1:
                    if grid.get((nr, nc)) not in ("water", "cliff") and (nr, nc) not in protected:
                        grid[(nr, nc)] = terrain

draw_path(grid, (10, 5), (7, 6), "dirt", 1, protected_positions)
draw_path(grid, (7, 6), (4, 10), "dirt", 1, protected_positions)
draw_path(grid, (4, 10), (4, 20), "dirt", 1, protected_positions)
draw_path(grid, (10, 5), (11, 13), "dirt", 1, protected_positions)
draw_path(grid, (11, 13), (13, 22), "dirt", 1, protected_positions)
draw_path(grid, (16, 5), (17, 10), "dirt", 1, protected_positions)
draw_path(grid, (17, 10), (19, 25), "dirt", 1, protected_positions)
draw_path(grid, (5, 34), (9, 37), "dirt", 1, protected_positions)
draw_path(grid, (18, 34), (21, 39), "dirt", 1, protected_positions)

# Mountain clusters
mountain_seeds = []
attempts = 0
while len(mountain_seeds) < 5 and attempts < 300:
    r = random.randint(2, ROWS - 3)
    c = random.randint(2, COLS - 3)
    if grid[(r, c)] in ("water", "cliff"):
        attempts += 1
        continue
    if (r, c) in protected_positions:
        attempts += 1
        continue
    if abs(r - player_start[0]) + abs(c - player_start[1]) < 5:
        attempts += 1
        continue
    too_close = False
    for pr, pc in protected_positions:
        if abs(r - pr) + abs(c - pc) < 3:
            too_close = True
            break
    if too_close:
        attempts += 1
        continue
    mountain_seeds.append((r, c))
    attempts += 1

for seed_r, seed_c in mountain_seeds:
    cluster_size = random.randint(2, 4)
    cluster = [(seed_r, seed_c)]
    for _ in range(cluster_size - 1):
        base = random.choice(cluster)
        dr = random.choice([-1, 0, 1])
        dc = random.choice([-1, 0, 1])
        nr, nc = base[0] + dr, base[1] + dc
        if 1 <= nr < ROWS - 1 and 1 <= nc < COLS - 1:
            if grid[(nr, nc)] not in ("water", "cliff"):
                if (nr, nc) not in protected_positions:
                    adj_protected = False
                    for pr, pc in protected_positions:
                        if abs(nr - pr) + abs(nc - pc) < 2:
                            adj_protected = True
                            break
                    if not adj_protected:
                        cluster.append((nr, nc))
    for pos in cluster:
        if pos not in protected_positions:
            grid[pos] = "mountain"

# Scattered dirt
for _ in range(60):
    r = random.randint(1, ROWS - 2)
    c = random.randint(1, COLS - 2)
    if grid[(r, c)] == "grass" and (r, c) not in protected_positions:
        grid[(r, c)] = "dirt"


# Additional forest to reach ~20%
for _ in range(180):
    r = random.randint(1, ROWS - 2)
    c = random.randint(1, COLS - 2)
    if grid[(r, c)] == "grass" and (r, c) not in protected_positions:
        grid[(r, c)] = "forest"

# Additional stone to reach ~16%
for _ in range(155):
    r = random.randint(1, ROWS - 2)
    c = random.randint(1, COLS - 2)
    if grid[(r, c)] == "grass" and (r, c) not in protected_positions:
        grid[(r, c)] = "stone"

# Additional dirt to reach ~19%
for _ in range(140):
    r = random.randint(1, ROWS - 2)
    c = random.randint(1, COLS - 2)
    if grid[(r, c)] == "grass" and (r, c) not in protected_positions:
        grid[(r, c)] = "dirt"

# Additional mountain to reach ~3%
for _ in range(30):
    r = random.randint(2, ROWS - 3)
    c = random.randint(2, COLS - 3)
    if grid[(r, c)] == "grass" and (r, c) not in protected_positions:
        too_close = False
        for pr, pc in protected_positions:
            if abs(r - pr) + abs(c - pc) < 2:
                too_close = True
                break
        if not too_close:
            grid[(r, c)] = "mountain"

# Ensure protected positions are accessible
for pos in protected_positions:
    if grid[pos] in ("water", "cliff", "mountain"):
        grid[pos] = "grass"

# Count terrain
terrain_counts = {}
for pos, terrain in grid.items():
    terrain_counts[terrain] = terrain_counts.get(terrain, 0) + 1
total = ROWS * COLS
print("Terrain distribution:")
for t, count in sorted(terrain_counts.items(), key=lambda x: -x[1]):
    pct = count/total*100
    print(f"  {t}: {count} ({pct:.1f}%)")

# Build terrain grid
terrain_grid = []
for r in range(ROWS):
    row = []
    for c in range(COLS):
        row.append(grid[(r, c)])
    terrain_grid.append(row)

# Build location hexes
location_hexes = []

assigned_location_data = [
    {"row": 7, "col": 6, "card_id": "village_church"},
    {"row": 16, "col": 5, "card_id": "forest_chapel"},
    {"row": 4, "col": 10, "card_id": "roadside_shrine"},
    {"row": 5, "col": 34, "card_id": "bandit_hideout"},
    {"row": 12, "col": 38, "card_id": "skeleton_fort"},
    {"row": 18, "col": 34, "card_id": "goblin_camp"},
    {"row": 21, "col": 39, "card_id": "smuggler_den"},
]

for loc in assigned_location_data:
    location_hexes.append({
        "row": loc["row"],
        "column": loc["col"],
        "location_deck_file": None,
        "assigned_location_card_id": loc["card_id"],
        "assigned_npc_card_id": None,
        "location_state": 1,
        "shop_inventory": [],
        "turns_since_cycle": 0,
        "visited_this_turn": False
    })

deck_location_positions = [
    (2, 8), (4, 20), (7, 30), (9, 37), (11, 13), (13, 22),
    (15, 32), (17, 10), (19, 25), (20, 15), (22, 35), (22, 7)
]

for r, c in deck_location_positions:
    location_hexes.append({
        "row": r,
        "column": c,
        "location_deck_file": "beta_location_deck.json",
        "assigned_location_card_id": None,
        "assigned_npc_card_id": None,
        "location_state": 1,
        "shop_inventory": [],
        "turns_since_cycle": 0,
        "visited_this_turn": False
    })

# Starting inventory
starting_inventory = [
    {"card_id": "example_hunting_bow", "state": 2},
    {"card_id": "example_arrow_quiver", "state": 2},
    {"card_id": "example_tool_belt", "state": 2},
    {"card_id": "example_steel_arrows", "state": 1},
    {"card_id": "example_sniper_crossbow", "state": 1},
    {"card_id": "example_crossbow_bolts", "state": 1},
    {"card_id": "beta_junk_healing_herbs", "state": 2},
    {"card_id": "revival_smelling_salts", "state": 2},
    {"card_id": "revival_phoenix_dust", "state": 2},
]

# Build level data
level_data = {
    "grid_rows": ROWS,
    "grid_cols": COLS,
    "terrain": terrain_grid,
    "player_start": {"row": player_start[0], "col": player_start[1]},
    "starting_inventory": starting_inventory,
    "units": [],
    "location_hexes": location_hexes,
    "inaccessible_hexes": [],
    "card_drawing_hexes": [],
    "obstacles": []
}

# Write output
output_path = os.path.join("C:" + chr(92) + "Users" + chr(92) + "Tony" + chr(92) + "Desktop" + chr(92) + "This is the current one", "levels", "beta_test_small.json")
with open(output_path, "w", encoding="utf-8") as fout:
    json.dump(level_data, fout, indent=2)

print(f"Level file written to: {output_path}")
print(f"Grid size: {ROWS} rows x {COLS} columns = {ROWS * COLS} hexes")
print(f"Location hexes: {len(location_hexes)} (7 assigned + 12 deck-based)")
wk = "water"
mk = "mountain"
print(f"Pond hexes (water): {terrain_counts.get(wk, 0)}")
print(f"Mountain hexes: {terrain_counts.get(mk, 0)}")

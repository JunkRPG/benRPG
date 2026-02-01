import random

# Quest Card Template
quest_card_template = {
    "text": "Help {npc} reach {location} while avoiding {enemy_gang}.",
    "placeholders": {"npc": "NPC", "location": "Location", "enemy_gang": "Enemy"},
    "rewards": {"initial": 10, "completion": 10},
    "costs": {"hire_npc": 1},
    "mechanics": ["spawn_enemy_per_turn"],
    "success": ["npc_reaches_location"],
    "failure": ["npc_dies"]
}

# Decks
decks = {
    "NPC": [{"name": "Villager 1"}, {"name": "Merchant"}],
    "Location": [{"name": "Old Mill"}, {"name": "Market"}],
    "Enemy": [{"name": "Thieves"}, {"name": "Bandits"}]
}

# Generate Quest
def generate_quest(quest_card_template, decks):
    final_quest = {"text": quest_card_template["text"], "placeholders": {}}
    for placeholder, card_type in quest_card_template["placeholders"].items():
        card = random.choice(decks[card_type])
        final_quest["placeholders"][placeholder] = card
        final_quest["text"] = final_quest["text"].replace("{" + placeholder + "}", card["name"])
    final_quest["rewards"] = quest_card_template["rewards"]
    final_quest["costs"] = quest_card_template["costs"]
    final_quest["mechanics"] = quest_card_template["mechanics"]
    final_quest["success"] = quest_card_template["success"]
    final_quest["failure"] = quest_card_template["failure"]
    return final_quest

# Hex Grid
class HexGrid:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.grid = [[[] for _ in range(width)] for _ in range(height)]

    def place_entity(self, entity, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x].append(entity)
            entity.x = x
            entity.y = y

    def move_entity(self, entity, new_x, new_y):
        if 0 <= new_x < self.width and 0 <= new_y < self.height:
            self.grid[entity.y][entity.x].remove(entity)
            self.grid[new_y][new_x].append(entity)
            entity.x = new_x
            entity.y = new_y

# Entity
class Entity:
    def __init__(self, name, health):
        self.name = name
        self.health = health
        self.x = None
        self.y = None

# Quest Simulation
class Quest:
    def __init__(self, final_quest, grid, npc, location_pos):
        self.final_quest = final_quest
        self.grid = grid
        self.npc = npc
        self.location_pos = location_pos
        self.enemies = []
        self.turn = 0
        self.grid.place_entity(npc, 0, 0)

    def spawn_enemy(self):
        enemy_x = self.location_pos[0] + random.randint(-1, 1)
        enemy_y = self.location_pos[1] + random.randint(-1, 1)
        if 0 <= enemy_x < self.grid.width and 0 <= enemy_y < self.grid.height:
            enemy = Entity(self.final_quest["placeholders"]["enemy_gang"]["name"], 1)
            self.grid.place_entity(enemy, enemy_x, enemy_y)
            self.enemies.append(enemy)

    def check_success(self):
        return self.npc.x == self.location_pos[0] and self.npc.y == self.location_pos[1]

    def check_failure(self):
        return self.npc.health <= 0

    def take_turn(self):
        self.turn += 1
        print(f"Turn {self.turn}")
        if self.npc.x < self.location_pos[0]:
            self.grid.move_entity(self.npc, self.npc.x + 1, self.npc.y)
        elif self.npc.y < self.location_pos[1]:
            self.grid.move_entity(self.npc, self.npc.x, self.npc.y + 1)
        if "spawn_enemy_per_turn" in self.final_quest["mechanics"]:
            self.spawn_enemy()
        for enemy in self.enemies:
            if abs(enemy.x - self.npc.x) <= 1 and abs(enemy.y - self.npc.y) <= 1:
                self.npc.health -= 1
                print(f"{enemy.name} attacks {self.npc.name}, health now {self.npc.health}")

# Run the simulation
final_quest = generate_quest(quest_card_template, decks)
grid = HexGrid(5, 5)
npc = Entity(final_quest["placeholders"]["npc"]["name"], 5)
quest = Quest(final_quest, grid, npc, (4, 4))
print(final_quest["text"])
while not quest.check_success() and not quest.check_failure():
    quest.take_turn()
if quest.check_success():
    print("Quest succeeded!")
else:
    print("Quest failed!")
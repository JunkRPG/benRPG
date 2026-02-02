# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JunkRPG is a Pygame-based hexagonal grid RPG with a card-based inventory and crafting system. It consists of multiple interconnected applications:

- **JunkRPG34.py** - Main game engine
- **CardMaker21.py** - Card creation/management UI (primary card editor)
- **Level_Maker19.py** - Hexagonal level editor
- **CardTemplateMaker7.py** - Card visual layout designer
- **RangeViewer40.py** - Attack range visualization tool

## Running Applications

```bash
# Install dependencies
pip install -r requirements.txt

# Run main game
python JunkRPG34.py

# Run card editor
python CardMaker21.py

# Run level editor
python Level_Maker19.py

# Run range viewer
python RangeViewer40.py

# Run card template maker
python "CardTemplateMaker7 (Use this one to progress).py"
```

All apps launch fullscreen. Press ESC to exit.

## Architecture

### Core Modules
- **hexgrid.py** - Hexagonal grid math (distance, line-of-sight, adjacency) and rendering with zoom/pan. Contains `TERRAIN_CONFIG` for terrain types (grass, water, mountain, etc.) with accessibility and LOS blocking properties. Manages location hexes with shops and NPC storage.
- **player.py** - Player entity with HP, movement, attacks, inventory, skills
- **unit.py** - Enemy/NPC entities with allegiance (Hostile/Neutral/Allied) and 2-state transformation
- **inventory_card.py** - Multi-state card management with flip animation
- **constants.py** - UI colors and dimensions

### Game Systems (in JunkRPG34.py)
- **CardManager** - Loads cards from `card_index.json`, validates fields by card type, draws from decks
- **QuestManager** - Activates quests, tracks conditions, handles rewards (max 5 active)
- **InstanceManager** - Random event cards with weighted outcomes and player choices
- **TransitionManager** - Turn-cycle events (weather, spawns, card draws)

### Quest System (`quest_system.py`)
"Madlib" style templating where Quest Cards have placeholders like `[NPC1]`, `[Location1]` that get resolved at activation:
- **PlaceholderResolver** - Draws cards, spawns units, fills template text
- **ActiveQuest** - Tracks spawned units/locations, checks success/failure conditions
- Condition types: `unit_death`, `player_death`, `unit_reaches_location`, `turn_limit`, `enemy_defeated`

### Instance System (`instance_system.py`)
Random events with weighted probability outcomes:
- Outcome types: `damage_player`, `heal_player`, `draw_card`, `spawn_enemy`, `spawn_ally`, `player_choice`
- Player choice outcomes have risk/reward with success/failure branches

### Transition System (`transition_system.py`)
Turn-cycle cards that trigger world events:
- Outcome types: `draw_instance`, `spawn_enemy`, `spawn_npc`, `draw_junk`, `weather`, `flip_state`
- Weather effects modify movement/projectile range

### Data Storage (JSON)
- `cards/` - Card definitions, indexed by `card_index.json`
- `cards/decks/` - Deck configurations (also check `decks/` for legacy location)
- `levels/` - Level data with grid, units, terrain, obstacles
- `layouts/` - Card visual templates
- `theme.json` - Pygame-GUI theme configuration (required at runtime)

### Card System
Cards support 1 or 2 states (flip mechanic). Types: Junk, Document/Blueprint, Enemy, NPC, Location, Quest, Instance, Transition, Boss.

Card data structure includes: Name, Health, Movement (3-6), Melee Damage, Projectile Damage, Projectile Range, Allegiance, Special Skill.

Quest/Instance/Transition cards store `Outcomes`, `Placeholders`, `Success_Conditions`, `Failure_Conditions` as JSON strings within the card data.

### Game Flow
Turn-based: Player turn → Transition card turn → Enemy/NPC turns → Loop. Actions include movement (costs action points) and attacks (melee/projectile).

### Hex Grid Coordinate System
Uses (row, col) offset coordinates with 6 directional adjacency. HexGrid class handles distance calculation, line-of-sight checks, and centered view rendering.

## Development Workflow

1. **CardMaker** → Create cards (saved to `cards/*.json`)
2. **LevelMaker** → Design levels, place units (saved to `levels/*.json`)
3. **RangeViewer** → Test attack/effect ranges (7 patterns: Line of Sight, Melee, Area Effect, Echo, Multi Echo, Perimeter, Mist/Shadow)
4. **JunkRPG** → Play and test

## Gotchas

- Windows-style absolute paths throughout codebase
- Image paths in cards may reference non-existent files
- Limited error handling - errors crash to console
- Deck files may exist in both `cards/decks/` and `decks/` - systems check both locations
- `card_index.json` must be updated when adding cards for discovery
- Cards store nested JSON as strings (e.g., `Outcomes`, `Placeholders`) - must parse with `json.loads()`
- Single-player only (no multiplayer)

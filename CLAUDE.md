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
- **hexgrid.py** - Hexagonal grid math (distance, line-of-sight, adjacency) and rendering with zoom/pan
- **player.py** - Player entity with HP, movement, attacks, inventory, skills
- **unit.py** - Enemy/NPC entities with allegiance (Hostile/Neutral/Allied) and 2-state transformation
- **inventory_card.py** - Multi-state card management with flip animation
- **constants.py** - UI colors and dimensions

### Data Storage (JSON)
- `cards/` - Card definitions, indexed by `card_index.json`
- `cards/decks/` - Deck configurations
- `levels/` - Level data with grid, units, terrain, obstacles
- `layouts/` - Card visual templates
- `theme.json` - Pygame-GUI theme configuration (required at runtime)

### Card System
Cards support 1 or 2 states (flip mechanic). Types: Junk, Document/Blueprint, Enemy, NPC, Location, Quest, Instance, Boss.

Card data structure includes: Name, Health, Movement (3-6), Melee Damage, Projectile Damage, Projectile Range, Allegiance, Special Skill.

### Game Flow
Turn-based: Player turn → Enemy/NPC turns → Loop. Actions include movement (costs action points) and attacks (melee/projectile).

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
- Quest system card type exists but no implementation
- Single-player only (no multiplayer)
- `card_index.json` must be updated when adding cards for discovery

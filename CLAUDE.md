# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JunkRPG is a Pygame-based hexagonal grid RPG with a card-based inventory and crafting system. It consists of multiple interconnected applications:

- **JunkRPG34.py** - Main game engine
- **CardMaker21.py** - Card creation/management UI (primary card editor)
- **Level_Maker19.py** - Hexagonal level editor
- **Campaign_Maker.py** - Campaign creation tool (links levels into campaigns)
- **CardTemplateMaker7.py** - Card visual layout designer
- **RangeViewer40.py** - Attack range visualization tool

## Running Applications

```bash
# Install dependencies
pip install -r requirements.txt

# Run main game
python JunkRPG34.py

# Run main game with campaign
python JunkRPG34.py --campaign campaigns/my_campaign.json

# Run main game with specific level
python JunkRPG34.py --level levels/my_level.json

# Run card editor
python CardMaker21.py

# Run level editor
python Level_Maker19.py

# Run campaign maker
python Campaign_Maker.py

# Run range viewer
python RangeViewer40.py

# Run card template maker
python "CardTemplateMaker7 (Use this one to progress).py"
```

All apps launch fullscreen. Press ESC to exit.

## Architecture

### Core Modules
- **terrain_config.py** - Single source of truth for `TERRAIN_CONFIG` defining terrain types (grass, water, mountain, etc.) with color, accessibility, and LOS blocking properties. Imported by hexgrid.py, Level_Maker19.py, and Campaign_Maker.py.
- **deck_utils.py** - Centralized deck path resolution. All deck files are stored in `decks/` directory. Provides `resolve_deck_path()` function used by all game systems to ensure consistent path handling.
- **card_utils.py** - Safe card loading and validation utilities. Provides `load_card()` for safe card loading (returns None instead of crashing), `validate_card_json_fields()` for validating JSON fields like Outcomes/Placeholders, and `load_card_index()`, `card_exists()`, `validate_card_references()`.
- **hexgrid.py** - Hexagonal grid math (distance, line-of-sight, adjacency) and rendering with zoom/pan. Manages location hexes with shops and NPC storage.
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
- `decks/` - All deck configurations (single canonical location)
- `levels/` - Level data with grid, units, terrain, obstacles
- `campaigns/` - Campaign files linking levels together
- `layouts/` - Card visual templates
- `theme.json` - Pygame-GUI theme configuration (required at runtime)

### Campaign System
Campaigns link existing levels into playable sequences with deck configuration per stage.

Campaign file format (`campaigns/*.json`):
```json
{
  "campaign_id": "unique_id",
  "name": "Campaign Name",
  "description": "Description text",
  "stages": [
    {
      "stage_id": "stage_1",
      "name": "Stage Name",
      "level_file": "level_filename.json",
      "deck_config": {
        "transition_deck": "decks/transition.json",
        "quest_deck": "decks/quest.json",
        "instance_deck": "decks/instance.json",
        "junk_deck": "decks/junk.json"
      },
      "completion_conditions": {
        "type": "defeat_all_enemies",
        "target": "",
        "turn_limit": null
      },
      "next_stage": "stage_2"
    }
  ]
}
```

Completion condition types:
- `defeat_all_enemies` - Clear all hostile units
- `defeat_boss` - Defeat unit with name matching `target`
- `collect_item` - Collect item with name matching `target`
- `reach_location` - Player reaches location hex named `target`
- `survive_turns` - Survive until `turn_limit` turns pass

### Card System
Cards support 1 or 2 states (flip mechanic). Types: Junk, Document/Blueprint, Enemy, NPC, Location, Quest, Instance, Transition, Boss.

Card data structure includes: Name, Health, Movement (3-6), Melee Damage, Projectile Damage, Projectile Range, Allegiance, Special Skill.

Quest/Instance/Transition cards store `Outcomes`, `Placeholders`, `Success_Conditions`, `Failure_Conditions` as JSON strings within the card data.

### Weapon/Ammunition System
Projectile weapons can require ammunition:
- **Bow-type weapons**: Set `Requires_Ammo: true` - weapon has NO damage alone, all damage comes from equipped ammo
- **Standard weapons**: Set `Requires_Ammo: false` - weapon has built-in damage

**Weapon Range Properties** (all projectile weapons):
- `Range_Type` - Pattern: line_of_sight, area_effect, echo, multi_echo, perimeter, mist_shadow
- `Range_Distance` - Maximum range in hexes
- `Include_Position` - Include caster's hex in range (true/false)
- `Exclude_Adjacent` - Exclude adjacent hexes, for sniper-type weapons (true/false)
- `Compatible_Ammo` - Comma-separated ammo types that work with this weapon

**Ammunition Cards** (Junk_to_Consumable_Item with Type: Ammunition):
- `Ammo_Type` - Arrow, Bolt, Stone, Bullet, Dart
- `Ammo_Damage` - Damage dealt when ammunition is used
- `Runout_Chance` - Percentage chance (0-100) ammo runs out after each shot
- `Compatible_Weapons` - Comma-separated weapon names this ammo works with

When ammunition runs out, it reverts to state 1 (raw materials) and returns to inventory.

### Range Pattern System
The game uses a unified range calculation system supporting 7 patterns:

**Range Patterns** (used by weapons, tools, and skills):
- `line_of_sight` - Standard projectile path along hex lines (requires alignment and LOS)
- `melee` - Adjacent hexes only (distance 1)
- `area_effect` - All hexes within distance (like a healing aura)
- `echo` - Hexes at odd distances only (1, 3, 5, ...)
- `multi_echo` - Hexes at even distances only (2, 4, 6, ...)
- `perimeter` - Hexes at exactly the specified distance (ring)
- `mist_shadow` - 6 directional lines at 30°, 90°, 150°, 210°, 270°, 330°

**Range Modifiers**:
- `Include_Position` - Include caster's hex in range (useful for self-healing)
- `Exclude_Adjacent` - Exclude adjacent hexes (for sniper weapons that can't hit close targets)

**HexGrid Range Methods**:
- `calculate_range(pos, distance, pattern, include_pos, exclude_adj)` - Get all hexes in range
- `is_in_range(attacker_pos, target_pos, distance, pattern, include_pos, exclude_adj)` - Check if target is valid

### Tool Belt/Accessory System
Players have an accessory slot for tool belts that expand tool capacity:
- **Base**: 1 tool slot
- **With Tool Belt**: 1 + Extra_Tool_Slots (up to 4 total)

**Accessory Types** (Junk_to_Tool or Blueprint_to_Tool):
- `Type` - Tool_Belt, Accessory, Belt, or Pouch
- `Extra_Tool_Slots` - Number of additional tool slots (0-3)

Multi-slot tool system allows:
- Equipping multiple consumables, tools, or ammunition simultaneously
- Using specific tools by slot index
- Mixing healing items with ammunition for bow users

### Ranged Tool Effects
Tools and consumables can have ranged effects (e.g., healing potions thrown at allies):

**Effect Range Properties** (for tools and consumables):
- `Effect_Range_Type` - Pattern type (same as weapon ranges)
- `Effect_Range_Distance` - Maximum effect range
- `Effect_Include_Position` - Include self in range (default: true for healing)
- `Effect_Exclude_Adjacent` - Exclude adjacent hexes

Tools with effect range > 0 can target allies at range. Self-healing still works when Include_Position is true.

### Game Flow
Turn-based: Player turn → Transition card turn → Enemy/NPC turns → Loop. Actions include movement (costs action points) and attacks (melee/projectile).

### Hex Grid Coordinate System
Uses (row, col) offset coordinates with 6 directional adjacency. HexGrid class handles distance calculation, line-of-sight checks, and centered view rendering.

## Development Workflow

1. **CardMaker** → Create cards (saved to `cards/*.json`)
2. **LevelMaker** → Design levels, place units (saved to `levels/*.json`)
3. **CampaignMaker** → Link levels into campaigns with deck config (saved to `campaigns/*.json`)
4. **RangeViewer** → Test attack/effect ranges (7 patterns: Line of Sight, Melee, Area Effect, Echo, Multi Echo, Perimeter, Mist/Shadow)
5. **JunkRPG** → Play and test

## Gotchas

- Windows-style absolute paths throughout codebase
- Image paths in cards may reference non-existent files
- All deck files must be in `decks/` directory (use `deck_utils.resolve_deck_path()` for path resolution)
- Use `card_utils.load_card()` for safe card loading (returns None on missing files instead of crashing)
- `card_index.json` must be updated when adding cards for discovery
- Cards store nested JSON as strings (e.g., `Outcomes`, `Placeholders`) - CardMaker validates JSON before saving, parse with `json.loads()` at runtime
- JSON fields validated by CardMaker: `Outcomes`, `Choices`, `Placeholders`, `Success_Conditions`, `Failure_Conditions`, `Rewards`, `Upgrade_Material_Cost`
- Supports 2-player local multiplayer mode
- Game supports both old campaign format (`levels` array) and new format (`stages` array with deck_config)
- Weapon cards with `Requires_Ammo: true` deal 0 damage without equipped ammunition
- Tool slot system uses both legacy `equipped_tool` and new `equipped_tools` list for backwards compatibility
- `card_utils.validate_all_card_fields()` validates both JSON fields and weapon/ammunition fields

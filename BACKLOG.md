# Backlog — Deferred Work Items

Items discussed but deferred during planning. Check this file at the start of related work.

---

## Teleportation System — Deferred Items
*Deferred from: Teleportation Pad Plan (Feb 2026)*
*Core teleportation was implemented. These items were discussed but scoped out:*

### Campaign Maker UI for Teleport Links
- Add teleport link editing to Campaign_Maker.py
- UI to pair pads between levels visually (select pad A from level 1, pad B from level 2)
- Currently teleport_links must be hand-edited in campaign JSON

### Recruiting Allied NPCs to Party (Junk Payment)
- When adjacent to an Allied NPC, player can spend Junk cards to recruit them as a party member
- Recruited NPCs follow the player and can be brought through teleport pads
- Discussed cost system: pay Junk cards proportional to NPC strength
- Distinguishes "party member" (recruited, follows you) from "allied unit" (just friendly, acts independently)

### Advanced Party Management
- Party roster screen showing all recruited NPCs
- Dismiss/release NPCs from party
- Set NPC behavior (follow player, guard location, patrol)
- Party size limits based on player level or equipment

---

## Player & Unit Transition Cards — Deferred Items
*Deferred from: Player/Unit Transition Cards Plan (Feb 2026)*
*Core player transition, unit transition, quest NPC spawn, and trip_fall were implemented.*

### Level_Maker UI for Transition Cards
- Add fields in Level_Maker19.py to set `player_transition_card`, `unit_transition_card`, and `unit_transition_trigger_chance` per level
- Currently these must be hand-edited in level JSON

### CardMaker Validation for Transition Card Subtypes
- Add validation in CardMaker21.py to distinguish world/player/unit transition card subtypes
- Ensure outcome types match the intended transition context (e.g. trip_fall only valid for unit transitions)

### Additional Unit Transition Outcomes
- `buff` — temporarily boost unit stats for one turn
- `rage` — increase melee damage but reduce defense
- `confusion` — unit moves in random direction instead of AI
- `heal` — unit recovers HP at start of turn

### Additional Player Transition Outcomes
- `buff_player` — temporarily boost player stats
- `debuff_player` — temporarily reduce player stats
- `find_item` — draw a random junk card to inventory
- `ambush` — spawn enemy adjacent to player

---

## Content Pipeline & Tooling — Deferred Items
*Deferred from: CardMaker/Template Generator/Content Pipeline Plan (Feb 2026)*
*Completed: template generator narrative field types, 8 card templates, visual editors for Quest/Location cards.*

### Actually Generate Cards from Templates
- Run the 8 new templates (instance_combat, instance_social, instance_exploration, instance_environmental, instance_funny, transition_forest, transition_wasteland, transition_mountain) to create 59-71 actual cards and populate decks
- These templates exist in `card_templates/` but haven't been run with `--count` to create real cards yet

### Hand-Author Quest Cards Using Visual Editors
- Create 10-15 new quest cards using the new Placeholder/Condition/Rewards/Chain editors
- Goal: expand quest pool from 10 to 25+ for replayability
- Include quest chains using Chain_Config (3-step narrative arcs)

### CardTemplate Generator UI Updates
- Update CardTemplateGeneratorUI.py to support the new `json_template` and `text_choice` field types
- Currently the UI only handles `fixed`, `int`, `float`, `choice`, `scaled`

### CardMaker UX Improvements
- **Deck picker**: File browser for `decks/` directory when a field references a deck
- **Card ID picker**: Searchable list from card_index.json when a field references a card
- **"Add to Deck" button**: After creating a card, offer to add it to an existing deck
- **Duplicate card**: Copy an existing card as a starting point for a new one

### More Content Cards (Mix of Templates + Hand-Authored)
*Card counts updated Feb 2026:*
- Location Cards: 48 (target met)
- Enemy Cards: 57 (target met)
- NPC Cards: 84 (target met)
- Junk Cards: 155 (target met)
- Document Cards: 75 (target met)
- Instance Cards: 107
- Quest Cards: 26 (goal was 25+, met)
- Transition Cards: 23
- Boss Cards: 15
- **Total: 590 cards indexed**

Focus areas for future content: more quest chains, more transition variety, campaign-specific boss encounters

---

## Allegiance System Phase 2 — Dynamic Allegiance Changes
*Deferred from: Decouple Allegiance from States + Universal Behavior Trees Plan (Feb 2026)*
*Phase 1 implemented: allegiance decoupled from state switching, per-allegiance behavior trees (Hostile/Neutral/Allied), universal behavior tree execution for all units, set_allegiance() method.*
*Phase 2 implemented (Feb 2026): Allegiance_Priority field, advance_allegiance() method, convert_enemy healer behavior.*

### ~~Allegiance Priority Order~~ — DONE
- ~~`Allegiance_Priority` field per unit: ordered list like `["Hostile", "Neutral", "Allied"]`~~
- ~~Defines the natural progression of allegiance for that unit type~~
- ~~Used by `advance_allegiance()` to step through the priority list~~

### ~~advance_allegiance() Method~~ — DONE
- ~~Steps a unit to the next allegiance in their priority list~~
- ~~Triggered by specific game events (defeat+revive, taming, quest rewards)~~
- ~~Includes log messages and visual effects for the transition~~

### ~~convert_enemy Healer Behavior~~ — DONE
- ~~New behavior tree entry: `convert_enemy`~~
- ~~Healer revives a dead hostile unit → advances allegiance via priority list~~
- ~~Requires: dead hostile in heal range, healer has `convert_enemy` in their behavior tree~~
- ~~4-turn cooldown between conversions~~

### Allegiance Regression Mechanics — Deferred to Phase 3
- Allied units can regress to Neutral under certain conditions (e.g. low morale, fear effects)
- Neutral units can become Hostile if attacked by the player
- Regression triggers: proximity to overwhelming enemy force, special transition card effects
- Visual indicators for allegiance instability (flashing allegiance icon)

---

## Junk Pile Feature — Deferred Items
*Deferred from: 3-Level Campaign + Junk Pile Feature Plan (Feb 2026)*
*Core junk pile mechanic implemented: loading from level JSON, search/move/place interactions, save/load, amber rendering.*

### Level Maker UI for Junk Piles
- Add junk pile placement tool to Level_Maker19.py
- UI to set search_chance and searches_remaining per pile
- Currently junk piles must be hand-edited in level JSON

### Junk Pile Visual Icon Customization
- Custom icon for junk piles instead of default token shape
- Could use "starburst" or a new "pile" icon type
- Different icons for searched vs unsearched piles

---

## UX & Polish — Deferred Items
*Consolidated from Future plans.txt (Feb 2026)*
*Most items from that file were already implemented. These remain relevant:*

### Death Recap / Defeat Screen Enhancement
- Show the final moment before death so the player knows why they died
- Slow-motion or freeze-frame replay of the killing blow
- Display attacker name, damage dealt, and attack type

### Inventory Tooltips
- Hover tooltips for inventory and crafting items using Pygame-GUI's UITextBox
- Show detailed card info (stats, description) without requiring selection
- Small delay before tooltip appears to avoid flicker

### Sprite Caching / Performance
- Pre-scale and cache unit images in Player and Unit constructors instead of scaling every frame in HexGrid.draw()
- Consider dirty rectangle rendering (pygame.display.update(rects)) for draw optimization

### ~~JunkRPG34.py Module Split~~ — DONE
- ~~Split main file into separate modules~~
- Completed Feb 2026: 26 classes extracted to `screens/` package + `game_context.py` shared namespace
- JunkRPG34.py reduced from 11,786 to 6,711 lines (GameScreen + Game + setup/loop remain)
- 10 new files: `game_context.py`, `screens/__init__.py`, `screens/card_manager.py`, `screens/menu_screens.py`, `screens/pause_screens.py`, `screens/game_overlay_screens.py`, `screens/party_screens.py`, `screens/crafting_screen.py`, `screens/location_screens.py`, `screens/inventory_screens.py`, `screens/tabbed_menu_screen.py`

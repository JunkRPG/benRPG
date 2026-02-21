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
- Location Cards: needs 15-20+ (currently 7)
- Enemy Cards: needs 20-30+ (currently 8)
- NPC Cards: needs 15-20+ (currently 8)
- Junk Cards: needs 20-30+ (currently 8)
- Document Cards: needs 10-15+ (currently 4)

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

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

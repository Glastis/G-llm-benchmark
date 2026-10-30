# Mini city builder

Build a small city-building game for the desktop, in **C++20 with SDL2 and libpng**, with the tiles provided in `assets/`. Follow the specification to the letter. A person will play it, so make it pleasant to use and to look at.

## Deliverables and constraints

- **C++20, SDL2 and libpng only**: no other library (no SDL_image, no SDL_ttf), no code generator, no network access. Both are installed with their headers (`pkg-config --cflags --libs sdl2 libpng`).
- The project must build from the workspace root with exactly `cmake -B build -G Ninja && cmake --build build`, which must produce the executable `build/city`. The game is started as `build/city` from the workspace root and loads its tiles from `assets/`.
- The game must never crash and must not print any error.
- There is no screen in the workspace: to run the game there, set `SDL_VIDEODRIVER=dummy`, and it runs without showing anything.
- The game must also offer the test mode described at the end of this statement.
- You have 60 minutes at most. Whatever is in the workspace when time runs out is what gets graded. It doesn't mean you have to spend 60 minutes, it means it's the hard upper limit.

## The tiles

`assets/` holds 151 tiles of 16×16 pixels (Kenney's Tiny City and Tiny Town packs, CC0, see the license files):

- `assets/opaque/`: tiles that fill a whole cell, such as ground, roads, walls and roofs;
- `assets/transparent/`: tiles with transparent pixels, meant to be drawn over another tile, such as trees, fences, vehicles, people and roof corners.

Each file is named after what it shows (`wall_red_door.png`, `road_line_horizontal_top.png`, `tree_tall_green_top.png`…). Look at them. How you depict the ground, the roads and each type of building with these tiles is up to you: compose the buildings from several tiles, and make the roads join up visually. Each type of building must be recognisable and distinct from the others.

## The window

- The map has 24 × 16 cells of 32 × 32 pixels, drawn at the top-left of the window, at 1:1 scale: a tile drawn at twice its size fills one cell. Cell (x, y), with x from 0 to 23 and y from 0 to 15, covers window pixels 32x to 32x+31 horizontally and 32y to 32y+31 vertically. The rest of the window, below or beside the map, holds the controls and the displays: design that UI yourself, so that the tools, play/pause and restart work with the mouse as well as with their keyboard shortcuts.
- Tools: road, house, shop, factory, park and bulldozer. A click on a tool's button selects it, and so do the keys `1` to `6`, in that order. The selected tool must be visible.
- A left click on a cell of the map applies the selected tool there (see Placement). A right click on a building selects it (see Research and upgrades).
- A play/pause button, and the space bar, start and pause the clock. The game starts paused. While it runs, it advances by one tick every 500 ms.
- A restart button, and the `R` key, bring the game back to its initial state, paused.
- Money, population, tick and status (`playing`, `won` or `bankrupt`) are always readable, in the window or in its title bar. The end of the game, whether won or bankrupt, must also be obvious on screen.
- Closing the window, or the `Escape` key, quits.

## Buildings

| Type        | Footprint (width × height, in cells) | Cost | Upkeep per tick |
|-------------|--------------------------------------|------|-----------------|
| road        | 1 × 1                                | 10   | 0               |
| house       | 2 × 2                                | 100  | 0               |
| shop        | 2 × 2                                | 250  | 2               |
| factory     | 3 × 2                                | 400  | 5               |
| park        | 2 × 2                                | 60   | 1               |
| decorations | variable                             | 10   | 0               |

Decorations are purely visual, and they are yours to design: which ones exist, their footprints, what they look like and how the player places them are up to you. Each costs 10 and has no upkeep. They play no part in the simulation rules, but they occupy their cells, follow the placement rules and are removed by the bulldozer like any other building.

### Placement

- A building placed at cell (x, y) has its **top-left** cell there. Its footprint spans x to x+width-1 and y to y+height-1.
- Placement is refused, with no change and no charge, when part of the footprint is off the map or already occupied, when the money is below the cost, or when the game is over (won or bankrupt).
- Otherwise the cost is deducted and the building is added. Buildings are kept in placement order.
- The bulldozer, applied to any cell of a building, removes that whole building, without refund. It does nothing on an empty cell, or when the game is over.
- Placing and bulldozing work whether the clock is running or paused.

## Simulation rules

At the start: money 1000, tick 0, no building, status `playing`.

Definitions:

- A building is **connected** when at least one cell orthogonally adjacent to its footprint, outside it, holds a road.
- The **distance** between two buildings is the Chebyshev distance between their footprints: `max(gap_x, gap_y)`, where `gap_x` is the number of columns strictly between them, plus one, or 0 when their columns overlap, and likewise for `gap_y`. Two buildings that touch, even by a corner, are at distance 1. Formally, for footprints A and B: `gap_x = max(0, B.x − (A.x + A.width − 1), A.x − (B.x + B.width − 1))`.
- Each house has a number of **residents**, starting at 0. **Population** is the sum of the residents of all houses.

A tick does the following, in this order:

1. The tick counter goes up by 1.
2. Each house, in placement order, moves its residents **one step** toward its target: +1 if below, −1 if above, no change if equal. The target is 0 for a house that is not connected. For a connected house it is its capacity:
   - 8;
   - plus 4 if at least one park is at distance ≤ 3 of the house;
   - minus 3 for each factory at distance ≤ 2 of the house (smoke);
   - parks and factories count whether they are connected or not;
   - never below 0.
3. The population is computed from the new residents.
4. **Jobs**: 10 per connected factory, plus 4 per connected shop. Income is 2 × min(population, jobs).
5. Each connected shop also earns 3 for each house with at least one resident at distance ≤ 4 of the shop, whether that house is connected or not.
6. On every tick that is a multiple of 10, taxes add the population to the income.
7. Money increases by the income and decreases by the upkeep of **every** building, connected or not.
8. If the population is at least 150, the status becomes `won`. Otherwise, if money is below 0, it becomes `bankrupt`. Once the game is over, ticks no longer change anything.

Every value is an integer.

## Research and upgrades

Design a research and upgrade system yourself: which upgrades exist, for which buildings, how many levels, their costs, durations and effects, and how the research is organised are up to you. The frame is fixed:

- Research is started from the UI. It costs money and lasts a number of ticks. When it completes, it unlocks an upgrade.
- A selected building is highlighted, and a panel shows its type, its state and the upgrades available for it. An unlocked upgrade is bought for that building from this panel, with the mouse.
- Starting research or buying an upgrade is refused, with no change and no charge, when the money is below its cost or when the game is over.
- Each upgrade shows what it does, and does exactly that. An upgraded building looks different from a plain one.
- As long as no research is started, the game follows the simulation rules above exactly. Restart also clears the research and the upgrades.

## Test mode

`build/city --script <file> --out <file>` runs the commands of the script, one per line, then quits. It drives the same game, with the same code and the same rendering, as the mouse and the keyboard do. The clock does not run by itself in this mode, and the game must work there with `SDL_VIDEODRIVER=dummy`.

| Command                | Effect                                                         |
|------------------------|----------------------------------------------------------------|
| `place <type> <x> <y>` | applies that tool to cell (x, y), as a left click would         |
| `bulldoze <x> <y>`     | applies the bulldozer to cell (x, y)                            |
| `step <n>`             | runs n ticks at once                                            |
| `reset`                | same as restart                                                 |
| `screenshot <file>`    | saves the whole window, exactly as it would be shown, as a PNG  |

`<type>` is `road`, `house`, `shop`, `factory` or `park`. Coordinates may lie off the map: the placement is then refused, like any other. Once the game is over, a tick changes nothing, not even the tick counter.

After each command, the program writes one line to the `--out` file:

```
<result> <tick> <money> <population> <status>
```

`<result>` is `ok` or `refused` for `place` and `bulldoze` (`refused` when nothing happened), and `-` for the other commands. The other values are the state after the command. For example, `place house 3 4` then `step 2` on a new game give:

```
ok 0 900 0 playing
- 2 900 0 playing
```

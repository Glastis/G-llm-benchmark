# Elevator simulation in C++20

Write a command-line program that simulates a group of elevators serving passengers in a building, following the exact rules below. Follow them to the letter: every ordering and tie-break matters.

## Deliverables and constraints

- **C++20, standard library only**: no third-party library, no code generator, no network access.
- The project must build from the workspace root with exactly `cmake -B build -G Ninja && cmake --build build`, which must produce the executable `build/sim`.
- It must build **without any warning** with `-Wall -Wextra`: enable these flags in your `CMakeLists.txt`.
- Usage: `build/sim --scenario <input file> --out <output file>`.
- **Performance**: a scenario with 200,000 passengers, 16 elevators and 100 floors, with arrival times spread up to 10^15, must run in under one second once built with the command above. Do not advance the clock one tick at a time, and use 64-bit integers.
- **Errors**: on invalid arguments or invalid input, print a single line starting with `error:` to stderr and exit with code 2. The program must never crash or hang.
- `examples/` holds an input file and the exact output expected for it.
- You have 30 minutes at most. Whatever is in the workspace when time runs out is what gets graded. It doesn't mean you have to spend 30 minutes, it means it's the hard upper limit.

## Input format

Plain text, one directive per line, tokens separated by spaces or tabs. `#` starts a comment that runs to the end of the line. Blank lines are ignored.

Header directives. Each one must appear exactly once, in any order, before the first `passenger` line:

| Directive     | Meaning                                  | Constraint        |
|---------------|------------------------------------------|-------------------|
| `floors F`    | floors are numbered `0` to `F-1`         | 2 ≤ F ≤ 1,000,000 |
| `elevators E` | elevators are numbered `0` to `E-1`      | 1 ≤ E ≤ 1,000     |
| `capacity C`  | maximum number of riders in one elevator | 1 ≤ C ≤ 1,000,000 |
| `travel T`    | ticks needed to move one floor           | 1 ≤ T ≤ 1,000,000 |
| `door D`      | ticks a stop lasts                       | 1 ≤ D ≤ 1,000,000 |

Optional directive, at most once and also before the first `passenger` line: `start f0 f1 … f(E-1)`, exactly E floors between 0 and F-1, the initial floor of each elevator. Without it, every elevator starts at floor 0.

Then any number of lines `passenger ID TIME FROM TO`, in any order:

- `ID`: an integer ≥ 0, unique;
- `TIME`: the arrival tick, 0 ≤ TIME ≤ 10^15;
- `FROM` and `TO`: floors between 0 and F-1, with `FROM ≠ TO`.

Every value is a decimal integer that fits in a signed 64-bit integer. Anything else is an error: unknown directive, wrong number of tokens, a token that is not an integer, a value out of range, a missing or repeated header directive, a header directive after a `passenger` line, a repeated passenger ID.

## The model

Time is counted in integer ticks. A passenger's **direction** is up if `TO > FROM`, down otherwise.

Each elevator has a floor, a direction (up, down or idle), its riders and the passengers that were assigned to it and are still waiting. It is either free or busy with an action until a given tick. At the start, every elevator is idle, free and empty.

An elevator performs two kinds of actions:

- **MOVE**: goes from floor f to the next floor in its direction, f+1 for up and f-1 for down, in T ticks. Its floor stays f during the move and becomes the next floor when the move ends.
- **STOP** at floor f, started at tick t:
  1. every rider whose destination is f gets out;
  2. then the waiting passengers assigned to this elevator, standing at floor f, whose direction equals the elevator's direction, board in order of (arrival tick, ID) as long as the elevator holds fewer than C riders. The others remain assigned to it and keep waiting.

  Exits and boardings happen at tick t. The stop keeps the elevator busy until t + D.

## Simulation loop

Ticks are processed in increasing order, and only the ticks where something happens: a passenger arrives or an action ends. At each such tick t, in this order:

1. Every action that ends at t ends: a MOVE updates the floor. The elevator becomes free.
2. The passengers arriving at t are taken in increasing ID order, and each one is assigned to one elevator (rule A). An assignment is final.
3. Each free elevator, in increasing index order, decides its next action (rule D) and starts it at t, or stays idle.

The simulation ends when every passenger has got out.

### Rule A: assignment

For a passenger standing at floor s, each elevator e gets a cost:

`cost(e) = |floor(e) − s| + n(e) + penalty(e)`

- `floor(e)` is the elevator's current floor, as defined above: during a move, the floor it left;
- `n(e)` is the number of its riders plus the number of waiting passengers already assigned to it;
- `penalty(e)` is F if e's direction is up and s < floor(e), or if its direction is down and s > floor(e). It is 0 otherwise, in particular for an idle elevator.

The passenger goes to the elevator with the lowest cost. A tie goes to the lowest index.

Step 1 runs before step 2, so an elevator whose move ends at t already has its new floor. Its direction is still the one it had before step 3 of tick t.

### Rule D: decision of a free elevator at floor f

Let R be its riders and W the waiting passengers assigned to it.

- `serve(d)` is true if a rider's destination is f, or if a passenger of W stands at floor f with direction d while the elevator holds fewer than C riders.
- `ahead(d)` is true if a rider's destination or a W passenger's floor is strictly beyond f in direction d: above f for up, below f for down.

1. If R and W are both empty, the direction becomes idle and the elevator does nothing.
2. If the direction is idle: when some W passengers stand at floor f, the direction becomes that of the first of them by (arrival tick, ID). Otherwise, take the first W passenger by (arrival tick, ID): the direction becomes up if that passenger's floor is above f, down if it is below.
3. If `serve(direction)`: STOP.
4. Otherwise, if `ahead(direction)`: MOVE.
5. Otherwise the direction reverses, then: if `serve(direction)`, STOP, else MOVE.

## Output format

The program writes the following lines to the `--out` file:

1. One line per STOP, in the order the stops start (by tick, then by elevator index):

   `<tick> <elevator> <floor> <up|down> out=<ids> in=<ids>`

   `out` lists the passengers getting out, in increasing ID order. `in` lists the passengers boarding, in boarding order. IDs are separated by commas without spaces, and `-` stands for an empty list.
2. One line per passenger, in increasing ID order:

   `passenger <id> elevator <e> wait <w> ride <r>`

   w is the boarding tick minus the arrival tick, r is the exit tick minus the boarding tick.
3. A final line:

   `summary passengers <n> makespan <m> avg_wait <a> max_wait <x> avg_ride <b>`

   m is the tick of the last exit. The averages are printed with exactly two decimals, like `printf("%.2f")`. With no passenger at all, every value is 0, and the averages are `0.00`.

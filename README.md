# Pimoroni Presto Arcade

An arcade carousel for the 240 x 240 Pimoroni Presto, controlled with a
QwSTPad on the board's Qw/ST (I2C) connector.

The game catalogue and controls guide is published with GitHub Pages at
[robmarkcole.github.io/pimoroni-presto-arcade](https://robmarkcole.github.io/pimoroni-presto-arcade/).
The no-build site source lives in [`docs/`](docs/).

## Games

- **Awesome Game** — dodge falling obstacles and collect treasure.
- **Random Maze** — escape increasingly difficult generated mazes.
- **Frogger** — cross traffic and ride platforms through four progressively
  faster themes: River, Night, Ice, and Lava. Game Over retries the current
  level rather than discarding level progress.
- **Ogre Smash!** — score as many points as possible with ten lives by
  jumping hazards, smashing traffic, and collecting lightning and mega bombs.

All games use the QwSTPad at its default address (`0x21`) on I2C 0, with SDA
on pin 40 and SCL on pin 41. Direction buttons move, `+` starts or restarts,
and `-` returns to the carousel.

## Ogre Smash! prototype

Ogre Smash is an endless score attack with ten lives. Traffic becomes faster
and more frequent the longer the ogre survives. Normal cars are quick targets;
long trucks are harder to avoid but award more points. Both can be smashed,
jumped, or zapped. Lakes and road holes must be jumped. Occasional duck flocks
cross the road—hitting one deducts 50 points and leaves a blood splatter without
costing a life. Smash a nearby vehicle to turn it into a lightning pickup,
collect the bolt to grow stronger, then fire up the current lane to destroy
every vehicle the lightning hits. Tanks appear later in the run. Jumping a tank
makes it launch a dodgeable missile before self-destructing; destroying one
instead arms a mega bomb that clears all cars and trucks on screen. After the
tenth life, the final score is saved to a large-print, persistent top-five
leaderboard. Distinct action sound effects play through Presto's onboard piezo
buzzer; background music is disabled.

| QwSTPad input | Action |
| --- | --- |
| `L` / `R` | Change lane |
| `U` | Jump over vehicles, lakes, and road holes |
| `A` | Smash a nearby car, truck, or tank |
| `B` | Use a mega bomb when held; otherwise fire charged lightning |
| `+` | Start or retry |
| `-` | Return to the arcade carousel |

## Frogger

Guide the frog from the grass at the bottom of the screen to the far bank.
Cross three traffic lanes without being hit, then use the moving platforms to
cross three water lanes. Reaching any point on the far bank completes the
level.

### Controls

| QwSTPad input | Action |
| --- | --- |
| D-pad | Move one cell up, down, left, or right |
| `+` | Advance to the next level, retry, or play again |
| `-` | Return to the arcade carousel |

The QwSTPad status LEDs show remaining lives during play. All four illuminate
when a level is complete.

### Rules and scoring

- The frog starts each level with the lives carried over from the previous
  level.
- A collision with traffic, falling in the water, or leaving the screen costs
  one life and returns the frog to the start of the current level.
- Running out of lives shows Game Over. Retrying restores three lives while
  preserving the current level and score.
- Each forward hop scores 10 points.
- Completing a level awards `100 × level` points.
- Completing Lava, the fourth level, wins the game.

### Levels

| Level | Theme | Speed | Description |
| ---: | --- | ---: | --- |
| 1 | River | 1.00× | The baseline road and river crossing. |
| 2 | Night | 1.25× | Darker lanes with faster traffic and platforms. |
| 3 | Ice | 1.55× | Bright frozen colours and a sharper pace. |
| 4 | Lava | 1.90× | The fastest crossing over lava and hot asphalt. |

### Screenshots

| River | Night |
| :---: | :---: |
| ![Frogger River level](docs/images/frogger-level-1-river.png) | ![Frogger Night level](docs/images/frogger-level-2-night.png) |

| Ice | Lava |
| :---: | :---: |
| ![Frogger Ice level](docs/images/frogger-level-3-ice.png) | ![Frogger Lava level](docs/images/frogger-level-4-lava.png) |

The screenshots use the game's native resolution, geometry, sprites, and
colour palettes. Regenerate them with:

```sh
uv run --with pillow tools/render_frogger_screenshots.py
```

## Install

With Presto connected over USB and `mpremote` available:

```sh
mpremote cp main.py awesome_game.py random_maze.py frogger.py ogre_smash.py :
mpremote reset
```

`awesome_game.py` also needs the two original pirate `.16bpp` sprite sheets
from the Presto demo bundle. The carousel uses an explicit game allowlist, so
other demo scripts can remain on the board without appearing as arcade games.

# Pimoroni Presto Arcade

An arcade carousel for the 240 x 240 Pimoroni Presto, controlled with a
QwSTPad on the board's Qw/ST (I2C) connector.

## Games

- **Awesome Game** — dodge falling obstacles and collect treasure.
- **Random Maze** — escape increasingly difficult generated mazes.
- **Frogger** — cross traffic and ride platforms through four progressively
  faster themes: River, Night, Ice, and Lava. Game Over retries the current
  level rather than discarding level progress.

All games use the QwSTPad at its default address (`0x21`) on I2C 0, with SDA
on pin 40 and SCL on pin 41. Direction buttons move, `+` starts or restarts,
and `-` returns to the carousel.

## Install

With Presto connected over USB and `mpremote` available:

```sh
mpremote cp main.py awesome_game.py random_maze.py frogger.py :
mpremote reset
```

`awesome_game.py` also needs the two original pirate `.16bpp` sprite sheets
from the Presto demo bundle. The carousel uses an explicit game allowlist, so
other demo scripts can remain on the board without appearing as arcade games.

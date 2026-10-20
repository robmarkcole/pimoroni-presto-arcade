# ICON joystick
# NAME Frogger
# DESC Cross the road and river with the QwSTPad!

import machine
import time

from machine import I2C
from presto import Presto
from qwstpad import ADDRESSES, QwSTPad


I2C_PINS = {"id": 0, "sda": 40, "scl": 41}
I2C_ADDRESS = ADDRESSES[0]

presto = Presto(ambient_light=True)
display = presto.display
WIDTH, HEIGHT = display.get_bounds()

CELL = 24
HUD_HEIGHT = 24
FROG_SIZE = 16
HOME_COLUMNS = (0, 2, 4, 6, 8)
LEVEL_SPEEDS = (1.0, 1.25, 1.55, 1.9)
FINAL_LEVEL = len(LEVEL_SPEEDS)
LEVEL_NAMES = ("RIVER", "NIGHT", "ICE", "LAVA")

BLACK = display.create_pen(0, 0, 0)
WHITE = display.create_pen(255, 255, 255)
GRASS = display.create_pen(35, 125, 55)
ROAD = display.create_pen(48, 48, 55)
WATER = display.create_pen(25, 90, 180)
MEDIAN = display.create_pen(64, 150, 70)
FROG = display.create_pen(100, 255, 80)
FROG_DARK = display.create_pen(25, 110, 30)
LOG = display.create_pen(145, 82, 38)
LOG_LIGHT = display.create_pen(205, 135, 65)
YELLOW = display.create_pen(255, 220, 40)
RED = display.create_pen(235, 55, 55)
CYAN = display.create_pen(50, 220, 235)
ORANGE = display.create_pen(255, 135, 40)
PINK = display.create_pen(245, 80, 170)

LEVEL_THEMES = (
    {
        "grass": GRASS, "water": WATER, "road": ROAD, "median": MEDIAN,
        "lane": YELLOW, "log": LOG, "log_light": LOG_LIGHT,
    },
    {
        "grass": display.create_pen(20, 70, 75),
        "water": display.create_pen(45, 20, 100),
        "road": display.create_pen(20, 20, 35),
        "median": display.create_pen(30, 75, 90),
        "lane": CYAN,
        "log": display.create_pen(100, 70, 160),
        "log_light": display.create_pen(170, 130, 220),
    },
    {
        "grass": display.create_pen(170, 215, 230),
        "water": display.create_pen(75, 175, 225),
        "road": display.create_pen(75, 105, 130),
        "median": display.create_pen(205, 235, 240),
        "lane": WHITE,
        "log": display.create_pen(45, 115, 155),
        "log_light": display.create_pen(175, 225, 250),
    },
    {
        "grass": display.create_pen(45, 25, 25),
        "water": display.create_pen(225, 45, 10),
        "road": display.create_pen(70, 30, 35),
        "median": display.create_pen(95, 45, 25),
        "lane": display.create_pen(255, 185, 20),
        "log": display.create_pen(45, 45, 45),
        "log_light": display.create_pen(130, 90, 65),
    },
)


def make_mover(row, x, width, speed, colour):
    return {
        "row": row,
        "x": float(x),
        "start_x": float(x),
        "width": width,
        "speed": float(speed),
        "base_speed": float(speed),
        "colour": colour,
    }


vehicles = [
    make_mover(5, -20, 34, 44, RED),
    make_mover(5, 100, 34, 44, RED),
    make_mover(6, 20, 44, -58, CYAN),
    make_mover(6, 170, 44, -58, CYAN),
    make_mover(7, -70, 30, 72, ORANGE),
    make_mover(7, 45, 30, 72, ORANGE),
    make_mover(7, 165, 30, 72, ORANGE),
]

logs = [
    make_mover(1, -30, 70, 30, LOG),
    make_mover(1, 95, 70, 30, LOG),
    make_mover(2, 20, 58, -38, LOG),
    make_mover(2, 125, 58, -38, LOG),
    make_mover(3, -55, 82, 46, LOG),
    make_mover(3, 85, 82, 46, LOG),
]


class Controller:
    def __init__(self):
        self.pad = QwSTPad(I2C(**I2C_PINS), I2C_ADDRESS)
        buttons = self.pad.read_buttons()
        # QwSTPad reuses and mutates one OrderedDict for every read, so retain
        # a value snapshot rather than a reference to the driver's live state.
        self.previous = {name: buttons[name] for name in buttons}
        self.events = {}
        self.held_since = {}
        self.last_repeat = {}

    def poll(self):
        now = time.ticks_ms()
        buttons = self.pad.read_buttons()
        self.events = {}

        for name in ("U", "D", "L", "R", "+", "-"):
            down = buttons[name]
            was_down = self.previous[name]

            if down and not was_down:
                self.events[name] = True
                self.held_since[name] = now
                self.last_repeat[name] = now
            elif down and name in ("U", "D", "L", "R"):
                held = time.ticks_diff(now, self.held_since.get(name, now))
                repeated = time.ticks_diff(now, self.last_repeat.get(name, now))
                if held >= 280 and repeated >= 140:
                    self.events[name] = True
                    self.last_repeat[name] = now

        self.previous = {name: buttons[name] for name in buttons}

    def pressed(self, name):
        return self.events.get(name, False)

    def show_progress(self, homes, lives):
        # QwSTPad has four single-colour status LEDs. Show collected homes once
        # scoring starts, otherwise use them as a lives indicator.
        count = homes if homes else lives
        self.pad.set_leds((1 << min(count, 4)) - 1)


def row_y(row):
    return HUD_HEIGHT + (row * CELL)


def overlaps(ax, ay, aw, ah, bx, by, bw, bh):
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def move_movers(movers, dt):
    for mover in movers:
        mover["x"] += mover["speed"] * dt
        if mover["speed"] > 0 and mover["x"] > WIDTH:
            mover["x"] = -mover["width"]
        elif mover["speed"] < 0 and mover["x"] + mover["width"] < 0:
            mover["x"] = WIDTH


def reset_movers(level):
    multiplier = LEVEL_SPEEDS[level - 1]
    for mover in vehicles + logs:
        mover["x"] = mover["start_x"]
        mover["speed"] = mover["base_speed"] * multiplier


def draw_background(level):
    theme = LEVEL_THEMES[level - 1]
    display.set_pen(BLACK)
    display.clear()

    display.set_pen(theme["grass"])
    display.rectangle(0, row_y(0), WIDTH, CELL)

    display.set_pen(theme["water"])
    display.rectangle(0, row_y(1), WIDTH, CELL * 3)

    display.set_pen(theme["median"])
    display.rectangle(0, row_y(4), WIDTH, CELL)

    display.set_pen(theme["road"])
    display.rectangle(0, row_y(5), WIDTH, CELL * 3)

    display.set_pen(theme["grass"])
    display.rectangle(0, row_y(8), WIDTH, CELL)

    display.set_pen(theme["lane"])
    for x in range(0, WIDTH, 30):
        display.rectangle(x, row_y(6), 15, 2)
        display.rectangle(x, row_y(7), 15, 2)


def draw_movers(level):
    theme = LEVEL_THEMES[level - 1]
    for log in logs:
        x = int(log["x"])
        y = row_y(log["row"]) + 4
        display.set_pen(theme["log"])
        display.rectangle(x, y, log["width"], CELL - 8)
        display.set_pen(theme["log_light"])
        display.rectangle(x + 5, y + 4, log["width"] - 10, 3)

    for vehicle in vehicles:
        x = int(vehicle["x"])
        y = row_y(vehicle["row"]) + 4
        display.set_pen(vehicle["colour"])
        display.rectangle(x, y, vehicle["width"], CELL - 8)
        display.set_pen(BLACK)
        display.rectangle(x + 5, y - 2, 6, 3)
        display.rectangle(x + vehicle["width"] - 11, y - 2, 6, 3)
        display.rectangle(x + 5, y + CELL - 9, 6, 3)
        display.rectangle(x + vehicle["width"] - 11, y + CELL - 9, 6, 3)


def draw_frog(x, row):
    y = row_y(row) + 4
    display.set_pen(FROG)
    display.rectangle(int(x) + 4, y, FROG_SIZE - 8, FROG_SIZE)
    display.rectangle(int(x), y + 4, FROG_SIZE, FROG_SIZE - 8)
    display.set_pen(FROG_DARK)
    display.rectangle(int(x) + 3, y + 2, 3, 3)
    display.rectangle(int(x) + FROG_SIZE - 6, y + 2, 3, 3)


def draw_homes(occupied):
    for index, column in enumerate(HOME_COLUMNS):
        x = column * CELL
        if index in occupied:
            draw_frog(x + 4, 0)
        else:
            display.set_pen(BLACK)
            display.rectangle(x + 3, row_y(0) + 3, CELL - 6, CELL - 6)


def draw_hud(score, lives, level):
    display.set_pen(BLACK)
    display.rectangle(0, 0, WIDTH, HUD_HEIGHT)
    display.set_pen(WHITE)
    display.text("SCORE " + str(score), 4, 5, WIDTH, 1)
    display.text("L" + str(level) + " " + LEVEL_NAMES[level - 1], 105, 5, WIDTH, 1)
    display.text("LIVES " + str(lives), 178, 5, WIDTH, 1)


def draw_message(title, subtitle):
    display.set_pen(BLACK)
    display.rectangle(12, 82, WIDTH - 24, 76)
    display.set_pen(WHITE)
    title_scale = 2 if len(title) > 10 else 3
    title_width = display.measure_text(title, title_scale)
    display.text(title, (WIDTH - title_width) // 2, 98, WIDTH, title_scale)
    subtitle_width = display.measure_text(subtitle, 1)
    display.text(subtitle, (WIDTH - subtitle_width) // 2, 135, WIDTH, 1)


def nearest_home(x):
    centre = x + (FROG_SIZE // 2)
    best = 0
    best_distance = WIDTH
    for index, column in enumerate(HOME_COLUMNS):
        home_centre = (column * CELL) + (CELL // 2)
        distance = abs(centre - home_centre)
        if distance < best_distance:
            best = index
            best_distance = distance
    if best_distance <= CELL // 2:
        return best
    return None


def main():
    try:
        controller = Controller()
    except OSError:
        while True:
            display.set_pen(BLACK)
            display.clear()
            display.set_pen(WHITE)
            display.text("QwSTPad not found", 18, 94, WIDTH, 2)
            display.text("Connect it and reset", 42, 126, WIDTH, 1)
            presto.update()

    frog_x = 4 * CELL + 4
    frog_row = 8
    lives = 3
    score = 0
    level = 1
    occupied_homes = set()
    state = "playing"
    last_tick = time.ticks_ms()

    reset_movers(level)
    controller.show_progress(0, lives)

    while True:
        now = time.ticks_ms()
        elapsed_ms = min(50, time.ticks_diff(now, last_tick))
        last_tick = now
        dt = elapsed_ms / 1000.0

        controller.poll()
        if controller.pressed("-"):
            controller.pad.clear_leds()
            machine.reset()

        if state == "level_complete":
            if controller.pressed("+"):
                frog_x = 4 * CELL + 4
                frog_row = 8
                level += 1
                occupied_homes = set()
                reset_movers(level)
                state = "playing"
                controller.show_progress(0, lives)
        elif state == "game_over":
            if controller.pressed("+"):
                frog_x = 4 * CELL + 4
                frog_row = 8
                lives = 3
                occupied_homes = set()
                reset_movers(level)
                state = "playing"
                controller.show_progress(0, lives)
        elif state == "won":
            if controller.pressed("+"):
                frog_x = 4 * CELL + 4
                frog_row = 8
                lives = 3
                score = 0
                level = 1
                occupied_homes = set()
                reset_movers(level)
                state = "playing"
                controller.show_progress(0, lives)
        elif state == "playing":
            move_movers(vehicles, dt)
            move_movers(logs, dt)

            if controller.pressed("L"):
                frog_x = max(4, (int(frog_x) // CELL * CELL) - CELL + 4)
            elif controller.pressed("R"):
                frog_x = min(WIDTH - CELL + 4, (int(frog_x) // CELL * CELL) + CELL + 4)
            elif controller.pressed("U"):
                frog_row = max(0, frog_row - 1)
                score += 10
            elif controller.pressed("D"):
                frog_row = min(8, frog_row + 1)

            died = False

            if frog_row in (5, 6, 7):
                frog_y = row_y(frog_row) + 4
                for vehicle in vehicles:
                    if vehicle["row"] == frog_row and overlaps(
                            frog_x, frog_y, FROG_SIZE, FROG_SIZE,
                            vehicle["x"], row_y(frog_row) + 4,
                            vehicle["width"], CELL - 8):
                        died = True
                        break

            elif frog_row in (1, 2, 3):
                supported = False
                frog_y = row_y(frog_row) + 4
                for log in logs:
                    if log["row"] == frog_row and overlaps(
                            frog_x, frog_y, FROG_SIZE, FROG_SIZE,
                            log["x"], row_y(frog_row) + 4,
                            log["width"], CELL - 8):
                        frog_x += log["speed"] * dt
                        supported = True
                        break
                if not supported or frog_x < -FROG_SIZE or frog_x > WIDTH:
                    died = True

            elif frog_row == 0:
                home = nearest_home(frog_x)
                if home is not None:
                    occupied_homes.add(home)
                score += 100 * level
                controller.show_progress(4, lives)
                state = "won" if level == FINAL_LEVEL else "level_complete"

            if died:
                lives -= 1
                frog_x = 4 * CELL + 4
                frog_row = 8
                controller.show_progress(len(occupied_homes), lives)
                if lives <= 0:
                    state = "game_over"

        draw_background(level)
        draw_movers(level)
        draw_homes(occupied_homes)
        if state == "playing":
            draw_frog(frog_x, frog_row)
        draw_hud(score, lives, level)

        if state == "won":
            draw_message("YOU WIN!", "+ PLAY AGAIN   - MENU")
        elif state == "level_complete":
            draw_message("LEVEL " + str(level) + " COMPLETE", "+ NEXT LEVEL   - MENU")
        elif state == "game_over":
            draw_message("GAME OVER", "+ RETRY   - MENU")

        presto.update()
        time.sleep(0.02)


try:
    main()
finally:
    try:
        controller.pad.clear_leds()
    except (NameError, OSError):
        pass

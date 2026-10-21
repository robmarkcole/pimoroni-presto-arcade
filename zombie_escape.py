# ICON joystick
# NAME Zombie Escape
# DESC Collect the gems, dodge the zombies and reach the exit!

import machine
import random
import time

from machine import I2C
from presto import Buzzer, Presto
from qwstpad import ADDRESSES, QwSTPad


I2C_PINS = {"id": 0, "sda": 40, "scl": 41}
I2C_ADDRESS = ADDRESSES[0]

presto = Presto(ambient_light=True)
display = presto.display
WIDTH, HEIGHT = display.get_bounds()

CELL = 16
GRID_X = 0
GRID_Y = 28
COLS = 15
ROWS = 13
FINAL_LEVEL = 3
ZOMBIE_INTERVALS = (850, 500, 380)
ZOMBIE_COUNTS = (2, 3, 4)

MAZE = (
    "###############",
    "#P....#.......#",
    "#.###.#.###.#.#",
    "#...#.....#...#",
    "###.#.###.#.###",
    "#...#...#.#...#",
    "#.#####.#.###.#",
    "#.......#.....#",
    "#.###.#####.#.#",
    "#...#.......#.#",
    "#.#.###.###...#",
    "#Z....#.....ZE#",
    "###############",
)

PLAYER_START = (1, 1)
EXIT_POSITION = (13, 11)
ZOMBIE_SPAWNS = ((1, 11), (12, 11), (13, 1), (7, 7))
DIRECTIONS = ((0, -1), (0, 1), (-1, 0), (1, 0))

BLACK = display.create_pen(0, 0, 0)
WHITE = display.create_pen(255, 255, 255)
FLOOR = display.create_pen(18, 20, 31)
WALL = display.create_pen(50, 65, 150)
WALL_EDGE = display.create_pen(95, 115, 235)
GEM = display.create_pen(60, 225, 255)
GEM_SHINE = display.create_pen(220, 255, 255)
PLAYER = display.create_pen(255, 205, 55)
PLAYER_DARK = display.create_pen(165, 95, 20)
ZOMBIE = display.create_pen(90, 205, 75)
ZOMBIE_DARK = display.create_pen(35, 100, 40)
RED = display.create_pen(235, 50, 55)
GREEN = display.create_pen(60, 225, 90)
YELLOW = display.create_pen(255, 230, 40)
PURPLE = display.create_pen(150, 70, 210)
GREY = display.create_pen(105, 110, 125)

LEVEL_WALLS = (
    (WALL, WALL_EDGE),
    (display.create_pen(90, 45, 135), display.create_pen(190, 85, 235)),
    (display.create_pen(105, 48, 38), display.create_pen(245, 105, 55)),
)

SOUND_START = ((392, 60), (523, 70), (659, 110))
SOUND_GEM = ((760, 35), (1040, 55))
SOUND_HIT = ((190, 90), (125, 130), (80, 180))
SOUND_EXIT = ((523, 80), (659, 80), (784, 90), (1047, 180))
SOUND_LOCKED = ((130, 90),)
SOUND_GAME_OVER = ((330, 140), (220, 180), (110, 260))


class Audio:
    def __init__(self):
        self.buzzer = Buzzer(43)
        self.frequency = None
        self.sequence = None
        self.index = 0
        self.deadline = None

    def set_frequency(self, frequency):
        if frequency == self.frequency:
            return
        self.frequency = frequency
        if frequency:
            self.buzzer.set_tone(frequency, 0.20)
        else:
            self.buzzer.set_tone(-1)

    def play(self, sequence):
        self.sequence = sequence
        self.index = 0
        self.deadline = None

    def update(self, now):
        if self.sequence is None:
            return
        if self.deadline is None:
            frequency, duration = self.sequence[self.index]
            self.set_frequency(frequency)
            self.deadline = time.ticks_add(now, duration)
        elif time.ticks_diff(now, self.deadline) >= 0:
            self.index += 1
            if self.index >= len(self.sequence):
                self.sequence = None
                self.deadline = None
                self.set_frequency(0)
            else:
                frequency, duration = self.sequence[self.index]
                self.set_frequency(frequency)
                self.deadline = time.ticks_add(now, duration)

    def stop(self):
        self.sequence = None
        self.set_frequency(0)


class Controller:
    KEYS = ("U", "D", "L", "R", "+", "-")

    def __init__(self):
        self.pad = QwSTPad(I2C(**I2C_PINS), I2C_ADDRESS)
        buttons = self.pad.read_buttons()
        self.previous = {name: buttons[name] for name in buttons}
        self.events = {}
        self.held_since = {}
        self.last_repeat = {}

    def poll(self):
        now = time.ticks_ms()
        buttons = self.pad.read_buttons()
        self.events = {}
        for name in self.KEYS:
            down = buttons[name]
            was_down = self.previous[name]
            if down and not was_down:
                self.events[name] = True
                self.held_since[name] = now
                self.last_repeat[name] = now
            elif down and name in ("U", "D", "L", "R"):
                held = time.ticks_diff(now, self.held_since.get(name, now))
                repeated = time.ticks_diff(now, self.last_repeat.get(name, now))
                if held >= 300 and repeated >= 145:
                    self.events[name] = True
                    self.last_repeat[name] = now
        self.previous = {name: buttons[name] for name in buttons}

    def pressed(self, name):
        return self.events.get(name, False)

    def show_lives(self, lives):
        self.pad.set_leds((1 << min(lives, 4)) - 1)


def centre_text(text, y, scale=1, pen=WHITE):
    display.set_pen(pen)
    width = display.measure_text(text, scale)
    display.text(text, (WIDTH - width) // 2, y, WIDTH, scale)


def grid_xy(position):
    return GRID_X + position[0] * CELL, GRID_Y + position[1] * CELL


def is_floor(position):
    x, y = position
    return 0 <= x < COLS and 0 <= y < ROWS and MAZE[y][x] != "#"


def initial_gems():
    return {
        (x, y)
        for y, row in enumerate(MAZE)
        for x, tile in enumerate(row)
        if tile == "."
    }


def reset_positions(game):
    game["player"] = PLAYER_START
    count = ZOMBIE_COUNTS[game["level"] - 1]
    game["zombies"] = list(ZOMBIE_SPAWNS[:count])
    game["last_zombie_move"] = time.ticks_ms()


def new_game(controller, level=1, score=0):
    game = {
        "level": level,
        "score": score,
        "lives": 3,
        "gems": initial_gems(),
        "player": PLAYER_START,
        "zombies": [],
        "last_zombie_move": time.ticks_ms(),
        "hit_until": None,
        "notice": None,
        "notice_until": None,
    }
    reset_positions(game)
    controller.show_lives(game["lives"])
    return game


def draw_wall(x, y, wall_pen, edge_pen):
    display.set_pen(wall_pen)
    display.rectangle(x, y, CELL, CELL)
    display.set_pen(edge_pen)
    display.rectangle(x + 2, y + 2, CELL - 4, 2)
    display.rectangle(x + 2, y + 2, 2, CELL - 4)


def draw_gem(position, pulse):
    x, y = grid_xy(position)
    inset = 4 if pulse else 5
    display.set_pen(GEM)
    display.polygon([
        (x + CELL // 2, y + inset),
        (x + CELL - inset, y + CELL // 2),
        (x + CELL // 2, y + CELL - inset),
        (x + inset, y + CELL // 2),
    ])
    display.set_pen(GEM_SHINE)
    display.pixel(x + 7, y + 6)


def draw_exit(opened):
    x, y = grid_xy(EXIT_POSITION)
    display.set_pen(GREEN if opened else RED)
    display.rectangle(x + 2, y + 1, CELL - 4, CELL - 2)
    display.set_pen(BLACK)
    display.rectangle(x + 5, y + 5, CELL - 10, CELL - 6)
    display.set_pen(YELLOW if opened else GREY)
    display.pixel(x + 11, y + 9)


def draw_player(position, frame):
    x, y = grid_xy(position)
    bob = frame % 2
    display.set_pen(PLAYER)
    display.rectangle(x + 4, y + 3 - bob, 8, 9)
    display.circle(x + 8, y + 4 - bob, 5)
    display.set_pen(BLACK)
    display.pixel(x + 6, y + 3 - bob)
    display.pixel(x + 10, y + 3 - bob)
    display.set_pen(PLAYER_DARK)
    display.rectangle(x + 3, y + 7 - bob, 3, 6)
    display.rectangle(x + 10, y + 7 - bob, 3, 6)


def draw_zombie(position, index, frame):
    x, y = grid_xy(position)
    stagger = (frame + index) % 2
    display.set_pen(ZOMBIE)
    display.rectangle(x + 3, y + 4, 10, 9)
    display.circle(x + 8, y + 5, 5)
    display.set_pen(RED)
    display.pixel(x + 6, y + 4)
    display.pixel(x + 10, y + 4)
    display.set_pen(ZOMBIE_DARK)
    display.rectangle(x + 4, y + 12, 3, 3 + stagger)
    display.rectangle(x + 9, y + 12, 3, 4 - stagger)


def draw_maze(game, now):
    display.set_pen(FLOOR)
    display.clear()
    wall_pen, edge_pen = LEVEL_WALLS[game["level"] - 1]
    for row_index, row in enumerate(MAZE):
        for column, tile in enumerate(row):
            if tile == "#":
                x, y = grid_xy((column, row_index))
                draw_wall(x, y, wall_pen, edge_pen)

    pulse = (now // 180) % 2
    for gem in game["gems"]:
        draw_gem(gem, pulse)
    draw_exit(not game["gems"])


def draw_hud(game):
    display.set_pen(BLACK)
    display.rectangle(0, 0, WIDTH, GRID_Y)
    display.set_pen(YELLOW)
    display.text("S " + str(game["score"]), 3, 3, 82, 2)
    display.set_pen(GEM)
    display.text("G " + str(len(game["gems"])), 88, 6, 65, 1)
    display.set_pen(WHITE)
    display.text("L" + str(game["level"]) + " LIFE " + str(game["lives"]), 154, 6, WIDTH, 1)


def draw_game(game, now):
    draw_maze(game, now)
    frame = (now // 180) % 2
    for index, zombie in enumerate(game["zombies"]):
        draw_zombie(zombie, index, frame)
    visible = game["hit_until"] is None or (now // 90) % 2 == 0
    if visible:
        draw_player(game["player"], frame)
    draw_hud(game)
    if game["notice_until"] is not None and time.ticks_diff(game["notice_until"], now) > 0:
        display.set_pen(BLACK)
        display.rectangle(24, 102, WIDTH - 48, 30)
        centre_text(game["notice"], 111, 1, YELLOW)


def draw_title(game, now):
    draw_maze(game, now)
    display.set_pen(BLACK)
    display.rectangle(12, 55, WIDTH - 24, 123)
    centre_text("ZOMBIE", 66, 3, ZOMBIE)
    centre_text("ESCAPE", 94, 3, GEM)
    centre_text("COLLECT EVERY GEM", 128, 1, WHITE)
    centre_text("THEN REACH THE EXIT", 144, 1, WHITE)
    centre_text("+ START     - MENU", 162, 1, YELLOW)


def distance_map(target):
    distances = {target: 0}
    queue = [target]
    index = 0
    while index < len(queue):
        x, y = queue[index]
        index += 1
        next_distance = distances[(x, y)] + 1
        for dx, dy in DIRECTIONS:
            neighbour = (x + dx, y + dy)
            if is_floor(neighbour) and neighbour not in distances:
                distances[neighbour] = next_distance
                queue.append(neighbour)
    return distances


def move_zombies(game):
    distances = distance_map(game["player"])
    occupied = set(game["zombies"])
    moved = []
    for zombie in game["zombies"]:
        occupied.discard(zombie)
        x, y = zombie
        choices = []
        for dx, dy in DIRECTIONS:
            candidate = (x + dx, y + dy)
            if is_floor(candidate) and candidate not in occupied and candidate not in moved:
                choices.append(candidate)
        if choices:
            if random.random() < 0.16:
                destination = random.choice(choices)
            else:
                destination = choices[0]
                best = distances.get(destination, 999)
                for candidate in choices[1:]:
                    candidate_distance = distances.get(candidate, 999)
                    if candidate_distance < best:
                        destination = candidate
                        best = candidate_distance
            zombie = destination
        moved.append(zombie)
    game["zombies"] = moved


def lose_life(game, controller, audio, now):
    game["lives"] -= 1
    controller.show_lives(game["lives"])
    audio.play(SOUND_HIT)
    if game["lives"] <= 0:
        return "game_over"
    reset_positions(game)
    game["hit_until"] = time.ticks_add(now, 1100)
    game["notice"] = "ZOMBIE GOT YOU!"
    game["notice_until"] = game["hit_until"]
    return "playing"


def move_player(game, direction, audio, now):
    x, y = game["player"]
    candidate = (x + direction[0], y + direction[1])
    if not is_floor(candidate):
        return None
    if candidate == EXIT_POSITION and game["gems"]:
        game["notice"] = "GEMS LEFT " + str(len(game["gems"]))
        game["notice_until"] = time.ticks_add(now, 800)
        audio.play(SOUND_LOCKED)
        return None

    game["player"] = candidate
    if candidate in game["gems"]:
        game["gems"].remove(candidate)
        game["score"] += 10
        audio.play(SOUND_GEM)
        if not game["gems"]:
            game["notice"] = "EXIT OPEN!"
            game["notice_until"] = time.ticks_add(now, 1000)
    if candidate == EXIT_POSITION:
        game["score"] += 500 * game["level"]
        audio.play(SOUND_EXIT)
        return "escaped"
    return None


def update_game(game, controller, audio, now):
    if game["hit_until"] is not None:
        if time.ticks_diff(now, game["hit_until"]) < 0:
            return "playing"
        game["hit_until"] = None

    move = None
    if controller.pressed("U"):
        move = (0, -1)
    elif controller.pressed("D"):
        move = (0, 1)
    elif controller.pressed("L"):
        move = (-1, 0)
    elif controller.pressed("R"):
        move = (1, 0)

    if move is not None:
        result = move_player(game, move, audio, now)
        if result == "escaped":
            return result
        if game["player"] in game["zombies"]:
            return lose_life(game, controller, audio, now)

    interval = ZOMBIE_INTERVALS[game["level"] - 1]
    if time.ticks_diff(now, game["last_zombie_move"]) >= interval:
        move_zombies(game)
        game["last_zombie_move"] = now
        if game["player"] in game["zombies"]:
            return lose_life(game, controller, audio, now)
    return "playing"


def draw_result(game, state):
    display.set_pen(BLACK)
    display.rectangle(12, 69, WIDTH - 24, 104)
    if state == "level_complete":
        centre_text("ESCAPED!", 80, 3, GREEN)
        centre_text("SCORE " + str(game["score"]), 116, 2, YELLOW)
        centre_text("+ NEXT MAZE", 148, 1, WHITE)
    elif state == "win":
        centre_text("YOU ESCAPED", 78, 2, GREEN)
        centre_text("THE HORDE!", 101, 2, ZOMBIE)
        centre_text("FINAL " + str(game["score"]), 129, 2, YELLOW)
        centre_text("+ PLAY AGAIN", 154, 1, WHITE)
    else:
        centre_text("GAME OVER", 82, 3, RED)
        centre_text("SCORE " + str(game["score"]), 119, 2, YELLOW)
        centre_text("+ RETRY", 151, 1, WHITE)


def main():
    try:
        controller = Controller()
    except OSError:
        while True:
            display.set_pen(BLACK)
            display.clear()
            centre_text("QwSTPad not found", 95, 2)
            centre_text("Connect it and reset", 127, 1)
            presto.update()

    audio = Audio()
    game = new_game(controller)
    state = "title"

    while True:
        now = time.ticks_ms()
        controller.poll()
        audio.update(now)

        if controller.pressed("-"):
            audio.stop()
            controller.pad.clear_leds()
            machine.reset()

        if state == "title":
            draw_title(game, now)
            if controller.pressed("+"):
                game = new_game(controller)
                state = "playing"
                audio.play(SOUND_START)
        elif state == "playing":
            state = update_game(game, controller, audio, now)
            draw_game(game, now)
            if state == "escaped":
                controller.pad.set_leds(0b1111)
                state = "win" if game["level"] >= FINAL_LEVEL else "level_complete"
            elif state == "game_over":
                audio.play(SOUND_GAME_OVER)
        else:
            draw_game(game, now)
            draw_result(game, state)
            if controller.pressed("+"):
                if state == "level_complete":
                    game = new_game(controller, game["level"] + 1, game["score"])
                else:
                    game = new_game(controller)
                state = "playing"
                audio.play(SOUND_START)

        presto.update()
        time.sleep(0.02)


try:
    main()
finally:
    try:
        controller.pad.clear_leds()
    except (NameError, OSError):
        pass
    try:
        audio.stop()
    except NameError:
        pass

# ICON joystick
# NAME Find Your Best Friend
# DESC Catch the monster, search the doors and find your friend!

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
GRID_Y = 28
COLS = 15
ROWS = 13
PLAYER_START = (1, 1)
MONSTER_START = (1, 11)
NET_POSITION = (3, 3)
MONSTER_INTERVAL = 620
NET_RANGE = 6

MAP = (
    "###############",
    "#P....D.......#",
    "#.###.#.###.#.#",
    "#..N#.....D...#",
    "###.#.###.#.###",
    "#...D...#.#...#",
    "#.#####.#.###.#",
    "#.......D.....#",
    "#.###.#####.#.#",
    "#...D.......#.#",
    "#.#.###.###...#",
    "#M....D.......#",
    "###############",
)

DIRECTIONS = ((0, -1), (0, 1), (-1, 0), (1, 0))
DOORS = tuple(
    (x, y)
    for y, row in enumerate(MAP)
    for x, tile in enumerate(row)
    if tile == "D"
)

BLACK = display.create_pen(0, 0, 0)
WHITE = display.create_pen(255, 255, 255)
FLOOR = display.create_pen(22, 25, 38)
FLOOR_DOT = display.create_pen(34, 39, 58)
WALL = display.create_pen(70, 60, 145)
WALL_EDGE = display.create_pen(125, 105, 235)
BROWN = display.create_pen(135, 76, 38)
DARK_BROWN = display.create_pen(65, 35, 25)
YELLOW = display.create_pen(255, 225, 40)
GREEN = display.create_pen(65, 220, 95)
CYAN = display.create_pen(45, 220, 240)
BLUE = display.create_pen(45, 95, 235)
PURPLE = display.create_pen(160, 70, 220)
RED = display.create_pen(240, 55, 60)
PINK = display.create_pen(245, 90, 175)
ORANGE = display.create_pen(255, 135, 35)
SKIN = display.create_pen(255, 190, 125)
GREY = display.create_pen(105, 115, 130)

SOUND_START = ((392, 55), (523, 60), (659, 100))
SOUND_STEP = ((330, 20),)
SOUND_NET = ((620, 30), (820, 45))
SOUND_CATCH = ((440, 45), (659, 55), (880, 100))
SOUND_DOOR = ((180, 45), (260, 65))
SOUND_EMPTY = ((180, 70), (135, 90))
SOUND_TOOL = ((523, 45), (784, 85))
SOUND_HIT = ((210, 80), (120, 120), (70, 170))
SOUND_WIN = ((523, 70), (659, 70), (784, 80), (1047, 180))
SOUND_ERROR = ((115, 90),)


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
        self.deadline = None
        self.set_frequency(0)


class Controller:
    KEYS = ("U", "D", "L", "R", "A", "+", "-")

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
    return position[0] * CELL, GRID_Y + position[1] * CELL


def tile_at(position):
    x, y = position
    if not (0 <= x < COLS and 0 <= y < ROWS):
        return "#"
    return MAP[y][x]


def is_floor(position):
    return tile_at(position) not in ("#", "D")


def reset_positions(game):
    game["player"] = PLAYER_START
    game["monster"] = MONSTER_START
    game["facing"] = (1, 0)
    game["last_monster_move"] = time.ticks_ms()


def new_game(controller):
    game = {
        "player": PLAYER_START,
        "monster": MONSTER_START,
        "facing": (1, 0),
        "lives": 3,
        "score": 0,
        "has_net": False,
        "monster_caught": False,
        "friend_door": random.choice(DOORS),
        "opened_doors": set(),
        "last_monster_move": time.ticks_ms(),
        "net_beam": None,
        "net_until": None,
        "hit_until": None,
        "notice": "FIND THE NET LAUNCHER",
        "notice_until": time.ticks_add(time.ticks_ms(), 1100),
    }
    controller.show_lives(game["lives"])
    return game


def distance_map(target):
    distances = {target: 0}
    queue = [target]
    index = 0
    while index < len(queue):
        x, y = queue[index]
        index += 1
        for dx, dy in DIRECTIONS:
            neighbour = (x + dx, y + dy)
            if is_floor(neighbour) and neighbour not in distances:
                distances[neighbour] = distances[(x, y)] + 1
                queue.append(neighbour)
    return distances


def move_monster(game):
    if game["monster_caught"]:
        return
    distances = distance_map(game["player"])
    x, y = game["monster"]
    choices = []
    for dx, dy in DIRECTIONS:
        candidate = (x + dx, y + dy)
        if is_floor(candidate):
            choices.append(candidate)
    if not choices:
        return
    if random.random() < 0.12:
        game["monster"] = random.choice(choices)
        return
    destination = choices[0]
    best = distances.get(destination, 999)
    for candidate in choices[1:]:
        distance = distances.get(candidate, 999)
        if distance < best:
            destination = candidate
            best = distance
    game["monster"] = destination


def lose_life(game, controller, audio, now):
    game["lives"] -= 1
    controller.show_lives(game["lives"])
    audio.play(SOUND_HIT)
    if game["lives"] <= 0:
        return "game_over"
    reset_positions(game)
    game["hit_until"] = time.ticks_add(now, 1000)
    game["notice"] = "MONSTER GOT YOU!"
    game["notice_until"] = game["hit_until"]
    return "playing"


def collect_tool(game, audio, now):
    if game["player"] == NET_POSITION and not game["has_net"]:
        game["has_net"] = True
        game["score"] += 50
        game["notice"] = "NET READY - FACE + A"
        game["notice_until"] = time.ticks_add(now, 1100)
        audio.play(SOUND_TOOL)


def move_player(game, direction, audio, now):
    game["facing"] = direction
    candidate = (game["player"][0] + direction[0],
                 game["player"][1] + direction[1])
    if not is_floor(candidate):
        if tile_at(candidate) == "D":
            if not game["monster_caught"]:
                game["notice"] = "CATCH MONSTER FIRST"
            else:
                game["notice"] = "PRESS A TO OPEN"
            game["notice_until"] = time.ticks_add(now, 650)
            audio.play(SOUND_ERROR)
        return
    game["player"] = candidate
    collect_tool(game, audio, now)
    audio.play(SOUND_STEP)


def fire_net(game, audio, now):
    if not game["has_net"]:
        game["notice"] = "FIND THE NET FIRST"
        game["notice_until"] = time.ticks_add(now, 700)
        audio.play(SOUND_ERROR)
        return
    start = game["player"]
    dx, dy = game["facing"]
    end = start
    caught = False
    for distance in range(1, NET_RANGE + 1):
        position = (start[0] + dx * distance, start[1] + dy * distance)
        if not is_floor(position):
            break
        end = position
        if position == game["monster"]:
            caught = True
            break
    game["net_beam"] = (start, end)
    game["net_until"] = time.ticks_add(now, 280)
    if caught:
        game["monster_caught"] = True
        game["monster"] = None
        game["score"] += 200
        game["notice"] = "MONSTER CAUGHT! FIND FRIEND"
        game["notice_until"] = time.ticks_add(now, 1200)
        audio.play(SOUND_CATCH)
    else:
        audio.play(SOUND_NET)


def open_door(game, audio, now):
    dx, dy = game["facing"]
    door = (game["player"][0] + dx, game["player"][1] + dy)
    if tile_at(door) != "D":
        game["notice"] = "FACE A DOOR"
        game["notice_until"] = time.ticks_add(now, 600)
        audio.play(SOUND_ERROR)
        return "playing"
    if door in game["opened_doors"]:
        game["notice"] = "ALREADY EMPTY"
        game["notice_until"] = time.ticks_add(now, 600)
        audio.play(SOUND_EMPTY)
        return "playing"
    game["opened_doors"].add(door)
    if door == game["friend_door"]:
        game["score"] += 500
        game["notice"] = "BEST FRIEND FOUND!"
        game["notice_until"] = time.ticks_add(now, 1200)
        audio.play(SOUND_WIN)
        return "won"
    game["score"] += 25
    game["notice"] = "EMPTY - KEEP LOOKING"
    game["notice_until"] = time.ticks_add(now, 850)
    audio.play(SOUND_EMPTY)
    return "playing"


def use_action(game, audio, now):
    if game["monster_caught"]:
        return open_door(game, audio, now)
    fire_net(game, audio, now)
    return "playing"


def update_game(game, controller, audio, now):
    if game["hit_until"] is not None:
        if time.ticks_diff(now, game["hit_until"]) < 0:
            return "playing"
        game["hit_until"] = None
    if game["net_until"] is not None and time.ticks_diff(now, game["net_until"]) >= 0:
        game["net_beam"] = None
        game["net_until"] = None

    direction = None
    if controller.pressed("U"):
        direction = (0, -1)
    elif controller.pressed("D"):
        direction = (0, 1)
    elif controller.pressed("L"):
        direction = (-1, 0)
    elif controller.pressed("R"):
        direction = (1, 0)
    if direction is not None:
        move_player(game, direction, audio, now)
        if not game["monster_caught"] and game["player"] == game["monster"]:
            return lose_life(game, controller, audio, now)

    if controller.pressed("A"):
        result = use_action(game, audio, now)
        if result == "won":
            return result

    if (not game["monster_caught"] and
            time.ticks_diff(now, game["last_monster_move"]) >= MONSTER_INTERVAL):
        move_monster(game)
        game["last_monster_move"] = now
        if game["player"] == game["monster"]:
            return lose_life(game, controller, audio, now)
    return "playing"


def draw_wall(x, y):
    display.set_pen(WALL)
    display.rectangle(x, y, CELL, CELL)
    display.set_pen(WALL_EDGE)
    display.rectangle(x + 2, y + 2, CELL - 4, 2)
    display.rectangle(x + 2, y + 2, 2, CELL - 4)


def draw_floor(x, y):
    display.set_pen(FLOOR)
    display.rectangle(x, y, CELL, CELL)
    display.set_pen(FLOOR_DOT)
    display.pixel(x + 4, y + 5)
    display.pixel(x + 12, y + 12)


def draw_door(position, game):
    x, y = grid_xy(position)
    draw_wall(x, y)
    opened = position in game["opened_doors"]
    display.set_pen(BLACK if opened else BROWN)
    display.rectangle(x + 3, y + 2, 10, 14)
    display.set_pen(DARK_BROWN)
    display.rectangle(x + 5, y + 4, 6, 9)
    if not opened:
        display.set_pen(YELLOW)
        display.pixel(x + 10, y + 9)
    elif position == game["friend_door"]:
        display.set_pen(PINK)
        display.circle(x + 8, y + 7, 4)
        display.set_pen(SKIN)
        display.circle(x + 8, y + 5, 3)


def draw_player(position, facing, frame):
    x, y = grid_xy(position)
    bob = frame % 2
    display.set_pen(CYAN)
    display.rectangle(x + 4, y + 8 - bob, 8, 7)
    display.set_pen(SKIN)
    display.circle(x + 8, y + 5 - bob, 5)
    display.set_pen(BLUE)
    display.rectangle(x + 4, y + 1 - bob, 8, 3)
    display.set_pen(BLACK)
    eye_x = x + 10 if facing[0] >= 0 else x + 6
    display.pixel(eye_x, y + 5 - bob)


def draw_monster(position, frame):
    x, y = grid_xy(position)
    wobble = frame % 2
    display.set_pen(PURPLE)
    display.circle(x + 8, y + 7, 7)
    display.rectangle(x + 2 + wobble, y + 8, 12 - wobble * 2, 7)
    display.set_pen(RED)
    display.pixel(x + 5, y + 6)
    display.pixel(x + 11, y + 6)
    display.set_pen(YELLOW)
    display.rectangle(x + 5, y + 11, 6, 2)


def draw_carried_monster(player, frame):
    x, y = grid_xy(player)
    display.set_pen(GREY)
    display.rectangle(x + 1, y + 10, 5, 5)
    display.set_pen(PURPLE)
    display.circle(x + 3, y + 11, 3)
    display.set_pen(WHITE)
    for offset in (0, 3, 6):
        display.line(x, y + 8 + offset, x + 7, y + 15 - offset, 1)


def draw_net_tool(now):
    x, y = grid_xy(NET_POSITION)
    pulse = (now // 130) % 2
    display.set_pen(GREEN)
    display.rectangle(x + 3, y + 7, 10, 4)
    display.rectangle(x + 9, y + 10, 3, 5)
    display.set_pen(CYAN)
    display.circle(x + 3, y + 8, 3 + pulse)


def draw_net_beam(game):
    if game["net_beam"] is None:
        return
    start, end = game["net_beam"]
    sx, sy = grid_xy(start)
    ex, ey = grid_xy(end)
    sx += CELL // 2
    sy += CELL // 2
    ex += CELL // 2
    ey += CELL // 2
    display.set_pen(WHITE)
    display.line(sx, sy, ex, ey, 2)
    display.set_pen(CYAN)
    for step in range(0, NET_RANGE * CELL, 8):
        if sx == ex:
            y = sy + step * (1 if ey >= sy else -1)
            if min(sy, ey) <= y <= max(sy, ey):
                display.line(sx - 3, y, sx + 3, y, 1)
        else:
            x = sx + step * (1 if ex >= sx else -1)
            if min(sx, ex) <= x <= max(sx, ex):
                display.line(x, sy - 3, x, sy + 3, 1)


def draw_hud(game):
    display.set_pen(BLACK)
    display.rectangle(0, 0, WIDTH, GRID_Y)
    display.set_pen(YELLOW)
    display.text("S " + str(game["score"]), 3, 4, 74, 2)
    display.set_pen(WHITE)
    display.text("L" + str(game["lives"]), 83, 8, 25, 1)
    display.set_pen(GREEN if game["has_net"] else GREY)
    display.text("NET", 112, 8, 28, 1)
    display.set_pen(CYAN if game["monster_caught"] else GREY)
    display.text("CAUGHT", 148, 8, 51, 1)
    display.set_pen(PINK)
    display.text(str(len(game["opened_doors"])) + "/" + str(len(DOORS)), 205, 8, 33, 1)


def draw_game(game, now):
    display.set_pen(FLOOR)
    display.clear()
    for row, tiles in enumerate(MAP):
        for column, tile in enumerate(tiles):
            position = (column, row)
            x, y = grid_xy(position)
            if tile == "#":
                draw_wall(x, y)
            elif tile == "D":
                draw_door(position, game)
            else:
                draw_floor(x, y)
    if not game["has_net"]:
        draw_net_tool(now)
    frame = (now // 140) % 4
    if not game["monster_caught"]:
        draw_monster(game["monster"], frame)
    else:
        draw_carried_monster(game["player"], frame)
    draw_player(game["player"], game["facing"], frame)
    draw_net_beam(game)
    draw_hud(game)
    if game["notice_until"] is not None and time.ticks_diff(game["notice_until"], now) > 0:
        display.set_pen(BLACK)
        display.rectangle(12, 107, WIDTH - 24, 22)
        centre_text(game["notice"], 113, 1, YELLOW)


def draw_title():
    display.set_pen(FLOOR)
    display.clear()
    for x in range(0, WIDTH, CELL):
        draw_wall(x, 28)
        draw_wall(x, 220)
    display.set_pen(BLACK)
    display.rectangle(10, 48, WIDTH - 20, 148)
    centre_text("FIND YOUR", 58, 3, CYAN)
    centre_text("BEST FRIEND", 86, 3, YELLOW)
    centre_text("1. GET THE NET", 125, 1, GREEN)
    centre_text("2. CATCH THE MONSTER", 140, 1, PURPLE)
    centre_text("3. SEARCH THE DOORS", 155, 1, PINK)
    centre_text("D-PAD MOVE   A USE", 176, 1, WHITE)
    centre_text("+ START       - MENU", 202, 1, YELLOW)


def draw_result(game, state):
    display.set_pen(BLACK)
    display.rectangle(15, 68, WIDTH - 30, 112)
    if state == "won":
        centre_text("FOUND!", 78, 4, PINK)
        centre_text("BEST FRIEND RESCUED", 119, 1, CYAN)
        centre_text("SCORE " + str(game["score"]), 139, 2, YELLOW)
        centre_text("+ PLAY AGAIN", 166, 1, GREEN)
    else:
        centre_text("GAME OVER", 80, 3, RED)
        centre_text("THE MONSTER WON", 118, 1, PURPLE)
        centre_text("SCORE " + str(game["score"]), 138, 2, YELLOW)
        centre_text("+ TRY AGAIN", 165, 1, GREEN)


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
    state = "title"
    game = None

    while True:
        now = time.ticks_ms()
        controller.poll()
        audio.update(now)

        if controller.pressed("-"):
            controller.pad.clear_leds()
            audio.stop()
            machine.reset()

        if state == "title":
            draw_title()
            if controller.pressed("+"):
                game = new_game(controller)
                state = "playing"
                audio.play(SOUND_START)
        elif state == "playing":
            state = update_game(game, controller, audio, now)
            draw_game(game, now)
        else:
            draw_game(game, now)
            draw_result(game, state)
            if controller.pressed("+"):
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

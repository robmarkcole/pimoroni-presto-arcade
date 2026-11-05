# ICON joystick
# NAME Duck Kart Rally
# DESC Race, collect coins and build the silliest duck kart!

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

HUD_HEIGHT = 28
ROAD_LEFT = 30
ROAD_RIGHT = 210
PLAYER_Y = 190
PLAYER_W = 20
PLAYER_H = 28
LANES = (52, 96, 144, 188)
RACE_METRES = 650
HIGH_SCORE_FILE = "duck_kart_high.txt"
UPGRADES = ("WHEELS", "KART", "NEW PLACE")

BLACK = display.create_pen(0, 0, 0)
WHITE = display.create_pen(255, 255, 255)
YELLOW = display.create_pen(255, 225, 35)
ORANGE = display.create_pen(255, 135, 35)
RED = display.create_pen(240, 55, 60)
GREEN = display.create_pen(65, 220, 95)
DARK_GREEN = display.create_pen(25, 115, 55)
CYAN = display.create_pen(45, 220, 240)
BLUE = display.create_pen(45, 95, 235)
PURPLE = display.create_pen(160, 70, 220)
PINK = display.create_pen(245, 85, 175)
GREY = display.create_pen(105, 110, 120)
DARK_GREY = display.create_pen(45, 48, 58)
BROWN = display.create_pen(115, 72, 42)
SAND = display.create_pen(225, 190, 105)
SNOW = display.create_pen(220, 245, 250)
GRASS = display.create_pen(55, 155, 70)
ROAD = display.create_pen(65, 68, 78)
ROAD_LIGHT = display.create_pen(92, 96, 108)

THEMES = (
    (GRASS, DARK_GREEN, ROAD, WHITE),
    (SAND, ORANGE, display.create_pen(100, 82, 70), YELLOW),
    (SNOW, CYAN, display.create_pen(70, 85, 105), WHITE),
    (PINK, PURPLE, display.create_pen(75, 55, 90), CYAN),
)

SOUND_START = ((392, 45), (523, 55), (659, 90))
SOUND_COIN = ((740, 30), (980, 55))
SOUND_BOOST = ((440, 35), (660, 35), (880, 70))
SOUND_ROCK = ((150, 60), (105, 90))
SOUND_CHOICE = ((523, 40), (784, 75))
SOUND_OVERTAKE = ((620, 25), (820, 40))
SOUND_FINISH = ((523, 60), (659, 60), (784, 70), (1047, 160))


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
            self.buzzer.set_tone(frequency, 0.18)
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
    KEYS = ("L", "R", "A", "+", "-")

    def __init__(self):
        self.pad = QwSTPad(I2C(**I2C_PINS), I2C_ADDRESS)
        buttons = self.pad.read_buttons()
        self.previous = {name: buttons[name] for name in buttons}
        self.buttons = buttons
        self.events = {}

    def poll(self):
        buttons = self.pad.read_buttons()
        self.events = {}
        for name in self.KEYS:
            if buttons[name] and not self.previous[name]:
                self.events[name] = True
        self.previous = {name: buttons[name] for name in buttons}
        self.buttons = buttons

    def pressed(self, name):
        return self.events.get(name, False)

    def held(self, name):
        return self.buttons.get(name, False)

    def show_coins(self, coins):
        self.pad.set_leds((1 << min(coins, 4)) - 1)


def centre_text(text, y, scale=1, pen=WHITE):
    display.set_pen(pen)
    width = display.measure_text(text, scale)
    display.text(text, (WIDTH - width) // 2, y, WIDTH, scale)


def load_high_score():
    try:
        with open(HIGH_SCORE_FILE, "r") as score_file:
            return int(score_file.readline().strip())
    except (OSError, ValueError):
        return 0


def save_high_score(score):
    high = load_high_score()
    if score <= high:
        return high
    try:
        with open(HIGH_SCORE_FILE, "w") as score_file:
            score_file.write(str(score))
    except OSError:
        pass
    return score


def new_game(controller):
    now = time.ticks_ms()
    game = {
        "player_x": float(WIDTH // 2),
        "distance": 0.0,
        "score": 0,
        "coins": 0,
        "wheel_level": 0,
        "kart_level": 0,
        "place_level": 0,
        "objects": [],
        "road_offset": 0.0,
        "next_spawn": time.ticks_add(now, 800),
        "boost_until": None,
        "slow_until": None,
        "wobble_until": None,
        "choice": 0,
        "notice": "GO DUCK GO!",
        "notice_until": time.ticks_add(now, 900),
        "high_score": load_high_score(),
    }
    controller.show_coins(0)
    return game


def current_speed(game, now):
    speed = 88 + game["kart_level"] * 8 + int(game["distance"] / 180) * 3
    if game["boost_until"] is not None and time.ticks_diff(game["boost_until"], now) > 0:
        speed += 55
    if game["slow_until"] is not None and time.ticks_diff(game["slow_until"], now) > 0:
        speed = max(46, speed // 2)
    return speed


def spawn_object(game, now):
    roll = random.random()
    lane = random.choice(LANES)
    if roll < 0.28:
        kind = "coin"
    elif roll < 0.46:
        kind = "boost"
    elif roll < 0.72:
        kind = "rock"
    else:
        kind = "rival"
    game["objects"].append({
        "kind": kind,
        "x": float(lane),
        "y": float(HUD_HEIGHT - 22),
        "drift": random.randint(-12, 18),
        "colour": random.choice((RED, CYAN, PURPLE, PINK, ORANGE)),
        "passed": False,
    })
    progress = min(1.0, game["distance"] / RACE_METRES)
    delay = random.randint(850, 1450) - int(progress * 250)
    game["next_spawn"] = time.ticks_add(now, delay)


def player_hits(game, obj):
    width = 19 if obj["kind"] == "rock" else 15
    height = 19 if obj["kind"] in ("rock", "rival") else 14
    return (abs(game["player_x"] - obj["x"]) < (PLAYER_W + width) / 2 and
            abs(PLAYER_Y + PLAYER_H / 2 - (obj["y"] + height / 2)) <
            (PLAYER_H + height) / 2)


def collect_coin(game, controller, audio, now):
    game["coins"] += 1
    game["score"] += 100
    game["choice"] = 0
    game["notice"] = "COIN! CHOOSE A PRIZE"
    game["notice_until"] = time.ticks_add(now, 900)
    controller.show_coins(game["coins"])
    audio.play(SOUND_COIN)


def update_objects(game, controller, audio, now, dt, speed):
    for obj in game["objects"][:]:
        obj_speed = speed * 0.74 + obj["drift"]
        obj["y"] += obj_speed * dt
        if obj["kind"] == "rival":
            obj["x"] += ((now // 420 + int(obj["y"])) % 3 - 1) * 7 * dt
            obj["x"] = max(ROAD_LEFT + 11, min(ROAD_RIGHT - 11, obj["x"]))
        if obj["y"] > HEIGHT + 25:
            if obj["kind"] == "rival" and not obj["passed"]:
                game["score"] += 25
                audio.play(SOUND_OVERTAKE)
            game["objects"].remove(obj)
            continue
        if not player_hits(game, obj):
            continue
        game["objects"].remove(obj)
        if obj["kind"] == "coin":
            collect_coin(game, controller, audio, now)
            return "upgrade"
        if obj["kind"] == "boost":
            game["boost_until"] = time.ticks_add(now, 1700)
            game["score"] += 40
            game["notice"] = "SPEED ARROWS!"
            game["notice_until"] = time.ticks_add(now, 650)
            audio.play(SOUND_BOOST)
        elif obj["kind"] == "rock":
            game["slow_until"] = time.ticks_add(now, 1700)
            game["wobble_until"] = time.ticks_add(now, 700)
            game["notice"] = "ROCK! SLOWING DOWN"
            game["notice_until"] = time.ticks_add(now, 850)
            audio.play(SOUND_ROCK)
        else:
            game["wobble_until"] = time.ticks_add(now, 550)
            game["score"] += 10
            game["notice"] = "FRIENDLY BUMP!"
            game["notice_until"] = time.ticks_add(now, 600)
    return "playing"


def update_game(game, controller, audio, now, dt):
    steering = 88 + game["wheel_level"] * 14
    if controller.held("L"):
        game["player_x"] -= steering * dt
    if controller.held("R"):
        game["player_x"] += steering * dt
    game["player_x"] = max(ROAD_LEFT + PLAYER_W // 2,
                           min(ROAD_RIGHT - PLAYER_W // 2, game["player_x"]))

    speed = current_speed(game, now)
    game["distance"] += speed * dt * 0.105
    game["score"] += int(speed * dt * 0.06)
    game["road_offset"] = (game["road_offset"] + speed * dt) % 40

    if time.ticks_diff(now, game["next_spawn"]) >= 0 and len(game["objects"]) < 9:
        spawn_object(game, now)
    state = update_objects(game, controller, audio, now, dt, speed)
    if game["distance"] >= RACE_METRES:
        game["distance"] = RACE_METRES
        game["score"] += 500
        game["high_score"] = save_high_score(game["score"])
        audio.play(SOUND_FINISH)
        return "finished"
    return state


def apply_upgrade(game, audio, now):
    upgrade = UPGRADES[game["choice"]]
    if upgrade == "WHEELS":
        game["wheel_level"] = min(5, game["wheel_level"] + 1)
        detail = "STEERING +"
    elif upgrade == "KART":
        game["kart_level"] = min(5, game["kart_level"] + 1)
        detail = "TOP SPEED +"
    else:
        game["place_level"] += 1
        detail = "NEW TRACK!"
    game["notice"] = detail
    game["notice_until"] = time.ticks_add(now, 850)
    audio.play(SOUND_CHOICE)


def update_upgrade(game, controller, audio, now):
    if controller.pressed("L"):
        game["choice"] = (game["choice"] - 1) % len(UPGRADES)
    elif controller.pressed("R"):
        game["choice"] = (game["choice"] + 1) % len(UPGRADES)
    if controller.pressed("A"):
        apply_upgrade(game, audio, now)
        return "playing"
    return "upgrade"


def draw_road(game, now):
    verge, edge, road, marker = THEMES[game["place_level"] % len(THEMES)]
    display.set_pen(verge)
    display.clear()
    display.set_pen(edge)
    display.rectangle(ROAD_LEFT - 6, HUD_HEIGHT, 6, HEIGHT - HUD_HEIGHT)
    display.rectangle(ROAD_RIGHT, HUD_HEIGHT, 6, HEIGHT - HUD_HEIGHT)
    display.set_pen(road)
    display.rectangle(ROAD_LEFT, HUD_HEIGHT, ROAD_RIGHT - ROAD_LEFT, HEIGHT - HUD_HEIGHT)
    display.set_pen(ROAD_LIGHT)
    offset = int(game["road_offset"])
    for y in range(HUD_HEIGHT - 40 + offset, HEIGHT, 40):
        for x in (74, 120, 166):
            display.rectangle(x - 2, y, 4, 20)
    display.set_pen(marker)
    display.rectangle(ROAD_LEFT, HUD_HEIGHT, 2, HEIGHT - HUD_HEIGHT)
    display.rectangle(ROAD_RIGHT - 2, HUD_HEIGHT, 2, HEIGHT - HUD_HEIGHT)


def draw_coin(obj, now):
    x = int(obj["x"])
    y = int(obj["y"])
    width = 3 + (now // 100) % 5
    display.set_pen(ORANGE)
    display.rectangle(x - width, y, width * 2, 14)
    display.set_pen(YELLOW)
    display.rectangle(x - max(1, width - 2), y + 2, max(2, (width - 2) * 2), 10)


def draw_boost(obj):
    x = int(obj["x"])
    y = int(obj["y"])
    display.set_pen(CYAN)
    display.polygon([(x - 12, y + 14), (x, y), (x + 12, y + 14),
                     (x + 5, y + 14), (x, y + 8), (x - 5, y + 14)])


def draw_rock(obj):
    x = int(obj["x"])
    y = int(obj["y"])
    display.set_pen(DARK_GREY)
    display.polygon([(x - 11, y + 18), (x - 8, y + 5), (x - 2, y),
                     (x + 8, y + 3), (x + 12, y + 18)])
    display.set_pen(GREY)
    display.polygon([(x - 5, y + 6), (x, y + 2), (x + 5, y + 6)])


def draw_rival(obj):
    x = int(obj["x"])
    y = int(obj["y"])
    display.set_pen(BLACK)
    display.circle(x - 7, y + 15, 4)
    display.circle(x + 7, y + 15, 4)
    display.set_pen(obj["colour"])
    display.rectangle(x - 9, y + 5, 18, 12)
    display.set_pen(YELLOW)
    display.circle(x, y + 4, 5)
    display.set_pen(ORANGE)
    display.rectangle(x + 4, y + 3, 5, 3)


def draw_player(game, now):
    x = int(game["player_x"])
    wobble = 0
    if game["wobble_until"] is not None and time.ticks_diff(game["wobble_until"], now) > 0:
        wobble = -3 if (now // 70) % 2 else 3
    x += wobble
    display.set_pen(BLACK)
    display.circle(x - 8, PLAYER_Y + 21, 5)
    display.circle(x + 8, PLAYER_Y + 21, 5)
    kart_colours = (RED, CYAN, PURPLE, PINK, ORANGE, GREEN)
    display.set_pen(kart_colours[game["kart_level"] % len(kart_colours)])
    display.rectangle(x - 11, PLAYER_Y + 9, 22, 14)
    display.set_pen(YELLOW)
    display.circle(x, PLAYER_Y + 7, 8)
    display.set_pen(ORANGE)
    display.rectangle(x + 5, PLAYER_Y + 5, 8, 4)
    display.set_pen(BLACK)
    display.pixel(x + 2, PLAYER_Y + 5)
    display.set_pen(CYAN)
    display.rectangle(x - 6, PLAYER_Y - 1, 12, 4)
    if game["boost_until"] is not None and time.ticks_diff(game["boost_until"], now) > 0:
        display.set_pen(ORANGE)
        display.polygon([(x - 6, PLAYER_Y + 25), (x - 1, PLAYER_Y + 34),
                         (x + 2, PLAYER_Y + 25)])
        display.set_pen(YELLOW)
        display.polygon([(x + 1, PLAYER_Y + 25), (x + 6, PLAYER_Y + 33),
                         (x + 8, PLAYER_Y + 25)])


def draw_hud(game, now):
    display.set_pen(BLACK)
    display.rectangle(0, 0, WIDTH, HUD_HEIGHT)
    display.set_pen(YELLOW)
    display.text("$" + str(game["coins"]), 3, 4, 42, 2)
    display.set_pen(WHITE)
    display.text(str(int(game["distance"])) + "m", 52, 7, 48, 1)
    display.set_pen(CYAN)
    display.text("SPD " + str(current_speed(game, now)), 103, 7, 55, 1)
    progress = int(72 * game["distance"] / RACE_METRES)
    display.set_pen(DARK_GREY)
    display.rectangle(165, 9, 72, 9)
    display.set_pen(GREEN)
    display.rectangle(165, 9, progress, 9)


def draw_game(game, now):
    draw_road(game, now)
    for obj in game["objects"]:
        if obj["kind"] == "coin":
            draw_coin(obj, now)
        elif obj["kind"] == "boost":
            draw_boost(obj)
        elif obj["kind"] == "rock":
            draw_rock(obj)
        else:
            draw_rival(obj)
    draw_player(game, now)
    draw_hud(game, now)
    if game["notice_until"] is not None and time.ticks_diff(game["notice_until"], now) > 0:
        display.set_pen(BLACK)
        display.rectangle(18, 38, WIDTH - 36, 21)
        centre_text(game["notice"], 44, 1, YELLOW)


def draw_upgrade(game):
    display.set_pen(BLACK)
    display.rectangle(10, 55, WIDTH - 20, 130)
    centre_text("COIN PRIZE!", 64, 2, YELLOW)
    for index, name in enumerate(UPGRADES):
        x = 18 + index * 72
        selected = index == game["choice"]
        display.set_pen(CYAN if selected else DARK_GREY)
        display.rectangle(x, 96, 60, 50)
        display.set_pen(BLACK if selected else WHITE)
        label = "WHEEL" if name == "WHEELS" else ("KART" if name == "KART" else "PLACE")
        width = display.measure_text(label, 1)
        display.text(label, x + (60 - width) // 2, 116, 60, 1)
    centre_text("L/R CHOOSE   A GET", 158, 1, GREEN)


def draw_title(high_score):
    display.set_pen(GRASS)
    display.clear()
    display.set_pen(ROAD)
    display.rectangle(48, 0, 144, HEIGHT)
    display.set_pen(WHITE)
    for y in range(0, HEIGHT, 34):
        display.rectangle(118, y, 4, 17)
    display.set_pen(BLACK)
    display.rectangle(12, 42, WIDTH - 24, 155)
    centre_text("DUCK KART", 53, 3, YELLOW)
    centre_text("RALLY", 82, 4, CYAN)
    centre_text("AGES 3+", 119, 2, GREEN)
    centre_text("L/R STEER", 143, 1, WHITE)
    centre_text("COINS = CHOOSE PRIZES", 158, 1, YELLOW)
    centre_text("ARROWS BOOST  ROCKS SLOW", 173, 1, ORANGE)
    centre_text("HIGH " + str(high_score), 204, 1, WHITE)
    centre_text("+ START       - MENU", 220, 1, GREEN)


def draw_finish(game):
    display.set_pen(BLACK)
    display.rectangle(16, 60, WIDTH - 32, 126)
    centre_text("FINISH!", 71, 4, YELLOW)
    centre_text("DUCK CHAMPION", 112, 2, CYAN)
    centre_text("COINS " + str(game["coins"]), 140, 1, WHITE)
    centre_text("SCORE " + str(game["score"]), 155, 2, GREEN)
    centre_text("+ RACE AGAIN", 178, 1, YELLOW)


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
    high_score = load_high_score()
    last_tick = time.ticks_ms()

    while True:
        now = time.ticks_ms()
        dt = min(50, max(0, time.ticks_diff(now, last_tick))) / 1000.0
        last_tick = now
        controller.poll()
        audio.update(now)

        if controller.pressed("-"):
            controller.pad.clear_leds()
            audio.stop()
            machine.reset()

        if state == "title":
            draw_title(high_score)
            if controller.pressed("+"):
                game = new_game(controller)
                state = "playing"
                audio.play(SOUND_START)
        elif state == "playing":
            state = update_game(game, controller, audio, now, dt)
            draw_game(game, now)
        elif state == "upgrade":
            state = update_upgrade(game, controller, audio, now)
            draw_game(game, now)
            draw_upgrade(game)
        else:
            draw_game(game, now)
            draw_finish(game)
            if controller.pressed("+"):
                high_score = max(high_score, game["high_score"])
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

# ICON bomb
# NAME Rainbow Barrage
# DESC Arc rainbow missiles into storm towers!

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
BASE_Y = 174
FLOOR_HEIGHT = 16
TOWER_CENTRES = (28, 89, 151, 212)
TOWER_WIDTH = 30
LAUNCHER_Y = 218
SPECTRUM_MAX = 7
SCORE_FILE = "rainbow_scores.txt"

BLACK = display.create_pen(0, 0, 0)
WHITE = display.create_pen(255, 255, 255)
SKY = display.create_pen(24, 25, 45)
SKY_LIGHT = display.create_pen(43, 48, 78)
GROUND = display.create_pen(32, 42, 38)
GROUND_LIGHT = display.create_pen(54, 72, 55)
GREY = display.create_pen(95, 100, 115)
DARK_GREY = display.create_pen(42, 45, 55)
YELLOW = display.create_pen(255, 225, 40)
RED = display.create_pen(240, 55, 60)
ORANGE = display.create_pen(255, 135, 35)
GREEN = display.create_pen(65, 220, 90)
CYAN = display.create_pen(45, 215, 235)
BLUE = display.create_pen(55, 95, 235)
PURPLE = display.create_pen(165, 70, 220)
PINK = display.create_pen(245, 85, 170)

RAINBOW = (RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, PURPLE)
TOWER_COLOURS = (PURPLE, CYAN, ORANGE, PINK)

SOUND_START = ((392, 55), (523, 65), (659, 100))
SOUND_LAUNCH = ((310, 35), (470, 50))
SOUND_HIT = ((170, 45), (105, 80))
SOUND_COLLAPSE = ((180, 45), (140, 50), (95, 110))
SOUND_INTERCEPT = ((880, 35), (1200, 60))
SOUND_DAMAGE = ((210, 90), (130, 120), (75, 180))
SOUND_SPECTRUM = ((440, 45), (554, 45), (659, 45), (880, 130))
SOUND_HELPER = ((659, 45), (880, 55), (1175, 100))
SOUND_WRAITH = ((150, 55), (110, 70), (75, 110))
SOUND_ERROR = ((115, 100),)
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
    KEYS = ("U", "D", "L", "R", "A", "B", "+", "-")

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
            elif down and name in ("U", "D", "L", "R", "A"):
                held = time.ticks_diff(now, self.held_since.get(name, now))
                repeated = time.ticks_diff(now, self.last_repeat.get(name, now))
                if held >= 300 and repeated >= 170:
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


def floor_y(floor):
    return BASE_Y - ((floor + 1) * FLOOR_HEIGHT)


def tower_top(tower):
    return floor_y(len(tower["blocks"]) - 1) if tower["blocks"] else BASE_Y


def make_tower(index, wave):
    height = min(8, 3 + wave + random.randint(0, 2))
    blocks = []
    for floor in range(height):
        armour_chance = min(0.55, 0.12 + wave * 0.05)
        hit_points = 2 if floor == 0 or random.random() < armour_chance else 1
        if wave >= 6 and floor == 0:
            hit_points = 3
        blocks.append({"hp": hit_points, "max_hp": hit_points})
    return {
        "index": index,
        "x": TOWER_CENTRES[index],
        "colour": TOWER_COLOURS[index],
        "blocks": blocks,
    }


def new_wave(game, now):
    game["towers"] = [make_tower(index, game["wave"])
                      for index in range(len(TOWER_CENTRES))]
    game["selected"] = 1
    game["target_floor"] = 0
    game["player_missiles"] = []
    game["enemy_missiles"] = []
    game["energy_pulses"] = []
    game["flyers"] = []
    game["helper_beam"] = None
    game["next_flyer"] = time.ticks_add(now, random.randint(7000, 12000))
    game["last_enemy_fire"] = now
    game["wave_ready"] = None
    game["notice"] = "WAVE " + str(game["wave"])
    game["notice_until"] = time.ticks_add(now, 900)


def reset_game(controller):
    now = time.ticks_ms()
    game = {
        "wave": 1,
        "score": 0,
        "lives": 3,
        "spectrum": 0,
        "towers": [],
        "selected": 1,
        "target_floor": 0,
        "player_missiles": [],
        "enemy_missiles": [],
        "energy_pulses": [],
        "flyers": [],
        "helper_beam": None,
        "next_flyer": time.ticks_add(now, random.randint(7000, 12000)),
        "last_flyer_kind": "wraith",
        "last_enemy_fire": now,
        "last_launch": time.ticks_add(now, -500),
        "invulnerable_until": None,
        "spectrum_until": None,
        "wave_ready": None,
        "notice": None,
        "notice_until": None,
        "leaderboard": None,
        "leaderboard_rank": None,
    }
    new_wave(game, now)
    controller.show_lives(game["lives"])
    return game


def missile_position(missile):
    progress = missile["progress"]
    inverse = 1.0 - progress
    x = (inverse * inverse * missile["start_x"] +
         2 * inverse * progress * missile["control_x"] +
         progress * progress * missile["target_x"])
    y = (inverse * inverse * missile["start_y"] +
         2 * inverse * progress * missile["control_y"] +
         progress * progress * missile["target_y"])
    return x, y


def launch_player_missile(game, now, audio):
    tower = game["towers"][game["selected"]]
    if not tower["blocks"]:
        game["notice"] = "TOWER DOWN"
        game["notice_until"] = time.ticks_add(now, 650)
        audio.play(SOUND_ERROR)
        return
    if time.ticks_diff(now, game["last_launch"]) < 260:
        return
    target_floor = min(game["target_floor"], len(tower["blocks"]) - 1)
    start_x = TOWER_CENTRES[game["selected"]]
    target_x = tower["x"]
    target_y = floor_y(target_floor) + FLOOR_HEIGHT // 2
    game["player_missiles"].append({
        "tower": game["selected"],
        "floor": target_floor,
        "start_x": float(start_x), "start_y": float(LAUNCHER_Y),
        "control_x": float((start_x + target_x) / 2 + random.randint(-24, 24)),
        "control_y": float(max(HUD_HEIGHT + 14, target_y - 42)),
        "target_x": float(target_x), "target_y": float(target_y),
        "progress": 0.0,
        "duration": 0.72,
        "trail": [],
    })
    game["last_launch"] = now
    audio.play(SOUND_LAUNCH)


def damage_tower(game, tower_index, target_floor, now, audio):
    tower = game["towers"][tower_index]
    if target_floor >= len(tower["blocks"]):
        return
    block = tower["blocks"][target_floor]
    block["hp"] -= 1
    if block["hp"] > 0:
        game["score"] += 40
        game["notice"] = "ARMOUR HIT"
        game["notice_until"] = time.ticks_add(now, 450)
        audio.play(SOUND_HIT)
        return

    collapsed = len(tower["blocks"]) - target_floor
    tower["blocks"] = tower["blocks"][:target_floor]
    points = 100 + max(0, collapsed - 1) * 75
    if collapsed >= 3:
        points += collapsed * 25
    game["score"] += points
    game["spectrum"] = min(SPECTRUM_MAX, game["spectrum"] + collapsed)
    game["notice"] = ("COLLAPSE x" + str(collapsed) if collapsed > 1 else "DIRECT HIT")
    game["notice_until"] = time.ticks_add(now, 700)
    audio.play(SOUND_COLLAPSE)
    if game["selected"] == tower_index:
        game["target_floor"] = max(0, min(game["target_floor"], len(tower["blocks"]) - 1))


def launch_enemy_missile(game, now):
    candidates = [tower for tower in game["towers"] if tower["blocks"]]
    if not candidates:
        return
    tower = random.choice(candidates)
    start_x = tower["x"]
    start_y = tower_top(tower)
    target_x = TOWER_CENTRES[game["selected"]]
    duration = max(0.72, 1.28 - game["wave"] * 0.045)
    game["enemy_missiles"].append({
        "start_x": float(start_x), "start_y": float(start_y),
        "control_x": float((start_x + target_x) / 2),
        "control_y": float(min(LAUNCHER_Y - 25, start_y + 75)),
        "target_x": float(target_x), "target_y": float(LAUNCHER_Y),
        "progress": 0.0,
        "duration": duration,
        "trail": [],
    })
    game["last_enemy_fire"] = now


def spawn_flyer(game, now):
    # Bias toward alternating visitors so both characters appear in a typical
    # run, while keeping their arrival side, height and timing unpredictable.
    if random.random() < 0.75:
        kind = "helper" if game["last_flyer_kind"] == "wraith" else "wraith"
    else:
        kind = random.choice(("helper", "wraith"))
    direction = random.choice((-1, 1))
    game["flyers"].append({
        "kind": kind,
        "x": -18.0 if direction > 0 else WIDTH + 18.0,
        "y": float(random.randint(45, 86)),
        "direction": direction,
        "speed": random.randint(38, 55),
        "acted": False,
    })
    game["last_flyer_kind"] = kind
    game["next_flyer"] = time.ticks_add(now, random.randint(9000, 16000))
    game["notice"] = "SKY SPARK!" if kind == "helper" else "VOID WRAITH!"
    game["notice_until"] = time.ticks_add(now, 850)


def helper_attack(game, flyer, now, audio):
    candidates = [tower for tower in game["towers"] if tower["blocks"]]
    if not candidates:
        return
    target = candidates[0]
    for tower in candidates[1:]:
        if len(tower["blocks"]) > len(target["blocks"]):
            target = tower
    target_y = tower_top(target) + FLOOR_HEIGHT // 2
    target["blocks"].pop()
    game["score"] += 125
    game["spectrum"] = min(SPECTRUM_MAX, game["spectrum"] + 1)
    game["helper_beam"] = {
        "start_x": flyer["x"], "start_y": flyer["y"],
        "target_x": target["x"], "target_y": target_y,
        "until": time.ticks_add(now, 550),
    }
    game["notice"] = "SKY SPARK +125"
    game["notice_until"] = time.ticks_add(now, 800)
    audio.play(SOUND_HELPER)


def wraith_attack(game, flyer, now, audio):
    game["energy_pulses"].append({
        "start_x": flyer["x"], "start_y": flyer["y"],
        "target_x": float(TOWER_CENTRES[game["selected"]]),
        "target_y": float(LAUNCHER_Y),
        "progress": 0.0,
        "duration": max(0.75, 1.15 - game["wave"] * 0.025),
    })
    game["notice"] = "ENERGY PULSE - MOVE!"
    game["notice_until"] = time.ticks_add(now, 950)
    audio.play(SOUND_WRAITH)


def pulse_position(pulse):
    progress = pulse["progress"]
    return (
        pulse["start_x"] + (pulse["target_x"] - pulse["start_x"]) * progress,
        pulse["start_y"] + (pulse["target_y"] - pulse["start_y"]) * progress,
    )


def update_flyers(game, now, dt, controller, audio):
    if time.ticks_diff(now, game["next_flyer"]) >= 0:
        spawn_flyer(game, now)

    for flyer in game["flyers"][:]:
        flyer["x"] += flyer["direction"] * flyer["speed"] * dt
        reached_centre = ((flyer["direction"] > 0 and flyer["x"] >= WIDTH // 2) or
                          (flyer["direction"] < 0 and flyer["x"] <= WIDTH // 2))
        if reached_centre and not flyer["acted"]:
            flyer["acted"] = True
            if flyer["kind"] == "helper":
                helper_attack(game, flyer, now, audio)
            else:
                wraith_attack(game, flyer, now, audio)
        if ((flyer["direction"] > 0 and flyer["x"] > WIDTH + 24) or
                (flyer["direction"] < 0 and flyer["x"] < -24)):
            game["flyers"].remove(flyer)

    if (game["helper_beam"] is not None and
            time.ticks_diff(now, game["helper_beam"]["until"]) >= 0):
        game["helper_beam"] = None

    for pulse in game["energy_pulses"][:]:
        pulse["progress"] = min(1.0, pulse["progress"] + dt / pulse["duration"])
        if pulse["progress"] >= 1.0:
            game["energy_pulses"].remove(pulse)
            current_launcher = TOWER_CENTRES[game["selected"]]
            invulnerable = (game["invulnerable_until"] is not None and
                            time.ticks_diff(game["invulnerable_until"], now) > 0)
            if abs(current_launcher - pulse["target_x"]) < 22 and not invulnerable:
                game["lives"] -= 1
                controller.show_lives(game["lives"])
                game["invulnerable_until"] = time.ticks_add(now, 900)
                game["notice"] = "PULSE HIT!"
                game["notice_until"] = time.ticks_add(now, 800)
                audio.play(SOUND_DAMAGE)
            else:
                game["score"] += 50


def use_spectrum(game, now, audio):
    if game["spectrum"] < SPECTRUM_MAX:
        game["notice"] = "NEED 7 COLOURS"
        game["notice_until"] = time.ticks_add(now, 700)
        audio.play(SOUND_ERROR)
        return
    destroyed = 0
    for tower in game["towers"]:
        if tower["blocks"]:
            tower["blocks"].pop()
            destroyed += 1
    cleared = len(game["enemy_missiles"]) + len(game["energy_pulses"])
    game["enemy_missiles"] = []
    game["energy_pulses"] = []
    game["spectrum"] = 0
    game["score"] += destroyed * 125 + cleared * 50
    game["spectrum_until"] = time.ticks_add(now, 650)
    game["notice"] = "SPECTRUM BLAST!"
    game["notice_until"] = time.ticks_add(now, 900)
    audio.play(SOUND_SPECTRUM)


def move_missiles(game, dt, now, controller, audio):
    for missile in game["player_missiles"][:]:
        missile["progress"] = min(1.0, missile["progress"] + dt / missile["duration"])
        position = missile_position(missile)
        missile["trail"].append(position)
        if len(missile["trail"]) > 13:
            missile["trail"].pop(0)
        if missile["progress"] >= 1.0:
            game["player_missiles"].remove(missile)
            damage_tower(game, missile["tower"], missile["floor"], now, audio)

    for missile in game["enemy_missiles"][:]:
        missile["progress"] = min(1.0, missile["progress"] + dt / missile["duration"])
        position = missile_position(missile)
        missile["trail"].append(position)
        if len(missile["trail"]) > 8:
            missile["trail"].pop(0)
        if missile["progress"] >= 1.0:
            game["enemy_missiles"].remove(missile)
            current_launcher = TOWER_CENTRES[game["selected"]]
            invulnerable = (game["invulnerable_until"] is not None and
                            time.ticks_diff(game["invulnerable_until"], now) > 0)
            if abs(current_launcher - missile["target_x"]) < 22 and not invulnerable:
                game["lives"] -= 1
                controller.show_lives(game["lives"])
                game["invulnerable_until"] = time.ticks_add(now, 900)
                game["notice"] = "LAUNCHER HIT!"
                game["notice_until"] = time.ticks_add(now, 800)
                audio.play(SOUND_DAMAGE)
            else:
                game["score"] += 25

    for player_missile in game["player_missiles"][:]:
        px, py = missile_position(player_missile)
        intercepted = None
        for enemy_missile in game["enemy_missiles"]:
            ex, ey = missile_position(enemy_missile)
            if (px - ex) * (px - ex) + (py - ey) * (py - ey) < 90:
                intercepted = enemy_missile
                break
        if intercepted is not None:
            game["player_missiles"].remove(player_missile)
            game["enemy_missiles"].remove(intercepted)
            game["score"] += 75
            game["notice"] = "INTERCEPT +75"
            game["notice_until"] = time.ticks_add(now, 650)
            audio.play(SOUND_INTERCEPT)


def update_game(game, controller, audio, now, dt):
    if controller.pressed("L"):
        game["selected"] = max(0, game["selected"] - 1)
        tower = game["towers"][game["selected"]]
        game["target_floor"] = max(0, min(game["target_floor"], len(tower["blocks"]) - 1))
    elif controller.pressed("R"):
        game["selected"] = min(len(TOWER_CENTRES) - 1, game["selected"] + 1)
        tower = game["towers"][game["selected"]]
        game["target_floor"] = max(0, min(game["target_floor"], len(tower["blocks"]) - 1))
    if controller.pressed("U"):
        tower = game["towers"][game["selected"]]
        game["target_floor"] = min(max(0, len(tower["blocks"]) - 1), game["target_floor"] + 1)
    elif controller.pressed("D"):
        game["target_floor"] = max(0, game["target_floor"] - 1)
    if controller.pressed("A"):
        launch_player_missile(game, now, audio)
    if controller.pressed("B"):
        use_spectrum(game, now, audio)

    move_missiles(game, dt, now, controller, audio)
    update_flyers(game, now, dt, controller, audio)

    fire_interval = max(900, 3000 - game["wave"] * 140)
    if game["wave_ready"] is None and time.ticks_diff(now, game["last_enemy_fire"]) >= fire_interval:
        launch_enemy_missile(game, now)

    if all(not tower["blocks"] for tower in game["towers"]):
        if game["wave_ready"] is None:
            game["score"] += game["wave"] * 500
            game["wave_ready"] = time.ticks_add(now, 1500)
            game["enemy_missiles"] = []
            game["energy_pulses"] = []
            game["notice"] = "WAVE CLEAR +" + str(game["wave"] * 500)
            game["notice_until"] = game["wave_ready"]
        elif time.ticks_diff(now, game["wave_ready"]) >= 0:
            game["wave"] += 1
            new_wave(game, now)


def draw_background():
    display.set_pen(SKY)
    display.clear()
    display.set_pen(SKY_LIGHT)
    for y in range(HUD_HEIGHT + 8, BASE_Y, 24):
        display.rectangle(0, y, WIDTH, 2)
    display.set_pen(GROUND)
    display.rectangle(0, BASE_Y, WIDTH, HEIGHT - BASE_Y)
    display.set_pen(GROUND_LIGHT)
    display.rectangle(0, BASE_Y, WIDTH, 4)
    for x in range(0, WIDTH, 18):
        display.rectangle(x, 230, 10, 3)


def draw_tower(tower, selected, target_floor):
    left = tower["x"] - TOWER_WIDTH // 2
    for floor, block in enumerate(tower["blocks"]):
        y = floor_y(floor)
        display.set_pen(DARK_GREY)
        display.rectangle(left - 2, y - 1, TOWER_WIDTH + 4, FLOOR_HEIGHT + 1)
        display.set_pen(tower["colour"])
        display.rectangle(left, y, TOWER_WIDTH, FLOOR_HEIGHT - 2)
        display.set_pen(BLACK)
        display.rectangle(left + 4, y + 4, 6, 7)
        display.rectangle(left + TOWER_WIDTH - 10, y + 4, 6, 7)
        if block["hp"] < block["max_hp"]:
            display.set_pen(WHITE)
            display.line(left + 17, y + 2, left + 22, y + 12, 2)
        if selected and floor == target_floor:
            display.set_pen(YELLOW)
            display.rectangle(left - 5, y + 2, 3, FLOOR_HEIGHT - 6)
            display.rectangle(left + TOWER_WIDTH + 2, y + 2, 3, FLOOR_HEIGHT - 6)
    if tower["blocks"]:
        top = tower_top(tower)
        display.set_pen(tower["colour"])
        display.polygon([
            (tower["x"] - 14, top), (tower["x"], top - 11),
            (tower["x"] + 14, top),
        ])


def draw_launcher(game, now):
    x = TOWER_CENTRES[game["selected"]]
    visible = (game["invulnerable_until"] is None or
               time.ticks_diff(game["invulnerable_until"], now) <= 0 or
               (now // 80) % 2 == 0)
    if not visible:
        return
    display.set_pen(GREY)
    display.rectangle(x - 14, LAUNCHER_Y, 28, 10)
    display.set_pen(CYAN)
    display.rectangle(x - 5, LAUNCHER_Y - 13, 10, 15)
    display.set_pen(WHITE)
    display.rectangle(x - 2, LAUNCHER_Y - 20, 4, 9)
    display.set_pen(DARK_GREY)
    display.rectangle(x - 18, LAUNCHER_Y + 8, 36, 5)


def draw_player_missile(missile):
    trail = missile["trail"]
    for index in range(1, len(trail)):
        display.set_pen(RAINBOW[(index + len(trail)) % len(RAINBOW)])
        display.line(int(trail[index - 1][0]), int(trail[index - 1][1]),
                     int(trail[index][0]), int(trail[index][1]), 3)
    x, y = missile_position(missile)
    display.set_pen(WHITE)
    display.circle(int(x), int(y), 3)


def draw_enemy_missile(missile):
    trail = missile["trail"]
    for index in range(1, len(trail)):
        display.set_pen(ORANGE if index % 2 else RED)
        display.line(int(trail[index - 1][0]), int(trail[index - 1][1]),
                     int(trail[index][0]), int(trail[index][1]), 2)
    x, y = missile_position(missile)
    display.set_pen(RED)
    display.circle(int(x), int(y), 4)


def draw_flyer(flyer, frame):
    x = int(flyer["x"])
    y = int(flyer["y"])
    direction = flyer["direction"]
    if flyer["kind"] == "helper":
        wing = 5 + (frame % 2) * 3
        display.set_pen(YELLOW)
        display.polygon([(x - 4, y), (x - 13, y - wing), (x - 10, y + 5)])
        display.polygon([(x + 4, y), (x + 13, y - wing), (x + 10, y + 5)])
        display.set_pen(CYAN)
        display.circle(x, y, 7)
        display.set_pen(WHITE)
        display.circle(x + direction * 4, y - 2, 2)
        display.set_pen(BLACK)
        display.pixel(x + direction * 5, y - 2)
        display.set_pen(PINK)
        display.rectangle(x - 2, y + 6, 5, 5)
    else:
        flap = 8 if frame % 2 else 4
        display.set_pen(PURPLE)
        display.polygon([(x - 3, y), (x - 15, y - flap),
                         (x - 11, y + 8), (x, y + 4)])
        display.polygon([(x + 3, y), (x + 15, y - flap),
                         (x + 11, y + 8), (x, y + 4)])
        display.set_pen(DARK_GREY)
        display.circle(x, y, 8)
        display.set_pen(RED)
        display.pixel(x - 3, y - 2)
        display.pixel(x + 3, y - 2)
        display.set_pen(PURPLE)
        display.polygon([(x - 6, y + 4), (x, y + 15), (x + 6, y + 4)])


def draw_energy_pulse(pulse, frame):
    x, y = pulse_position(pulse)
    radius = 6 + frame % 3
    display.set_pen(PURPLE)
    display.circle(int(x), int(y), radius)
    display.set_pen(PINK)
    display.circle(int(x), int(y), max(2, radius - 3))
    display.set_pen(WHITE)
    display.pixel(int(x), int(y))


def draw_helper_beam(beam):
    for index, colour in enumerate(RAINBOW):
        display.set_pen(colour)
        display.line(int(beam["start_x"]), int(beam["start_y"] + index - 3),
                     int(beam["target_x"]), int(beam["target_y"] + index - 3), 1)


def draw_hud(game):
    display.set_pen(BLACK)
    display.rectangle(0, 0, WIDTH, HUD_HEIGHT)
    display.set_pen(YELLOW)
    display.text("S " + str(game["score"]), 3, 3, 92, 2)
    display.set_pen(WHITE)
    display.text("W" + str(game["wave"]) + " L" + str(game["lives"]), 105, 7, 55, 1)
    for index, colour in enumerate(RAINBOW):
        display.set_pen(colour if index < game["spectrum"] else DARK_GREY)
        display.rectangle(165 + index * 10, 8, 8, 10)


def draw_game(game, now):
    draw_background()
    for index, tower in enumerate(game["towers"]):
        draw_tower(tower, index == game["selected"], game["target_floor"])
    if game["helper_beam"] is not None:
        draw_helper_beam(game["helper_beam"])
    frame = (now // 120) % 4
    for flyer in game["flyers"]:
        draw_flyer(flyer, frame)
    for missile in game["player_missiles"]:
        draw_player_missile(missile)
    for missile in game["enemy_missiles"]:
        draw_enemy_missile(missile)
    for pulse in game["energy_pulses"]:
        draw_energy_pulse(pulse, frame)
    draw_launcher(game, now)

    if game["spectrum_until"] is not None and time.ticks_diff(game["spectrum_until"], now) > 0:
        offset = (now // 35) % 18
        for index, colour in enumerate(RAINBOW):
            display.set_pen(colour)
            display.rectangle(0, 38 + index * 17 + offset, WIDTH, 5)

    draw_hud(game)
    if game["notice_until"] is not None and time.ticks_diff(game["notice_until"], now) > 0:
        display.set_pen(BLACK)
        display.rectangle(22, 34, WIDTH - 44, 20)
        centre_text(game["notice"], 39, 1, YELLOW)


def draw_title():
    draw_background()
    for index, colour in enumerate(RAINBOW):
        display.set_pen(colour)
        display.line(15, 176 - index * 3, 225, 62 + index * 2, 3)
    display.set_pen(BLACK)
    display.rectangle(10, 50, WIDTH - 20, 125)
    centre_text("RAINBOW", 61, 3, CYAN)
    centre_text("BARRAGE", 89, 3, YELLOW)
    centre_text("L/R TOWER  U/D FLOOR", 124, 1)
    centre_text("A FIRE   B SPECTRUM", 141, 1)
    centre_text("+ START     - MENU", 160, 1, GREEN)


def load_scores():
    scores = []
    try:
        with open(SCORE_FILE, "r") as score_file:
            for line in score_file:
                try:
                    scores.append(int(line.strip()))
                except ValueError:
                    pass
    except OSError:
        pass
    return scores


def record_score(score):
    scores = load_scores()
    scores.append(score)
    for left in range(len(scores)):
        for right in range(left + 1, len(scores)):
            if scores[right] > scores[left]:
                scores[left], scores[right] = scores[right], scores[left]
    scores = scores[:5]
    rank = scores.index(score) + 1 if score in scores else 6
    try:
        with open(SCORE_FILE, "w") as score_file:
            for saved_score in scores:
                score_file.write(str(saved_score) + "\n")
    except OSError:
        pass
    return scores, rank


def draw_leaderboard(game):
    display.set_pen(BLACK)
    display.rectangle(9, 30, WIDTH - 18, 205)
    centre_text("GAME OVER", 38, 2, RED)
    centre_text("FINAL " + str(game["score"]), 64, 2, YELLOW)
    for index in range(5):
        y = 94 + index * 23
        display.set_pen(CYAN if index + 1 == game["leaderboard_rank"] else WHITE)
        score = game["leaderboard"][index] if index < len(game["leaderboard"]) else "---"
        display.text(str(index + 1) + ".", 48, y, WIDTH, 2)
        display.text(str(score), 90, y, WIDTH, 2)
    centre_text("+ RETRY     - MENU", 216, 1, GREEN)


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
    last_tick = time.ticks_ms()

    while True:
        now = time.ticks_ms()
        dt = min(50, time.ticks_diff(now, last_tick)) / 1000.0
        last_tick = now
        controller.poll()
        audio.update(now)

        if controller.pressed("-"):
            audio.stop()
            controller.pad.clear_leds()
            machine.reset()

        if state == "title":
            draw_title()
            if controller.pressed("+"):
                game = reset_game(controller)
                state = "playing"
                audio.play(SOUND_START)
        elif state == "playing":
            update_game(game, controller, audio, now, dt)
            draw_game(game, now)
            if game["lives"] <= 0:
                game["leaderboard"], game["leaderboard_rank"] = record_score(game["score"])
                state = "game_over"
                audio.play(SOUND_GAME_OVER)
        else:
            draw_game(game, now)
            draw_leaderboard(game)
            if controller.pressed("+"):
                game = reset_game(controller)
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

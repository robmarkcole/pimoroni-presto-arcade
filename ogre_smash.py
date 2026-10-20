# ICON bomb
# NAME Ogre Smash!
# DESC Smash traffic, leap lakes and wield lightning!

import math
import random
import time

import machine
from machine import I2C
from presto import Buzzer, Presto
from qwstpad import ADDRESSES, QwSTPad


I2C_PINS = {"id": 0, "sda": 40, "scl": 41}
I2C_ADDRESS = ADDRESSES[0]

presto = Presto(ambient_light=True)
display = presto.display
WIDTH, HEIGHT = display.get_bounds()

HUD_HEIGHT = 24
PLAYER_Y = 184
LANE_CENTRES = (36, 92, 148, 204)
JUMP_DURATION_MS = 1600
POWER_DURATION_MS = 8000
SCORE_FILE = "ogre_scores.txt"

BLACK = display.create_pen(0, 0, 0)
WHITE = display.create_pen(255, 255, 255)
ROAD = display.create_pen(55, 58, 66)
ROAD_EDGE = display.create_pen(30, 115, 55)
LANE_MARK = display.create_pen(250, 220, 70)
OGRE = display.create_pen(75, 205, 65)
OGRE_DARK = display.create_pen(30, 105, 35)
OGRE_GLOW = display.create_pen(175, 255, 95)
PURPLE = display.create_pen(115, 60, 145)
RED = display.create_pen(230, 55, 55)
ORANGE = display.create_pen(255, 135, 35)
CYAN = display.create_pen(40, 210, 230)
BLUE = display.create_pen(35, 115, 225)
BLUE_LIGHT = display.create_pen(80, 185, 255)
YELLOW = display.create_pen(255, 230, 35)
GREY = display.create_pen(115, 120, 135)
DARK_GREY = display.create_pen(45, 48, 55)
HOLE_EDGE = display.create_pen(105, 68, 42)

MUSIC = (
    (262, 150), (0, 40), (330, 150), (0, 40),
    (392, 150), (0, 40), (523, 230), (0, 80),
    (392, 150), (0, 40), (330, 150), (0, 40),
    (294, 150), (330, 150), (392, 260), (0, 100),
)
SOUND_START = ((392, 70), (523, 90), (659, 120))
SOUND_JUMP = ((440, 55), (587, 55), (784, 90))
SOUND_SMASH = ((180, 55), (110, 100))
SOUND_PICKUP = ((523, 55), (659, 55), (784, 55), (1047, 120))
SOUND_LIGHTNING = ((1200, 40), (700, 40), (1500, 50), (520, 120))
SOUND_DAMAGE = ((220, 100), (150, 120), (90, 180))
SOUND_GAME_OVER = ((330, 160), (262, 180), (196, 320))
SOUND_ERROR = ((110, 120),)
SOUND_DUCK = ((740, 70), (520, 110))


class Audio:
    def __init__(self):
        self.buzzer = Buzzer(43)
        self.current_frequency = None
        self.effect = None
        self.effect_index = 0
        self.effect_deadline = None
        self.music_index = 0
        self.music_deadline = None

    def set_frequency(self, frequency):
        if frequency == self.current_frequency:
            return
        self.current_frequency = frequency
        if frequency:
            self.buzzer.set_tone(frequency, 0.22)
        else:
            self.buzzer.set_tone(-1)

    def play(self, sequence):
        self.effect = sequence
        self.effect_index = 0
        self.effect_deadline = None

    def update(self, now):
        if self.effect is not None:
            if self.effect_deadline is None:
                frequency, duration = self.effect[self.effect_index]
                self.set_frequency(frequency)
                self.effect_deadline = time.ticks_add(now, duration)
            elif time.ticks_diff(now, self.effect_deadline) >= 0:
                self.effect_index += 1
                if self.effect_index >= len(self.effect):
                    self.effect = None
                    self.effect_deadline = None
                    self.music_deadline = None
                else:
                    frequency, duration = self.effect[self.effect_index]
                    self.set_frequency(frequency)
                    self.effect_deadline = time.ticks_add(now, duration)
            return

        if self.music_deadline is None or time.ticks_diff(now, self.music_deadline) >= 0:
            frequency, duration = MUSIC[self.music_index]
            self.set_frequency(frequency)
            self.music_deadline = time.ticks_add(now, duration)
            self.music_index = (self.music_index + 1) % len(MUSIC)

    def stop(self):
        self.effect = None
        self.set_frequency(0)


class Controller:
    KEYS = ("U", "D", "L", "R", "A", "B", "+", "-")

    def __init__(self):
        self.pad = QwSTPad(I2C(**I2C_PINS), I2C_ADDRESS)
        buttons = self.pad.read_buttons()
        self.previous = {name: buttons[name] for name in buttons}
        self.events = {}

    def poll(self):
        buttons = self.pad.read_buttons()
        self.events = {}
        for name in self.KEYS:
            if buttons[name] and not self.previous[name]:
                self.events[name] = True
        self.previous = {name: buttons[name] for name in buttons}

    def pressed(self, name):
        return self.events.get(name, False)

    def show_lives(self, lives):
        self.pad.set_leds((1 << min(lives, 4)) - 1)


def centre_text(text, y, scale=1, pen=WHITE):
    display.set_pen(pen)
    width = display.measure_text(text, scale)
    display.text(text, (WIDTH - width) // 2, y, WIDTH, scale)


def lane_x(lane, width):
    return LANE_CENTRES[lane] - (width // 2)


def overlaps(ax, ay, aw, ah, bx, by, bw, bh):
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def new_obstacle(kind, lane):
    if kind == "car":
        return {
            "kind": kind, "lane": lane, "y": -38.0,
            "width": 28, "height": 38,
            "colour": random.choice((RED, ORANGE, CYAN, PURPLE)),
            "speed_factor": random.choice((0.85, 1.0, 1.15, 1.3)),
        }
    if kind == "truck":
        return {
            "kind": kind, "lane": lane, "y": -58.0,
            "width": 38, "height": 58, "colour": GREY,
            "speed_factor": random.choice((0.8, 0.95)),
        }
    if kind == "hole":
        return {
            "kind": kind, "lane": lane, "y": -46.0,
            "width": 48, "height": 46, "colour": BLACK,
            "speed_factor": 1.0,
        }
    return {
        "kind": "lake", "lane": lane, "y": -46.0,
        "width": 48, "height": 46, "colour": BLUE, "speed_factor": 1.0,
    }


def new_powerup(lane, y):
    return {"lane": lane, "y": float(y), "width": 18, "height": 22}


def new_duck_crossing():
    direction = random.choice((-1, 1))
    return {
        "x": -28.0 if direction > 0 else WIDTH + 28.0,
        "y": PLAYER_Y + 8,
        "direction": direction,
        "speed": random.randint(42, 62),
        "hit": False,
    }


def duck_x(crossing, index):
    return crossing["x"] - (crossing["direction"] * index * 19)


def draw_road(elapsed_ms):
    display.set_pen(ROAD_EDGE)
    display.clear()
    display.set_pen(ROAD)
    display.rectangle(8, HUD_HEIGHT, WIDTH - 16, HEIGHT - HUD_HEIGHT)

    scroll = int(elapsed_ms / 12) % 32
    display.set_pen(LANE_MARK)
    for divider in (64, 120, 176):
        for y in range(HUD_HEIGHT - 32 + scroll, HEIGHT, 32):
            display.rectangle(divider - 1, y, 3, 15)


def draw_car(obstacle):
    x = lane_x(obstacle["lane"], obstacle["width"])
    y = int(obstacle["y"])
    display.set_pen(obstacle["colour"])
    display.rectangle(x, y, obstacle["width"], obstacle["height"])
    display.set_pen(BLACK)
    display.rectangle(x + 5, y + 7, obstacle["width"] - 10, 10)
    if obstacle["speed_factor"] > 1.1:
        display.set_pen(YELLOW)
        display.rectangle(x + (obstacle["width"] // 2) - 2, y + 19, 4, 13)
    display.set_pen(BLACK)
    display.rectangle(x - 2, y + 6, 4, 9)
    display.rectangle(x + obstacle["width"] - 2, y + 6, 4, 9)
    display.rectangle(x - 2, y + obstacle["height"] - 15, 4, 9)
    display.rectangle(x + obstacle["width"] - 2, y + obstacle["height"] - 15, 4, 9)


def draw_truck(obstacle):
    x = lane_x(obstacle["lane"], obstacle["width"])
    y = int(obstacle["y"])
    display.set_pen(GREY)
    display.rectangle(x, y, obstacle["width"], obstacle["height"])
    display.set_pen(DARK_GREY)
    display.rectangle(x + 4, y + 5, obstacle["width"] - 8, 12)
    display.set_pen(RED)
    display.rectangle(x + 4, y + obstacle["height"] - 6, 7, 4)
    display.rectangle(x + obstacle["width"] - 11, y + obstacle["height"] - 6, 7, 4)
    display.set_pen(BLACK)
    display.rectangle(x - 3, y + 10, 5, 13)
    display.rectangle(x + obstacle["width"] - 2, y + 10, 5, 13)
    display.rectangle(x - 3, y + obstacle["height"] - 14, 5, 10)
    display.rectangle(x + obstacle["width"] - 2, y + obstacle["height"] - 14, 5, 10)


def draw_lake(obstacle, elapsed_ms):
    x = lane_x(obstacle["lane"], obstacle["width"])
    y = int(obstacle["y"])
    display.set_pen(BLUE)
    display.rectangle(x, y, obstacle["width"], obstacle["height"])
    display.set_pen(BLUE_LIGHT)
    wave = (elapsed_ms // 120) % 12
    for row in (9, 24, 39):
        display.rectangle(x + ((row + wave) % 14), y + row, 18, 3)


def draw_hole(obstacle):
    x = lane_x(obstacle["lane"], obstacle["width"])
    y = int(obstacle["y"])
    display.set_pen(HOLE_EDGE)
    display.rectangle(x, y, obstacle["width"], obstacle["height"])
    display.set_pen(BLACK)
    display.rectangle(x + 5, y + 5, obstacle["width"] - 10, obstacle["height"] - 10)
    display.set_pen(DARK_GREY)
    display.rectangle(x + 10, y + 9, obstacle["width"] - 20, 4)


def draw_powerup(powerup, elapsed_ms):
    x = lane_x(powerup["lane"], powerup["width"])
    y = int(powerup["y"])
    if (elapsed_ms // 100) % 2:
        display.set_pen(WHITE)
        display.rectangle(x - 2, y - 2, powerup["width"] + 4, powerup["height"] + 4)
    display.set_pen(YELLOW)
    display.polygon([
        (x + 10, y), (x + 3, y + 12), (x + 9, y + 12),
        (x + 6, y + 22), (x + 16, y + 8), (x + 10, y + 8),
    ])


def draw_ducks(crossing):
    y = int(crossing["y"])
    direction = crossing["direction"]
    for index in range(3):
        x = int(duck_x(crossing, index))
        display.set_pen(YELLOW)
        display.rectangle(x, y + 3, 13, 8)
        head_x = x + 9 if direction > 0 else x - 3
        display.rectangle(head_x, y, 7, 7)
        display.set_pen(ORANGE)
        beak_x = head_x + 7 if direction > 0 else head_x - 3
        display.rectangle(beak_x, y + 3, 3, 3)
        display.rectangle(x + 3, y + 11, 2, 3)
        display.rectangle(x + 9, y + 11, 2, 3)
        display.set_pen(BLACK)
        eye_x = head_x + 4 if direction > 0 else head_x + 1
        display.pixel(eye_x, y + 2)


def jump_height(now, jump_started):
    if jump_started is None:
        return 0
    elapsed = time.ticks_diff(now, jump_started)
    if elapsed < 0 or elapsed >= JUMP_DURATION_MS:
        return 0
    return int(math.sin((elapsed / JUMP_DURATION_MS) * math.pi) * 40)


def draw_ogre(lane, height, powered, visible=True):
    if not visible:
        return

    size = 32 if powered else 24
    x = lane_x(lane, size)
    y = PLAYER_Y - height

    display.set_pen(DARK_GREY)
    display.rectangle(x + 3, PLAYER_Y + size - 2, size - 6, 4)

    display.set_pen(OGRE_GLOW if powered else OGRE)
    display.rectangle(x + 5, y + 5, size - 10, size - 8)
    display.rectangle(x, y + 10, size, size - 17)
    display.rectangle(x + 2, y, size - 4, 10)

    display.set_pen(OGRE_DARK)
    display.rectangle(x + 6, y + 4, 4, 4)
    display.rectangle(x + size - 10, y + 4, 4, 4)
    display.rectangle(x + 8, y + size - 6, 5, 6)
    display.rectangle(x + size - 13, y + size - 6, 5, 6)

    display.set_pen(PURPLE)
    display.rectangle(x + 4, y + size - 12, size - 8, 7)


def draw_smash_arm(lane, height, powered):
    size = 32 if powered else 24
    centre_x = LANE_CENTRES[lane]
    ogre_y = PLAYER_Y - height
    arm_width = 9 if powered else 7
    arm_length = 30 if powered else 24

    display.set_pen(OGRE_GLOW if powered else OGRE)
    display.rectangle(centre_x - (arm_width // 2), ogre_y - arm_length + 7,
                      arm_width, arm_length)
    display.rectangle(centre_x - 8, ogre_y - arm_length, 16, 11)
    display.set_pen(OGRE_DARK)
    display.rectangle(centre_x - 6, ogre_y - arm_length + 2, 3, 5)
    display.rectangle(centre_x - 1, ogre_y - arm_length, 3, 6)
    display.rectangle(centre_x + 4, ogre_y - arm_length + 2, 3, 5)


def draw_lightning_flash(target, elapsed_ms):
    if target is None:
        return
    x = LANE_CENTRES[target["lane"]]
    y = int(target["y"] + target["height"])
    display.set_pen(YELLOW if (elapsed_ms // 60) % 2 else WHITE)
    points = [(x, PLAYER_Y), (x - 9, PLAYER_Y - 28), (x + 5, PLAYER_Y - 55),
              (x - 6, y + 28), (x, y)]
    for index in range(len(points) - 1):
        display.line(points[index][0], points[index][1],
                     points[index + 1][0], points[index + 1][1], 4)


def draw_hud(score, lives, powered):
    display.set_pen(BLACK)
    display.rectangle(0, 0, WIDTH, HUD_HEIGHT)
    display.set_pen(YELLOW)
    display.text("SCORE " + str(score), 3, 2, 126, 2)
    display.set_pen(WHITE)
    display.text("LIVES " + str(lives), 133, 5, WIDTH, 1)
    display.set_pen(YELLOW if powered else GREY)
    display.text("BOLT" if powered else "----", 188, 5, WIDTH, 1)


def draw_title():
    draw_road(0)
    draw_ogre(1, 0, True)
    display.set_pen(BLACK)
    display.rectangle(12, 35, WIDTH - 24, 126)
    centre_text("OGRE SMASH!", 48, 3, OGRE_GLOW)
    centre_text("L/R MOVE   U JUMP", 92, 1)
    centre_text("A SMASH   B LIGHTNING", 111, 1)
    centre_text("10 LIVES - SCORE BIG!", 131, 1, OGRE_GLOW)
    centre_text("+ START     - MENU", 147, 1, YELLOW)


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
    rank = 1
    for previous_score in scores:
        if previous_score > score:
            rank += 1

    scores.append(score)
    for left in range(len(scores)):
        for right in range(left + 1, len(scores)):
            if scores[right] > scores[left]:
                scores[left], scores[right] = scores[right], scores[left]

    scores = scores[:5]
    try:
        with open(SCORE_FILE, "w") as score_file:
            for saved_score in scores:
                score_file.write(str(saved_score) + "\n")
    except OSError:
        pass
    return scores, rank


def draw_leaderboard(game):
    display.set_pen(BLACK)
    display.rectangle(8, 24, WIDTH - 16, 214)
    centre_text("LEADERBOARD", 32, 2, OGRE_GLOW)
    centre_text("FINAL " + str(game["score"]), 59, 2, YELLOW)

    scores = game["leaderboard"] or []
    for index in range(5):
        y = 88 + (index * 24)
        if index < len(scores):
            highlight = index + 1 == game["leaderboard_rank"] and scores[index] == game["score"]
            display.set_pen(OGRE_GLOW if highlight else WHITE)
            display.text(str(index + 1) + ".", 42, y, WIDTH, 2)
            display.text(str(scores[index]), 88, y, WIDTH, 2)
        else:
            display.set_pen(GREY)
            display.text(str(index + 1) + ".  ---", 42, y, WIDTH, 2)

    centre_text("+ RETRY     - MENU", 220, 1, YELLOW)


def reset_game(controller):
    controller.show_lives(10)
    now = time.ticks_ms()
    return {
        "lane": 1,
        "lives": 10,
        "score": 0,
        "obstacles": [],
        "powerups": [],
        "ducks": [],
        "started": now,
        "last_spawn": now,
        "next_duck": time.ticks_add(now, random.randint(10000, 17000)),
        "jump_started": None,
        "powered_until": None,
        "invulnerable_until": None,
        "lightning_target": None,
        "lightning_until": None,
        "smash_until": None,
        "notice": None,
        "notice_until": None,
        "truck_spawned": False,
        "leaderboard": None,
        "leaderboard_rank": None,
    }


def spawn_kind(elapsed_ms):
    if elapsed_ms < 9000:
        return "car"
    roll = random.random()
    if elapsed_ms < 20000:
        if roll < 0.18:
            return "lake"
        if roll < 0.34:
            return "hole"
        return "car"
    if roll < 0.15:
        return "truck"
    if roll < 0.35:
        return "lake"
    if roll < 0.53:
        return "hole"
    return "car"


def smash_car(game, now, audio):
    game["smash_until"] = time.ticks_add(now, 300)
    audio.play(SOUND_SMASH)
    target = None
    target_distance = HEIGHT
    for obstacle in game["obstacles"]:
        if obstacle["kind"] not in ("car", "truck") or obstacle["lane"] != game["lane"]:
            continue
        distance = abs((obstacle["y"] + obstacle["height"]) - PLAYER_Y)
        if obstacle["y"] > PLAYER_Y - 72 and obstacle["y"] < PLAYER_Y + 22 and distance < target_distance:
            target = obstacle
            target_distance = distance

    if target is not None:
        game["obstacles"].remove(target)
        game["powerups"].append(new_powerup(target["lane"], target["y"]))
        if target["kind"] == "truck":
            game["score"] += 75
            game["notice"] = "LONG TRUCK +75!"
        else:
            game["score"] += 25
            game["notice"] = "CAR SMASHED +25!"
        game["notice_until"] = time.ticks_add(now, 700)


def fire_lightning(game, now, controller, audio):
    if game["powered_until"] is None or time.ticks_diff(game["powered_until"], now) <= 0:
        game["notice"] = "GET A BOLT FIRST!"
        game["notice_until"] = time.ticks_add(now, 900)
        audio.play(SOUND_ERROR)
        return

    targets = [
        obstacle for obstacle in game["obstacles"]
        if obstacle["kind"] in ("car", "truck")
        and obstacle["lane"] == game["lane"]
        and obstacle["y"] < PLAYER_Y
    ]
    if not targets:
        game["lightning_target"] = {
            "lane": game["lane"], "y": HUD_HEIGHT, "height": 1,
        }
        game["lightning_until"] = time.ticks_add(now, 550)
        game["notice"] = "NO TARGET - BOLT SAVED"
        game["notice_until"] = time.ticks_add(now, 900)
        audio.play(SOUND_LIGHTNING)
        return

    target = targets[0]
    for obstacle in targets[1:]:
        if obstacle["y"] < target["y"]:
            target = obstacle

    points = 0
    trucks = 0
    for obstacle in targets:
        game["obstacles"].remove(obstacle)
        if obstacle["kind"] == "truck":
            points += 100
            trucks += 1
        else:
            points += 50

    game["lightning_target"] = target
    game["lightning_until"] = time.ticks_add(now, 550)
    game["powered_until"] = None
    game["score"] += points
    if len(targets) > 1:
        game["notice"] = str(len(targets)) + " VEHICLES ZAPPED!"
    elif trucks:
        game["notice"] = "TRUCK ZAPPED!"
    else:
        game["notice"] = "CAR ZAPPED!"
    game["notice_until"] = time.ticks_add(now, 900)
    audio.play(SOUND_LIGHTNING)
    controller.show_lives(game["lives"])


def update_game(game, controller, audio, now, dt):
    elapsed_ms = time.ticks_diff(now, game["started"])
    powered = game["powered_until"] is not None and time.ticks_diff(game["powered_until"], now) > 0

    if game["powered_until"] is not None and not powered:
        game["powered_until"] = None
        controller.show_lives(game["lives"])

    if controller.pressed("L"):
        game["lane"] = max(0, game["lane"] - 1)
    elif controller.pressed("R"):
        game["lane"] = min(len(LANE_CENTRES) - 1, game["lane"] + 1)

    if controller.pressed("U") and jump_height(now, game["jump_started"]) == 0:
        game["jump_started"] = now
        audio.play(SOUND_JUMP)
    if controller.pressed("A"):
        smash_car(game, now, audio)
    if controller.pressed("B"):
        fire_lightning(game, now, controller, audio)

    if game["jump_started"] is not None and time.ticks_diff(now, game["jump_started"]) >= JUMP_DURATION_MS:
        game["jump_started"] = None

    spawn_interval = max(350, 1200 - (elapsed_ms // 50))
    if time.ticks_diff(now, game["last_spawn"]) >= spawn_interval:
        if elapsed_ms >= 16000 and not game["truck_spawned"]:
            kind = "truck"
        else:
            kind = spawn_kind(elapsed_ms)

        available_lanes = []
        for lane in range(len(LANE_CENTRES)):
            blocked = False
            for obstacle in game["obstacles"]:
                if obstacle["lane"] == lane and obstacle["y"] < 70:
                    blocked = True
                    break
            if not blocked:
                available_lanes.append(lane)

        if available_lanes:
            lane = random.choice(available_lanes)
            game["obstacles"].append(new_obstacle(kind, lane))
            if kind == "truck":
                game["truck_spawned"] = True
        game["last_spawn"] = now

    speed = 44 + min(100, elapsed_ms / 650)
    for obstacle in game["obstacles"][:]:
        obstacle_speed = speed * obstacle["speed_factor"]
        obstacle["y"] += obstacle_speed * dt
        if obstacle["y"] > HEIGHT + 8:
            game["obstacles"].remove(obstacle)
            game["score"] += 10 if obstacle["kind"] == "truck" else 5

    # Faster cars may catch slower traffic, but vehicles should queue rather
    # than drawing on top of one another in the same lane.
    for lane in range(len(LANE_CENTRES)):
        vehicles = [
            obstacle for obstacle in game["obstacles"]
            if obstacle["lane"] == lane and obstacle["kind"] in ("car", "truck")
        ]
        for left in range(len(vehicles)):
            for right in range(left + 1, len(vehicles)):
                if vehicles[right]["y"] > vehicles[left]["y"]:
                    vehicles[left], vehicles[right] = vehicles[right], vehicles[left]

        for index in range(1, len(vehicles)):
            ahead = vehicles[index - 1]
            following = vehicles[index]
            maximum_y = ahead["y"] - following["height"] - 8
            if following["y"] > maximum_y:
                following["y"] = maximum_y

    if time.ticks_diff(now, game["next_duck"]) >= 0:
        game["ducks"].append(new_duck_crossing())
        game["next_duck"] = time.ticks_add(now, random.randint(12000, 22000))
        game["notice"] = "DUCK CROSSING!"
        game["notice_until"] = time.ticks_add(now, 1100)
        audio.play(SOUND_DUCK)

    for crossing in game["ducks"][:]:
        crossing["x"] += crossing["direction"] * crossing["speed"] * dt
        if ((crossing["direction"] > 0 and crossing["x"] > WIDTH + 60) or
                (crossing["direction"] < 0 and crossing["x"] < -60)):
            game["ducks"].remove(crossing)

    for powerup in game["powerups"][:]:
        powerup["y"] += speed * 0.65 * dt
        if powerup["y"] > HEIGHT:
            game["powerups"].remove(powerup)

    height = jump_height(now, game["jump_started"])
    player_size = 32 if powered else 24
    player_x = lane_x(game["lane"], player_size)
    player_y = PLAYER_Y - height

    if height <= 6:
        for crossing in game["ducks"]:
            if crossing["hit"]:
                continue
            for index in range(3):
                x = duck_x(crossing, index)
                if overlaps(player_x, player_y, player_size, player_size,
                            x - 3, crossing["y"], 20, 14):
                    crossing["hit"] = True
                    game["score"] = max(0, game["score"] - 50)
                    game["notice"] = "DUCK HIT -50!"
                    game["notice_until"] = time.ticks_add(now, 900)
                    audio.play(SOUND_ERROR)
                    break

    for powerup in game["powerups"][:]:
        power_x = lane_x(powerup["lane"], powerup["width"])
        if overlaps(player_x, player_y, player_size, player_size,
                    power_x, powerup["y"], powerup["width"], powerup["height"]):
            game["powerups"].remove(powerup)
            game["powered_until"] = time.ticks_add(now, POWER_DURATION_MS)
            game["score"] += 50
            game["notice"] = "LIGHTNING READY!"
            game["notice_until"] = time.ticks_add(now, 900)
            audio.play(SOUND_PICKUP)
            controller.pad.set_leds(0b1111)
            powered = True

    invulnerable = (game["invulnerable_until"] is not None and
                    time.ticks_diff(game["invulnerable_until"], now) > 0)

    if not invulnerable:
        for obstacle in game["obstacles"][:]:
            obstacle_x = lane_x(obstacle["lane"], obstacle["width"])
            airborne = height > 6
            if not airborne and overlaps(
                    player_x, player_y, player_size, player_size,
                    obstacle_x, obstacle["y"], obstacle["width"], obstacle["height"]):
                game["obstacles"].remove(obstacle)
                game["lives"] -= 1
                game["lane"] = 1
                game["jump_started"] = None
                game["powered_until"] = None
                game["invulnerable_until"] = time.ticks_add(now, 1200)
                controller.show_lives(game["lives"])
                audio.play(SOUND_DAMAGE)
                break

    return elapsed_ms


def draw_game(game, now, elapsed_ms):
    powered = game["powered_until"] is not None and time.ticks_diff(game["powered_until"], now) > 0
    draw_road(elapsed_ms)

    for obstacle in game["obstacles"]:
        if obstacle["kind"] == "car":
            draw_car(obstacle)
        elif obstacle["kind"] == "truck":
            draw_truck(obstacle)
        elif obstacle["kind"] == "lake":
            draw_lake(obstacle, elapsed_ms)
        else:
            draw_hole(obstacle)

    for powerup in game["powerups"]:
        draw_powerup(powerup, elapsed_ms)

    for crossing in game["ducks"]:
        draw_ducks(crossing)

    visible = (game["invulnerable_until"] is None or
               time.ticks_diff(game["invulnerable_until"], now) <= 0 or
               (elapsed_ms // 90) % 2 == 0)
    draw_ogre(game["lane"], jump_height(now, game["jump_started"]), powered, visible)

    if game["smash_until"] is not None and time.ticks_diff(game["smash_until"], now) > 0:
        draw_smash_arm(game["lane"], jump_height(now, game["jump_started"]), powered)

    if game["lightning_until"] is not None and time.ticks_diff(game["lightning_until"], now) > 0:
        draw_lightning_flash(game["lightning_target"], elapsed_ms)

    draw_hud(game["score"], game["lives"], powered)

    if game["notice_until"] is not None and time.ticks_diff(game["notice_until"], now) > 0:
        display.set_pen(BLACK)
        display.rectangle(18, HUD_HEIGHT + 3, WIDTH - 36, 18)
        centre_text(game["notice"], HUD_HEIGHT + 7, 1, YELLOW)


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
            elapsed_ms = update_game(game, controller, audio, now, dt)
            draw_game(game, now, elapsed_ms)
            if game["lives"] <= 0:
                game["leaderboard"], game["leaderboard_rank"] = record_score(game["score"])
                state = "game_over"
                audio.play(SOUND_GAME_OVER)

        elif state == "game_over":
            draw_game(game, now, time.ticks_diff(now, game["started"]))
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

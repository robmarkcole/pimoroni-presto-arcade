# ICON joystick
# NAME Fly Smash
# DESC Bounce through opening clouds and smash flying cars!

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
GROUND_SCREEN_Y = 218
PLAYER_W = 14
PLAYER_H = 18
GRAVITY = 430.0
JUMP_SPEEDS = (228.0, 234.0, 240.0)
MOVE_SPEED = 118.0
LASER_SPEED = 230.0
SHIELD_DURATION = 60000
FINAL_LEVEL = 3
HIGH_SCORE_FILE = "fly_smash_high.txt"

BLACK = display.create_pen(0, 0, 0)
WHITE = display.create_pen(255, 255, 255)
SKY = display.create_pen(65, 174, 235)
SKY_LIGHT = display.create_pen(120, 210, 250)
BLUE = display.create_pen(35, 110, 245)
CYAN = display.create_pen(45, 225, 245)
GREEN = display.create_pen(65, 220, 95)
DARK_GREEN = display.create_pen(25, 125, 65)
YELLOW = display.create_pen(255, 225, 35)
ORANGE = display.create_pen(255, 130, 35)
RED = display.create_pen(240, 55, 60)
PINK = display.create_pen(245, 80, 175)
PURPLE = display.create_pen(155, 70, 220)
GREY = display.create_pen(85, 100, 120)
DARK_GREY = display.create_pen(40, 48, 65)
SKIN = display.create_pen(255, 190, 120)
BROWN = display.create_pen(125, 70, 35)

RAINBOW = (RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, PURPLE)

SOUND_START = ((392, 45), (523, 55), (659, 90))
SOUND_BOUNCE = ((420, 25), (570, 35))
SOUND_LASER = ((780, 28), (1120, 38))
SOUND_SMASH = ((180, 40), (105, 75))
SOUND_WEAPON = ((523, 40), (659, 45), (880, 80))
SOUND_SHIELD = ((440, 45), (660, 45), (990, 100))
SOUND_HIT = ((210, 75), (125, 110), (70, 170))
SOUND_LEVEL = ((523, 55), (659, 55), (784, 65), (1047, 130))
SOUND_WIN = ((523, 70), (659, 70), (784, 70), (1047, 180))
SOUND_ERROR = ((120, 80),)


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

    def show_shield(self, active):
        self.pad.set_leds(15 if active else 0)


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
    previous = load_high_score()
    if score <= previous:
        return previous
    try:
        with open(HIGH_SCORE_FILE, "w") as score_file:
            score_file.write(str(score))
    except OSError:
        pass
    return score


def overlaps(ax, ay, aw, ah, bx, by, bw, bh):
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def make_platforms(level):
    platforms = []
    x = 82
    y = 0
    count = 15 + level
    opening_chance = (0.18, 0.34, 0.48)[level - 1]
    for index in range(count):
        if index:
            y += random.randint(38, 50)
            x += random.randint(-58, 58)
            x = max(4, min(WIDTH - 62, x))
        platform = {
            "x": float(x),
            "y": float(y),
            "width": 60 if index < 3 else random.randint(48, 60),
            "opening": index > 1 and index < count - 1 and random.random() < opening_chance,
            "phase": random.randint(0, 4800),
            "scored": index == 0,
            "finish": index == count - 1,
        }
        platforms.append(platform)
    return platforms


def make_hazards(platforms, level):
    hazards = []
    if level == 1:
        return hazards
    step = 5 if level == 2 else 4
    for index in range(5, len(platforms) - 1, step):
        platform = platforms[index]
        left_side = (index // step) % 2 == 0
        hazards.append({
            "y": platform["y"] + 24,
            "x": 0 if left_side else 90,
            "width": 150,
            "phase": random.randint(0, 2400),
        })
    return hazards


def make_pickups(platforms, level):
    pickups = [{
        "kind": "weapon",
        "x": platforms[2]["x"] + platforms[2]["width"] // 2 - 7,
        "y": platforms[2]["y"] + 12,
        "taken": False,
    }]
    shield_index = 7 if level == 1 else 6
    platform = platforms[shield_index]
    pickups.append({
        "kind": "shield",
        "x": platform["x"] + platform["width"] // 2 - 7,
        "y": platform["y"] + 13,
        "taken": False,
    })
    if level == 3:
        platform = platforms[12]
        pickups.append({
            "kind": "shield",
            "x": platform["x"] + platform["width"] // 2 - 7,
            "y": platform["y"] + 13,
            "taken": False,
        })
    return pickups


def new_level(controller, level, score=0, high_score=0):
    now = time.ticks_ms()
    platforms = make_platforms(level)
    player = {
        "x": platforms[0]["x"] + platforms[0]["width"] // 2 - PLAYER_W // 2,
        "y": platforms[0]["y"],
        "previous_y": platforms[0]["y"],
        "vy": JUMP_SPEEDS[level - 1],
        "facing": 1,
        "weapon": False,
        "shield_until": None,
    }
    game = {
        "level": level,
        "score": score,
        "high_score": high_score,
        "player": player,
        "platforms": platforms,
        "hazards": make_hazards(platforms, level),
        "pickups": make_pickups(platforms, level),
        "cars": [],
        "lasers": [],
        "explosions": [],
        "camera_y": 0.0,
        "next_car": time.ticks_add(now, 2800),
        "last_shot": time.ticks_add(now, -1000),
        "started_at": now,
        "notice": "LEVEL " + str(level),
        "notice_until": time.ticks_add(now, 1000),
        "state_until": None,
        "pieces": [],
    }
    controller.show_shield(False)
    return game


def cloud_gap(platform, game, now):
    if not platform["opening"]:
        return 0, "closed"
    elapsed = time.ticks_diff(now, game["started_at"])
    phase = (elapsed + platform["phase"]) % 5000
    maximum = int(platform["width"] * 0.58)
    if phase < 2000:
        return 0, "closed"
    if phase < 2500:
        return 0, "warning"
    if phase < 3000:
        return int(maximum * (phase - 2500) / 500), "opening"
    if phase < 4500:
        return maximum, "open"
    return int(maximum * (5000 - phase) / 500), "closing"


def world_to_screen(game, world_y):
    return int(GROUND_SCREEN_Y - (world_y - game["camera_y"]))


def shield_active(game, now):
    shield_until = game["player"]["shield_until"]
    return shield_until is not None and time.ticks_diff(shield_until, now) > 0


def start_defeat(game, now, audio, controller, reason):
    if game["state_until"] is not None:
        return
    player = game["player"]
    colours = (RED, YELLOW, GREEN, CYAN, PURPLE, PINK)
    game["pieces"] = []
    for index in range(6):
        game["pieces"].append({
            "x": player["x"] + PLAYER_W // 2,
            "y": player["y"] + PLAYER_H // 2,
            "vx": -80 + index * 32,
            "vy": 90 + (index % 3) * 35,
            "colour": colours[index],
        })
    game["state_until"] = time.ticks_add(now, 1500)
    game["notice"] = reason
    game["notice_until"] = game["state_until"]
    game["high_score"] = save_high_score(game["score"])
    controller.show_shield(False)
    audio.play(SOUND_HIT)


def spawn_car(game, now):
    direction = random.choice((-1, 1))
    car_y = game["camera_y"] + random.randint(65, 165)
    game["cars"].append({
        "x": -30.0 if direction > 0 else WIDTH + 4.0,
        "y": car_y,
        "direction": direction,
        "speed": random.randint(42, 56) + game["level"] * 10,
        "bomb": random.random() < 0.55,
    })
    delay = random.randint(2300, 3600) - game["level"] * 300
    game["next_car"] = time.ticks_add(now, max(1300, delay))


def fire_laser(game, now, audio):
    player = game["player"]
    if not player["weapon"]:
        game["notice"] = "FIND THE LASER BOX"
        game["notice_until"] = time.ticks_add(now, 700)
        audio.play(SOUND_ERROR)
        return
    if time.ticks_diff(now, game["last_shot"]) < 280:
        return
    direction = player["facing"]
    game["lasers"].append({
        "x": player["x"] + (PLAYER_W if direction > 0 else -8),
        "y": player["y"] + 9,
        "direction": direction,
    })
    game["last_shot"] = now
    audio.play(SOUND_LASER)


def update_player(game, controller, now, dt, audio):
    player = game["player"]
    movement = 0
    if controller.held("L"):
        movement -= MOVE_SPEED * dt
        player["facing"] = -1
    if controller.held("R"):
        movement += MOVE_SPEED * dt
        player["facing"] = 1
    player["x"] += movement
    if player["x"] < -PLAYER_W:
        player["x"] = WIDTH
    elif player["x"] > WIDTH:
        player["x"] = -PLAYER_W

    player["previous_y"] = player["y"]
    player["vy"] -= GRAVITY * dt
    next_y = player["y"] + player["vy"] * dt

    if player["vy"] <= 0:
        player_centre = player["x"] + PLAYER_W / 2
        for platform in game["platforms"]:
            if player["previous_y"] >= platform["y"] and next_y <= platform["y"]:
                if player_centre < platform["x"] or player_centre > platform["x"] + platform["width"]:
                    continue
                gap, phase = cloud_gap(platform, game, now)
                gap_left = platform["x"] + (platform["width"] - gap) / 2
                gap_right = gap_left + gap
                if gap and gap_left < player_centre < gap_right:
                    continue
                player["y"] = platform["y"]
                player["vy"] = JUMP_SPEEDS[game["level"] - 1]
                if not platform["scored"]:
                    platform["scored"] = True
                    game["score"] += 10
                if platform["finish"]:
                    game["state_until"] = time.ticks_add(now, 1400)
                    game["score"] += 200
                    game["notice"] = "LEVEL CLEAR +200"
                    game["notice_until"] = game["state_until"]
                    audio.play(SOUND_LEVEL)
                elif phase == "warning":
                    game["notice"] = "CLOUD CRACKING!"
                    game["notice_until"] = time.ticks_add(now, 500)
                else:
                    audio.play(SOUND_BOUNCE)
                break
        else:
            player["y"] = next_y
    else:
        player["y"] = next_y

    if player["y"] > game["camera_y"] + 95:
        game["camera_y"] = player["y"] - 95

    if player["y"] < game["camera_y"] - 45:
        start_defeat(game, now, audio, controller, "YOU FELL! RESTARTING")


def update_pickups(game, now, audio, controller):
    player = game["player"]
    for pickup in game["pickups"]:
        if pickup["taken"]:
            continue
        if overlaps(player["x"], player["y"], PLAYER_W, PLAYER_H,
                    pickup["x"], pickup["y"], 14, 14):
            pickup["taken"] = True
            game["score"] += 50
            if pickup["kind"] == "weapon":
                player["weapon"] = True
                game["notice"] = "LASER READY! A TO FIRE"
                audio.play(SOUND_WEAPON)
            else:
                player["shield_until"] = time.ticks_add(now, SHIELD_DURATION)
                controller.show_shield(True)
                game["notice"] = "BLUE SHIELD 60s"
                audio.play(SOUND_SHIELD)
            game["notice_until"] = time.ticks_add(now, 1000)


def update_cars_and_lasers(game, now, dt, audio, controller):
    if time.ticks_diff(now, game["next_car"]) >= 0 and len(game["cars"]) < 4:
        spawn_car(game, now)

    for laser in game["lasers"][:]:
        laser["x"] += laser["direction"] * LASER_SPEED * dt
        if laser["x"] < -15 or laser["x"] > WIDTH + 15:
            game["lasers"].remove(laser)

    for car in game["cars"][:]:
        car["x"] += car["direction"] * car["speed"] * dt
        if car["x"] < -38 or car["x"] > WIDTH + 38:
            game["cars"].remove(car)
            continue
        hit_laser = None
        for laser in game["lasers"]:
            if overlaps(laser["x"], laser["y"], 9, 3,
                        car["x"], car["y"], 27, 13):
                hit_laser = laser
                break
        if hit_laser is not None:
            game["lasers"].remove(hit_laser)
            game["cars"].remove(car)
            game["explosions"].append({
                "x": car["x"] + 13, "y": car["y"] + 6,
                "until": time.ticks_add(now, 450),
            })
            game["score"] += 25
            audio.play(SOUND_SMASH)
            continue
        player = game["player"]
        if overlaps(player["x"], player["y"], PLAYER_W, PLAYER_H,
                    car["x"], car["y"], 27, 13):
            if shield_active(game, now):
                game["cars"].remove(car)
                game["score"] += 10
                game["notice"] = "SHIELD SMASH +10"
                game["notice_until"] = time.ticks_add(now, 550)
                audio.play(SOUND_SMASH)
            else:
                start_defeat(game, now, audio, controller, "CAR CRASH! RESTARTING")

    for explosion in game["explosions"][:]:
        if time.ticks_diff(now, explosion["until"]) >= 0:
            game["explosions"].remove(explosion)


def hazard_active(hazard, game, now):
    elapsed = time.ticks_diff(now, game["started_at"])
    return (elapsed + hazard["phase"]) % 2700 < 1250


def update_hazards(game, now, audio, controller):
    player = game["player"]
    for hazard in game["hazards"]:
        if not hazard_active(hazard, game, now):
            continue
        if overlaps(player["x"], player["y"], PLAYER_W, PLAYER_H,
                    hazard["x"], hazard["y"] - 2, hazard["width"], 5):
            if not shield_active(game, now):
                start_defeat(game, now, audio, controller, "YELLOW LASER! RESTARTING")
                return


def update_playing(game, controller, audio, now, dt):
    if controller.pressed("A"):
        fire_laser(game, now, audio)
    update_player(game, controller, now, dt, audio)
    if game["state_until"] is not None:
        return
    update_pickups(game, now, audio, controller)
    update_cars_and_lasers(game, now, dt, audio, controller)
    update_hazards(game, now, audio, controller)

    if game["player"]["shield_until"] is not None and not shield_active(game, now):
        game["player"]["shield_until"] = None
        controller.show_shield(False)
        game["notice"] = "SHIELD EXPIRED"
        game["notice_until"] = time.ticks_add(now, 700)


def update_pieces(game, dt):
    for piece in game["pieces"]:
        piece["x"] += piece["vx"] * dt
        piece["y"] += piece["vy"] * dt
        piece["vy"] -= GRAVITY * dt


def draw_background(game):
    display.set_pen(SKY)
    display.clear()
    display.set_pen(SKY_LIGHT)
    offset = int(game["camera_y"] * 0.15) % 50
    for index in range(6):
        x = (index * 57 + 20) % WIDTH
        y = 42 + ((index * 47 + offset) % 150)
        display.circle(x, y, 7)
        display.circle(x + 8, y + 2, 9)
        display.circle(x + 17, y, 6)


def draw_cloud(platform, game, now):
    y = world_to_screen(game, platform["y"])
    if y < HUD_HEIGHT - 16 or y > HEIGHT + 12:
        return
    x = int(platform["x"])
    width = platform["width"]
    gap, phase = cloud_gap(platform, game, now)
    colour = YELLOW if phase == "warning" and (now // 100) % 2 else WHITE
    display.set_pen(colour)
    if gap:
        side = (width - gap) // 2
        display.rectangle(x, y, side, 7)
        display.circle(x + 8, y, 8)
        display.rectangle(x + width - side, y, side, 7)
        display.circle(x + width - 8, y, 8)
    else:
        display.rectangle(x + 6, y - 3, width - 12, 10)
        display.circle(x + 8, y, 8)
        display.circle(x + width // 2, y - 4, 10)
        display.circle(x + width - 8, y, 8)
    if platform["finish"]:
        for index, colour in enumerate(RAINBOW):
            display.set_pen(colour)
            display.rectangle(x + 5 + index * 7, y - 18, 6, 3)


def draw_pickup(pickup, game, now):
    if pickup["taken"]:
        return
    x = int(pickup["x"])
    y = world_to_screen(game, pickup["y"] + 14)
    if y < HUD_HEIGHT or y > HEIGHT:
        return
    if pickup["kind"] == "weapon":
        display.set_pen(GREEN)
        display.rectangle(x, y, 14, 14)
        display.set_pen(DARK_GREEN)
        display.rectangle(x + 2, y + 2, 10, 10)
        display.set_pen(CYAN)
        display.rectangle(x + 3, y + 6, 8, 3)
    else:
        pulse = 6 + (now // 120) % 3
        display.set_pen(CYAN)
        display.circle(x + 7, y + 7, pulse)
        display.set_pen(BLUE)
        display.circle(x + 7, y + 7, 3)


def draw_car(car, game):
    x = int(car["x"])
    y = world_to_screen(game, car["y"] + 13)
    if y < HUD_HEIGHT - 15 or y > HEIGHT + 15:
        return
    colour = PINK if car["direction"] > 0 else ORANGE
    display.set_pen(DARK_GREY)
    display.rectangle(x + 3, y + 10, 21, 4)
    display.set_pen(colour)
    display.rectangle(x, y + 3, 27, 8)
    display.rectangle(x + 7, y, 12, 5)
    display.set_pen(CYAN)
    display.rectangle(x + 9, y + 1, 7, 3)
    display.set_pen(BLACK)
    display.circle(x + 6, y + 12, 3)
    display.circle(x + 21, y + 12, 3)
    if car["bomb"]:
        display.set_pen(RED)
        display.circle(x + 13, y + 18, 4)
        display.set_pen(YELLOW)
        display.pixel(x + 16, y + 14)


def draw_player(game, now):
    player = game["player"]
    x = int(player["x"])
    y = world_to_screen(game, player["y"] + PLAYER_H)
    if shield_active(game, now):
        display.set_pen(CYAN)
        display.circle(x + PLAYER_W // 2, y + PLAYER_H // 2, 13)
        display.set_pen(SKY)
        display.circle(x + PLAYER_W // 2, y + PLAYER_H // 2, 10)
    display.set_pen(PURPLE)
    display.rectangle(x + 2, y + 8, 10, 10)
    display.set_pen(SKIN)
    display.circle(x + 7, y + 6, 6)
    display.set_pen(BROWN)
    display.rectangle(x + 2, y + 1, 10, 3)
    display.set_pen(BLACK)
    eye_x = x + (10 if player["facing"] > 0 else 4)
    display.pixel(eye_x, y + 6)
    display.set_pen(YELLOW)
    foot = 2 if (now // 100) % 2 else 0
    display.rectangle(x, y + 16, 5, 2 + foot)
    display.rectangle(x + 9, y + 16, 5, 4 - foot)
    if player["weapon"]:
        display.set_pen(GREEN)
        gun_x = x + 11 if player["facing"] > 0 else x - 5
        display.rectangle(gun_x, y + 10, 7, 3)


def draw_hazards(game, now):
    for hazard in game["hazards"]:
        y = world_to_screen(game, hazard["y"])
        if y < HUD_HEIGHT or y > HEIGHT:
            continue
        if hazard_active(hazard, game, now):
            display.set_pen(ORANGE)
            display.rectangle(hazard["x"], y - 2, hazard["width"], 5)
            display.set_pen(YELLOW)
            display.rectangle(hazard["x"], y - 1, hazard["width"], 2)
        else:
            display.set_pen(GREY)
            display.rectangle(hazard["x"], y, hazard["width"], 1)
        display.set_pen(DARK_GREY)
        display.rectangle(hazard["x"], y - 5, 5, 10)
        display.rectangle(hazard["x"] + hazard["width"] - 5, y - 5, 5, 10)


def draw_effects(game, now):
    for laser in game["lasers"]:
        y = world_to_screen(game, laser["y"] + 2)
        display.set_pen(CYAN)
        display.rectangle(int(laser["x"]), y, 9, 3)
    for explosion in game["explosions"]:
        x = int(explosion["x"])
        y = world_to_screen(game, explosion["y"])
        radius = 3 + max(0, time.ticks_diff(explosion["until"], now)) // 75
        display.set_pen(RED)
        display.circle(x, y, radius)
        display.set_pen(YELLOW)
        display.circle(x, y, max(2, radius // 2))
    for piece in game["pieces"]:
        display.set_pen(piece["colour"])
        display.rectangle(int(piece["x"]), world_to_screen(game, piece["y"]), 4, 4)


def draw_hud(game, now):
    display.set_pen(BLACK)
    display.rectangle(0, 0, WIDTH, HUD_HEIGHT)
    display.set_pen(YELLOW)
    display.text("S " + str(game["score"]), 3, 4, 93, 2)
    display.set_pen(WHITE)
    display.text("L" + str(game["level"]), 101, 8, 28, 1)
    if game["player"]["weapon"]:
        display.set_pen(GREEN)
        display.text("A LASER", 130, 8, 50, 1)
    if shield_active(game, now):
        remaining = max(0, time.ticks_diff(game["player"]["shield_until"], now) // 1000)
        display.set_pen(CYAN)
        display.text("SH " + str(remaining), 184, 8, 53, 1)


def draw_game(game, now):
    draw_background(game)
    for platform in game["platforms"]:
        draw_cloud(platform, game, now)
    draw_hazards(game, now)
    for pickup in game["pickups"]:
        draw_pickup(pickup, game, now)
    for car in game["cars"]:
        draw_car(car, game)
    draw_effects(game, now)
    if not game["pieces"]:
        draw_player(game, now)
    draw_hud(game, now)
    if game["notice_until"] is not None and time.ticks_diff(game["notice_until"], now) > 0:
        display.set_pen(BLACK)
        display.rectangle(12, 34, WIDTH - 24, 21)
        centre_text(game["notice"], 40, 1, YELLOW)


def draw_title(high_score):
    display.set_pen(SKY)
    display.clear()
    for index, colour in enumerate(RAINBOW):
        display.set_pen(colour)
        display.rectangle(18 + index * 29, 44 + (index % 2) * 8, 24, 5)
    display.set_pen(WHITE)
    display.circle(45, 154, 14)
    display.circle(60, 150, 18)
    display.circle(78, 155, 13)
    display.set_pen(BLACK)
    display.rectangle(12, 58, WIDTH - 24, 120)
    centre_text("FLY", 67, 4, CYAN)
    centre_text("SMASH", 103, 4, YELLOW)
    centre_text("L/R MOVE   A LASER", 143, 1)
    centre_text("AUTO-BOUNCE ON CLOUDS", 158, 1, GREEN)
    centre_text("HIGH " + str(high_score), 190, 2, WHITE)
    centre_text("+ START       - MENU", 218, 1, YELLOW)


def draw_win(game, now):
    draw_game(game, now)
    display.set_pen(BLACK)
    display.rectangle(18, 60, WIDTH - 36, 122)
    centre_text("YOU WIN!", 71, 3, YELLOW)
    centre_text("FLY SMASH CHAMPION", 108, 1, CYAN)
    centre_text("FINAL " + str(game["score"]), 130, 2, WHITE)
    centre_text("+ PLAY AGAIN", 162, 1, GREEN)


def main():
    try:
        controller = Controller()
    except OSError:
        while True:
            display.set_pen(BLACK)
            display.clear()
            centre_text("QwSTPad not found", 96, 2)
            centre_text("Connect it and reset", 126, 1)
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
                game = new_level(controller, 1, 0, high_score)
                state = "playing"
                audio.play(SOUND_START)
        elif state == "playing":
            update_playing(game, controller, audio, now, dt)
            draw_game(game, now)
            if game["state_until"] is not None:
                if game["pieces"]:
                    state = "defeated"
                else:
                    state = "level_clear"
        elif state == "defeated":
            update_pieces(game, dt)
            draw_game(game, now)
            if time.ticks_diff(now, game["state_until"]) >= 0:
                high_score = max(high_score, game["high_score"])
                game = new_level(controller, 1, 0, high_score)
                state = "playing"
                audio.play(SOUND_START)
        elif state == "level_clear":
            draw_game(game, now)
            if time.ticks_diff(now, game["state_until"]) >= 0:
                if game["level"] >= FINAL_LEVEL:
                    game["high_score"] = save_high_score(game["score"])
                    high_score = max(high_score, game["high_score"])
                    state = "won"
                    audio.play(SOUND_WIN)
                else:
                    game = new_level(controller, game["level"] + 1,
                                     game["score"], high_score)
                    state = "playing"
        else:
            draw_win(game, now)
            if controller.pressed("+"):
                game = new_level(controller, 1, 0, high_score)
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

# ICON bomb
# NAME Ogre Smash!
# DESC Smash traffic, leap lakes and wield lightning!

import math
import random
import time

import machine
from machine import I2C
from presto import Presto
from qwstpad import ADDRESSES, QwSTPad


I2C_PINS = {"id": 0, "sda": 40, "scl": 41}
I2C_ADDRESS = ADDRESSES[0]

presto = Presto(ambient_light=True)
display = presto.display
WIDTH, HEIGHT = display.get_bounds()

HUD_HEIGHT = 24
PLAYER_Y = 184
LANE_CENTRES = (36, 92, 148, 204)
LEVEL_DURATION_MS = 45000
JUMP_DURATION_MS = 800
POWER_DURATION_MS = 8000

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
        }
    if kind == "truck":
        return {
            "kind": kind, "lane": lane, "y": -58.0,
            "width": 38, "height": 58, "colour": GREY,
        }
    return {
        "kind": "lake", "lane": lane, "y": -46.0,
        "width": 48, "height": 46, "colour": BLUE,
    }


def new_powerup(lane, y):
    return {"lane": lane, "y": float(y), "width": 18, "height": 22}


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
    display.rectangle(x + 4, y + 5, obstacle["width"] - 8, 18)
    display.set_pen(RED)
    display.rectangle(x + 4, y + obstacle["height"] - 6, 7, 4)
    display.rectangle(x + obstacle["width"] - 11, y + obstacle["height"] - 6, 7, 4)
    display.set_pen(BLACK)
    display.rectangle(x - 3, y + 10, 5, 13)
    display.rectangle(x + obstacle["width"] - 2, y + 10, 5, 13)
    display.rectangle(x - 3, y + obstacle["height"] - 22, 5, 13)
    display.rectangle(x + obstacle["width"] - 2, y + obstacle["height"] - 22, 5, 13)


def draw_lake(obstacle, elapsed_ms):
    x = lane_x(obstacle["lane"], obstacle["width"])
    y = int(obstacle["y"])
    display.set_pen(BLUE)
    display.rectangle(x, y, obstacle["width"], obstacle["height"])
    display.set_pen(BLUE_LIGHT)
    wave = (elapsed_ms // 120) % 12
    for row in (9, 24, 39):
        display.rectangle(x + ((row + wave) % 14), y + row, 18, 3)


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


def jump_height(now, jump_started):
    if jump_started is None:
        return 0
    elapsed = time.ticks_diff(now, jump_started)
    if elapsed < 0 or elapsed >= JUMP_DURATION_MS:
        return 0
    return int(math.sin((elapsed / JUMP_DURATION_MS) * math.pi) * 34)


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


def draw_hud(score, lives, powered, remaining_seconds):
    display.set_pen(BLACK)
    display.rectangle(0, 0, WIDTH, HUD_HEIGHT)
    display.set_pen(WHITE)
    display.text("S " + str(score), 3, 5, WIDTH, 1)
    display.text("L " + str(lives), 76, 5, WIDTH, 1)
    display.text("T " + str(remaining_seconds), 123, 5, WIDTH, 1)
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
    centre_text("+ START     - MENU", 137, 1, YELLOW)


def draw_message(title, subtitle, score):
    display.set_pen(BLACK)
    display.rectangle(12, 69, WIDTH - 24, 100)
    centre_text(title, 82, 2, OGRE_GLOW)
    centre_text("SCORE " + str(score), 116, 1)
    centre_text(subtitle, 142, 1, YELLOW)


def reset_game(controller):
    controller.show_lives(3)
    return {
        "lane": 1,
        "lives": 3,
        "score": 0,
        "obstacles": [],
        "powerups": [],
        "started": time.ticks_ms(),
        "last_spawn": time.ticks_ms(),
        "jump_started": None,
        "powered_until": None,
        "invulnerable_until": None,
        "lightning_target": None,
        "lightning_until": None,
    }


def spawn_kind(elapsed_ms):
    if elapsed_ms < 9000:
        return "car"
    roll = random.random()
    if elapsed_ms < 20000:
        return "lake" if roll < 0.28 else "car"
    if roll < 0.2:
        return "truck"
    if roll < 0.48:
        return "lake"
    return "car"


def smash_car(game):
    target = None
    target_distance = HEIGHT
    for obstacle in game["obstacles"]:
        if obstacle["kind"] != "car" or obstacle["lane"] != game["lane"]:
            continue
        distance = abs((obstacle["y"] + obstacle["height"]) - PLAYER_Y)
        if obstacle["y"] > PLAYER_Y - 72 and obstacle["y"] < PLAYER_Y + 22 and distance < target_distance:
            target = obstacle
            target_distance = distance

    if target is not None:
        game["obstacles"].remove(target)
        game["powerups"].append(new_powerup(target["lane"], target["y"]))
        game["score"] += 25


def fire_lightning(game, now, controller):
    if game["powered_until"] is None or time.ticks_diff(game["powered_until"], now) <= 0:
        return

    trucks = [obstacle for obstacle in game["obstacles"] if obstacle["kind"] == "truck"]
    if not trucks:
        return

    target = trucks[0]
    for truck in trucks[1:]:
        if truck["y"] > target["y"]:
            target = truck
    game["obstacles"].remove(target)
    game["lightning_target"] = target
    game["lightning_until"] = time.ticks_add(now, 350)
    game["powered_until"] = None
    game["score"] += 100
    controller.show_lives(game["lives"])


def update_game(game, controller, now, dt):
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
    if controller.pressed("A"):
        smash_car(game)
    if controller.pressed("B"):
        fire_lightning(game, now, controller)

    if game["jump_started"] is not None and time.ticks_diff(now, game["jump_started"]) >= JUMP_DURATION_MS:
        game["jump_started"] = None

    spawn_interval = max(680, 1250 - (elapsed_ms // 70))
    if time.ticks_diff(now, game["last_spawn"]) >= spawn_interval:
        kind = spawn_kind(elapsed_ms)
        lane = random.randrange(len(LANE_CENTRES))
        game["obstacles"].append(new_obstacle(kind, lane))
        game["last_spawn"] = now

    speed = 48 + min(34, elapsed_ms / 1100)
    for obstacle in game["obstacles"][:]:
        obstacle_speed = speed * (1.15 if obstacle["kind"] == "car" else 1.0)
        obstacle["y"] += obstacle_speed * dt
        if obstacle["y"] > HEIGHT + 8:
            game["obstacles"].remove(obstacle)
            game["score"] += 5

    for powerup in game["powerups"][:]:
        powerup["y"] += speed * 0.65 * dt
        if powerup["y"] > HEIGHT:
            game["powerups"].remove(powerup)

    height = jump_height(now, game["jump_started"])
    player_size = 32 if powered else 24
    player_x = lane_x(game["lane"], player_size)
    player_y = PLAYER_Y - height

    for powerup in game["powerups"][:]:
        power_x = lane_x(powerup["lane"], powerup["width"])
        if overlaps(player_x, player_y, player_size, player_size,
                    power_x, powerup["y"], powerup["width"], powerup["height"]):
            game["powerups"].remove(powerup)
            game["powered_until"] = time.ticks_add(now, POWER_DURATION_MS)
            game["score"] += 50
            controller.pad.set_leds(0b1111)
            powered = True

    invulnerable = (game["invulnerable_until"] is not None and
                    time.ticks_diff(game["invulnerable_until"], now) > 0)

    if not invulnerable:
        for obstacle in game["obstacles"][:]:
            obstacle_x = lane_x(obstacle["lane"], obstacle["width"])
            airborne = height > 12 and obstacle["kind"] != "truck"
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
        else:
            draw_lake(obstacle, elapsed_ms)

    for powerup in game["powerups"]:
        draw_powerup(powerup, elapsed_ms)

    visible = (game["invulnerable_until"] is None or
               time.ticks_diff(game["invulnerable_until"], now) <= 0 or
               (elapsed_ms // 90) % 2 == 0)
    draw_ogre(game["lane"], jump_height(now, game["jump_started"]), powered, visible)

    if game["lightning_until"] is not None and time.ticks_diff(game["lightning_until"], now) > 0:
        draw_lightning_flash(game["lightning_target"], elapsed_ms)

    remaining = max(0, (LEVEL_DURATION_MS - elapsed_ms + 999) // 1000)
    draw_hud(game["score"], game["lives"], powered, remaining)


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

    state = "title"
    game = None
    last_tick = time.ticks_ms()

    while True:
        now = time.ticks_ms()
        dt = min(50, time.ticks_diff(now, last_tick)) / 1000.0
        last_tick = now

        controller.poll()
        if controller.pressed("-"):
            controller.pad.clear_leds()
            machine.reset()

        if state == "title":
            draw_title()
            if controller.pressed("+"):
                game = reset_game(controller)
                state = "playing"

        elif state == "playing":
            elapsed_ms = update_game(game, controller, now, dt)
            draw_game(game, now, elapsed_ms)
            if game["lives"] <= 0:
                state = "game_over"
            elif elapsed_ms >= LEVEL_DURATION_MS:
                controller.pad.set_leds(0b1111)
                state = "complete"

        elif state == "game_over":
            draw_game(game, now, time.ticks_diff(now, game["started"]))
            draw_message("GAME OVER", "+ RETRY   - MENU", game["score"])
            if controller.pressed("+"):
                game = reset_game(controller)
                state = "playing"

        elif state == "complete":
            draw_game(game, now, LEVEL_DURATION_MS)
            draw_message("EASY STREET CLEAR", "+ PLAY AGAIN   - MENU", game["score"])
            if controller.pressed("+"):
                game = reset_game(controller)
                state = "playing"

        presto.update()
        time.sleep(0.02)


try:
    main()
finally:
    try:
        controller.pad.clear_leds()
    except (NameError, OSError):
        pass

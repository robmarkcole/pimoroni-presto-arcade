# ICON joystick
# NAME Road Riot
# DESC Race hard, dodge traffic, outsmart rival riders!

"""An original motorcycle racer for Presto and the Qw/ST Pad.

No external sprites or ROMs required. Distances, rival positions and collisions
live in road coordinates; perspective is only applied when drawing.
"""

import math
import random
import time

import machine
from machine import I2C
from presto import Buzzer, Presto
from qwstpad import QwSTPad


presto = Presto(ambient_light=True, layers=1)
display = presto.display
WIDTH, HEIGHT = display.get_bounds()
HORIZON = 62
ROAD_HEIGHT = 152
VIEW_DISTANCE = 360
SAVE_FILE = "road_riot_high.txt"
COURSES = ("SUNSET STRIP", "CANYON RUN", "MIDNIGHT COAST")
LENGTHS = (2200, 2600, 3000)

# Cache perspective geometry once. The inner road loop only moves strips and
# changes their colours, avoiding hundreds of float conversions per frame.
ROAD_STRIPS = []
for _y in range(HORIZON, HEIGHT, 6):
    _depth = max(0.015, (_y - HORIZON + 3) / ROAD_HEIGHT)
    ROAD_STRIPS.append((_y, int(93 * _depth), max(1, int(5 * _depth)),
                        (1 - _depth) ** 2, 22 / _depth - 22,
                        int(31 * _depth), max(1, int(_depth * 2))))


def pen(r, g, b):
    return display.create_pen(r, g, b)


INK = pen(16, 20, 34)
BLACK = pen(5, 8, 16)
WHITE = pen(248, 241, 217)
CYAN = pen(57, 224, 235)
YELLOW = pen(255, 215, 72)
ORANGE = pen(255, 133, 67)
RED = pen(244, 74, 88)
PINK = pen(238, 104, 171)
PURPLE = pen(147, 119, 214)
BLUE = pen(73, 129, 222)
GREEN = pen(98, 209, 141)
GREY = pen(101, 113, 135)
ROAD = pen(47, 53, 69)
ROAD_ALT = pen(51, 57, 73)
SKIN = pen(255, 186, 135)
THEMES = (
    (pen(87, 103, 172), pen(199, 131, 161), pen(244, 173, 130),
     pen(77, 85, 122), pen(92, 132, 111), pen(81, 119, 100)),
    (pen(82, 153, 194), pen(140, 192, 213), pen(210, 221, 205),
     pen(151, 105, 101), pen(191, 150, 99), pen(173, 133, 89)),
    (pen(21, 31, 68), pen(38, 55, 98), pen(77, 88, 133),
     pen(39, 50, 85), pen(46, 92, 100), pen(38, 79, 88)),
)


def rect(x, y, w, h, colour):
    display.set_pen(colour)
    display.rectangle(int(x), int(y), max(1, int(w)), max(1, int(h)))


def text(label, x, y, colour=WHITE, scale=1):
    display.set_pen(colour)
    display.text(str(label), int(x), int(y), WIDTH, scale)


def centre(label, y, colour=WHITE, scale=1):
    text(label, (WIDTH - display.measure_text(label, scale)) // 2,
         y, colour, scale)


def clamp(value, low, high):
    return max(low, min(high, value))


class Controller:
    def __init__(self):
        self.pad = QwSTPad(I2C(0, sda=40, scl=41), 0x21)
        self.buttons = dict(self.pad.read_buttons())
        self.events = {}
        self.leds = -1

    def poll(self):
        # The driver reuses its dictionary; snapshot it before the next read.
        buttons = dict(self.pad.read_buttons())
        self.events = {key: value and not self.buttons.get(key, False)
                       for key, value in buttons.items()}
        self.buttons = buttons

    def held(self, key):
        return self.buttons.get(key, False)

    def pressed(self, key):
        return self.events.get(key, False)

    def show_health(self, health):
        count = max(0, min(4, (int(health) + 24) // 25))
        leds = (1 << count) - 1
        if leds != self.leds:
            self.pad.set_leds(leds)
            self.leds = leds


class Audio:
    """Non-blocking effects; no continuous engine tone to mask warnings."""
    def __init__(self):
        self.buzzer = Buzzer(43)
        self.notes = ()
        self.index = 0
        self.deadline = None

    def play(self, notes):
        self.notes = notes
        self.index = 0
        self.deadline = None

    def update(self, now):
        if not self.notes:
            return
        if self.deadline is not None:
            if time.ticks_diff(now, self.deadline) < 0:
                return
            self.index += 1
        if self.index >= len(self.notes):
            self.stop()
            return
        frequency, duration = self.notes[self.index]
        self.buzzer.set_tone(frequency, 0.13)
        self.deadline = time.ticks_add(now, duration)

    def stop(self):
        self.notes = ()
        self.deadline = None
        self.buzzer.set_tone(-1)


START_SOUND = ((392, 70), (523, 70), (784, 130))
HIT_SOUND = ((150, 50), (95, 65))
STRIKE_SOUND = ((380, 25), (190, 45))
KO_SOUND = ((523, 45), (784, 45), (1047, 80))
FINISH_SOUND = ((523, 70), (659, 70), (784, 70), (1047, 180))


def load_high_score():
    try:
        with open(SAVE_FILE) as handle:
            return max(0, int(handle.read()))
    except (OSError, ValueError):
        return 0


def save_high_score(score, high):
    global presto, display
    if score <= high:
        return high
    # Stock Presto firmware scans the display on core1. Stop that worker before
    # writing internal flash, then restore the display for the results screen.
    # Leaving it active can deadlock flash writes on MicroPython v1.29 firmware.
    driver = getattr(presto, "presto", None)
    if driver is not None:
        driver.__del__()
    try:
        with open(SAVE_FILE, "w") as handle:
            handle.write(str(score))
    except OSError:
        pass
    finally:
        if driver is not None:
            presto = Presto(ambient_light=True, layers=1)
            display = presto.display
    return score


def new_race(stage=0, score=0):
    rivals = []
    for index in range(5):
        rivals.append({"x": (-0.62, 0.48, -0.15, 0.66, -0.50)[index],
                       "z": 14.0 + index * 19, "speed": 44 + stage * 3 + index,
                       "hp": 2, "down": 0.0, "attack": 1.2 + index * 0.4,
                       "flash": 0.0, "colour": (PINK, YELLOW, PURPLE, GREEN, RED)[index],
                       "phase": index * 1.7})
    traffic = []
    for index in range(6):
        traffic.append(new_traffic(110 + index * 65, index))
    return {"stage": stage, "length": LENGTHS[stage], "distance": 0.0,
            "x": 0.0, "speed": 0.0, "health": 100.0, "boost": 100.0,
            "clock": 0.0, "countdown": 3.0, "score": score, "kos": 0,
            "rivals": rivals, "traffic": traffic, "attack": 0.0,
            "side": 0, "invulnerable": 0.0, "crash": 0.0,
            "message": "", "message_time": 0.0, "position": 6,
            "result": None, "lean": 0.0, "boosting": False,
            "boost_ready": True}


def new_traffic(z, index):
    # One hazard per depth band leaves a route past every obstacle.
    kind = "oil" if index % 4 == 3 else "car"
    return {"x": random.choice((-0.65, 0.0, 0.65)), "z": float(z),
            "speed": 0 if kind == "oil" else 23 + index % 3 * 3,
            "kind": kind, "colour": (BLUE, ORANGE, WHITE)[index % 3],
            "hit": False}


def curve(distance):
    return math.sin(distance * 0.0028) * 0.70 + math.sin(distance * 0.0011) * 0.35


def announce(race, message):
    race["message"] = message
    race["message_time"] = 1.0


def damage(race, amount, audio):
    if race["invulnerable"] > 0:
        return
    race["health"] = max(0, race["health"] - amount)
    race["speed"] *= 0.48
    race["invulnerable"] = 1.35
    race["crash"] = 0.55
    announce(race, "BIKE DOWN!" if amount >= 20 else "RIVAL HIT!")
    audio.play(HIT_SOUND)


def attack(race, side, audio):
    if race["attack"] > 0 or race["crash"] > 0 or race["countdown"] > 0:
        return
    race["side"] = side
    race["attack"] = 0.38
    audio.play(STRIKE_SOUND)
    # Hit the nearest rider on that side, once per button press.
    target = None
    nearest = 100.0
    for rival in race["rivals"]:
        dx = (rival["x"] - race["x"]) * side
        dz = abs(rival["z"] - race["distance"])
        if rival["down"] <= 0 and 0.08 < dx < 0.65 and dz < 10:
            if dz < nearest:
                target, nearest = rival, dz
    if target is None:
        return
    target["hp"] -= 1
    target["flash"] = 0.25
    target["attack"] = 1.0
    target["x"] = clamp(target["x"] + side * 0.16, -0.85, 0.85)
    race["score"] += 75
    if target["hp"] <= 0:
        target["down"] = 2.8
        race["kos"] += 1
        race["score"] += 225
        race["boost"] = min(100, race["boost"] + 30)
        announce(race, "KNOCKOUT! +300")
        audio.play(KO_SOUND)
    else:
        announce(race, "NICE HIT! +75")


def update_race(race, controls, audio, dt):
    if race["result"] is not None:
        return
    if race["countdown"] > 0:
        race["countdown"] = max(0, race["countdown"] - dt)
        return
    race["clock"] += dt
    for key in ("attack", "invulnerable", "crash", "message_time"):
        race[key] = max(0, race[key] - dt)
    top_speed = 62 + race["stage"] * 3
    throttle = controls.held("A")
    brake = controls.held("B") or controls.held("D")
    if not controls.held("U"):
        race["boost_ready"] = True
    if race["boost"] <= 0:
        race["boost_ready"] = False
    boosting = (controls.held("U") and throttle and not brake
                and race["boost"] > 0 and race["boost_ready"]
                and race["crash"] <= 0)
    race["boosting"] = boosting
    race["boost"] = clamp(race["boost"] + (-34 if boosting else 8) * dt, 0, 100)
    target_speed = top_speed + 20 if boosting else top_speed
    if race["crash"] > 0:
        race["speed"] = max(0, race["speed"] - 45 * dt)
    elif brake:
        race["speed"] = max(0, race["speed"] - 65 * dt)
    elif throttle:
        race["speed"] = min(target_speed, race["speed"] + 27 * dt)
    else:
        race["speed"] = max(0, race["speed"] - 14 * dt)
    steering = int(controls.held("R")) - int(controls.held("L"))
    race["lean"] = steering
    if race["crash"] <= 0:
        race["x"] += steering * (0.65 + race["speed"] / 100) * dt
        race["x"] -= curve(race["distance"]) * race["speed"] / top_speed * 0.28 * dt
    race["x"] = clamp(race["x"], -1.35, 1.35)
    if abs(race["x"]) > 0.98:
        race["speed"] = max(0, race["speed"] - 48 * dt)
        race["health"] = max(0, race["health"] - 4 * dt)
        announce(race, "OFF ROAD - STEER IN")
    old_distance = race["distance"]
    race["distance"] += race["speed"] * dt

    for rival in race["rivals"]:
        rival["flash"] = max(0, rival["flash"] - dt)
        if rival["down"] > 0:
            rival["down"] = max(0, rival["down"] - dt)
            if rival["down"] == 0:
                rival["hp"] = 2
                rival["attack"] = 1.5
            continue
        rival["z"] += rival["speed"] * dt
        dz = rival["z"] - race["distance"]
        if abs(dz) < 18:
            rival["attack"] = max(0, rival["attack"] - dt)
            # Rivals edge alongside, then flash before throwing a punch.
            desired = clamp(race["x"] + (0.40 if rival["phase"] % 2 < 1 else -0.40), -0.8, 0.8)
            rival["x"] += clamp(desired - rival["x"], -dt * 0.35, dt * 0.35)
        else:
            # Never spend the warning while a rider is far away or off-screen.
            rival["attack"] = max(0.8, rival["attack"])
            rival["x"] += math.sin(race["clock"] + rival["phase"]) * dt * 0.06
            rival["x"] = clamp(rival["x"], -0.8, 0.8)
        dx = abs(rival["x"] - race["x"])
        if abs(dz) < 8 and dx < 0.60 and rival["attack"] <= 0:
            damage(race, 12, audio)
            rival["attack"] = 2.1
        if abs(dz) < 3.5 and dx < 0.18:
            damage(race, 16, audio)
    for index, car in enumerate(race["traffic"]):
        old_z = car["z"]
        car["z"] += car["speed"] * dt
        relative_before = old_z - old_distance
        relative_after = car["z"] - race["distance"]
        if not car["hit"] and min(relative_before, relative_after) <= 3 and max(relative_before, relative_after) >= -3:
            width = 0.27 if car["kind"] == "car" else 0.23
            if abs(car["x"] - race["x"]) < width:
                car["hit"] = True
                damage(race, 24 if car["kind"] == "car" else 18, audio)
            elif relative_before >= 0 > relative_after and abs(car["x"] - race["x"]) < 0.48:
                race["score"] += 40
                announce(race, "CLOSE PASS +40")
        if relative_after < -35:
            furthest = max(item["z"] for item in race["traffic"])
            car.update(new_traffic(max(furthest + 60, race["distance"] + 290),
                                   random.randrange(12)))
    race["position"] = 1 + sum(rival["z"] > race["distance"] for rival in race["rivals"])
    if race["health"] <= 0:
        race["result"] = "wrecked"
        audio.play(HIT_SOUND)
    elif race["distance"] >= race["length"]:
        race["result"] = "qualified" if race["position"] <= 3 else "too_slow"
        race["score"] += (7 - race["position"]) * 200 + int(race["health"]) * 5
        audio.play(FINISH_SOUND)


def project(race, x, relative_z):
    depth = 22 / (max(-3, relative_z) + 22)
    bend = curve(race["distance"])
    centre_x = 120 + bend * 65 * (1 - depth) ** 2
    return int(centre_x + x * 93 * depth), int(HORIZON + ROAD_HEIGHT * depth), depth


def draw_road(race):
    theme = THEMES[race["stage"]]
    rect(0, 0, WIDTH, 30, theme[0])
    rect(0, 30, WIDTH, 18, theme[1])
    rect(0, 48, WIDTH, 20, theme[2])
    display.set_pen(YELLOW if race["stage"] != 2 else WHITE)
    display.circle(183, 39, 13)
    display.set_pen(theme[3])
    display.polygon([(0, 67), (0, 51), (23, 43), (52, 58), (86, 38),
                     (117, 59), (149, 49), (173, 60), (213, 44), (240, 57), (240, 67)])
    bend = curve(race["distance"])
    rectangle = display.rectangle
    set_pen = display.set_pen
    set_pen(theme[4])
    rectangle(0, HORIZON, WIDTH, HEIGHT - HORIZON)
    for y, half, edge, offset, z, lane, lane_width in ROAD_STRIPS:
        stripe = int((race["distance"] + z) / 11) % 2
        centre_x = int(120 + bend * 65 * offset)
        if stripe:
            set_pen(theme[5])
            rectangle(0, y, WIDTH, 6)
        set_pen(WHITE if stripe else RED)
        rectangle(centre_x - half - edge, y, half * 2 + edge * 2, 6)
        set_pen(ROAD if stripe else ROAD_ALT)
        rectangle(centre_x - half, y, max(1, half * 2), 6)
        if stripe:
            set_pen(WHITE)
            rectangle(centre_x - lane, y, lane_width, 6)
            rectangle(centre_x + lane, y, lane_width, 6)
    # Roadside posts use the same projection as the traffic.
    for index in range(9, -1, -1):
        z = (index * 38 - race["distance"] % 38)
        if z <= 0:
            continue
        for side in (-1.16, 1.16):
            x, y, scale = project(race, side, z)
            h = max(2, int(scale * 23))
            rect(x, y - h, max(1, scale * 3), h, WHITE)
            rect(x, y - h, max(1, scale * 3), max(1, h // 3), RED)
    remaining = race["length"] - race["distance"]
    if 0 < remaining < VIEW_DISTANCE:
        x, y, scale = project(race, 0, remaining)
        width = int(186 * scale)
        tile = max(2, int(width / 16))
        for row in range(2):
            for column in range(16):
                rect(x - width // 2 + column * tile, y + row * tile,
                     tile, tile, BLACK if (row + column) % 2 else WHITE)


def draw_bike(x, y, scale, colour, lean=0, arm=0, down=False):
    scale = max(0.13, scale)
    def block(dx, dy, w, h, c):
        rect(x + (dx + lean * 2) * scale, y + dy * scale, w * scale, h * scale, c)
    if down:
        block(-15, -7, 30, 5, BLACK)
        block(-9, -11, 18, 7, colour)
        block(8, -14, 8, 8, YELLOW)
        return
    block(-9, -2, 18, 4, BLACK)
    block(-4, -17, 8, 18, BLACK)
    block(-2, -15, 2, 13, GREY)
    block(-6, -27, 12, 18, colour)
    block(-4, -14, 8, 4, RED)
    block(-11, -30, 22, 3, GREY)
    block(-11, -27, 5, 15, INK)
    block(6, -27, 5, 15, INK)
    block(-7, -36, 14, 15, colour)
    block(-4, -34, 8, 3, WHITE)
    block(-7, -47, 14, 13, BLACK)
    block(-6, -48, 12, 10, WHITE)
    block(-6, -43, 12, 4, colour)
    if arm:
        block(-22 if arm < 0 else 8, -30, 14, 5, colour)
        block(-26 if arm < 0 else 22, -31, 6, 6, SKIN)
        block(-30 if arm < 0 else 28, -34, 3, 4, YELLOW)


def draw_car(x, y, scale, colour):
    rect(x - 17 * scale, y - 31 * scale, 34 * scale, 29 * scale, BLACK)
    rect(x - 14 * scale, y - 36 * scale, 28 * scale, 34 * scale, colour)
    rect(x - 10 * scale, y - 30 * scale, 20 * scale, 10 * scale, INK)
    rect(x - 8 * scale, y - 29 * scale, 16 * scale, 2 * scale, CYAN)
    for side in (-11, 6):
        rect(x + side * scale, y - 8 * scale, 5 * scale, 3 * scale, RED)


def draw_hud(race):
    rect(0, 0, WIDTH, 27, INK)
    text("%d/6" % race["position"], 6, 4, YELLOW, 2)
    text("%03d" % int(race["speed"] * 3.6), 83, 4, WHITE, 2)
    text("KM/H", 130, 12, GREY)
    text("%dm" % max(0, int(race["length"] - race["distance"])), 172, 9, CYAN)
    rect(0, 237, WIDTH, 3, GREY)
    rect(0, 237, WIDTH * min(1, race["distance"] / race["length"]), 3, YELLOW)
    rect(0, 223, WIDTH, 14, INK)
    text("BIKE", 4, 226, WHITE)
    rect(32, 227, 57, 5, ROAD)
    rect(32, 227, max(0, race["health"]) * 0.57, 5, GREEN if race["health"] > 30 else RED)
    text("BOOST", 100, 226, CYAN)
    rect(135, 227, 51, 5, ROAD)
    rect(135, 227, race["boost"] * 0.51, 5, CYAN)
    text("%02dKO" % race["kos"], 197, 226, YELLOW)


def draw_race(race):
    draw_road(race)
    # A tiny bounded list, drawn far-to-near for correct occlusion.
    objects = []
    for rival in race["rivals"]:
        z = rival["z"] - race["distance"]
        if -3 < z < VIEW_DISTANCE:
            objects.append((z, 0, rival))
    for car in race["traffic"]:
        z = car["z"] - race["distance"]
        if -3 < z < VIEW_DISTANCE:
            objects.append((z, 1, car))
    objects.sort(key=lambda item: item[0], reverse=True)
    for z, kind, obj in objects:
        x, y, scale = project(race, obj["x"], z)
        if kind == 0:
            warning = obj["attack"] < 0.45 and obj["down"] <= 0 and abs(z) < 18
            draw_bike(x, y, scale, WHITE if obj["flash"] > 0 else obj["colour"],
                      arm=(-1 if obj["x"] > race["x"] else 1) if warning else 0,
                      down=obj["down"] > 0)
            if warning:
                text("!", x - 2, y - 60 * scale, YELLOW)
        elif obj["kind"] == "oil":
            rect(x - 14 * scale, y - 3 * scale, 28 * scale, 5 * scale, BLACK)
            rect(x - 8 * scale, y - 2 * scale, 12 * scale, 2 * scale, PURPLE)
        else:
            draw_car(x, y, scale, obj["colour"])
    px, py, scale = project(race, race["x"], 0)
    if race["boosting"]:
        for side in (-7, 4):
            rect(px + side, py - 3, 4, 8 + int(race["clock"] * 30) % 7, ORANGE)
            rect(px + side + 1, py - 2, 2, 6, YELLOW)
    if race["invulnerable"] <= 0 or int(race["clock"] * 15) % 2:
        draw_bike(px, py, 1, CYAN, race["lean"],
                  race["side"] if race["attack"] > 0.17 else 0, race["crash"] > 0)
    draw_hud(race)
    if race["message_time"] > 0:
        rect(16, 76, 208, 18, INK)
        centre(race["message"], 81, YELLOW)
    if race["countdown"] > 0:
        rect(51, 91, 138, 55, INK)
        centre(str(int(math.ceil(race["countdown"]))), 98, YELLOW, 4)
        centre("HOLD A TO ACCELERATE", 136, WHITE)
    elif race["clock"] < 0.75:
        centre("GO!", 103, GREEN, 4)


def panel(title, subtitle):
    rect(9, 47, 222, 165, BLACK)
    rect(9, 47, 222, 3, CYAN)
    centre(title, 58, YELLOW, 2)
    centre(subtitle, 82, WHITE)


def draw_title(race, high):
    draw_road(race)
    # Big original pixel motorcycle, rather than a licensed sprite.
    draw_bike(120, 125, 1.25, CYAN, lean=-1)
    rect(7, 7, 226, 43, INK)
    centre("ROAD RIOT", 12, YELLOW, 3)
    centre("MOTORCYCLE MAYHEM", 38, WHITE)
    rect(8, 134, 224, 101, INK)
    centre("L/R STEER   A GAS   B BRAKE", 142, WHITE)
    centre("X HIT LEFT   Y HIT RIGHT", 157, WHITE)
    centre("U BOOST   + PAUSE   - MENU", 172, CYAN)
    centre("FINISH TOP 3 TO ADVANCE", 187, YELLOW)
    centre("+ START YOUR ENGINE", 204, GREEN)
    centre("BEST %d" % high, 220, GREY)


def draw_result(race, high):
    draw_race(race)
    result = race["result"]
    won = result == "qualified"
    final = won and race["stage"] == len(COURSES) - 1
    title = "TOUR COMPLETE" if final else ("QUALIFIED!" if won else "BIKE WRECKED" if result == "wrecked" else "MISSED THE CUT")
    panel(title, COURSES[race["stage"]])
    centre("PLACE %d/6   KOs %d" % (race["position"], race["kos"]), 105, CYAN)
    centre("SCORE %d" % race["score"], 126, WHITE, 2)
    centre("BEST %d" % high, 153, GREY)
    centre("+ NEXT COURSE" if won and not final else "+ RACE AGAIN", 176, GREEN)
    centre("- ARCADE MENU", 194, WHITE)


def main():
    controller = None
    audio = None
    try:
        audio = Audio()
        while controller is None:
            try:
                controller = Controller()
            except OSError:
                rect(0, 0, WIDTH, HEIGHT, INK)
                centre("CONNECT Qw/ST PAD", 96, YELLOW, 2)
                centre("Retrying controller...", 127, WHITE)
                presto.update()
                time.sleep_ms(400)
        race = new_race()
        high = load_high_score()
        state = "title"
        last_tick = time.ticks_ms()
        while True:
            frame_start = time.ticks_ms()
            dt = min(0.1, max(0, time.ticks_diff(frame_start, last_tick)) / 1000)
            last_tick = frame_start
            controller.poll()
            audio.update(frame_start)
            if controller.pressed("-"):
                break
            if controller.pressed("+"):
                if state == "title":
                    race = new_race()
                    state = "race"
                    audio.play(START_SOUND)
                elif state == "result":
                    next_stage = race["stage"] + 1 if race["result"] == "qualified" else 0
                    if next_stage >= len(COURSES):
                        next_stage = 0
                    race = new_race(next_stage, race["score"] if next_stage else 0)
                    state = "race"
                    audio.play(START_SOUND)
                elif state == "race":
                    state = "pause"
                    audio.stop()
                else:
                    state = "race"
            if state == "race":
                # Combat is edge-triggered; holding a button cannot auto-hit.
                if controller.pressed("X"):
                    attack(race, -1, audio)
                elif controller.pressed("Y"):
                    attack(race, 1, audio)
                remaining = dt
                while remaining > 0:
                    step = min(0.025, remaining)
                    update_race(race, controller, audio, step)
                    remaining -= step
                if race["result"] is not None:
                    high = save_high_score(race["score"], high)
                    state = "result"
                draw_race(race)
            elif state == "title":
                draw_title(race, high)
            elif state == "pause":
                draw_race(race)
                panel("PAUSED", COURSES[race["stage"]])
                centre("+ BACK TO THE RACE", 119, GREEN)
                centre("- ARCADE MENU", 146, WHITE)
            else:
                draw_result(race, high)
            controller.show_health(race["health"])
            presto.update()
            time.sleep_ms(max(1, 33 - time.ticks_diff(time.ticks_ms(), frame_start)))
    finally:
        if audio is not None:
            audio.stop()
        if controller is not None:
            controller.pad.clear_leds()
        for index in range(7):
            presto.set_led_hsv(index, 0, 0, 0)
    machine.reset()


if __name__ in ("__main__", "road_riot"):
    main()

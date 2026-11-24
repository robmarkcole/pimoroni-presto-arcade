"""Host gameplay checks and optional previews of the actual game renderer.

    python3 tools/check_road_riot.py
    uv run --with pillow python tools/check_road_riot.py --render

Hardware stubs only replace the device APIs, not the game rules or drawing.
"""

import importlib.util
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class Pad:
    def __init__(self, *args):
        self.buttons = dict.fromkeys(("L", "R", "U", "D", "A", "B", "X", "Y", "+", "-"), False)
        self.leds = 0

    def read_buttons(self):
        # Match QwSTPad's mutable return value, including aliasing behaviour.
        return self.buttons

    def set_leds(self, value):
        self.leds = value

    def clear_leds(self):
        self.leds = 0


class Display:
    def get_bounds(self):
        return 240, 240

    def create_pen(self, *rgb):
        return rgb


def load_game(display=None):
    screen = display or Display()
    hardware = types.SimpleNamespace(display=screen)
    machine = types.ModuleType("machine")
    machine.I2C = lambda *args, **kwargs: None
    presto = types.ModuleType("presto")
    presto.Presto = lambda **kwargs: hardware
    presto.Buzzer = lambda *args: None
    pad = types.ModuleType("qwstpad")
    pad.QwSTPad = Pad
    spec = importlib.util.spec_from_file_location("road_riot_host", ROOT / "road_riot.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"machine": machine, "presto": presto, "qwstpad": pad}):
        spec.loader.exec_module(module)
    return module


class Controls:
    def __init__(self, *keys):
        self.keys = set(keys)

    def held(self, key):
        return key in self.keys


class Audio:
    def play(self, notes):
        pass


class GameplayChecks(unittest.TestCase):
    def setUp(self):
        random.seed(17)
        self.game = load_game()
        self.race = self.game.new_race()
        self.race["countdown"] = 0
        self.audio = Audio()

    def step(self, seconds, controls=None):
        for _ in range(round(seconds / 0.02)):
            self.game.update_race(self.race, controls or Controls(), self.audio, 0.02)

    def test_driver_dictionary_does_not_swallow_button_edges(self):
        control = self.game.Controller()
        control.pad.buttons["+"] = True
        control.poll()
        self.assertTrue(control.pressed("+"))
        control.poll()
        self.assertFalse(control.pressed("+"))
        control.pad.buttons["+"] = False
        control.poll()
        control.pad.buttons["+"] = True
        control.poll()
        self.assertTrue(control.pressed("+"))

    def test_countdown_freezes_the_entire_race(self):
        self.race["countdown"] = 3
        positions = [r["z"] for r in self.race["rivals"]]
        self.step(2, Controls("A", "U"))
        self.assertEqual(self.race["distance"], 0)
        self.assertEqual(positions, [r["z"] for r in self.race["rivals"]])
        self.assertEqual(self.race["boost"], 100)

    def test_acceleration_brake_and_no_throttle(self):
        self.race["rivals"] = []
        self.race["traffic"] = []
        self.step(2, Controls("A"))
        speed = self.race["speed"]
        self.assertGreater(speed, 40)
        self.step(0.4, Controls("B", "A", "U"))
        self.assertLess(self.race["speed"], speed - 20)
        self.assertFalse(self.race["boosting"])
        self.race["speed"] = 0
        self.step(0.4, Controls("U"))
        self.assertEqual(self.race["speed"], 0)

    def test_steering_and_road_verge_cost(self):
        self.race["rivals"] = []
        self.race["traffic"] = []
        self.step(2, Controls("L", "A"))
        self.assertLess(self.race["x"], -0.98)
        self.assertLess(self.race["health"], 100)
        self.assertLessEqual(abs(self.race["x"]), 1.35)
        self.step(1, Controls("R", "A"))
        self.assertGreater(self.race["x"], -0.98)

    def test_attack_side_cooldown_and_knockout(self):
        rival = self.race["rivals"][0]
        rival.update(x=-0.4, z=4)
        self.game.attack(self.race, 1, self.audio)
        self.assertEqual(rival["hp"], 2)
        self.race["attack"] = 0
        self.game.attack(self.race, -1, self.audio)
        self.assertEqual(rival["hp"], 1)
        self.game.attack(self.race, -1, self.audio)
        self.assertEqual(rival["hp"], 1)
        self.race["attack"] = 0
        self.race["boost"] = 20
        self.game.attack(self.race, -1, self.audio)
        self.assertGreater(rival["down"], 0)
        self.assertEqual(self.race["kos"], 1)
        self.assertEqual(self.race["score"], 375)
        self.assertEqual(self.race["boost"], 50)

    def test_crash_immunity_and_recovery(self):
        self.race["speed"] = 60
        self.game.damage(self.race, 24, self.audio)
        self.game.damage(self.race, 24, self.audio)
        self.assertEqual(self.race["health"], 76)
        self.assertLess(self.race["speed"], 30)
        self.race["rivals"] = []
        self.race["traffic"] = []
        self.step(1.6, Controls("A"))
        self.assertEqual(self.race["crash"], 0)
        self.assertEqual(self.race["invulnerable"], 0)
        self.assertGreater(self.race["speed"], 30)

    def test_fast_traffic_collision_cannot_tunnel(self):
        self.race["speed"] = 82
        self.race["rivals"] = []
        car = self.game.new_traffic(3.1, 0)
        car.update(x=0, speed=0)
        self.race["traffic"] = [car]
        self.game.update_race(self.race, Controls("A", "U"), self.audio, 0.1)
        self.assertEqual(self.race["health"], 76)

    def test_near_miss_scores_once_and_traffic_recycles_ahead(self):
        self.race["rivals"] = []
        car = self.game.new_traffic(0.5, 0)
        car.update(x=0.4, speed=0)
        self.race["traffic"] = [car]
        self.race["speed"] = 60
        self.step(1, Controls("A"))
        self.assertEqual(self.race["score"], 40)
        self.assertGreater(car["z"], self.race["distance"] + 200)

    def test_rivals_attack_and_knocked_down_rider_recovers(self):
        rival = self.race["rivals"][0]
        self.race["rivals"] = [rival]
        self.race["traffic"] = []
        rival.update(x=0.4, z=2, attack=0)
        self.step(0.02)
        self.assertEqual(self.race["health"], 88)
        rival.update(down=0.1, hp=0)
        self.step(0.12)
        self.assertEqual(rival["hp"], 2)
        self.assertEqual(rival["down"], 0)

    def test_boost_depletes_recharges_and_requires_release(self):
        self.race["rivals"] = []
        self.race["traffic"] = []
        self.race["boost"] = 1
        self.race["speed"] = 62
        self.step(0.2, Controls("A", "U"))
        self.assertFalse(self.race["boosting"])
        self.assertFalse(self.race["boost_ready"])
        self.assertGreater(self.race["boost"], 0)
        self.step(0.2, Controls("A"))
        self.step(0.02, Controls("A", "U"))
        self.assertTrue(self.race["boosting"])

    def test_qualification_failure_wreck_and_finished_race_freeze(self):
        for position, expected in ((1, "qualified"), (3, "qualified"), (4, "too_slow")):
            race = self.game.new_race()
            race.update(countdown=0, distance=race["length"] - 0.1, speed=60)
            for index, rival in enumerate(race["rivals"]):
                rival["z"] = race["length"] + 30 if index < position - 1 else 0
            self.game.update_race(race, Controls("A"), self.audio, 0.02)
            self.assertEqual(race["result"], expected)
            score = race["score"]
            self.game.update_race(race, Controls("A"), self.audio, 0.02)
            self.assertEqual(race["score"], score)
        self.race["health"] = 0
        self.step(0.02)
        self.assertEqual(self.race["result"], "wrecked")

    def test_scores_persist_and_invalid_save_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            self.game.SAVE_FILE = str(Path(directory) / "score.txt")
            self.assertEqual(self.game.load_high_score(), 0)
            self.assertEqual(self.game.save_high_score(1234, 0), 1234)
            self.game.save_high_score(12, 1234)
            self.assertEqual(self.game.load_high_score(), 1234)
            Path(self.game.SAVE_FILE).write_text("incomplete")
            self.assertEqual(self.game.load_high_score(), 0)

    def test_display_worker_stops_before_flash_save_and_is_restored(self):
        events = []
        driver = types.SimpleNamespace(__del__=lambda: events.append("stopped"))
        self.game.presto = types.SimpleNamespace(presto=driver)
        replacement = types.SimpleNamespace(display=Display())
        self.game.Presto = lambda **kwargs: (events.append("restarted") or replacement)
        def unavailable_storage(*args):
            self.assertEqual(events, ["stopped"])
            raise OSError("storage unavailable")
        with patch("builtins.open", side_effect=unavailable_storage):
            self.game.save_high_score(100, 0)
        self.assertEqual(events, ["stopped", "restarted"])
        self.assertIs(self.game.presto, replacement)
        self.assertIs(self.game.display, replacement.display)

    def test_all_courses_can_finish_with_traffic_and_rivals_active(self):
        for stage in range(3):
            self.race = self.game.new_race(stage)
            self.race["countdown"] = 0
            for _ in range(6500):
                # Simple pilot: choose the safest of five road positions.
                options = (-0.78, -0.39, 0, 0.39, 0.78)
                danger = [car for car in self.race["traffic"]
                          if -8 < car["z"] - self.race["distance"] < 55]
                target = min(options, key=lambda x: abs(x - self.race["x"]) * 0.1 +
                             sum(max(0, 0.48 - abs(x - car["x"])) * 10 for car in danger))
                keys = ["A"]
                if self.race["clock"] % 6 < 3:
                    keys.append("U")
                if abs(target - self.race["x"]) > 0.04:
                    keys.append("R" if target > self.race["x"] else "L")
                for rival in self.race["rivals"]:
                    dx = rival["x"] - self.race["x"]
                    if 0.08 < abs(dx) < 0.65 and abs(rival["z"] - self.race["distance"]) < 10:
                        self.game.attack(self.race, 1 if dx > 0 else -1, self.audio)
                self.game.update_race(self.race, Controls(*keys), self.audio, 0.02)
                if self.race["result"]:
                    break
            self.assertEqual(self.race["result"], "qualified", self.race)
            self.assertGreater(self.race["health"], 0)


def render():
    from PIL import Image, ImageDraw, ImageFont

    class PillowDisplay(Display):
        def __init__(self):
            self.image = Image.new("RGB", (240, 240))
            self.draw = ImageDraw.Draw(self.image)
            self.colour = (0, 0, 0)
            self.font = ImageFont.truetype("/System/Library/Fonts/Monaco.ttf", 8)

        def set_pen(self, colour):
            self.colour = colour

        def rectangle(self, x, y, w, h):
            self.draw.rectangle((x, y, x + w - 1, y + h - 1), fill=self.colour)

        def circle(self, x, y, radius):
            self.draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=self.colour)

        def polygon(self, points):
            self.draw.polygon(points, fill=self.colour)

        def measure_text(self, text, scale):
            return int(self.font.getlength(str(text)) * scale)

        def text(self, text, x, y, width, scale):
            label = Image.new("RGBA", (max(1, self.measure_text(str(text), 1) + 2), 12))
            ImageDraw.Draw(label).text((0, -2), str(text), font=self.font, fill=self.colour)
            label = label.resize((label.width * scale, label.height * scale), Image.Resampling.NEAREST)
            self.image.paste(label, (x, y), label)

    display = PillowDisplay()
    game = load_game(display)
    random.seed(7)
    race = game.new_race()
    game.draw_title(race, 4200)
    out = ROOT / "docs" / "images"
    display.image.save(out / "road-riot-title.png")
    race.update(countdown=0, distance=790, speed=71, x=0.1, boost=57,
                health=76, position=3, clock=14, kos=2, side=-1, attack=0.3,
                boosting=True, score=1420)
    for rival, (x, z) in zip(race["rivals"], ((-0.4, 4), (0.5, 28), (-0.6, 75), (0, 150), (0.5, -20))):
        rival.update(x=x, z=race["distance"] + z)
    for car, (x, z) in zip(race["traffic"], ((0.5, 65), (-0.6, 125), (0.0, 230), (0.5, 170), (-0.5, 280), (0, 340))):
        car.update(x=x, z=race["distance"] + z)
    game.draw_race(race)
    display.image.save(out / "road-riot-gameplay.png")
    for stage in (1, 2):
        race["stage"] = stage
        game.draw_race(race)
        display.image.save(out / ("road-riot-course-%d.png" % (stage + 1)))
    race.update(result="qualified", stage=2)
    game.draw_result(race, 4200)
    display.image.save(out / "road-riot-finish.png")
    print("Rendered actual Road Riot draw functions into", out)


if __name__ == "__main__":
    if "--render" in sys.argv:
        render()
    else:
        unittest.main()

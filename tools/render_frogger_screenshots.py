"""Render representative Frogger screens for the README.

Run with:
    uv run --with pillow tools/render_frogger_screenshots.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 240
HEIGHT = 240
CELL = 24
HUD_HEIGHT = 24

THEMES = (
    {
        "name": "river",
        "grass": (35, 125, 55),
        "water": (25, 90, 180),
        "road": (48, 48, 55),
        "median": (64, 150, 70),
        "lane": (255, 220, 40),
        "log": (145, 82, 38),
        "log_light": (205, 135, 65),
    },
    {
        "name": "night",
        "grass": (20, 70, 75),
        "water": (45, 20, 100),
        "road": (20, 20, 35),
        "median": (30, 75, 90),
        "lane": (50, 220, 235),
        "log": (100, 70, 160),
        "log_light": (170, 130, 220),
    },
    {
        "name": "ice",
        "grass": (170, 215, 230),
        "water": (75, 175, 225),
        "road": (75, 105, 130),
        "median": (205, 235, 240),
        "lane": (255, 255, 255),
        "log": (45, 115, 155),
        "log_light": (175, 225, 250),
    },
    {
        "name": "lava",
        "grass": (45, 25, 25),
        "water": (225, 45, 10),
        "road": (70, 30, 35),
        "median": (95, 45, 25),
        "lane": (255, 185, 20),
        "log": (45, 45, 45),
        "log_light": (130, 90, 65),
    },
)

VEHICLES = (
    (5, -8, 34, (235, 55, 55)),
    (5, 112, 34, (235, 55, 55)),
    (6, 22, 44, (50, 220, 235)),
    (6, 172, 44, (50, 220, 235)),
    (7, -4, 30, (255, 135, 40)),
    (7, 92, 30, (255, 135, 40)),
    (7, 188, 30, (255, 135, 40)),
)

LOGS = (
    (1, -12, 70),
    (1, 118, 70),
    (2, 28, 58),
    (2, 150, 58),
    (3, -18, 82),
    (3, 112, 82),
)

FROG_POSITIONS = ((100, 7), (132, 3), (76, 4), (28, 2))


def row_y(row):
    return HUD_HEIGHT + row * CELL


def font(size):
    paths = (
        Path("/System/Library/Fonts/Monaco.ttf"),
        Path("/System/Library/Fonts/Supplemental/Andale Mono.ttf"),
    )
    for path in paths:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def draw_frog(draw, x, row):
    y = row_y(row) + 4
    draw.rectangle((x + 4, y, x + 11, y + 15), fill=(100, 255, 80))
    draw.rectangle((x, y + 4, x + 15, y + 11), fill=(100, 255, 80))
    draw.rectangle((x + 3, y + 2, x + 5, y + 4), fill=(25, 110, 30))
    draw.rectangle((x + 10, y + 2, x + 12, y + 4), fill=(25, 110, 30))


def render(level, theme, output):
    image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, row_y(0), WIDTH, row_y(1) - 1), fill=theme["grass"])
    draw.rectangle((0, row_y(1), WIDTH, row_y(4) - 1), fill=theme["water"])
    draw.rectangle((0, row_y(4), WIDTH, row_y(5) - 1), fill=theme["median"])
    draw.rectangle((0, row_y(5), WIDTH, row_y(8) - 1), fill=theme["road"])
    draw.rectangle((0, row_y(8), WIDTH, HEIGHT), fill=theme["grass"])

    for x in range(0, WIDTH, 30):
        draw.rectangle((x, row_y(6), x + 14, row_y(6) + 1), fill=theme["lane"])
        draw.rectangle((x, row_y(7), x + 14, row_y(7) + 1), fill=theme["lane"])

    for column in (0, 2, 4, 6, 8):
        x = column * CELL
        draw.rectangle((x + 3, row_y(0) + 3, x + CELL - 4, row_y(1) - 4), fill=(0, 0, 0))

    offset = (level - 1) * 9
    for row, start_x, width in LOGS:
        x = start_x + offset
        y = row_y(row) + 4
        draw.rectangle((x, y, x + width - 1, y + CELL - 9), fill=theme["log"])
        draw.rectangle((x + 5, y + 4, x + width - 6, y + 6), fill=theme["log_light"])

    for row, start_x, width, colour in VEHICLES:
        x = start_x - offset
        y = row_y(row) + 4
        draw.rectangle((x, y, x + width - 1, y + CELL - 9), fill=colour)
        for wheel_x in (x + 5, x + width - 11):
            draw.rectangle((wheel_x, y - 2, wheel_x + 5, y), fill=(0, 0, 0))
            draw.rectangle((wheel_x, y + CELL - 9, wheel_x + 5, y + CELL - 7), fill=(0, 0, 0))

    frog_x, frog_row = FROG_POSITIONS[level - 1]
    draw_frog(draw, frog_x, frog_row)

    hud_font = font(10)
    draw.rectangle((0, 0, WIDTH, HUD_HEIGHT - 1), fill=(0, 0, 0))
    draw.text((4, 6), "SCORE " + str((level - 1) * 100), font=hud_font, fill=(255, 255, 255))
    draw.text((105, 6), "L" + str(level) + " " + theme["name"].upper(), font=hud_font, fill=(255, 255, 255))
    draw.text((178, 6), "LIVES 3", font=hud_font, fill=(255, 255, 255))

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)


def main():
    output_dir = Path(__file__).resolve().parents[1] / "docs" / "images"
    for level, theme in enumerate(THEMES, 1):
        render(level, theme, output_dir / ("frogger-level-%d-%s.png" % (level, theme["name"])))


if __name__ == "__main__":
    main()

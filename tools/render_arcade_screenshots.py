"""Render representative 240 x 240 screenshots for the GitHub Pages site.

Run with:
    uv run --with pillow tools/render_arcade_screenshots.py
"""

from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont


WIDTH = 240
HEIGHT = 240
OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "images"


def font(size):
    for path in (
        Path("/System/Library/Fonts/Monaco.ttf"),
        Path("/System/Library/Fonts/Supplemental/Andale Mono.ttf"),
    ):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def save(image, name):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT / name, optimize=True)


def render_ogre_smash():
    image = Image.new("RGB", (WIDTH, HEIGHT), (30, 115, 55))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 24, 231, 239), fill=(55, 58, 66))
    for divider in (64, 120, 176):
        for y in range(31, HEIGHT, 32):
            draw.rectangle((divider - 1, y, divider + 1, y + 14), fill=(250, 220, 70))

    draw.rectangle((0, 0, WIDTH, 23), fill=(0, 0, 0))
    draw.text((3, 2), "SCORE 1840", font=font(13), fill=(255, 230, 35))
    draw.text((133, 6), "LIVES 7", font=font(8), fill=(255, 255, 255))
    draw.text((188, 6), "BOMB", font=font(8), fill=(255, 135, 35))

    # Long truck.
    draw.rectangle((17, 45, 54, 102), fill=(115, 120, 135))
    draw.rectangle((21, 50, 50, 62), fill=(45, 48, 55))
    for x in (14, 52):
        draw.rectangle((x, 55, x + 4, 67), fill=(0, 0, 0))
        draw.rectangle((x, 88, x + 4, 98), fill=(0, 0, 0))

    # Tank and barrel.
    draw.rectangle((128, 56, 167, 100), fill=(45, 48, 55))
    draw.rectangle((132, 51, 163, 105), fill=(65, 105, 45))
    draw.rectangle((138, 67, 157, 84), fill=(105, 145, 65))
    draw.rectangle((148, 40, 151, 68), fill=(105, 145, 65))

    # Fast car.
    draw.rectangle((190, 114, 217, 151), fill=(230, 55, 55))
    draw.rectangle((195, 121, 212, 130), fill=(0, 0, 0))
    draw.rectangle((202, 133, 205, 145), fill=(255, 230, 35))

    # Hole and lightning pickup.
    draw.rectangle((68, 72, 115, 117), fill=(105, 68, 42))
    draw.rectangle((73, 77, 110, 112), fill=(0, 0, 0))
    draw.polygon(((95, 127), (87, 140), (94, 140), (90, 153),
                  (104, 136), (97, 136)), fill=(255, 230, 35))

    # Duck crossing and one road splatter.
    for x in (33, 53, 73):
        draw.rectangle((x, 176, x + 12, 183), fill=(255, 230, 35))
        draw.rectangle((x + 9, 173, x + 15, 179), fill=(255, 230, 35))
        draw.rectangle((x + 16, 176, x + 18, 178), fill=(255, 135, 35))
    draw.ellipse((91, 178, 111, 188), fill=(170, 15, 20))
    draw.rectangle((86, 182, 116, 185), fill=(85, 5, 10))

    # Ogre.
    draw.rectangle((136, 188, 159, 207), fill=(75, 205, 65))
    draw.rectangle((140, 183, 155, 211), fill=(75, 205, 65))
    draw.rectangle((143, 187, 146, 190), fill=(30, 105, 35))
    draw.rectangle((151, 187, 154, 190), fill=(30, 105, 35))
    draw.rectangle((140, 199, 155, 205), fill=(115, 60, 145))
    save(image, "ogre-smash-gameplay.png")


def carve_maze(columns, rows, seed=7):
    random.seed(seed)
    maze = [[1 for _ in range(columns)] for _ in range(rows)]
    stack = [(1, rows - 2)]
    maze[rows - 2][1] = 0
    while stack:
        x, y = stack[-1]
        choices = []
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nx, ny = x + dx, y + dy
            if 0 < nx < columns - 1 and 0 < ny < rows - 1 and maze[ny][nx] == 1:
                choices.append((nx, ny, dx, dy))
        if not choices:
            stack.pop()
            continue
        nx, ny, dx, dy = random.choice(choices)
        maze[y + dy // 2][x + dx // 2] = 0
        maze[ny][nx] = 0
        stack.append((nx, ny))
    return maze


def render_random_maze():
    image = Image.new("RGB", (WIDTH, HEIGHT), (60, 57, 169))
    draw = ImageDraw.Draw(image)
    maze = carve_maze(15, 15)
    cell = 15
    offset = 8
    for y, row in enumerate(maze):
        for x, wall in enumerate(row):
            colour = (127, 125, 244) if wall else (143, 144, 139)
            draw.rectangle((offset + x * cell, offset + y * cell,
                            offset + x * cell + 13, offset + y * cell + 13), fill=colour)
    draw.rectangle((offset + cell, offset + 13 * cell,
                    offset + cell + 13, offset + 13 * cell + 13), fill=(255, 0, 0))
    draw.rectangle((offset + 13 * cell, offset + cell,
                    offset + 13 * cell + 13, offset + cell + 13), fill=(0, 255, 0))
    draw.rectangle((offset + 7 * cell, offset + 9 * cell,
                    offset + 7 * cell + 13, offset + 9 * cell + 13), fill=(227, 231, 110))
    draw.text((4, 3), "Lvl: 4", font=font(9), fill=(255, 255, 255), stroke_width=1,
              stroke_fill=(0, 0, 0))
    save(image, "random-maze-gameplay.png")


def render_awesome_game():
    image = Image.new("RGB", (WIDTH, HEIGHT), (72, 180, 224))
    draw = ImageDraw.Draw(image)
    draw.text((10, 8), "Score: 6", font=font(14), fill=(255, 255, 255))
    draw.text((175, 10), "FPS: 30", font=font(9), fill=(255, 255, 255))
    # Falling hazards.
    for x, y in ((30, 58), (88, 102), (148, 42), (207, 119)):
        draw.rectangle((x, y, x + 15, y + 15), fill=(105, 55, 70))
        draw.line((x + 2, y + 2, x + 13, y + 13), fill=(245, 170, 70), width=3)
        draw.line((x + 13, y + 2, x + 2, y + 13), fill=(245, 170, 70), width=3)
    # Treasure.
    draw.rectangle((48, 178, 64, 194), fill=(110, 65, 25))
    draw.rectangle((50, 174, 62, 180), fill=(255, 215, 0))
    draw.rectangle((54, 178, 58, 193), fill=(255, 235, 80))
    # Player.
    draw.rectangle((143, 174, 157, 208), fill=(40, 45, 70))
    draw.rectangle((141, 164, 159, 180), fill=(235, 180, 125))
    draw.rectangle((139, 160, 161, 168), fill=(185, 35, 45))
    draw.rectangle((144, 172, 157, 177), fill=(255, 255, 255))
    # Pixel ground.
    draw.rectangle((0, 210, WIDTH, HEIGHT), fill=(60, 120, 55))
    for x in range(0, WIDTH, 32):
        draw.rectangle((x, 210, x + 15, 214), fill=(105, 175, 75))
        draw.rectangle((x + 10, 224, x + 27, 228), fill=(45, 95, 45))
    save(image, "awesome-game-gameplay.png")


def main():
    render_ogre_smash()
    render_random_maze()
    render_awesome_game()


if __name__ == "__main__":
    main()

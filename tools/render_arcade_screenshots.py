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


def render_zombie_escape():
    image = Image.new("RGB", (WIDTH, HEIGHT), (18, 20, 31))
    draw = ImageDraw.Draw(image)
    cell = 16
    maze = (
        "###############", "#.....#.......#", "#.###.#.###.#.#",
        "#...#.....#...#", "###.#.###.#.###", "#...#...#.#...#",
        "#.#####.#.###.#", "#.......#.....#", "#.###.#####.#.#",
        "#...#.......#.#", "#.#.###.###...#", "#.....#.......#",
        "###############",
    )
    for row, tiles in enumerate(maze):
        for column, tile in enumerate(tiles):
            x = column * cell
            y = 28 + row * cell
            if tile == "#":
                draw.rectangle((x, y, x + 15, y + 15), fill=(50, 65, 150))
                draw.line((x + 2, y + 2, x + 13, y + 2), fill=(95, 115, 235), width=2)
                draw.line((x + 2, y + 2, x + 2, y + 13), fill=(95, 115, 235), width=2)
            elif (column * 3 + row * 5) % 7 == 0:
                draw.polygon(((x + 8, y + 3), (x + 12, y + 8),
                              (x + 8, y + 13), (x + 4, y + 8)), fill=(60, 225, 255))
    draw.rectangle((0, 0, WIDTH, 27), fill=(0, 0, 0))
    draw.text((3, 4), "GEMS 23", font=font(12), fill=(255, 230, 40))
    draw.text((154, 7), "L2 LIFE 3", font=font(8), fill=(255, 255, 255))
    # Player.
    draw.ellipse((52, 61, 64, 73), fill=(255, 205, 55))
    draw.rectangle((54, 72, 62, 78), fill=(165, 95, 20))
    # Zombies.
    for x, y in ((180, 61), (68, 189), (196, 173)):
        draw.ellipse((x, y, x + 12, y + 12), fill=(90, 205, 75))
        draw.rectangle((x + 2, y + 11, x + 10, y + 16), fill=(35, 100, 40))
        draw.rectangle((x + 3, y + 4, x + 4, y + 5), fill=(235, 50, 55))
        draw.rectangle((x + 8, y + 4, x + 9, y + 5), fill=(235, 50, 55))
    # Exit.
    draw.rectangle((211, 205, 225, 219), fill=(60, 225, 90))
    draw.rectangle((215, 209, 221, 215), fill=(18, 20, 31))
    save(image, "zombie-escape-gameplay.png")


def render_rainbow_barrage():
    image = Image.new("RGB", (WIDTH, HEIGHT), (24, 25, 45))
    draw = ImageDraw.Draw(image)
    for y in range(36, 174, 24):
        draw.rectangle((0, y, WIDTH, y + 1), fill=(43, 48, 78))
    draw.rectangle((0, 174, WIDTH, HEIGHT), fill=(32, 42, 38))
    draw.rectangle((0, 174, WIDTH, 178), fill=(54, 72, 55))
    colours = ((165, 70, 220), (45, 215, 235), (255, 135, 35), (245, 85, 170))
    centres = (28, 89, 151, 212)
    heights = (5, 3, 6, 4)
    for centre, colour, height in zip(centres, colours, heights):
        left = centre - 15
        for floor in range(height):
            y = 174 - (floor + 1) * 16
            draw.rectangle((left - 2, y - 1, left + 31, y + 15), fill=(42, 45, 55))
            draw.rectangle((left, y, left + 29, y + 13), fill=colour)
            draw.rectangle((left + 4, y + 4, left + 9, y + 10), fill=(0, 0, 0))
            draw.rectangle((left + 20, y + 4, left + 25, y + 10), fill=(0, 0, 0))
        top = 174 - height * 16
        draw.polygon(((centre - 14, top), (centre, top - 11),
                      (centre + 14, top)), fill=colour)
    rainbow = ((240, 55, 60), (255, 135, 35), (255, 225, 40),
               (65, 220, 90), (45, 215, 235), (55, 95, 235), (165, 70, 220))
    for index, colour in enumerate(rainbow):
        draw.arc((76, 58 + index * 2, 190, 210), 205, 302, fill=colour, width=3)
    draw.ellipse((181, 103, 188, 110), fill=(255, 255, 255))
    # Sky Spark and Void Wraith.
    draw.polygon(((47, 69), (34, 60), (38, 75)), fill=(255, 225, 40))
    draw.ellipse((41, 63, 55, 77), fill=(45, 215, 235))
    draw.polygon(((195, 57), (181, 49), (184, 66)), fill=(165, 70, 220))
    draw.ellipse((190, 51, 206, 67), fill=(42, 45, 55))
    draw.ellipse((199, 57, 211, 69), fill=(165, 70, 220))
    # Launcher and HUD.
    draw.rectangle((137, 218, 165, 228), fill=(95, 100, 115))
    draw.rectangle((146, 205, 156, 220), fill=(45, 215, 235))
    draw.rectangle((0, 0, WIDTH, 27), fill=(0, 0, 0))
    draw.text((3, 3), "S 2380", font=font(13), fill=(255, 225, 40))
    draw.text((105, 7), "W4 L2", font=font(8), fill=(255, 255, 255))
    for index, colour in enumerate(rainbow):
        draw.rectangle((165 + index * 10, 8, 172 + index * 10, 17), fill=colour)
    save(image, "rainbow-barrage-gameplay.png")


def render_fly_smash():
    image = Image.new("RGB", (WIDTH, HEIGHT), (65, 174, 235))
    draw = ImageDraw.Draw(image)
    # Soft background clouds.
    for x, y in ((18, 62), (170, 78), (82, 150)):
        draw.ellipse((x, y, x + 15, y + 14), fill=(120, 210, 250))
        draw.ellipse((x + 9, y - 3, x + 28, y + 15), fill=(120, 210, 250))
        draw.ellipse((x + 22, y + 1, x + 35, y + 14), fill=(120, 210, 250))
    # Cloud helper.
    def cloud(x, y, width=55, gap=0, warning=False):
        colour = (255, 225, 35) if warning else (255, 255, 255)
        if gap:
            side = (width - gap) // 2
            draw.rectangle((x, y, x + side, y + 6), fill=colour)
            draw.ellipse((x, y - 6, x + 16, y + 10), fill=colour)
            draw.rectangle((x + width - side, y, x + width, y + 6), fill=colour)
            draw.ellipse((x + width - 16, y - 6, x + width, y + 10), fill=colour)
        else:
            draw.rectangle((x + 6, y - 3, x + width - 6, y + 7), fill=colour)
            draw.ellipse((x, y - 7, x + 17, y + 10), fill=colour)
            draw.ellipse((x + width // 2 - 10, y - 12, x + width // 2 + 10, y + 8), fill=colour)
            draw.ellipse((x + width - 17, y - 7, x + width, y + 10), fill=colour)
    cloud(15, 198)
    cloud(114, 159, gap=30)
    cloud(40, 112, warning=True)
    cloud(154, 67)
    # Player and blue shield.
    draw.ellipse((53, 150, 83, 180), outline=(45, 225, 245), width=3)
    draw.rectangle((63, 163, 73, 178), fill=(155, 70, 220))
    draw.ellipse((62, 151, 74, 163), fill=(255, 190, 120))
    draw.rectangle((62, 151, 74, 154), fill=(125, 70, 35))
    draw.rectangle((73, 166, 81, 169), fill=(65, 220, 95))
    draw.rectangle((82, 166, 104, 168), fill=(45, 225, 245))
    # Car with bomb.
    draw.rectangle((164, 113, 191, 121), fill=(245, 80, 175))
    draw.rectangle((171, 109, 183, 114), fill=(245, 80, 175))
    draw.rectangle((173, 110, 180, 112), fill=(45, 225, 245))
    draw.ellipse((168, 119, 174, 125), fill=(0, 0, 0))
    draw.ellipse((183, 119, 189, 125), fill=(0, 0, 0))
    draw.ellipse((175, 126, 183, 134), fill=(240, 55, 60))
    # Yellow hazard and blue shield pickup.
    draw.rectangle((0, 91, 150, 95), fill=(255, 130, 35))
    draw.rectangle((0, 92, 150, 93), fill=(255, 225, 35))
    draw.ellipse((183, 184, 197, 198), fill=(45, 225, 245))
    draw.ellipse((188, 189, 192, 193), fill=(35, 110, 245))
    # HUD.
    draw.rectangle((0, 0, WIDTH, 27), fill=(0, 0, 0))
    draw.text((3, 3), "S 470", font=font(13), fill=(255, 225, 35))
    draw.text((101, 7), "L2", font=font(8), fill=(255, 255, 255))
    draw.text((130, 7), "A LASER", font=font(8), fill=(65, 220, 95))
    draw.text((184, 7), "SH 42", font=font(8), fill=(45, 225, 245))
    save(image, "fly-smash-gameplay.png")


def main():
    render_ogre_smash()
    render_random_maze()
    render_awesome_game()
    render_zombie_escape()
    render_rainbow_barrage()
    render_fly_smash()


if __name__ == "__main__":
    main()

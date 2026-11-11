#
# Experiment: can the GDEH0576T81 update just a horizontal strip of the screen,
# and is that faster than a full-screen partial update?
#
# Run on the Pi (not while main.py is running):
#     sudo python3 window_test.py
#
# It pauses after every step. Look at the screen, answer the questions it
# prints, and send the output (including the timing lines) back.
#
from PIL import Image, ImageDraw, ImageFont
from waveshare_epd import epd5in76

epd = epd5in76.EPD()
W, H = epd.width, epd.height
font = ImageFont.truetype('Courier Prime.ttf', 28)
big = ImageFont.truetype('Courier Prime.ttf', 56)


def win(img, img_y0, img_y1, repeat=1):
    """Update only image rows [img_y0, img_y1) (flip_y puts them at buffer
    rows H-img_y1 .. H-img_y0)."""
    assert epd.flip_y, "window_test assumes the default flip_y=True"
    epd.display_window(epd.getbuffer(img), H - img_y1, img_y1 - img_y0, repeat)


def pause(msg):
    print(msg)
    input("--- press Enter to continue ---\n")


def base_image():
    img = Image.new('1', (W, H), 255)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W - 1, H - 1), outline=0, width=6)
    d.line((0, 0, W, H), fill=0, width=3)
    d.line((0, H, W, 0), fill=0, width=3)
    d.text((30, 20), "TOP OF SCREEN", font=big, fill=0)
    d.text((30, H - 90), "BOTTOM OF SCREEN", font=big, fill=0)
    for y in range(100, H, 100):
        d.line((0, y, 80, y), fill=0, width=3)
        d.text((90, y - 14), "y=%d" % y, font=font, fill=0)
    return img


def band_image(img, img_y0, img_y1, label, fill_black=True):
    img = img.copy()
    d = ImageDraw.Draw(img)
    d.rectangle((120, img_y0 + 10, W - 120, img_y1 - 10), fill=0 if fill_black else 255, outline=0, width=4)
    d.text((140, img_y0 + 40), label, font=font, fill=255 if fill_black else 0)
    return img


try:
    epd.init()
    base = base_image()
    epd.display(epd.getbuffer(base))
    pause("STEP 0: full test pattern drawn (border, X, TOP/BOTTOM labels, y= ticks).\n"
          "Check it is the right way up. Then continue.")

    epd.init_Partial()

    # --- Test A: bottom 120 rows (gate offset now converted) ---
    imgA = band_image(base, H - 120, H, "WINDOW A: bottom 120 rows")
    win(imgA, H - 120, H)
    pause("TEST A: a black bar in the BOTTOM 120 rows only; rest unchanged.\n"
          "Report: (1) is the bar at the bottom? is its text readable and upright?\n"
          "        (2) how dark is the bar vs the black border lines (full / medium / dim)?\n"
          "        (3) the timing line above.")

    # --- Test B: middle band ---
    imgB = band_image(imgA, 300, 420, "WINDOW B: rows 300-420")
    win(imgB, 300, 420)
    pause("TEST B: a black bar between the y=300 and y=400 ticks (about y=300..420).\n"
          "Report: (1) is it positioned there? (2) did bar A and the rest stay?\n"
          "        (3) how dark is it? (4) the timing line above.")

    # --- Test D: does repeating the update build contrast? ---
    epd.init()
    epd.Clear()
    epd.init_Partial()
    cur = Image.new('1', (W, H), 255)
    for n, (y0, y1) in enumerate([(0, 120), (120, 240), (240, 360), (360, 480)], start=1):
        cur = band_image(cur, y0, y1, "repeat x%d" % n)
        win(cur, y0, y1, repeat=n)
    pause("TEST D: four black bars, top to bottom, updated 1, 2, 3, 4 times.\n"
          "Report: which bar is the first that looks as dark as a normal full\n"
          "update (x1, x2, x3, x4)? Also send the four timing lines above.")

    # --- Test E: a taller strip, one update ---
    cur = band_image(cur, 440, 680, "240 rows x1")
    win(cur, 440, 680, repeat=1)
    pause("TEST E: a 240-row strip (bottom of the screen), one update.\n"
          "Report: how dark is it compared with the x1 bar and with the x4 bar?\n"
          "        and the timing line above.")

    # --- Test F: reference, normal full-frame partial update ---
    d = ImageDraw.Draw(cur)
    d.rectangle((120, 490, W - 120, 540), fill=0)
    epd.display(epd.getbuffer(cur))
    pause("TEST F: reference. A black bar near y=490..540 drawn with the normal\n"
          "full-frame partial update (this is how main.py draws today).\n"
          "Report: how dark is it compared with the bars from test D?")

finally:
    epd.init()
    epd.Clear()
    epd.sleep()

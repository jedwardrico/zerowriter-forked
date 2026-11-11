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


def band_rows(img_y0, img_y1):
    """Image rows [img_y0, img_y1) -> (buffer y0, rows), allowing for flip_y."""
    if epd.flip_y:
        return H - img_y1, img_y1 - img_y0
    return img_y0, img_y1 - img_y0


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

    # --- Test A: bottom 120 rows, resolution change only (no gate offset) ---
    y0, rows = band_rows(H - 120, H)
    imgA = band_image(base, H - 120, H, "WINDOW A: bottom 120 rows")
    epd.display_window(epd.getbuffer(imgA), y0, rows)
    pause("TEST A (resolution only, no offset): a black bar should appear in the\n"
          "BOTTOM 120 rows only, and the rest of the pattern should be unchanged.\n"
          "Report: (1) did the bar appear at the bottom, top, or elsewhere?\n"
          "        (2) did the rest of the screen keep its pattern, go blank, or garble?\n"
          "        (3) the timing line above.")

    # --- Test B: middle band, needs the gate offset (GSST) ---
    y0, rows = band_rows(300, 420)
    imgB = band_image(imgA, 300, 420, "WINDOW B: rows 300-420")
    epd.display_window(epd.getbuffer(imgB), y0, rows)
    pause("TEST B (gate offset): a black bar should appear around y=300..420\n"
          "(between the y=300 and y=400 ticks), and bar A at the bottom should stay.\n"
          "Report: (1) where did the bar appear? (2) did bar A and the rest stay?\n"
          "        (3) the timing line above.")

    # --- Test C: typing-like repeated small updates ---
    y0, rows = band_rows(H - 120, H)
    cur = imgA
    for i, text in enumerate(["h", "he", "hel", "hell", "hello"]):
        cur = band_image(base, H - 120, H, "typing: " + text, fill_black=False)
        epd.display_window(epd.getbuffer(cur), y0, rows)
    pause("TEST C: five quick updates of the bottom strip like keystrokes.\n"
          "Report the five timing lines above and whether the text looked clean.")

finally:
    epd.init()
    epd.Clear()
    epd.sleep()

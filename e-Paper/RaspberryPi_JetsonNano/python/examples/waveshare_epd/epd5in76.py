# Good Display GDEH0576T81 (5.76", 920x680, SSD2677) driver for the Zerowriter.
#
# Ported from Good Display's Arduino demo for this panel (Display_EPD_W21.cpp)
# and the SSD2677 datasheet. Same public API as the other drivers in this
# directory (init / init_Partial / getbuffer / display / Clear / sleep).
#
# Notes:
# * Wire it via a DESPI-C02 with its P3 switch on 2.2. See WIRING.md.
# * BUSY is active low: the pin reads 0 while the panel is busy, 1 when ready.
# * The controller always takes a whole frame, 2 bits per pixel.
#   - Full update:    each pixel is 00 (black) or 11 (white).
#   - Partial update: each pixel is (previous bit, new bit), so the driver
#     remembers the last frame it sent. The waveform comes from the chip's OTP.
# * Partial updates leave ghosting. Do a full update (init + display +
#   init_Partial) now and then; see partial_count.
# * Always call sleep() when finished (Good Display: otherwise it shortens the
#   panel's life).

import logging
import os
import struct
import time

from PIL import Image

from . import epdconfig

EPD_WIDTH = 920
EPD_HEIGHT = 680

logger = logging.getLogger(__name__)


def _build_tables():
    # Full update: 1bpp byte -> 2 bytes (each bit becomes 00 or 11).
    full = []
    for b in range(256):
        v = 0
        for i in range(7, -1, -1):
            v = (v << 2) | (3 if (b >> i) & 1 else 0)
        full.append(struct.pack('>H', v))
    # Partial update: (old byte, new byte) -> 2 bytes of (old,new) bit pairs,
    # first pixel in the top bits. Same as bitInterleave() in the demo.
    spread = []
    for b in range(256):
        v = 0
        for i in range(8):
            v |= ((b >> (7 - i)) & 1) << (14 - 2 * i)
        spread.append(v)
    part = [struct.pack('>H', (spread[o] << 1) | spread[n])
            for o in range(256) for n in range(256)]
    return full, part


_FULL, _PART = _build_tables()


class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_pin = epdconfig.CS_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT
        self.busy_timeout_s = 30

        # SPI clock. The repo default of 4 MHz makes sending a frame take
        # ~0.3 s. 10 MHz cuts that to ~0.13 s. The SSD2677 datasheet leaves
        # the maximum clock as TBD, so if the screen shows garbage, lower it.
        self.spi_speed_hz = 10000000

        # Set ZW_TIMING=1 in the environment to print per-update timings.
        self.timing = bool(os.environ.get('ZW_TIMING'))

        # Orientation fix-ups applied to the image before sending. With the
        # demo's scan direction this panel shows the image flipped top to
        # bottom, so flip_y is on by default. If text is mirrored left to
        # right, toggle flip_x; if it is upside down, toggle flip_y.
        self.flip_x = False
        self.flip_y = True

        # Value for register 0xE6 (forced temperature) from the demo's table.
        # 241 is the 20-30 C setting. See set_temperature().
        self.temperature_code = 241

        self._module_open = False
        self._partial = False
        self._prev = None            # last frame sent (1bpp bytes)
        self.partial_count = 0       # partial updates since the last full one

    # --- low level -------------------------------------------------------

    def reset(self):
        epdconfig.delay_ms(10)
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(10)
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(10)

    def send_command(self, command):
        epdconfig.digital_write(self.dc_pin, 0)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte([command])
        epdconfig.digital_write(self.cs_pin, 1)

    def send_data(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte([data])
        epdconfig.digital_write(self.cs_pin, 1)

    def send_data_block(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte2(data)
        epdconfig.digital_write(self.cs_pin, 1)

    def ReadBusy(self):
        # BUSY_N: 0 = busy, 1 = ready
        start = time.time()
        while epdconfig.digital_read(self.busy_pin) == 0:
            if time.time() - start > self.busy_timeout_s:
                logger.warning("e-Paper BUSY still low after %ss, continuing",
                               self.busy_timeout_s)
                return
            epdconfig.delay_ms(5)

    def set_temperature(self, celsius):
        """Pick the waveform temperature code (same thresholds as the demo)."""
        if celsius <= 5:
            self.temperature_code = 232
        elif celsius <= 10:
            self.temperature_code = 235
        elif celsius <= 20:
            self.temperature_code = 238
        elif celsius <= 30:
            self.temperature_code = 241
        else:
            self.temperature_code = 244

    def _open(self):
        if not self._module_open:
            if epdconfig.module_init() != 0:
                return -1
            self._module_open = True
        epdconfig.SPI.max_speed_hz = self.spi_speed_hz
        return 0

    def _common_init(self):
        self.reset()
        self.ReadBusy()

        self.send_command(0x00)  # PSR
        self.send_data(0x27)
        self.send_data(0x0E)
        self.ReadBusy()

        self.send_command(0x06)  # BTST
        self.send_data(0x0F)
        self.send_data(0x8B)
        self.send_data(0x9C)
        self.send_data(0xC1)

        self.send_command(0xE7)
        self.send_data(0xC1)

        self.send_command(0x30)  # frame go with waveform
        self.send_data(0x08)

        self.send_command(0x50)  # CDI, border white
        self.send_data(0x77)

        self.send_command(0x61)  # TRES
        self.send_data(self.width // 256)
        self.send_data(self.width % 256)
        self.send_data(self.height // 256)
        self.send_data(self.height % 256)

        self.send_command(0x62)  # HTOTAL
        for b in (0x98, 0x98, 0x98, 0x75, 0xCA, 0xB2, 0x98, 0x7E):
            self.send_data(b)

        self.send_command(0x65)  # GSST
        for _ in range(4):
            self.send_data(0x00)

        self.send_command(0xE9)
        self.send_data(0x01)

    def _power_on(self):
        self.send_command(0x04)
        self.ReadBusy()

    def _update(self):
        self.send_command(0x12)
        self.send_data(0x00)
        self.ReadBusy()

    # --- public API ------------------------------------------------------

    def init(self):
        """Full-update init (slow waveform, clears ghosting)."""
        if self._open() != 0:
            return -1
        self._common_init()

        # Forced temperature + load waveform from OTP
        self.send_command(0xE0)
        self.send_data(0x02)
        self.send_command(0xE6)
        self.send_data(self.temperature_code)
        self.send_command(0xA5)
        self.ReadBusy()
        epdconfig.delay_ms(10)

        self._power_on()
        self._partial = False
        return 0

    def init_Partial(self):
        """Partial-update init (no flicker). Call display() repeatedly after."""
        if self._open() != 0:
            return -1
        self._common_init()

        # Partial waveform from OTP
        self.send_command(0xE0)
        self.send_data(0x00)
        self.send_command(0xA5)
        self.ReadBusy()

        self._power_on()
        self._partial = True
        self.partial_count = 0
        return 0

    def getbuffer(self, image):
        """PIL image -> 1bpp bytes (115 bytes per row), 1 = white."""
        if image.size == (self.width, self.height):
            img = image
        elif image.size == (self.height, self.width):
            img = image.rotate(90, expand=True)
        else:
            logger.warning("Wrong image size %s, expected %dx%d",
                           image.size, self.width, self.height)
            return None
        img = img.convert('1')
        if self.flip_x:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if self.flip_y:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        return img.tobytes()

    def display(self, buf):
        """Show a getbuffer() frame. Full or partial depending on last init."""
        if buf is None:
            return
        # Nothing changed since the last partial update: skip the whole
        # transfer and refresh (this is the common case while the main loop
        # keeps redrawing the same input line).
        if self._partial and buf == self._prev:
            return
        t0 = time.time()
        self.send_command(0x10)
        self.ReadBusy()
        if self._partial:
            old = self._prev if self._prev is not None else b'\xff' * len(buf)
            data = b''.join([_PART[(o << 8) | n] for o, n in zip(old, buf)])
            self.partial_count += 1
        else:
            data = b''.join(map(_FULL.__getitem__, buf))
        t1 = time.time()
        self.send_data_block(data)
        t2 = time.time()
        self._update()
        self._prev = buf
        if self.timing:
            t3 = time.time()
            print("epd %s: convert %.0fms  spi %.0fms  refresh %.0fms  total %.0fms" % (
                "partial" if self._partial else "full",
                (t1 - t0) * 1000, (t2 - t1) * 1000, (t3 - t2) * 1000, (t3 - t0) * 1000))

    def Clear(self):
        """Fill the screen white (uses the current init mode)."""
        self.display(b'\xff' * (self.width // 8 * self.height))

    def sleep(self):
        self.send_command(0x02)  # power off
        self.send_data(0x00)
        self.ReadBusy()
        self.send_command(0x07)  # deep sleep
        self.send_data(0xA5)
        epdconfig.delay_ms(2000)
        epdconfig.module_exit()
        self._module_open = False
        self._prev = None

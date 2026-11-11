# Wiring: Raspberry Pi Zero 2 W -> DESPI-C02 -> GDEH0576T81

Sources: GDEH0576T81 datasheet (FPC pin table, section 1.5) and DESPI-C02
datasheet (header P2 labels, DIP switch P3). Pi pins come from `epdconfig.py`
(BCM numbering).

## DESPI-C02 header P2 (8 pins, top to bottom as printed on the board)

```
 DESPI-C02 P2           Raspberry Pi (40-pin header)
 ------------           ----------------------------
 BUSY   ------------->  Pin 18  GPIO24            (display -> Pi)
 RES    <-------------  Pin 11  GPIO17
 D/C    <-------------  Pin 22  GPIO25
 CS     <-------------  Pin 24  GPIO8  (SPI0 CE0)
 SCK    <-------------  Pin 23  GPIO11 (SPI0 SCLK)
 SDI    <-------------  Pin 19  GPIO10 (SPI0 MOSI)
 GND    -------------   Pin 6   GND
 3.3V   <-------------  Pin 1   3V3
```

| DESPI-C02 pin | Pi BCM | Pi physical pin | Direction |
|---------------|--------|-----------------|-----------|
| BUSY          | GPIO24 | 18              | display -> Pi |
| RES           | GPIO17 | 11              | Pi -> display |
| D/C           | GPIO25 | 22              | Pi -> display |
| CS            | GPIO8 (CE0) | 24         | Pi -> display |
| SCK           | GPIO11 (SCLK) | 23       | Pi -> display |
| SDI           | GPIO10 (MOSI) | 19       | Pi -> display |
| GND           | -      | 6 (or 9, 14, 20, 25) | ground |
| 3.3V          | -      | 1 (or 17)       | power |

## Board settings

- **DIP switch P3 must be set to 2.2** (the SSD series position). The DESPI-C02
  datasheet says to use 2.2 for SSD (Solomon Systech) driver ICs and 0.47 only
  for UC series. The GDEH0576T81 uses an SSD2677. A wrong setting can stop the
  display refreshing.
- Insert the panel FPC into connector P1 with the display surface facing up,
  then press down the black FPC latch.
- Power from 3.3V only. Do not use 5V.

## Notes

- `epdconfig.py` also toggles GPIO18 (PWR_PIN). The DESPI-C02 has no such pin; leave GPIO18 unconnected.
- Enable SPI (`dtparam=spi=on` in config.txt, see `sampleconfig`).
- Panel BS pin (FPC pin 8): Low = 4-line SPI, High = 3-line (9-bit). The DESPI-C02 header has no BS pin and its datasheet doesn't say how the board sets it. This code needs 4-line SPI (separate D/C). If the display never responds, check the BS setting on the board.
- CS is active low. D/C high = data, low = command. RES is active low.
- BUSY is active low (BUSY_N): the pin reads 0 while the panel is busy and 1 when ready. This matches the SSD2677 datasheet and Good Display's demo code (`lcd_chkstatus` waits for 1). The GDEH0576T81 datasheet note saying "busy = high" is wrong or misleading.
- Driver: `e-Paper/RaspberryPi_JetsonNano/python/examples/waveshare_epd/epd5in76.py`, ported from Good Display's Arduino demo. `main.py` uses it.

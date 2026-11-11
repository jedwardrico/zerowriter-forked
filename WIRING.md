# Wiring: Raspberry Pi Zero 2 W -> DESPI-C02 -> GDEH0576T81

Status: the Pi-side pins come from `epdconfig.py` (BCM numbering) and are reliable.
The DESPI-C02 pin labels are the usual 4-wire SPI signal names and are **not yet
checked against the GDEH0576T81 / DESPI-C02 datasheets**. Match each signal to
the label printed on your board before powering up.

```
 Raspberry Pi (40-pin header)                DESPI-C02 header
 ----------------------------                ----------------
 Pin 1   3V3                    ----------->  VCC / 3.3V
 Pin 6   GND                    ----------->  GND
 Pin 19  GPIO10 (SPI0 MOSI)     ----------->  SDA / DIN
 Pin 23  GPIO11 (SPI0 SCLK)     ----------->  SCL / CLK
 Pin 24  GPIO8  (SPI0 CE0)      ----------->  CS
 Pin 22  GPIO25                 ----------->  D/C
 Pin 11  GPIO17                 ----------->  RES
 Pin 18  GPIO24                 <-----------  BUSY   (display -> Pi)
```

| Signal | Pi BCM | Pi physical pin | Direction |
|--------|--------|-----------------|-----------|
| 3.3V   | -      | 1 (or 17)       | power     |
| GND    | -      | 6 (or 9, 14, 20, 25) | ground |
| SDA/DIN (MOSI) | GPIO10 | 19      | Pi -> display |
| SCL/CLK (SCLK) | GPIO11 | 23      | Pi -> display |
| CS     | GPIO8 (CE0) | 24         | Pi -> display |
| D/C    | GPIO25 | 22              | Pi -> display |
| RES    | GPIO17 | 11              | Pi -> display |
| BUSY   | GPIO24 | 18              | display -> Pi |

Notes
- Power the board from 3.3V only. Do not use 5V.
- `epdconfig.py` also toggles GPIO18 (PWR_PIN). The DESPI-C02 has no such pin; leave GPIO18 unconnected.
- Enable SPI (`dtparam=spi=on` in config.txt, see `sampleconfig`).
- Check the DESPI-C02 for a 4-wire/3-wire SPI selector (BS1) and set it to 4-wire SPI. This code uses a separate D/C line.
- The display FPC goes into the DESPI-C02 connector with the contacts facing the correct way; see the board datasheet.

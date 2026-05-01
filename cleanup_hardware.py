#!/usr/bin/env python3
import time


def main():
    try:
        from rpi_ws281x import Color, PixelStrip

        strip = PixelStrip(4, 18, 800000, 10, False, 0, 0)
        strip.begin()
        for _ in range(4):
            for index in range(4):
                strip.setPixelColor(index, Color(0, 0, 0))
            strip.show()
            time.sleep(0.05)
    except Exception:
        pass

    try:
        from smbus2 import SMBus

        with SMBus(1) as bus:
            bus.write_byte(0x70, 0x00)
    except Exception:
        pass


if __name__ == "__main__":
    main()

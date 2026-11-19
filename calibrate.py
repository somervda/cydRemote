
"""
calibrate.py

Read raw touchscreen coordinates.
Run manually from Thonny.
"""

import time
from cyd_hardware import CYDDisplay, CYDTouch

display = CYDDisplay()
touch = CYDTouch()

WHITE = 0xFFFF
BLACK = 0x0000
RED = 0xF800

display.fill(BLACK)


def crosshair(x, y):
    display.fill(BLACK)
    display.fill_rect(x - 8, y, 16, 1, RED)
    display.fill_rect(x, y - 8, 1, 16, RED)


points = [
    (25, 25),
    (295, 25),
    (25, 215),
    (295, 215)
]

for x, y in points:
    crosshair(x, y)

    print("Touch crosshair at:", x, y)

    # Wait for any previous touch to be released.
    while touch.read_raw() is not None:
        time.sleep_ms(30)

    # Wait for a new touch.
    raw = None
    while raw is None:
        raw = touch.read_raw()
        time.sleep_ms(30)

    print("Raw:", raw)

    # Wait for release before next point.
    while touch.read_raw() is not None:
        time.sleep_ms(30)

    time.sleep_ms(200)

display.fill(BLACK)
display.text("Calibration done", 60, 100, WHITE)

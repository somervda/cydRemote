
from cyd_hardware import CYDDisplay, CYDTouch
import time

display = CYDDisplay()
touch = CYDTouch()

# Test display colors
display.fill(0xF800)   # Red
time.sleep(1)

display.fill(0x07E0)   # Green
time.sleep(1)

display.fill(0x001F)   # Blue
time.sleep(1)

display.fill(0x0000)   # Black

display.text("CYD READY", 100, 100, 0xFFFF)

# Test raw touchscreen coordinates
while True:
    point = touch.read_raw()

    if point is not None:
        print("Raw touch:", point)

    time.sleep_ms(100)

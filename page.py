
"""
main.py

CYD touchscreen application.
Loads JSON buttons and handles button presses.
"""

import time

from cyd_hardware import CYDDisplay, CYDTouch
from cyd_buttons import CYDButtons


def handle_button(callback_id):
    """Process callback IDs from touchscreen."""

    print("Button pressed:", callback_id)

    if callback_id == "action_toggle_power":
        print("Toggle power")

    elif callback_id == "action_volume_up":
        print("Increase volume")

    elif callback_id == "action_volume_down":
        print("Decrease volume")

    else:
        print("Unknown callback:", callback_id)


def main():
    print("Initializing CYD display...")

    display = CYDDisplay()

    print("Initializing touchscreen...")

    touch = CYDTouch(
        width=display.width,
        height=display.height,

        # Replace after calibration.
        x_min=200,
        x_max=3900,
        y_min=200,
        y_max=3900,

        swap_xy=False,
        invert_x=False,
        invert_y=False
    )

    print("Loading buttons...")

    buttons = CYDButtons(
        display=display,
        touch=touch,
        filename="buttons.json",
        callback=handle_button
    )

    print("Screen:", buttons.screen_id)
    print("Buttons:", buttons.list_buttons())
    print("Ready")

    while True:
        buttons.update()
        time.sleep_ms(20)


if __name__ == "__main__":
    main()

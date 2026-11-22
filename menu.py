
import time
from cyd_buttons import CYDButtons
from pico_string import PicoWStringClient

remote = PicoWStringClient()
remote.connect()



def handle_button(callback_id):

    print("Button pressed:", callback_id)

    if callback_id == "action_toggle_power":
        print("Toggle power")

    elif callback_id == "action_volume_up":
        print("Increase volume")

    elif callback_id == "action_volume_down":
        print("Decrease volume")
    elif callback_id.startswith("IR "):
        irCommand=callback_id[3:]
        print("Sending ",irCommand)
        remote.send(irCommand)
    else:
        print("Unknown action:", callback_id)


# Initialize screen and register callback
cyd = CYDButtons(
    "channels.json",
    callback=handle_button
)

print("Screen:", cyd.get_screen_id())
print("Buttons:", cyd.list_buttons())

while True:

    cyd.poll()

    time.sleep_ms(20)

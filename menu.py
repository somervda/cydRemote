
import time
from cyd import CYD
from pico_string import PicoWStringClient





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


# Initialize the display and register the callback.
cyd = CYD(callback=handle_button)
cyd.write_line("Starting bluetooth. This may take a few seconds so take it easy. Maybe get a coffee ...",0,10)

remote = PicoWStringClient()
try:
    remote.connect()
except Exception as e:
    cyd.write_line(f"Connection Error",0,10)
    raise

# Load and display buttons immediately before polling starts.
cyd.write_line("Loading buttons...",0,10)
cyd.change_screen("channels.json")

print("Screen:", cyd.get_screen_id())
print("Buttons:", cyd.list_buttons())

while True:

    cyd.poll()

    time.sleep_ms(20)

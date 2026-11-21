

## CYD MicroPython BLE client

`lib/pico_string.py` provides `PicoWStringClient` for a CYD running an ESP32
MicroPython build with BLE central support. Copy the module to the CYD's `lib`
directory, then connect and send commands to the Pico W:

```python
from pico_string import PicoWStringClient

remote = PicoWStringClient()
remote.connect()
remote.send("T Menu")
remote.send_key("D", "Play")
remote.send_sequence(("T Up", "T Ok"))
remote.disconnect()
```

The client looks for the advertised name `PicoW-String` and discovers the BLE
service and characteristic UUIDs used by `bt_ir.py`. Commands use the server's
existing syntax: `T`, `D`, `Y`, or `R` followed by a key name; `U P` is a pause.
The server accepts up to 100 bytes per write. The client attempts MTU
negotiation for longer writes and otherwise enforces the default 20-byte BLE
payload limit. A BLE write acknowledgment does not confirm that an IR signal
was transmitted.
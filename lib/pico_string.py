"""MicroPython BLE client for the irRemote ``PicoW-String`` service.

Example::

    from pico_string import PicoWStringClient

    remote = PicoWStringClient()
    remote.connect()
    remote.send("T Menu")
    remote.send_sequence(("T Up", "T Ok"))
    remote.disconnect()

The CYD must run an ESP32 MicroPython build with the ``bluetooth`` module and
BLE central support. A successful write confirms delivery to the BLE
characteristic, not that the Pico W completed the IR transmission.
"""

import time


SERVICE_UUID = "4f7b2c81-9d5a-4e2b-b8f3-6c7d1e0a2930"
CHAR_UUID = "4f7b2c81-9d5a-4e2b-b8f3-6c7d1e0a2931"
DEFAULT_NAME = "PicoW-String"
SERVER_MAX_COMMAND_BYTES = 100
DEFAULT_ATT_MTU = 23


class BLETimeoutError(Exception):
    """Raised when a BLE operation does not complete before its deadline."""


_IRQ_SCAN_RESULT = 5
_IRQ_SCAN_DONE = 6
_IRQ_PERIPHERAL_CONNECT = 7
_IRQ_PERIPHERAL_DISCONNECT = 8
_IRQ_GATTC_SERVICE_RESULT = 9
_IRQ_GATTC_SERVICE_DONE = 10
_IRQ_GATTC_CHARACTERISTIC_RESULT = 11
_IRQ_GATTC_CHARACTERISTIC_DONE = 12
_IRQ_GATTC_WRITE_DONE = 17
_IRQ_MTU_EXCHANGED = 21


class PicoWStringClient:
    """Connect to a Pico W advertising ``PicoW-String`` and send IR commands."""

    def __init__(self, name=DEFAULT_NAME, timeout_ms=10000):
        try:
            import bluetooth
        except ImportError:
            raise ImportError(
                "This client requires a MicroPython build with bluetooth support"
            )

        self.name = name
        self.timeout_ms = timeout_ms
        self._bluetooth = bluetooth
        self._service_uuid = bluetooth.UUID(SERVICE_UUID)
        self._char_uuid = bluetooth.UUID(CHAR_UUID)
        self._ble = bluetooth.BLE()

        # Ask for enough MTU to carry the server's full command buffer. If this
        # option is unavailable, the client falls back to the default MTU.
        try:
            self._ble.config(mtu=SERVER_MAX_COMMAND_BYTES + 3)
        except (AttributeError, OSError, TypeError, ValueError):
            pass

        self._ble.active(True)
        self._ble.irq(self._irq)

        self._peer = None
        self._scan_done = False
        self._conn_handle = None
        self._connected = False
        self._disconnected = False
        self._connect_done = False
        self._connect_status = 0
        self._service = None
        self._service_done = False
        self._service_status = 0
        self._characteristic = None
        self._characteristic_done = False
        self._characteristic_status = 0
        self._write_done = False
        self._write_status = 0
        self._mtu_done = False
        self._mtu = DEFAULT_ATT_MTU
        self.max_payload = DEFAULT_ATT_MTU - 3

    def _irq(self, event, data):
        if event == _IRQ_SCAN_RESULT:
            addr_type, addr, _adv_type, _rssi, adv_data = data
            if self._peer is None and self._advertised_name(adv_data) == self.name:
                self._peer = (addr_type, bytes(addr))
        elif event == _IRQ_SCAN_DONE:
            self._scan_done = True
        elif event == _IRQ_PERIPHERAL_CONNECT:
            conn_handle, _addr_type, _addr = data
            self._conn_handle = conn_handle
            self._connected = True
            self._disconnected = False
            self._connect_done = True
            self._connect_status = 0
        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            conn_handle, _addr_type, _addr = data
            if conn_handle == self._conn_handle:
                self._connected = False
                self._disconnected = True
                self._conn_handle = None
        elif event == _IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start_handle, end_handle, uuid = data
            if conn_handle == self._conn_handle and uuid == self._service_uuid:
                self._service = (start_handle, end_handle)
        elif event == _IRQ_GATTC_SERVICE_DONE:
            conn_handle, status = data
            if conn_handle == self._conn_handle:
                self._service_done = True
                self._service_status = status
        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            conn_handle, _def_handle, value_handle, _properties, uuid = data
            if conn_handle == self._conn_handle and uuid == self._char_uuid:
                self._characteristic = value_handle
        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            conn_handle, status = data
            if conn_handle == self._conn_handle:
                self._characteristic_done = True
                self._characteristic_status = status
        elif event == _IRQ_GATTC_WRITE_DONE:
            conn_handle, value_handle, status = data
            if (
                conn_handle == self._conn_handle
                and value_handle == self._characteristic
            ):
                self._write_done = True
                self._write_status = status
        elif event == _IRQ_MTU_EXCHANGED:
            conn_handle, mtu = data
            if conn_handle == self._conn_handle:
                self._mtu = mtu
                self.max_payload = min(
                    SERVER_MAX_COMMAND_BYTES, max(0, mtu - 3)
                )
                self._mtu_done = True

    @staticmethod
    def _advertised_name(adv_data):
        """Return a complete or shortened local name from advertising data."""
        pos = 0
        while pos < len(adv_data):
            length = adv_data[pos]
            if length == 0:
                break
            end = pos + 1 + length
            if end > len(adv_data):
                break
            ad_type = adv_data[pos + 1]
            if ad_type in (0x08, 0x09):
                try:
                    return bytes(adv_data[pos + 2:end]).decode("utf-8")
                except UnicodeError:
                    return None
            pos = end
        return None

    def _wait(self, attribute, timeout_ms, operation):
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while not getattr(self, attribute):
            if self._disconnected:
                raise OSError("BLE connection was lost during " + operation)
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                raise BLETimeoutError("Timed out during " + operation)
            time.sleep_ms(10)

    def connect(self, timeout_ms=None):
        """Scan for the named Pico W, connect, and discover its writable char."""
        if self._connected and self._characteristic is not None:
            return self

        timeout_ms = self.timeout_ms if timeout_ms is None else timeout_ms
        self._peer = None
        self._scan_done = False
        self._disconnected = False

        try:
            # The server advertises its name, but not its service UUID.
            self._ble.gap_scan(0, 30000, 30000, True)
            try:
                self._wait("_peer", timeout_ms, "device scan")
            finally:
                self._ble.gap_scan(None)

            self._connect_done = False
            self._connect_status = 0
            addr_type, addr = self._peer
            self._ble.gap_connect(addr_type, addr)
            self._wait("_connect_done", timeout_ms, "connection")
            if self._connect_status:
                raise OSError("BLE connection failed: {}".format(self._connect_status))

            self._discover_characteristic(timeout_ms)
            self._exchange_mtu(timeout_ms)
            return self
        except Exception:
            if self._connected:
                self.disconnect()
            raise

    def _discover_characteristic(self, timeout_ms):
        self._service = None
        self._service_done = False
        self._service_status = 0
        self._ble.gattc_discover_services(self._conn_handle)
        self._wait("_service_done", timeout_ms, "service discovery")
        if self._service_status:
            raise OSError(
                "BLE service discovery failed: {}".format(self._service_status)
            )
        if self._service is None:
            raise OSError("PicoW-String BLE service was not found")

        self._characteristic = None
        self._characteristic_done = False
        self._characteristic_status = 0
        start_handle, end_handle = self._service
        self._ble.gattc_discover_characteristics(
            self._conn_handle, start_handle, end_handle
        )
        self._wait("_characteristic_done", timeout_ms, "characteristic discovery")
        if self._characteristic_status:
            raise OSError(
                "BLE characteristic discovery failed: {}".format(
                    self._characteristic_status
                )
            )
        if self._characteristic is None:
            raise OSError("PicoW-String writable characteristic was not found")

    def _exchange_mtu(self, timeout_ms):
        """Negotiate a larger write size when supported; otherwise use 20 bytes."""
        exchange = getattr(self._ble, "gattc_exchange_mtu", None)
        if exchange is None:
            return
        self._mtu_done = False
        try:
            exchange(self._conn_handle)
            self._wait("_mtu_done", min(timeout_ms, 2000), "MTU negotiation")
        except (OSError, BLETimeoutError, TypeError):
            self._mtu = DEFAULT_ATT_MTU
            self.max_payload = DEFAULT_ATT_MTU - 3

    @staticmethod
    def _validate_command(command):
        if not isinstance(command, str):
            raise TypeError("command must be a string")
        if not command:
            raise ValueError("command must not be empty")

        for item in command.split(","):
            parts = item.strip().split()
            if len(parts) != 2:
                raise ValueError(
                    "each command must be '<operation> <key>' or 'U P'"
                )
            operation = parts[0].upper()
            parameter = parts[1]
            if operation == "U":
                if parameter.upper() != "P":
                    raise ValueError("pause command must be 'U P'")
            elif operation not in ("T", "D", "Y", "R"):
                raise ValueError("unsupported operation: " + parts[0])

        try:
            encoded = command.encode("utf-8")
        except UnicodeError:
            raise ValueError("command must be valid UTF-8")
        if len(encoded) > SERVER_MAX_COMMAND_BYTES:
            raise ValueError("command exceeds the server's 100-byte limit")
        return encoded

    def send(self, command, timeout_ms=None):
        """Write one command or a comma-separated command sequence.

        The method waits for the BLE write acknowledgment. It does not indicate
        whether the remote accepted the key or transmitted its IR signal.
        """
        if not self._connected or self._characteristic is None:
            raise OSError("not connected; call connect() first")

        encoded = self._validate_command(command)
        if len(encoded) > self.max_payload:
            raise ValueError(
                "command is {} bytes but the negotiated BLE write limit is {}; "
                "use a shorter command or a firmware with MTU negotiation".format(
                    len(encoded), self.max_payload
                )
            )

        self._write_done = False
        self._write_status = 0
        self._ble.gattc_write(
            self._conn_handle, self._characteristic, encoded, 1
        )
        self._wait(
            "_write_done",
            self.timeout_ms if timeout_ms is None else timeout_ms,
            "characteristic write",
        )
        if self._write_status:
            raise OSError("BLE write failed: {}".format(self._write_status))
        return True

    def send_key(self, operation, key, timeout_ms=None):
        """Send one stored key, for example ``send_key("T", "Menu")``."""
        return self.send("{} {}".format(operation, key), timeout_ms)

    def send_sequence(self, commands, timeout_ms=None):
        """Send commands in server order, e.g. ``("T Up", "T Ok")``."""
        return self.send(",".join(commands), timeout_ms)

    def disconnect(self, timeout_ms=2000):
        """Disconnect from the Pico W, keeping the local BLE interface active."""
        if not self._connected or self._conn_handle is None:
            self._connected = False
            self._conn_handle = None
            self._characteristic = None
            return

        self._disconnected = False
        conn_handle = self._conn_handle
        try:
            self._ble.gap_disconnect(conn_handle)
            self._wait("_disconnected", timeout_ms, "disconnect")
        except (OSError, BLETimeoutError):
            # Clear local state even if the peer disappeared without an IRQ.
            pass
        self._connected = False
        self._conn_handle = None
        self._characteristic = None

    close = disconnect

    def deinit(self):
        """Disconnect and disable BLE."""
        self.disconnect()
        self._ble.gap_scan(None)
        self._ble.irq(None)
        self._ble.active(False)

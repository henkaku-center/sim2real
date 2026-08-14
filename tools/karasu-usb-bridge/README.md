# Karasu USB CDC RFC2217 bridge

Experimental Android/Termux bridge for using Karasu as a USB-OTG field adapter between a workstation and a Sesame ESP32-S2/S3-class USB CDC device.

## Status

Verified:

- Karasu can open Sesame via `termux-usb` raw USB file descriptors.
- The bridge exposes an RFC2217 TCP serial endpoint.
- pySerial/esptool on calcifer can connect to `rfc2217://karasu:7779`.
- Normal firmware Serial CLI traffic works through the bridge.
- esptool DTR/RTS/baud operations reach the USB CDC device and can cause re-enumeration.

Not yet solved:

- Native USB reset re-enumerates the Android USB device, invalidating the old `termux-usb` fd.
- Android permission is per device instance; if the OS prompts after re-enumeration, the user must grant access again.
- Current Sesame firmware/board state does not enter ROM bootloader from RFC2217 DTR/RTS alone. Manual BOOT/GPIO0 + RESET may be required unless firmware-assisted bootloader entry is added.

## Install on Karasu

```sh
pkg install python termux-api
# install the separate Termux:API Android app too
scp cdc_rfc2217_bridge.py run_py_rfc2217_bridge.sh karasu:~
chmod +x ~/cdc_rfc2217_bridge.py ~/run_py_rfc2217_bridge.sh
```

## Run on Karasu

List USB devices:

```sh
termux-usb -l
```

Grant access and start bridge:

```sh
termux-usb -r /dev/bus/usb/001/005
termux-usb -r -e ~/run_py_rfc2217_bridge.sh /dev/bus/usb/001/005
```

The bridge listens on TCP port `7779` by default.

## Use from calcifer

Normal serial smoke test:

```python
import serial, time
s = serial.serial_for_url('rfc2217://100.77.51.88:7779?ign_set_control', baudrate=115200, timeout=2)
s.write(b'st\n')
time.sleep(.5)
print(s.read(4096))
s.close()
```

esptool probe, once the board is in ROM bootloader mode:

```sh
esptool --before no-reset --after no-reset \
  --port 'rfc2217://100.77.51.88:7779?ign_set_control' \
  chip-id
```

## Notes

For ESP32-S2/S3 native USB CDC, DTR/RTS are virtual line states, not physical EN/GPIO0 pins. Reliable bootloader entry still requires one of:

- physical GPIO0/BOOT held low while resetting,
- board hardware that maps USB serial control lines to EN/GPIO0,
- firmware-assisted 1200-bps touch or explicit reboot-to-bootloader command,
- OTA/web firmware update support.

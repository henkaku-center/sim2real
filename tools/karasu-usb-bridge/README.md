# Karasu USB CDC bridges

**S3 update (2026-09-22):** the course's new S3 SuperMini uses serial endpoints `0x01`/`0x81`,
not the old S2 bridge's `0x03`/`0x84`. The tested S3 snapshot with 64-byte bulk transfers is at
`firmware-tests/sesame-s3-bringup/sesame-s3-cdc-bridge.c` from the repo root. See
[`reference/SESAME-S3-BUILD-STATE.md`](../../reference/SESAME-S3-BUILD-STATE.md) for results and limitations.
Direct Artemis USB is the current working programming route. The commands/results below describe
the earlier S2 workflow; do not reuse device paths, endpoints or chip targets without identification.

Experimental Android/Termux bridges for using Karasu as a USB-OTG field adapter between a workstation and a Sesame ESP32-S2/S3-class USB CDC device.

Two bridge modes are useful:

- `cdc_rfc2217_bridge.py` on TCP `7779`: pySerial RFC2217 bridge with baud/DTR/RTS forwarding. Useful for normal serial and reset experiments.
- `cdc_tcp_bridge.c` on TCP `7777`: raw byte bridge. Useful once the board is already in ROM bootloader mode; avoids RFC2217/telnet escaping during large esptool transfers.

## Status

Verified:

- Karasu can open Sesame via `termux-usb` raw USB file descriptors.
- pySerial/esptool on calcifer can connect through Karasu over Tailscale.
- Normal firmware Serial CLI traffic works through the RFC2217 bridge.
- esptool DTR/RTS/baud operations reach the USB CDC device and can cause re-enumeration.
- Manual BOOT/GPIO0 + RESET puts Sesame into ROM bootloader, enumerating as `303a:0002`.
- `esptool --no-stub` can read chip/flash information through the raw socket bridge.
- First write smoke test succeeded through Karasu:

```sh
esptool --no-stub --before no-reset --after no-reset \
  --port 'socket://100.77.51.88:7777' \
  write-flash 0x3F0000 sector-ff.bin
```

Result: 4096 bytes erased/written at `0x003f0000`, verification hash passed.

Not yet solved:

- Native USB reset re-enumerates the Android USB device, invalidating the old `termux-usb` fd.
- Android permission is per device instance; if the OS prompts after re-enumeration, the user must grant access again.
- Current Sesame firmware/board state does not enter ROM bootloader from RFC2217 DTR/RTS alone. Manual BOOT/GPIO0 + RESET is currently required unless firmware-assisted bootloader entry is added.
- RFC2217 stub upload improved with 64-byte USB write chunks but is still less reliable than raw socket mode for binary flashing.

## Install on Karasu

```sh
pkg install python termux-api clang
# install and open the separate Termux:API Android app too
scp cdc_rfc2217_bridge.py run_py_rfc2217_bridge.sh cdc_tcp_bridge.c run_cdc_bridge.sh karasu:~
ssh karasu 'cc ~/cdc_tcp_bridge.c -o ~/cdc_tcp_bridge && chmod +x ~/cdc_tcp_bridge ~/cdc_rfc2217_bridge.py ~/run_py_rfc2217_bridge.sh ~/run_cdc_bridge.sh'
```

## Manual bootloader workflow

1. Put Sesame into bootloader mode: hold **BOOT**, tap **RESET**, release **BOOT**.
2. On Karasu, list the new USB device:

```sh
termux-usb -l
```

3. Grant access:

```sh
termux-usb -r /dev/bus/usb/001/006
```

4. Start the raw bridge:

```sh
termux-usb -r -e ~/run_cdc_bridge.sh /dev/bus/usb/001/006
```

The raw bridge listens on TCP port `7777` by default.

5. From calcifer, probe:

```sh
esptool --no-stub --before no-reset --after no-reset \
  --port 'socket://100.77.51.88:7777' \
  chip-id
```

6. Flash with `--no-stub` and `--before no-reset` while the board remains in bootloader mode.

## RFC2217 normal serial smoke test

Start RFC2217 bridge on Karasu:

```sh
termux-usb -r -e ~/run_py_rfc2217_bridge.sh /dev/bus/usb/001/005
```

Normal serial smoke test from calcifer:

```python
import serial, time
s = serial.serial_for_url('rfc2217://100.77.51.88:7779?ign_set_control', baudrate=115200, timeout=2)
s.write(b'st\n')
time.sleep(.5)
print(s.read(4096))
s.close()
```

## Notes

For ESP32-S2/S3 native USB CDC, DTR/RTS are virtual line states, not physical EN/GPIO0 pins. Reliable bootloader entry still requires one of:

- physical GPIO0/BOOT held low while resetting,
- board hardware that maps USB serial control lines to EN/GPIO0,
- firmware-assisted 1200-bps touch or explicit reboot-to-bootloader command,
- OTA/web firmware update support.

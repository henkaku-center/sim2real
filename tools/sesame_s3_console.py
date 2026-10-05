#!/usr/bin/env python3
"""Interactive USB console. No reconnect, no auto-arm, explicit heartbeat switch."""
import argparse
import queue
import sys
import threading
import time

import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    args = parser.parse_args()
    commands = queue.Queue()

    def read_input():
        for line in sys.stdin:
            commands.put(line.strip())
        commands.put(":quit")

    device = serial.Serial(port=None, baudrate=115200, timeout=0, write_timeout=.2)
    device.dtr = False; device.rts = False; device.port = args.port
    device.open(); device.dtr = True
    print("Opening USB may reset the board. No automatic actuation.")
    print(":live enables 100ms heartbeats; :pause stops them; :quit sends off.")
    print("Start with help / show. Use only with the documented power isolation.")
    threading.Thread(target=read_input, daemon=True).start()
    live = False; last = 0; buffer = b""
    try:
        while True:
            if not commands.empty():
                command = commands.get_nowait()
                if command == ":quit": break
                if command == ":live": live = True; print("Heartbeat ON (does not arm)")
                elif command == ":pause": live = False; print("Heartbeat OFF; expect watchdog >500ms")
                elif command:
                    if command == "off": live = False
                    if len(command.encode()) >= 160: print("Rejected: command exceeds firmware line length")
                    else: device.write((command + "\n").encode())
            now = time.monotonic()
            if live and now - last >= .1:
                device.write(b"heartbeat\n"); last = now
            buffer += device.read(4096)
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                print(line.decode(errors="replace").rstrip("\r"), flush=True)
            if len(buffer) > 8192: buffer = b""  # bound garbage from a wrong baud/firmware
            time.sleep(.005)
    except (KeyboardInterrupt, serial.SerialException) as exc:
        print(f"Console closed: {exc}; no automatic reconnect")
    finally:
        try: device.write(b"off\n")
        except serial.SerialException: pass
        device.close()


if __name__ == "__main__":
    main()

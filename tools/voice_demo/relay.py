"""Pi relay CLI. Never reconnect or resume a plan after a serial failure."""
import argparse
import os
import signal

from .client import Controller, request_plan, visible
from .inputs import PushToTalk, Recorder, gui_inputs, linux_inputs
from .plan import Catalog
from .playback import Player, SerialLink


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=os.environ.get("VOICE_SERIAL_PORT"), required=not os.environ.get("VOICE_SERIAL_PORT"))
    parser.add_argument("--server", default=os.environ.get("VOICE_SERVER_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--text", help="one-shot development text prompt")
    parser.add_argument("--local", help="one-shot offline stock motion")
    parser.add_argument("--input", choices=("terminal", "gui", "evdev"), default=os.environ.get("VOICE_INPUT", "terminal"))
    parser.add_argument("--input-device", action="append", default=None, help="Linux event device; repeat for button plus keyboard")
    parser.add_argument("--ptt-key", default=os.environ.get("VOICE_PTT_KEY", "space"), help="Tk keysym; default space")
    parser.add_argument("--ptt-code", type=int, default=int(os.environ.get("VOICE_PTT_CODE", "57")), help="Linux evdev key code; default 57 = space")
    parser.add_argument("--audio-device", default=os.environ.get("VOICE_AUDIO_DEVICE"))
    parser.add_argument("--gpio-chip", default=os.environ.get("VOICE_GPIO_CHIP", "/dev/gpiochip0"))
    parser.add_argument("--gpio-line", type=int, default=os.environ.get("VOICE_GPIO_LINE"))
    args = parser.parse_args()
    if args.input_device is None:
        args.input_device = list(filter(None, os.environ.get("VOICE_INPUT_DEVICE", "").split(",")))
    log = lambda text: print(text, flush=True)
    catalog = Catalog()
    token = os.environ.get("VOICE_DEVICE_TOKEN", "")
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    with SerialLink(args.port, log=log) as link:
        link.off()
        player = Player(link, catalog, log=log)
        if args.local:
            player.play(catalog.plan([{"type": "motion", "name": args.local}]))
            return
        if args.text:
            result = request_plan(args.server, token, text=args.text)
            log("HEARD " + visible(result["transcript"]))
            for note in result["notes"]:
                log("NOTE " + visible(note))
            player.play(result["plan"])
            return
        controller = Controller(player, args.server, token, log=log)
        ptt = PushToTalk(controller, Recorder(args.audio_device), log=log)
        try:
            log("READY: 1 bow | 2 wave | 3 rest | Escape outputs OFF")
            if args.input == "gui":
                gui_inputs(ptt, args.ptt_key)
            elif args.input == "evdev":
                linux_inputs(ptt, args.input_device, args.ptt_code, args.gpio_chip, args.gpio_line)
            else:
                log("Development terminal: type a prompt + Enter; 1/2/3 local, off, quit. For true hold/release use gui or evdev.")
                while True:
                    text = input("> ").strip()
                    if text == "quit":
                        break
                    if text in ("1", "2", "3", "off"):
                        ptt.key("Escape" if text == "off" else text)
                    elif text:
                        controller.prompt(text=text)
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            ptt.abort()
            controller.close()


if __name__ == "__main__":
    main()

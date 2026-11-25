"""Bounded audio recording and press/release sources; no global keyboard hooks."""
from contextlib import ExitStack
from datetime import timedelta
import io
import os
import selectors
import signal
import struct
import subprocess
import sys
import threading
import wave

from .providers import MAX_AUDIO_SECONDS, check_wav

OFFLINE_KEYS = {"1": "bow", "2": "wave", "3": "rest"}
INPUT_EVENT = struct.Struct("llHHI")  # Linux input_event, native timeval (arm64/x86_64)


class Recorder:
    def __init__(self, device=None):
        if sys.platform == "darwin":
            self.command = ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "avfoundation", "-i",
                            device or ":0", "-t", str(MAX_AUDIO_SECONDS), "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"]
        else:
            self.command = ["arecord", "-q", "-D", device or "default", "-t", "raw", "-f", "S16_LE",
                            "-r", "16000", "-c", "1", "-d", str(MAX_AUDIO_SECONDS)]
        self.process = None
        self.data = bytearray()
        self.reader = None

    def start(self):
        if self.process:
            return
        self.data = bytearray()
        self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        process = self.process

        def read():
            maximum = 16000 * 2 * MAX_AUDIO_SECONDS
            while len(self.data) < maximum:
                chunk = process.stdout.read(min(4096, maximum - len(self.data)))
                if not chunk:
                    break
                self.data.extend(chunk)
        self.reader = threading.Thread(target=read, name="audio-capture", daemon=True)
        self.reader.start()

    def finish(self, *, discard=False):
        if not self.process:
            return None
        process, self.process = self.process, None
        try:
            failed = process.poll() not in (None, 0)
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            self.reader.join(timeout=1)
            if self.reader.is_alive():
                raise RuntimeError("audio reader failed to stop")
            if discard:
                return None
            if failed:
                raise RuntimeError("microphone capture exited with an error; check device and permissions")
            if len(self.data) < 3200:
                raise RuntimeError("no usable microphone audio (minimum 100ms); check device and permissions")
            output = io.BytesIO()
            with wave.open(output, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(self.data[:len(self.data) // 2 * 2])
            audio = output.getvalue()
            check_wav(audio)
            return audio
        finally:
            process.stdout.close()
            self.data = bytearray()


class PushToTalk:
    def __init__(self, controller, recorder, *, log=print):
        self.controller, self.recorder, self.log = controller, recorder, log
        self.down = False

    def edge(self, pressed):
        if pressed == self.down:
            return  # USB key repeat never starts multiple recordings
        self.down = pressed
        try:
            if pressed:
                with self.controller.lock:
                    if self.controller.playing or self.controller.network_busy or not self.controller.pending.empty():
                        self.log("BUSY: use Escape to stop; wait for idle before speaking")
                        return
                self.recorder.start()
                self.log("RECORDING (maximum 30 seconds); release to send")
            else:
                audio = self.recorder.finish()
                if audio:
                    self.controller.prompt(audio=audio)
        except Exception as exc:
            self.recorder.finish(discard=True)
            self.log("RECORDING FAILED: " + str(exc))

    def abort(self):
        self.recorder.finish(discard=True)
        self.down = False

    def key(self, key):
        if key in OFFLINE_KEYS:
            self.abort()
            self.controller.local(OFFLINE_KEYS[key])
        elif key == "Escape":
            self.abort()
            self.controller.stop()


def linux_inputs(ptt, input_device, key_code=57, gpio_chip=None, gpio_line=None, finish=None):
    finish = finish or threading.Event()
    if key_code in (1, 2, 3, 4):
        raise ValueError("PTT key conflicts with Escape or offline keys 1/2/3")
    if not input_device and gpio_line is None:
        raise ValueError("evdev input needs --input-device and/or --gpio-line")
    with ExitStack() as stack:
        selector = stack.enter_context(selectors.DefaultSelector())
        devices = [input_device] if isinstance(input_device, str) else (input_device or [])
        for device in devices:
            keyboard = stack.enter_context(open(device, "rb", buffering=0))
            selector.register(keyboard, selectors.EVENT_READ, "keyboard")
        if gpio_line is not None:
            import gpiod
            from gpiod.line import Bias, Edge
            gpio = stack.enter_context(gpiod.request_lines(
                gpio_chip or "/dev/gpiochip0", consumer="sesame-voice-ptt",
                config={gpio_line: gpiod.LineSettings(edge_detection=Edge.BOTH, bias=Bias.PULL_UP,
                                                     debounce_period=timedelta(milliseconds=20))}))
            selector.register(gpio.fd, selectors.EVENT_READ, "gpio")
        while not finish.is_set():
            for event, _ in selector.select(timeout=.1):
                if event.data == "gpio":
                    for edge in gpio.read_edge_events():
                        ptt.edge(edge.event_type == edge.Type.FALLING_EDGE)
                    continue
                data = os.read(event.fileobj.fileno(), INPUT_EVENT.size * 16)
                if not data or len(data) % INPUT_EVENT.size:
                    raise OSError("keyboard-style button disconnected or input event truncated")
                for _, _, kind, code, value in INPUT_EVENT.iter_unpack(data):
                    if kind == 0 and code == 3:  # SYN_DROPPED: cannot trust press/release state
                        ptt.abort()
                        ptt.controller.stop()
                        raise OSError("keyboard input events lost; restart input reader")
                    if kind != 1 or value == 2:
                        continue
                    if code == key_code:
                        ptt.edge(value == 1)
                    elif value == 1:
                        ptt.key({1: "Escape", 2: "1", 3: "2", 4: "3"}.get(code, ""))


def gui_inputs(ptt, key="space"):
    import tkinter as tk
    if key in (*OFFLINE_KEYS, "Escape"):
        raise ValueError("PTT key conflicts with local controls")
    root = tk.Tk()
    root.title("Sesame voice demo — local relay")
    tk.Label(root, text=f"Hold {key} to record; release to send\n1 Bow · 2 Wave · 3 Rest · Escape Off\nKeep this window focused. See console for transcript and playback.",
             padx=25, pady=25).pack()
    release = [None]

    def down(event):
        if event.keysym == key:
            if release[0]:
                root.after_cancel(release[0])
                release[0] = None
            ptt.edge(True)
        else:
            ptt.key(event.keysym)

    def up(event):
        if event.keysym == key:
            release[0] = root.after(30, lambda: ptt.edge(False))

    root.bind("<KeyPress>", down)
    root.bind("<KeyRelease>", up)
    root.bind("<FocusOut>", lambda _: ptt.abort())
    for k, name in OFFLINE_KEYS.items():
        tk.Button(root, text=f"{k} {name.title()}", command=lambda k=k: ptt.key(k), height=2).pack(fill="x")
    tk.Button(root, text="Outputs OFF", command=lambda: ptt.key("Escape"), height=2).pack(fill="x")
    try:
        root.mainloop()
    finally:
        ptt.abort()
        try:
            root.destroy()
        except tk.TclError:
            pass

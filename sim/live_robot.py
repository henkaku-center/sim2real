"""A MuJoCo stand-in for the Sesame S3's HTTP command interface.

`tools/sesame_mind.py --host sim` drives this instead of the robot, so motion
work (the voice body, designed specs, library motions) can be developed and
watched without hardware. It answers the commands the mind sends:

    heartbeat | arm run | off | stop | motion NAME | pose D0 .. D7

`pose` takes firmware degrees in canonical joint order. Targets are clamped to
the manifest soft limits and approached at the firmware's run rate (RUN_RATE,
300 deg/s on the robot's build line), so the simulated servos lag the same way
the real ones are told to. Like the firmware, it requires `arm run` before
motion, goes limp on `off` and freezes in place when no command arrives for
LINK_HOLD_S. A background thread steps physics in real time; a render thread
keeps the newest JPEG of the scene for the mind's /sim.mjpg view.

Not modelled: the real MG90S lag and torque (the MJCF gains are placeholders),
Wi-Fi delay, the staggered servo start, OUTPUTS-OFF after HOLD_MS.

    robot = SimRobot(); robot.start()
    robot.command("arm run"); robot.command("pose 135 45 45 135 0 180 0 180")
"""

from __future__ import annotations

import io
import math
import threading
import time
import urllib.parse

import numpy as np

from sim.manifest import load_manifest
from sim.motions import flatten, load_motions
from sim.sound_motion import physics_model

RUN_RATE_DEG_S = 300.0  # firmware/sesame-s3 RUN_RATE on the robot's build line
LINK_HOLD_S = 0.5  # the firmware freezes and holds when commands stop
STEP_S = 0.01  # physics advanced per real-time tick


class SimRobot:
    base = host = "sim"

    def __init__(self, rate_deg_s: float = RUN_RATE_DEG_S):
        import mujoco

        self.mj = mujoco
        self.m = load_manifest()
        self.motions = load_motions()["motions"]
        self.model = physics_model()
        self.data = mujoco.MjData(self.model)
        self.lock = threading.Lock()
        self.rate = math.radians(rate_deg_s)
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.kp = self.model.actuator_gainprm[:, 0].copy()
        self.lo = np.array([self.m.internal_range(j)[0] for j in self.m.joints])
        self.hi = np.array([self.m.internal_range(j)[1] for j in self.m.joints])
        self.mode, self.motion, self.t, self.last_cmd = "off", None, 0.0, 0.0
        self.ctrl = self.data.qpos[self.qadr].copy()
        self.target = self.ctrl.copy()
        self._limp(True)
        self.advance(0.5)  # settle on the floor
        self.jpeg_bytes, self.frame_no, self.viewers = b"", 0, 0
        self.running = False

    # ------------------------------------------------------------ commands

    def command(self, text: str) -> tuple[bool, str]:
        words = text.split()
        with self.lock:
            self.last_cmd = self.t
            if words == ["heartbeat"]:
                return True, "OK"
            if words == ["arm", "run"]:
                self.mode, self.motion = "run", None
                self.ctrl = self.data.qpos[self.qadr].copy()
                self.target = self.ctrl.copy()
                self._limp(False)
                return True, "OK ARMED RUN (sim)"
            if words == ["off"]:
                self.mode, self.motion = "off", None
                self._limp(True)
                return True, "OK OFF (sim)"
            if words == ["stop"]:
                self.motion, self.target = None, self.ctrl.copy()
                return True, "OK STOP (sim)"
            if words[:1] in (["motion"], ["pose"]) and self.mode != "run":
                return False, "ERR arm run first"
            if len(words) == 2 and words[0] == "motion":
                if words[1] not in self.motions:
                    return False, "ERR unknown motion"
                events = flatten(self.motions[words[1]], self.m.raw["poses"])
                self.motion = (words[1], events, self.t, 0)
                return True, f"OK MOTION {words[1]}"
            if len(words) == 9 and words[0] == "pose":
                try:
                    degs = [float(w) for w in words[1:]]
                except ValueError:
                    return False, "ERR pose numbers"
                self.motion = None
                self.target = np.clip([self.m.to_internal(j, d) for j, d in zip(self.m.joints, degs)],
                                      self.lo, self.hi)
                return True, "OK TARGETS (sim: soft limits applied)"
            return False, f"ERR unknown command (sim): {text}"

    def get(self, path: str) -> tuple[bool, str]:
        if path.startswith("/cmd?c="):
            return self.command(urllib.parse.unquote(path[len("/cmd?c="):]))
        if path == "/status":
            name = self.motion[0] if self.motion else "none"
            return True, (f"mode={'5' if self.mode == 'run' else '0'} outputs={255 if self.mode == 'run' else 0} "
                          f"motion={name} sweep=0 hold=0 up_s={int(self.t)} sim=1")
        return False, "ERR not found (sim)"

    def busy(self) -> bool:
        return self.motion is not None

    # ------------------------------------------------------------ physics

    def _limp(self, limp: bool) -> None:
        """Position servos with no torque (OUTPUTS OFF) or with their gain back."""
        gain = 0.0 if limp else 1.0
        self.model.actuator_gainprm[:, 0] = gain * self.kp
        self.model.actuator_biasprm[:, 1] = -gain * self.kp

    def joints(self) -> np.ndarray:
        """Measured joint angles, internal radians, manifest order."""
        return self.data.qpos[self.qadr].copy()

    def advance(self, seconds: float) -> None:
        """Step physics by `seconds` of robot time (tests call this directly)."""
        dt = self.model.opt.timestep
        for _ in range(round(seconds / dt)):
            with self.lock:
                self._tick(dt)

    def _tick(self, dt: float) -> None:
        if self.motion:
            name, events, start, i = self.motion
            ms = (self.t - start) * 1000
            while i < len(events) and events[i].time_ms <= ms:
                for jn, deg in events[i].targets_deg.items():
                    k = next(n for n, j in enumerate(self.m.joints) if j.name == jn)
                    self.target[k] = np.clip(self.m.to_internal(self.m.joints[k], deg), self.lo[k], self.hi[k])
                i += 1
            self.motion = (name, events, start, i) if i < len(events) else None
            self.last_cmd = self.t  # a playing motion keeps the link alive, as on the robot
        if self.mode == "run" and self.t - self.last_cmd > LINK_HOLD_S:
            self.target = self.ctrl.copy()  # link lost: freeze and hold
        self.ctrl += np.clip(self.target - self.ctrl, -self.rate * dt, self.rate * dt)
        self.data.ctrl[:] = self.ctrl
        self.mj.mj_step(self.model, self.data)
        self.t += dt

    def start(self) -> "SimRobot":
        """Real-time physics and a render thread for jpeg()."""
        if not self.running:
            self.running = True
            threading.Thread(target=self._realtime, daemon=True).start()
            threading.Thread(target=self._render, daemon=True).start()
        return self

    def _realtime(self) -> None:
        next_t = time.monotonic()
        while self.running:
            self.advance(STEP_S)
            next_t += STEP_S
            lag = next_t - time.monotonic()
            if lag > 0:
                time.sleep(lag)
            elif lag < -0.5:  # fell behind (e.g. the laptop slept): do not try to catch up
                next_t = time.monotonic()

    # ------------------------------------------------------------ view

    def render_jpeg(self, renderer, cam, opt) -> bytes:
        from PIL import Image

        with self.lock:
            cam.lookat[:] = self.data.qpos[:3]
            cam.lookat[2] = 0.03
            renderer.update_scene(self.data, cam, opt)
        buf = io.BytesIO()
        Image.fromarray(renderer.render()).save(buf, "JPEG", quality=80)
        return buf.getvalue()

    def _render(self, fps: float = 15.0) -> None:
        """Renderer lives on this thread (GL contexts are per thread)."""
        renderer = self.mj.Renderer(self.model, 360, 480)
        opt = self.mj.MjvOption()
        opt.geomgroup[3] = 1  # collision boxes stand in for the LFS meshes
        cam = self.mj.MjvCamera()
        cam.distance, cam.azimuth, cam.elevation = 0.42, 135, -22
        while self.running:
            if self.viewers:
                self.jpeg_bytes = self.render_jpeg(renderer, cam, opt)
                self.frame_no += 1
            time.sleep(1 / fps)

    def frames(self, timeout: float = 2.0):
        """New JPEG frames as they are rendered, for one viewer (never a stale one)."""
        self.viewers += 1
        try:
            seen = self.frame_no
            while True:
                deadline = time.monotonic() + timeout
                while self.frame_no == seen:
                    if time.monotonic() > deadline:
                        return
                    time.sleep(0.01)
                seen = self.frame_no
                yield self.jpeg_bytes
        finally:
            self.viewers -= 1

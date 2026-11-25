"""A task-owned PTY, backed by the existing firmware's native C++ SafeAction."""
import argparse
import os
from pathlib import Path
import pty
import signal
import subprocess
import tempfile
import tty

from . import ROOT
from .plan import Catalog


class SimulatedRobot:
    def __init__(self, catalog=None, *, fresh=False, narrow=False):
        self.catalog = catalog or Catalog()
        self.directory = tempfile.TemporaryDirectory(prefix="sesame-voice-sim-")
        self.master = self.slave = None
        self.process = None
        try:
            binary = Path(self.directory.name) / "robot-sim"
            subprocess.run(["c++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "firmware/sesame-s3"),
                            str(Path(__file__).with_name("robot_sim.cpp")), "-o", str(binary)], check=True)
            self.master, self.slave = pty.openpty()
            tty.setraw(self.slave)
            self.port = os.ttyname(self.slave)
            command = [str(binary), *self.catalog.faces]
            if fresh:
                command.append("--fresh")
            if narrow:
                command.append("--narrow")
            self.process = subprocess.Popen(command, stdin=self.master, stdout=self.master, close_fds=True)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for fd in (self.master, self.slave):
            if fd is not None:
                os.close(fd)
        self.master = self.slave = None
        self.directory.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh", action="store_true", help="simulate unsaved/unverified factory calibration")
    parser.add_argument("--narrow", action="store_true", help="simulate saved 85..95 degree limits")
    args = parser.parse_args()
    with SimulatedRobot(fresh=args.fresh, narrow=args.narrow) as robot:
        print(robot.port, flush=True)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        try:
            robot.process.wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

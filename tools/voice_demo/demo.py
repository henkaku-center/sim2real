"""One command: fake HTTP server → real serial relay → native firmware PTY."""
import argparse
import secrets
import threading

from .client import request_plan
from .plan import Catalog
from .playback import Player, SerialLink
from .providers import FakeProvider
from .server import Server
from .simulator import SimulatedRobot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="move like a snake")
    args = parser.parse_args()
    catalog = Catalog()
    token = secrets.token_urlsafe(32)
    with Server(("127.0.0.1", 0), token, catalog, FakeProvider(catalog)) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with SimulatedRobot(catalog) as robot, SerialLink(robot.port) as link:
                link.off()
                result = request_plan(f"http://127.0.0.1:{server.server_port}", token, text=args.text)
                print("HEARD", result["transcript"])
                print("NOTE", result["notes"][0])
                Player(link, catalog).play(result["plan"])
                status, _ = link.status()
                assert status["mode"] == "0" and status["outputs"] == "0", status
                print("DEMO verified: firmware reports mode=0 outputs=0")
        finally:
            server.shutdown()
            worker.join(timeout=2)


if __name__ == "__main__":
    main()

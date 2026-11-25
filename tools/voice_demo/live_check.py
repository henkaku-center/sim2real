"""Explicit live text-only Claude → HTTP server → firmware PTY check (uses quota)."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import subprocess
import threading
import time

from .client import request_plan, ServerUnavailable
from .plan import Catalog
from .playback import Player, SerialLink
from .providers import ClaudeProvider
from .server import Server
from .simulator import SimulatedRobot

PROMPTS = ["do a bow", "say hello to the audience", "おじぎして", "みんなに挨拶して",
           "dance", "泳いで", "look cute", "move like a snake",
           "change your face to one eyeball", "blorpt zibble flarn 987"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Synthetic prompt/result JSON; never credentials")
    parser.add_argument("--prompt", action="append", help="Override the ten-prompt matrix")
    args = parser.parse_args()
    catalog = Catalog()

    class MeasuredClaude(ClaudeProvider):
        def request(self, body):
            start = time.monotonic()
            response = super().request(body)
            attempts.append({"seconds": round(time.monotonic() - start, 3),
                             "model": response.get("model"), "stop_reason": response.get("stop_reason"),
                             "usage": response.get("usage")})
            return response

    provider = MeasuredClaude(catalog)
    report = {"date_utc": datetime.now(timezone.utc).isoformat(),
              "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
              "model": provider.plan_model, "results": []}
    # The endpoint/token are intentionally absent from the report.
    token = secrets.token_urlsafe(32)
    with Server(("127.0.0.1", 0), token, catalog, provider) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with SimulatedRobot(catalog) as robot:
                for prompt in args.prompt or PROMPTS:
                    attempts = []
                    row = {"prompt": prompt}
                    started = time.monotonic()
                    stop = False
                    try:
                        result = request_plan(f"http://127.0.0.1:{server.server_port}", token, text=prompt)
                        row.update(result)
                        row["latency_seconds"] = round(time.monotonic() - started, 3)
                        with SerialLink(robot.port, log=lambda _: None) as link:
                            link.off()
                            Player(link, catalog, log=lambda _: None).play(result["plan"])
                            status, rows = link.status()
                            assert status["mode"] == "0" and status["outputs"] == "0" and rows == {}
                        row["simulation"] = "completed; mode=0 outputs=0"
                    except ServerUnavailable as exc:
                        row["latency_seconds"] = round(time.monotonic() - started, 3)
                        row["error"] = str(exc)
                        row["simulation"] = "no plan; no playback"
                        # Refusal is an expected matrix outcome; endpoint errors stop live work.
                        stop = "HTTP 422" not in str(exc)
                    row["attempts"] = attempts
                    report["results"].append(row)
                    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
                    print(json.dumps(row, ensure_ascii=False), flush=True)
                    if stop:
                        break
        finally:
            server.shutdown()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()

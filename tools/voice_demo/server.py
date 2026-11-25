"""Small bounded HTTP service; deploy behind the private Tailscale endpoint."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading

from .plan import Catalog, InvalidPlan
from .providers import MAX_AUDIO_BYTES, ProviderError, check_text, check_wav, provider_from_env


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, address, token, catalog=None, provider=None):
        if not token or len(token) < 16 or not token.isascii():
            raise ValueError("VOICE_DEVICE_TOKEN must contain at least 16 ASCII characters")
        self.token = token
        self.catalog = catalog or Catalog()
        self.provider = provider or provider_from_env(self.catalog)
        self.slot = threading.BoundedSemaphore(2)
        self.connections = threading.BoundedSemaphore(8)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connections.release()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, *_):
        pass  # No audio, transcript, URL, token or provider body in server logs.

    def reply(self, code, value):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        supplied = self.headers.get("Authorization", "").encode()
        return hmac.compare_digest(supplied, ("Bearer " + self.server.token).encode())

    def do_GET(self):
        if not self.authorized():
            return self.reply(401, {"error": "device token required"})
        if self.path == "/health":
            return self.reply(200, {"ok": True, "provider": self.server.provider.name,
                                    "contract": self.server.catalog.contract})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if not self.authorized():
            return self.reply(401, {"error": "device token required"})
        if self.path != "/prompt":
            return self.reply(404, {"error": "not found"})
        if not self.server.slot.acquire(blocking=False):
            return self.reply(503, {"error": "server busy; use local motions"})
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or self.headers.get("Transfer-Encoding"):
                raise InvalidPlan("one Content-Length required; chunked requests unsupported")
            try:
                length = int(lengths[0])
            except ValueError:
                raise InvalidPlan("invalid Content-Length")
            if not 0 < length <= MAX_AUDIO_BYTES:
                return self.reply(413, {"error": "request exceeds 1000000 bytes or is empty"})
            data = self.rfile.read(length)
            if len(data) != length:
                raise InvalidPlan("truncated request")
            content_type = self.headers.get_content_type()
            if content_type == "audio/wav":
                check_wav(data)
                transcript = self.server.provider.transcribe(data)
            elif content_type == "application/json":
                body = json.loads(data)
                if not isinstance(body, dict) or set(body) != {"text"}:
                    raise InvalidPlan("JSON body must contain only text")
                transcript = check_text(body["text"])
            else:
                return self.reply(415, {"error": "use application/json or audio/wav"})
            transcript = check_text(transcript)
            plan, notes = self.server.provider.generate(transcript)
            self.server.catalog.validate(plan)
            self.reply(200, {"transcript": transcript, "plan": plan, "notes": notes})
        except RecursionError:
            self.reply(422, {"error": "JSON is too deeply nested"})
        except (InvalidPlan, ValueError, UnicodeError) as exc:
            self.reply(422, {"error": str(exc)[:1000]})
        except ProviderError as exc:
            self.reply(502, {"error": str(exc)})
        except (TimeoutError, OSError):
            # Client disappeared or stopped uploading; never retain its recording.
            pass
        finally:
            self.server.slot.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with Server((args.host, args.port), os.environ.get("VOICE_DEVICE_TOKEN", "")) as server:
        print(f"Voice server {server.server_address}; provider={server.provider.name}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

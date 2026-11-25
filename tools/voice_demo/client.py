"""Bounded network client and local/offline request arbitration."""
import json
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request

from .playback import Cancelled
from .providers import check_text, check_wav


class ServerUnavailable(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ServerUnavailable("server redirect refused")


def request_plan(url, token, *, text=None, audio=None, timeout=45):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ServerUnavailable("server must be an http(s) URL without credentials")
    if not token:
        raise ServerUnavailable("VOICE_DEVICE_TOKEN is not configured; local keys still work")
    if audio is not None:
        check_wav(audio)
        body, mime = audio, "audio/wav"
    else:
        body, mime = json.dumps({"text": check_text(text)}).encode(), "application/json"
    request = urllib.request.Request(url.rstrip("/") + "/prompt", data=body,
                                     headers={"Content-Type": mime, "Authorization": "Bearer " + token})
    try:
        # Do not send private-Tailscale requests or device tokens via an environment proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            data = response.read(65537)
            if len(data) > 65536:
                raise ServerUnavailable("server plan too large")
            result = json.loads(data)
        if not isinstance(result, dict) or set(result) != {"transcript", "plan", "notes"}:
            raise ServerUnavailable("invalid server response")
        check_text(result["transcript"])
        if not isinstance(result["notes"], list) or len(result["notes"]) > 10 or not all(isinstance(n, str) and len(n) <= 2000 for n in result["notes"]):
            raise ServerUnavailable("invalid server notes")
        return result
    except urllib.error.HTTPError as exc:
        try:
            reason = json.loads(exc.read(4096)).get("error", "request refused")
        except (ValueError, OSError):
            reason = "request refused"
        raise ServerUnavailable(f"server HTTP {exc.code}: {str(reason)[:1000]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ServerUnavailable("server unavailable or invalid response; use local keys 1/2/3") from exc


def visible(text):
    # Transcript is untrusted text: escape terminal controls but preserve Japanese.
    return json.dumps(text, ensure_ascii=False)


class Controller:
    """One network worker, one player. New local intent invalidates late replies.

    Network requests only start while the player is idle and outputs are off.
    A local key cancels pending network intent and works without waiting for it.
    No queue of unattended motions accumulates.
    """
    def __init__(self, player, url, token, *, log=print, requester=request_plan):
        self.player, self.url, self.token = player, url, token
        self.player.link.off()
        self.log, self.requester = log, requester
        self.lock = threading.RLock()
        self.generation = 0
        self.cancel = threading.Event()
        self.closed = False
        self.network_busy = False
        self.playing = False
        self.pending = queue.Queue(maxsize=1)
        self.worker = threading.Thread(target=self._play_loop, name="local-playback", daemon=True)
        self.worker.start()

    def _invalidate(self):
        self.generation += 1
        self.cancel.set()
        self.cancel = threading.Event()
        while True:
            try:
                self.pending.get_nowait()
            except queue.Empty:
                break

    def stop(self):
        with self.lock:
            self._invalidate()
        self.log("STOP requested; outputs off; late server replies discarded")

    def local(self, name):
        plan = self.player.catalog.plan([{"type": "motion", "name": name}])
        self.player.catalog.validate(plan)
        with self.lock:
            if self.closed:
                return False
            self._invalidate()
            self.pending.put_nowait((self.generation, plan, self.cancel))
        self.log("LOCAL " + name)
        return True

    def prompt(self, *, text=None, audio=None):
        with self.lock:
            if self.closed or self.network_busy or self.playing or not self.pending.empty():
                self.log("BUSY: stop playback first; local keys remain available")
                return False
            self._invalidate()
            generation = self.generation
            self.network_busy = True
        self.log("REQUEST: outputs off while waiting for server")

        def request():
            try:
                result = self.requester(self.url, self.token, text=text, audio=audio)
                self.player.catalog.validate(result["plan"])
                with self.lock:
                    if self.closed or generation != self.generation:
                        return
                    self.log("HEARD " + visible(result["transcript"]))
                    for note in result["notes"]:
                        self.log("NOTE " + visible(note))
                    self.pending.put_nowait((generation, result["plan"], self.cancel))
            except Exception as exc:
                with self.lock:
                    if generation == self.generation and not self.closed:
                        self._invalidate()
                        self.log("REQUEST FAILED " + visible(str(exc)) + "; outputs remain off; keys 1/2/3 available")
            finally:
                with self.lock:
                    self.network_busy = False
        threading.Thread(target=request, name="prompt-http", daemon=True).start()
        return True

    def _play_loop(self):
        while True:
            try:
                generation, plan, cancel = self.pending.get(timeout=.05)
            except queue.Empty:
                if self.closed:
                    return
                continue
            with self.lock:
                if self.closed:
                    return
                if generation != self.generation:
                    continue
                self.playing = True
            try:
                self.player.play(plan, cancel)
            except Cancelled:
                self.log("PLAY cancelled")
            except Exception as exc:
                self.log("PLAY FAILED " + visible(str(exc)) + "; outputs off requested")
            finally:
                with self.lock:
                    self.playing = False

    def close(self):
        with self.lock:
            self.closed = True
            self._invalidate()
        self.worker.join(timeout=3)
        if self.worker.is_alive():
            raise RuntimeError("playback worker did not stop; heartbeat lease remains bounded")

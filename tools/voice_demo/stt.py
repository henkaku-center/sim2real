"""Speech transcription through the Kotoleaf Deepgram gateway."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .providers import USER_AGENT, ProviderError, check_text, check_wav


class NoSpeech(ProviderError):
    """A successful recognition response contained no speech."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, _request, _response, code, *_args, **_kwargs):
        raise ProviderError(f"Deepgram HTTP {code}; endpoint redirect refused")


class DeepgramSpeechProvider:
    name = "deepgram"

    def __init__(self):
        self.token = os.environ.get("VOICE_STT_TOKEN", "")
        if not self.token:
            raise ProviderError("VOICE_STT_TOKEN is required for Deepgram through Kotoleaf")
        base = os.environ.get("VOICE_STT_URL", "https://kotoleaf.wandering-sky-fcce.workers.dev").rstrip("/")
        try:
            parsed = urllib.parse.urlsplit(base)
            valid = (parsed.scheme == "https" and parsed.hostname and not parsed.username
                     and not parsed.password and not parsed.query and not parsed.fragment
                     and not parsed.path)
            parsed.port  # Reject malformed ports without exposing the supplied URL.
        except ValueError:
            valid = False
        if not valid:
            raise ProviderError("VOICE_STT_URL must be an HTTPS origin without credentials")
        self.url = base + "/v1/listen?smart_format=true"

    def transcribe(self, audio):
        check_wav(audio)
        try:
            request = urllib.request.Request(self.url, data=audio, headers={
                "Authorization": f"Token {self.token}", "Content-Type": "audio/wav",
                "User-Agent": USER_AGENT})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=30) as response:
                data = response.read(262145)
                if len(data) > 262144:
                    raise ProviderError("Deepgram response too large")
                result = json.loads(data)
            text = result["results"]["channels"][0]["alternatives"][0]["transcript"]
            if not isinstance(text, str):
                raise ProviderError("Deepgram returned an invalid transcript")
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise ProviderError(f"Deepgram HTTP {code}; check endpoint and credentials") from None
        except (urllib.error.URLError, OSError, ValueError, RecursionError, KeyError, IndexError, TypeError):
            raise ProviderError("Deepgram request failed: network, timeout or invalid JSON response") from None
        if not text.strip():
            raise NoSpeech("Deepgram returned no speech; try another recording")
        check_text(text)
        return text


def speech_from_env():
    return DeepgramSpeechProvider()

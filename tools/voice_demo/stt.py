"""Speech adapters expose only transcribe(wav_bytes) -> text; no planner coupling."""
import os
import re

from .providers import USER_AGENT, ProviderError, check_text, check_wav


class GoogleSpeechProvider:
    name = "google"

    def __init__(self):
        self.project = os.environ.get("GOOGLE_CLOUD_PROJECT", "sesame-robots")
        self.location = os.environ.get("VOICE_STT_LOCATION", "us")
        self.model = os.environ.get("VOICE_STT_MODEL", "chirp_3")
        self.languages = os.environ.get("VOICE_STT_LANGUAGES", "en-US,ja-JP").split(",")
        self.languages = [language.strip() for language in self.languages]
        if (not re.fullmatch(r"[a-z][a-z0-9-]*", self.project) or
                not re.fullmatch(r"[a-z][a-z0-9-]*", self.location) or self.location == "global"):
            raise ProviderError("Google Speech needs a project ID and regional location (not global)")
        if not 1 <= len(self.languages) <= 3 or any(not language for language in self.languages):
            raise ProviderError("VOICE_STT_LANGUAGES needs 1..3 comma-separated language codes")
        if "auto" in self.languages and self.languages != ["auto"]:
            raise ProviderError("Use auto alone in VOICE_STT_LANGUAGES")

    def transcribe(self, audio):
        check_wav(audio)
        # Lazy import/ADC: fake mode and text-only Claude need no Google packages or credentials.
        try:
            from google.api_core.client_options import ClientOptions
            from google.api_core.gapic_v1.client_info import ClientInfo
            from google.api_core.exceptions import GoogleAPICallError
            from google.auth.exceptions import GoogleAuthError
            from google.cloud.speech_v2 import SpeechClient
            from google.cloud.speech_v2.types import cloud_speech
        except ImportError:
            raise ProviderError("Install the voice demo google extra for Google Speech") from None
        request = cloud_speech.RecognizeRequest(
            recognizer=f"projects/{self.project}/locations/{self.location}/recognizers/_",
            config=cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=self.languages, model=self.model),
            content=audio)
        try:
            # ADC uses the VM's attached service account. No key-file plumbing.
            with SpeechClient(client_options=ClientOptions(
                    api_endpoint=f"{self.location}-speech.googleapis.com"),
                    client_info=ClientInfo(user_agent=USER_AGENT)) as client:
                response = client.recognize(request=request, retry=None, timeout=30)
        except (GoogleAPICallError, GoogleAuthError, OSError, ValueError):
            raise ProviderError("Google Speech failed; check ADC, Speech API, IAM, region and model") from None
        text = " ".join(result.alternatives[0].transcript for result in response.results if result.alternatives)
        if not text.strip():
            raise ProviderError("Google Speech returned no speech; try another recording")
        return check_text(text)


def speech_from_env():
    selected = os.environ.get("VOICE_STT_PROVIDER", "google")
    if selected == "google":
        return GoogleSpeechProvider()
    raise ProviderError("VOICE_STT_PROVIDER must be google; use VOICE_PROVIDER=fake for offline fixtures")

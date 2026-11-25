"""Mocked HTTP/Google RPC tests. Never discover real ADC or call a model."""
import io
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.voice_demo.providers import ClaudeProvider, NoRedirect, PlanRefusal, ProviderError, provider_from_env
from tools.voice_demo.plan import InvalidPlan
from tools.voice_demo.stt import GoogleSpeechProvider, speech_from_env
from test_voice_demo import catalog, serving, wav, TOKEN
from tools.voice_demo.client import request_plan, ServerUnavailable


def tool_response(plan):
    return {"type": "message", "role": "assistant", "stop_reason": "tool_use", "content": [
        {"type": "text", "text": "A short bow."},
        {"type": "tool_use", "id": "toolu_fixture", "name": "submit_plan", "input": plan}]}


@pytest.fixture
def claude(catalog, monkeypatch):
    monkeypatch.setenv("VOICE_CLAUDE_TOKEN", "fixture-not-a-secret")
    monkeypatch.setenv("VOICE_CLAUDE_BASE_URL", "https://worker.example")
    monkeypatch.setenv("VOICE_PLAN_MODEL", "claude-haiku-4-5")
    monkeypatch.delenv("VOICE_PROVIDER", raising=False)
    monkeypatch.delenv("VOICE_STT_PROVIDER", raising=False)
    return provider_from_env(catalog)


def mock_http(monkeypatch, responses):
    calls = []
    responses = iter(responses)

    def open_request(self, request, timeout):
        calls.append((request, timeout))
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return io.BytesIO(response if isinstance(response, bytes) else json.dumps(response).encode())

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", open_request)
    return calls


@pytest.mark.parametrize("base", ["https://worker.example", "https://api.anthropic.com/v1/"])
def test_claude_exact_shared_wire_contract(catalog, claude, monkeypatch, base):
    monkeypatch.setenv("VOICE_CLAUDE_BASE_URL", base)
    claude = ClaudeProvider(catalog)
    plan = catalog.plan([{"type": "motion", "name": "bow"}])
    calls = mock_http(monkeypatch, [tool_response(plan)])
    assert claude.generate("do a bow") == (plan, ["A short bow."])
    request, timeout = calls[0]
    body = json.loads(request.data)
    assert set(body) == {"model", "max_tokens", "system", "messages", "tools"}
    assert len(body["tools"]) == 1 and body["tools"][0]["input_schema"] == catalog.schema()
    assert body["messages"] == [{"role": "user", "content": "do a bow"}]
    assert body["model"] == "claude-haiku-4-5" and 1 <= body["max_tokens"] <= 20000
    assert request.full_url == base.rstrip("/").removesuffix("/v1") + "/v1/messages"
    assert request.get_header("X-api-key") == "fixture-not-a-secret"
    assert request.get_header("Anthropic-version") == "2023-06-01" and timeout == 30
    assert request.get_header("User-agent") == "sesame-voice-demo/0.1.0"


def test_invalid_plan_then_retry_uses_validator_reason(catalog, claude, monkeypatch):
    bad = catalog.plan([{"type": "pose", "angles": [180, 90, 90, 90, 90, 90, 90, 90],
                         "duration_ms": 100, "hold_ms": 0}])
    good = catalog.plan([{"type": "motion", "name": "bow"}])
    calls = mock_http(monkeypatch, [tool_response(bad), tool_response(good)])
    plan, notes = claude.generate("bow")
    assert plan == good and "at least 1500" in notes[0]
    retry = json.loads(calls[1][0].data)
    assert all(call[0].get_header("User-agent") == "sesame-voice-demo/0.1.0" for call in calls)
    assert "at least 1500" in retry["messages"][0]["content"]
    assert len(calls) == 2


def test_no_tool_then_correct_tool(catalog, claude, monkeypatch):
    calls = mock_http(monkeypatch, [
        {"stop_reason": "end_turn", "content": [{"type": "text", "text": "I can bow."}]},
        tool_response(catalog.plan([{"type": "motion", "name": "bow"}]))])
    assert claude.generate("bow")[0]["steps"][0]["name"] == "bow"
    assert "exactly one submit_plan" in json.loads(calls[1][0].data)["messages"][0]["content"]


@pytest.mark.parametrize("response", [
    {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Custom eye bitmaps are unsupported."}]},
    {"stop_reason": "max_tokens", "content": []},
    {"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "exec", "input": {}}]},
    {"stop_reason": "tool_use", "content": None},
])
def test_two_failures_are_clear_refusal_with_notes(claude, monkeypatch, response):
    calls = mock_http(monkeypatch, [response, response])
    with pytest.raises(PlanRefusal) as error:
        claude.generate("change your face to one eyeball")
    assert "two attempts" in str(error.value)
    assert error.value.notes[0].startswith("Attempt 1:") and error.value.notes[1].startswith("Attempt 2:")
    assert len(calls) == 2


def test_invalid_plan_twice_never_returns_plan(catalog, claude, monkeypatch):
    response = tool_response(catalog.plan([{"type": "motion", "name": "walk"}]))
    calls = mock_http(monkeypatch, [response, response])
    with pytest.raises(PlanRefusal, match="valid plan"):
        claude.generate("walk")
    assert len(calls) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 502])
def test_worker_http_errors_do_not_retry_or_leak(claude, monkeypatch, status):
    failure = urllib.error.HTTPError(claude.url, status, "private detail", {}, io.BytesIO(b'{"error":"private token"}'))
    calls = mock_http(monkeypatch, [failure])
    with pytest.raises(ProviderError, match=f"HTTP {status}") as error:
        claude.generate("bow")
    assert len(calls) == 1 and "private" not in str(error.value) and error.value.__suppress_context__


@pytest.mark.parametrize("body,visible", [
    (b"error code: 1010", True), (b" Error code: 1010\n", True),
    (b"error code: 1010 private token", False),
    (b'{"error":"private token", "code":1010}', False),
    (b"error code: 1010" + b" " * 257, False),
])
def test_only_short_numeric_edge_diagnostics_are_exposed(claude, monkeypatch, body, visible):
    failure = urllib.error.HTTPError(claude.url, 403, "private", {}, io.BytesIO(body))
    calls = mock_http(monkeypatch, [failure])
    with pytest.raises(ProviderError) as error:
        claude.generate("bow")
    assert ("error code: 1010" in str(error.value)) == visible
    assert "private" not in str(error.value) and len(calls) == 1


@pytest.mark.parametrize("response", [b"not json", b"[", b"x" * 262145, TimeoutError("secret")])
def test_bad_transport_response_fails_closed(claude, monkeypatch, response):
    calls = mock_http(monkeypatch, [response])
    with pytest.raises(ProviderError):
        claude.generate("bow")
    assert len(calls) == 1


def test_truncated_valid_tool_is_not_playable(catalog, claude, monkeypatch):
    response = tool_response(catalog.plan([{"type": "rest"}]))
    response["stop_reason"] = "max_tokens"
    mock_http(monkeypatch, [response, response])
    with pytest.raises(PlanRefusal):
        claude.generate("rest")


def test_multiple_tool_calls_are_rejected(catalog, claude, monkeypatch):
    response = tool_response(catalog.plan([{"type": "rest"}]))
    response["content"].append(response["content"][-1])
    mock_http(monkeypatch, [response, response])
    with pytest.raises(PlanRefusal):
        claude.generate("rest")


def test_redirect_cannot_forward_provider_token():
    with pytest.raises(ProviderError, match="redirect refused"):
        NoRedirect().redirect_request(None, None, 307, "redirect", {}, "https://other.example")


def test_default_is_claude_and_missing_token_does_not_silently_fake(catalog, monkeypatch):
    monkeypatch.delenv("VOICE_PROVIDER", raising=False)
    monkeypatch.delenv("VOICE_CLAUDE_TOKEN", raising=False)
    with pytest.raises(ProviderError, match="VOICE_CLAUDE_TOKEN"):
        provider_from_env(catalog)
    monkeypatch.delenv("VOICE_STT_PROVIDER", raising=False)
    assert isinstance(speech_from_env(), GoogleSpeechProvider)


def test_refusal_notes_survive_server_and_relay(catalog, claude, monkeypatch):
    def refuse(_text):
        raise PlanRefusal(["Custom eye bitmaps are unsupported."])
    monkeypatch.setattr(claude, "generate", refuse)
    with serving(catalog, claude) as (url, _):
        with pytest.raises(ServerUnavailable, match="Custom eye bitmaps"):
            request_plan(url, TOKEN, text="one eyeball")


def test_separate_stt_adapter_passes_transcript_to_planner(catalog, claude, monkeypatch):
    class Speech:
        name = "fixture"
        def transcribe(self, audio):
            assert audio == wav()
            return "おじぎして"
    seen = []
    monkeypatch.setattr(claude, "generate", lambda text: (seen.append(text) or catalog.plan([{"type": "rest"}]), []))
    with serving(catalog, claude) as (url, server):
        server.transcriber = Speech()
        result = request_plan(url, TOKEN, audio=wav())
    assert result["transcript"] == "おじぎして" and seen == ["おじぎして"]


@pytest.fixture
def google(monkeypatch):
    speech = pytest.importorskip("google.cloud.speech_v2")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sesame-robots")
    monkeypatch.setenv("VOICE_STT_LOCATION", "us")
    monkeypatch.setenv("VOICE_STT_MODEL", "chirp_3")
    monkeypatch.setenv("VOICE_STT_LANGUAGES", "en-US,ja-JP")
    return speech


@pytest.mark.parametrize("languages", ["en-US,ja-JP", "auto"])
def test_google_v2_request_uses_adc_and_short_bilingual_audio(google, monkeypatch, languages):
    from google.cloud.speech_v2.types import cloud_speech
    calls = []
    monkeypatch.setenv("VOICE_STT_LANGUAGES", languages)
    class Client:
        def __init__(self, *, client_options, client_info):
            assert client_options.api_endpoint == "us-speech.googleapis.com"
            assert client_info.user_agent == "sesame-voice-demo/0.1.0"
        def __enter__(self):
            return self
        def __exit__(self, *_):
            calls.append("closed")
        def recognize(self, *, request, retry, timeout):
            calls.append(request)
            assert retry is None and timeout == 30
            return cloud_speech.RecognizeResponse(results=[
                {"alternatives": [{"transcript": "おじぎして"}]}])
    monkeypatch.setattr(google, "SpeechClient", Client)
    assert GoogleSpeechProvider().transcribe(wav()) == "おじぎして"
    request = calls[0]
    assert request.recognizer == "projects/sesame-robots/locations/us/recognizers/_"
    assert request.config.model == "chirp_3" and list(request.config.language_codes) == languages.split(",")
    assert request.config._pb.HasField("auto_decoding_config")
    assert request.content == wav() and calls[-1] == "closed"


@pytest.mark.parametrize("error_type", ["adc", "api", "empty"])
def test_google_failure_is_clear_and_private(google, monkeypatch, error_type):
    from google.api_core.exceptions import PermissionDenied
    from google.auth.exceptions import DefaultCredentialsError
    from google.cloud.speech_v2.types import cloud_speech
    class Client:
        def __init__(self, **kwargs):
            if error_type == "adc":
                raise DefaultCredentialsError("private credential path")
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def recognize(self, **kwargs):
            if error_type == "api":
                raise PermissionDenied("private provider error")
            return cloud_speech.RecognizeResponse()
    monkeypatch.setattr(google, "SpeechClient", Client)
    with pytest.raises(ProviderError, match="Google Speech") as error:
        GoogleSpeechProvider().transcribe(wav())
    assert "private" not in str(error.value)


def test_google_rejects_bad_audio_before_adc(google, monkeypatch):
    monkeypatch.setattr(google, "SpeechClient", lambda **kwargs: pytest.fail("must not discover ADC"))
    with pytest.raises(InvalidPlan, match="WAV"):
        GoogleSpeechProvider().transcribe(b"not a recording")

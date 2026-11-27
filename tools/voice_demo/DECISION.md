# Voice provider decision — 27 November 2026

**Claude plans; Deepgram through Kotoleaf transcribes.** This replaces Google
Speech outright, including its SDK and configuration. There is one production
speech path. The deterministic fake remains explicitly opt-in for offline tests.

## Speech: Deepgram through the existing Kotoleaf gateway

Grisha's comparison on **27 November 2026** used the same two synthetic
English/Japanese recordings: Deepgram took **0.5–1.2 seconds per request from
a Tokyo Mac**, versus **about 1.7 seconds for Google `chirp_3` in `us` measured
from the Pi**. These are different client machines/routes, not a controlled
same-host benchmark. `chirp_3` failed in `asia-northeast1` and `asia-southeast1`
for this project. Deepgram's Japanese transcript came back without inter-word
spaces. These owner-reported observations motivated the replacement; they do
not establish real-microphone accuracy or venue latency.

`VOICE_STT_URL` defaults to `https://kotoleaf.wandering-sky-fcce.workers.dev`.
The adapter POSTs mono PCM16 16 kHz WAV bytes (at most 30 seconds) to
`/v1/listen?smart_format=true`, with `Authorization: Token ${VOICE_STT_TOKEN}`
and `Content-Type: audio/wav`. Kotoleaf forces Nova-3 English/Japanese
code-switching, so the application sends no model or language parameters.
The transcript is `results.channels[0].alternatives[0].transcript`; an empty
transcript is an explicit no-speech result, never a fake transcription. `/prompt`
reports it as a provider error; the transcript-only `/transcribe` route returns
HTTP 200 with an empty transcript and never calls the planner.

The token is mandatory at startup in real-provider mode. Cloud Run receives it
from `voice-stt-token:latest` in Secret Manager. No Google Speech extra, ADC,
Speech Client role or Speech API is needed by this adapter. Base dependencies
remain PySerial 3.5 and PyYAML 6.0.3; transport uses Python's standard library.

## Claude: one tool, validated locally

The default planner remains Claude Haiku 4.5. A private Worker and an Anthropic
Console key share the HTTP implementation, configured through base URL, token
and model. `POST /v1/messages` sends only `model`, `max_tokens=4000`, `system`,
`messages` and `tools`. The sole tool is `submit_plan`, with the manifest-derived
plan schema. Its input is data, not executable code.

Exactly one correctly named tool call with `stop_reason=tool_use` is required.
The local validator checks joint travel, soft limits, timing and the firmware
contract. Missing or invalid output gets one correction attempt; a second
failure returns HTTP 422 with refusal notes and no plan. Transport errors are
HTTP 502 without automatic retry. The Pi revalidates plans and stays independent
of provider latency. Claude receives `x-api-key` with the configured backend's
token and `anthropic-version: 2023-06-01`.

## Transport, evidence and privacy

Both providers require HTTPS, disable redirects and environment proxies, set
`User-Agent: sesame-voice-demo/0.1.0`, and use 30-second timeouts with bounded
responses. Errors retain HTTP status without exposing tokens or response bodies.
Claude additionally preserves only exact short numeric edge-code envelopes.
An earlier Cloudflare rejection of urllib's default User-Agent motivated the
explicit application identifier.

Offline tests mock HTTP for both providers, including English/Japanese output,
empty speech, invalid JSON, HTTP failures and credential privacy. The deployed
Deepgram check will follow the owner's deployment from main; this change makes
no live provider calls or cloud modifications. Historical Claude and Google
deployment results remain in [VALIDATION.md](VALIDATION.md), labelled by date.

Audio goes through Kotoleaf to Deepgram; transcripts and plan requests go to
Claude through the configured backend. No provider retention claim is implied.
The server stores neither audio nor transcripts; the relay console/journal
includes transcripts and needs the installation's intended retention policy.

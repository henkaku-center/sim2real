# Voice provider decision — 25 November 2026

**Use OpenAI file transcription (`gpt-transcribe`) followed by a Responses API
structured plan (`gpt-6.1-terra`, low reasoning effort).** The server returns
data only; it has no robot tools or serial port. Both models are environment
overrides, and both provider outputs are independently validated. This choice
minimizes credentials, dependencies and integration surfaces, not a claim of
measured latency or superior motion quality.

Official documentation was fetched during implementation:

1. [OpenAI file transcription](https://developers.openai.com/api/docs/guides/speech-to-text):
   `POST /v1/audio/transcriptions` accepts multipart WAV with `model` and `file`,
   returning a JSON `text` transcript. The fetched guide recommends
   `gpt-transcribe`. It says older Whisper/GPT-4o transcription models are
   deprecated and shut down on **26 February 2027**. Avoid building this
   December-to-February installation on those retiring defaults.
2. [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs):
   Responses `text.format` supports `type=json_schema`, `strict=true` and a
   schema. Required fields and `additionalProperties=false` are used on all
   objects. A tagged `anyOf` describes the step variants. Incomplete results,
   refusals and semantic constraints still require application handling. No
   tool-execution loop is needed when the output is a plan for another process.
3. [GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini) was checked
   as an initially plausible small planner; the fetched page marks it deprecated
   and points new low-latency workloads to Terra.
4. [GPT-6.1 Terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra):
   supports Responses, structured outputs and low reasoning effort. Its listed
   snapshot is `gpt-6.1-terra`. This is the selected current planner, not a claim
   that the account already has access. No image, code, search or robot tools are
   supplied to it.
5. [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages):
   the fetched API documents text/image input, document/tool blocks and
   structured outputs, but no audio input block or speech-to-text endpoint.
   **No public Anthropic API STT path was established from these docs.** Claude
   could plan from a transcript produced elsewhere; that would add a second
   provider/key without eliminating transcription. Claude app voice features
   are not evidence of a public API transcription endpoint.

The adapter uses standard-library HTTPS rather than adding an SDK. Keys come
only from environment variables; errors never echo authorization headers or
provider response bodies. Audio is bounded to 30 seconds and held in memory.
The Responses request sets `store=false`; that is a request option, not a claim
about a provider's complete retention policy. Transcripts are shown only in the
relay console/journal. Operators should tell speakers that audio leaves the Pi
when using the real provider.

The fake provider deterministically maps stock names, greetings and a snake-like
pose example. Its WAV path deliberately returns a labelled fixed “do a bow”
fixture; it does **not** pretend to recognize speech. Tests force fake or mocked
HTTP even if environment keys happen to exist. No live paid requests were made.
Model availability, latency, recognition quality and plan acceptance rate remain
installation commissioning work.

Other primary implementation references:
- [libgpiod official Python edge example](https://github.com/brgl/libgpiod/blob/master/bindings/python/examples/watch_line_value.py)
  for GPIO edge/debounce APIs (optional Linux-only backend).
- [gpiod 2.3.0 release metadata](https://pypi.org/pypi/gpiod/2.3.0/json)
  publishes arm64/Linux wheels, including Python 3.11. It is platform-gated;
  macOS development uses keyboard input, not Linux GPIO.
- [Tailscale Serve CLI](https://tailscale.com/kb/1242/tailscale-serve)
  documents the private-tailnet HTTPS proxy and persistent `--bg` invocation
  used in the deployment instructions. No tailnet route was changed here.

Firmware facts come from local `controller.cpp`, `safe_action.h`,
`command_line.h`, `manifest_generated.h`, FACE_LIST, the generated interface and
the manifests. They take precedence over generic SafeAction vocabulary notes
(for example, the S3 parser does not accept a duration after `pose`).

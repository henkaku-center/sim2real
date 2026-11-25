# Voice provider decision — 25 November 2026

**Claude plans; Google Cloud Speech-to-Text transcribes.** This supersedes PR #42's
combined OpenAI adapter, which has been removed. The default planner is Claude
Haiku 4.5. A private test Worker and a normal Anthropic Console key use the same
HTTP implementation; only base URL, token and model configuration change.

## Claude: one tool, validated locally

`POST /v1/messages` sends only `model`, `max_tokens=4000`, `system`, `messages`
and `tools`. The sole tool, `submit_plan`, has the manifest-derived plan schema
as its `input_schema`. Its input is the plan itself, not executable code. Text
blocks become bounded explanatory notes. There is no `tool_choice`, streaming,
temperature, metadata, output-config or SDK-added top-level field.

Exactly one correctly named tool call with `stop_reason=tool_use` is required.
The existing validator checks the complete plan, including fitted joint travel,
soft limits, timing and the firmware contract. A missing tool, truncated response
or invalid plan gets **one** correction attempt with the validator's reason and
previous candidate. A second failure returns HTTP 422 with refusal notes and no
plan. Transport/HTTP failures are HTTP 502 and are not retried. The relay remains
independent of provider latency and revalidates every returned plan.

The Worker accepts `x-api-key` containing its **own access token**. Anthropic
accepts the same header containing a Console API key, with
`anthropic-version: 2023-06-01`. Credentials are only environment settings, never
prompt content. HTTPS only, no redirects or environment proxies. Claude requests
send `User-Agent: sesame-voice-demo/0.1.0`; Google gets the same application
identifier through its SDK `ClientInfo`. Error messages include HTTP status and,
for an exact short plain-text `error code: <digits>` envelope, that numeric edge
code. Arbitrary provider bodies, headers and exception detail remain hidden.

Sources inspected/fetched on 25 November 2026:

- Local gateway `README.md` and `docs/integration.md` in
  `claude-cloudflare-worker`: restricted Messages subset; automatic tool choice;
  1–20000 max tokens; structured-output forwarding not live-validated there.
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages):
  tool definitions, input schema, `tool_use` blocks and stop reasons. Claude
  consumes the transcript; this implementation does not send it audio.

## Speech: Google V2, Chirp 3, two expected languages

Use synchronous **Speech-to-Text V2 `Recognize`**, model **`chirp_3`**, region
**`us`**, and **`language_codes=["en-US", "ja-JP"]`**. Each push-to-talk clip is
mono PCM16 WAV at 16 kHz, limited to 30 seconds, and sent inline. Use
`AutoDetectDecodingConfig` for its WAV header. The implicit recognizer
`projects/sesame-robots/locations/us/recognizers/_` needs no persisted recognizer
or Cloud Storage bucket. The endpoint matches the recognizer location:
`us-speech.googleapis.com`.

Why this fit: the official Chirp 3 guide supports synchronous recognition for
audio below one minute and either unrestricted `auto` detection or a list of
expected locales. Restricting the list to English/Japanese matches the exhibition
and avoids an unnecessary language-selection UI. It detects the dominant spoken
language; this is not a promise of word-by-word code-switch recognition. `auto`
remains an environment option. The supported-language table lists both locales
for Chirp 3 in `us`; the model is unavailable on `global`. Region can be changed
after checking model/language availability and measuring venue latency.

The official `google-cloud-speech==2.41.0` library uses **Application Default
Credentials**. On the planned VM in `sesame-robots`, attach a service account
with Speech Client (`roles/speech.client`), enable `speech.googleapis.com`, and
use the `cloud-platform` VM access scope. Leave `GOOGLE_APPLICATION_CREDENTIALS`
unset: metadata-server credentials mean **no downloaded service-account key**.
No VM, API enablement, IAM, billing or credential configuration was changed here.
The Google client and ADC are created only for audio, so text-only Claude and
fake runs need neither the Google extra nor Google credentials.

Official sources fetched on 25 November 2026:

1. [Chirp 3 model and examples](https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3):
   V2-only; synchronous short-audio support; regional endpoint; automatic and
   language-restricted detection; WAV auto-decoding example.
2. [V2 supported languages](https://docs.cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages):
   English `en-US` and Japanese `ja-JP`, Chirp 3, `us`.
3. [Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials):
   attached service account via metadata server is the preferred production
   Google Cloud path; local ADC and ordinary gcloud login are distinct.
4. [Speech-to-Text pricing](https://cloud.google.com/speech-to-text/pricing):
   V2 standard recognition is **US$0.016/audio minute** for the first 500,000
   minutes/month, rounded up per request to whole seconds. Thus a 5-second mono
   request is about **$0.00133**, and 30 seconds about **$0.008**, excluding VM,
   networking, Claude and taxes. Successfully processed silence/empty results
   are billed too. The V1 60-minute free tier must not be assumed for V2.
   Dynamic batch's listed $0.003/minute is cheaper but lower priority and not
   appropriate for this interactive synchronous path. No Google audio calls or
   billing measurements were performed.
5. [Python package metadata](https://pypi.org/project/google-cloud-speech/2.41.0/):
   universal Python wheel. Its transitive dependencies are pinned in the demo
   lockfile; the `google` extra is exercised on macOS and both Linux CI targets.

Alternatives: a short-utterance-specific Google `short` model is a plausible
latency benchmark; Chirp 3 was selected for its documented multilingual detection
path, not because a comparative accuracy/latency experiment was run. Workers AI
Whisper or an OpenAI STT adapter could replace only `transcribe(wav_bytes) -> str`
and the speech factory; neither requires changing Claude or the relay. Keeping
the old combined OpenAI adapter would retain an unwanted alternate planner and
couple its credentials to transcription, so it was removed.

## Evidence and privacy

Offline tests mock Claude HTTP and Google RPC, explicitly preventing live ADC
discovery. The deterministic fake remains opt-in (`VOICE_PROVIDER=fake`), with a
clearly labelled fixed WAV transcript. Missing Claude configuration fails loudly
rather than silently pretending to recognize speech or plan with AI.

The initial HTTP 403 was diagnosed as edge filtering of Python urllib's default
User-Agent. With an explicit application User-Agent, the ten-prompt live matrix
completed; a wrong face substitution was exposed, the capability prompt was
clarified, and English/Japanese refusals plus a supported face were rechecked.
Stock planning took 2.46 seconds median; see [VALIDATION.md](VALIDATION.md) for
the initial failure, limited snake interpretation, correction and evidence scope.
Live Google recognition and the direct Console-key path remain unverified.
Audio goes to Google; transcripts and plan requests go to Claude
through the configured backend. No provider retention claim is implied. The
server stores neither audio nor transcripts; the relay console/journal includes
transcripts and should use the installation's intended retention policy.

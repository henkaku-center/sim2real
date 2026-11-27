#!/usr/bin/env bash
# Deploy the voice plan server to Cloud Run from a committed revision.
# Secrets voice-device-token, voice-claude-token and voice-stt-token must exist in
# Secret Manager and be readable by the service account; values never pass
# through this script.
set -euo pipefail
: "${GCP_PROJECT:?set GCP_PROJECT}"
: "${VOICE_CLAUDE_BASE_URL:?set VOICE_CLAUDE_BASE_URL (Worker origin or https://api.anthropic.com)}"
REGION="${GCP_REGION:-asia-northeast1}"
SERVICE="${VOICE_SERVICE:-sesame-voice}"
REF="${1:-HEAD}"
ACCOUNT="voice-server@${GCP_PROJECT}.iam.gserviceaccount.com"
BUILDER="projects/${GCP_PROJECT}/serviceAccounts/voice-build@${GCP_PROJECT}.iam.gserviceaccount.com"
ROOT="$(git rev-parse --show-toplevel)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
git -C "$ROOT" archive "$REF" firmware manifest reference tools \
  assets/printing/internal-frame-s3 assets/stl/upstream | tar -x -C "$STAGE"
cp "$STAGE/tools/voice_demo/deploy/Dockerfile" "$STAGE/Dockerfile"
gcloud run deploy "$SERVICE" --source "$STAGE" --project "$GCP_PROJECT" --region "$REGION" \
  --service-account "$ACCOUNT" --build-service-account "$BUILDER" --no-invoker-iam-check \
  --min-instances "${VOICE_MIN_INSTANCES:-0}" --max-instances 1 --concurrency 8 \
  --memory 512Mi --cpu 1 --timeout 120 \
  --set-secrets "VOICE_DEVICE_TOKEN=voice-device-token:latest,VOICE_CLAUDE_TOKEN=voice-claude-token:latest,VOICE_STT_TOKEN=voice-stt-token:latest" \
  --set-env-vars "^@^VOICE_PROVIDER=claude@VOICE_CLAUDE_BASE_URL=${VOICE_CLAUDE_BASE_URL}@VOICE_PLAN_MODEL=${VOICE_PLAN_MODEL:-claude-haiku-4-5}@VOICE_STT_URL=${VOICE_STT_URL:-https://kotoleaf.wandering-sky-fcce.workers.dev}@SOURCE_REVISION=$(git -C "$ROOT" rev-parse --short "$REF")"
gcloud run services describe "$SERVICE" --project "$GCP_PROJECT" --region "$REGION" --format='value(status.url)'

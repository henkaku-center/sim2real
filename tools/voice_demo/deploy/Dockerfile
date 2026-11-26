# Voice plan server for Cloud Run. Build from the staged context that
# cloud-run.sh prepares (firmware, manifest, reference, tools and the course
# body's leg-clearance evidence); the full repository is not needed.
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv
WORKDIR /opt/sim2real
COPY . .
RUN uv sync --project tools/voice_demo --locked --extra google --no-dev --python /usr/local/bin/python3 \
 && useradd --system --no-create-home --shell /usr/sbin/nologin sesame-voice
USER sesame-voice
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["sh", "-c", "exec tools/voice_demo/.venv/bin/python -m tools.voice_demo.server --host 0.0.0.0 --port ${PORT:-8080}"]

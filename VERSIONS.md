# VERSIONS

Tool versions this repo is developed and tested against. Lockfiles (`uv.lock`,
`web/package-lock.json`) are authoritative; this file is the human summary.
Update when bumping anything below.

## Core

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.12.x (pinned via `.python-version`) | managed by uv |
| uv | 0.11.x | `uv sync --locked` |
| MuJoCo (native, `mujoco` pip) | 3.10.0 | reference physics core |
| MuJoCo (WASM, `@mujoco/mujoco` npm) | 3.10.0 | **must match native minor version** — parity is CDP-tested |
| NumPy | 2.5.x | |
| Node | 24.x | |
| npm | 11.x | `npm ci` in `web/` |
| Vite | 8.x | vanilla-ts template |
| TypeScript | 6.0.x | |
| PlayCanvas | 2.x | browser rendering |
| pytest | 9.x | |
| Playwright (Python) | latest | drives system Chrome; no browser download |

## Browsers

CDP smoke tests use the system Chrome/Chromium (`tests/test_browser.py`
searches PATH + the macOS app bundle). GitHub runners provide Chrome stable
on both platforms.

## OS coverage

| OS | Verified by |
|----|-------------|
| Linux x86_64 (Ubuntu 24.04 dev machine, ubuntu-latest CI) | local + CI, every push |
| macOS arm64 (macos-latest CI, Apple Silicon) | CI, every push |
| Windows | unsupported (MuJoCo WASM experimental there; not a course target) |

## Cross-backend determinism tolerances (declared)

| Comparison | Tolerance | Test |
|------------|-----------|------|
| Same machine, repeated runs | bit-identical | `tests/test_determinism.py` |
| Linux reference vs macOS native | atol 1e-3 over 1000 steps | `tests/test_determinism.py` |
| Native vs browser WASM (same OS) | atol 1e-3 over 1000 steps | `tests/test_browser.py` |

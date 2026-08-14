#!/data/data/com.termux/files/usr/bin/sh
set -eu
PORT="${2:-7779}"
exec python "$HOME/cdc_rfc2217_bridge.py" "$1" "$PORT"

#!/data/data/com.termux/files/usr/bin/sh
set -eu
PORT="${2:-7777}"
exec "$HOME/cdc_tcp_bridge" "$1" "$PORT"

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import sesame_mind_agent as agent  # noqa: E402


def test_systemd_unit_runs_radio_group_with_chosen_mic_and_escapes_specifiers():
    text = agent.unit("sesame-s3-8b2c.local", "alsa:plughw:CARD=Device,DEV=0", 8765, None)
    exec_line = next(line for line in text.splitlines() if line.startswith("ExecStart="))
    assert "--group radio" in exec_line and "--group dev" not in exec_line
    assert "--mic-device alsa:plughw:CARD=Device,DEV=0" in exec_line
    assert "--serve 8765 --robot sesame-s3-8b2c.local" in exec_line
    assert f"StandardOutput=append:{agent.LOG}" in text and "Restart=always" in text
    assert "EnvironmentFile=-" in text  # optional ANTHROPIC_API_KEY file
    odd = agent.unit("r", "pulse:50% mic", 8765, None)
    assert "'pulse:50%% mic'" in odd


def test_launchd_plist_keeps_mac_defaults():
    p = agent.plist("sesame-s3-8b2c.local", agent.MAC_MIC, 8765, None)
    args = p["ProgramArguments"]
    assert args[args.index("--mic-device") + 1] == agent.MAC_MIC
    assert "--group" in args and "dev" in args and p["KeepAlive"] is True

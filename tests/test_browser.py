"""CDP smoke test: the browser WASM sim must numerically agree with native MuJoCo.

Launches the Vite dev server + headless Chrome (system install, no download),
drives the sim through the window.__sim test hook, and compares qpos after an
identical command sequence against a native Python run of the same MJCF.

Skipped locally when Chrome or web/node_modules are missing, unless
REQUIRE_BROWSER_TESTS=1 (set in CI) forces a hard failure.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import mujoco
import numpy as np
import pytest

from sim.build_mjcf import MODEL_PATH
from sim.manifest import load_manifest

REPO_ROOT = Path(__file__).parent.parent
WEB_DIR = REPO_ROOT / "web"
ARTIFACTS = Path(__file__).parent / "artifacts"
PORT = 5173
STEPS = 1000
# Native (clang/gcc x86_64/arm64) vs Emscripten WASM builds differ in
# low-order bits; 2 s of contact dynamics amplifies them.
BROWSER_ATOL = 1e-3

REQUIRED = os.environ.get("REQUIRE_BROWSER_TESTS") == "1"


def _chrome_path() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if path := shutil.which(name):
            return path
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return mac if os.path.exists(mac) else None


def _skip_or_fail(reason: str):
    if REQUIRED:
        pytest.fail(f"browser test required but {reason}")
    pytest.skip(reason)


@pytest.fixture(scope="module")
def dev_server():
    if not (WEB_DIR / "node_modules").exists():
        _skip_or_fail("web/node_modules missing (run: cd web && npm ci)")
    ARTIFACTS.mkdir(exist_ok=True)
    log_path = ARTIFACTS / "vite_dev.log"
    log = open(log_path, "w")
    proc = subprocess.Popen(
        ["npm", "run", "dev", "--",
         "--host", "127.0.0.1", "--port", str(PORT), "--strictPort"],
        cwd=WEB_DIR,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 60  # CI runners can be slow to cold-start
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            pass
        try:
            socket.create_connection(("127.0.0.1", PORT), timeout=1).close()
        except OSError:
            log.flush()
            pytest.fail(
                "vite dev server did not start; log tail:\n"
                + "\n".join(log_path.read_text().splitlines()[-20:])
            )
        yield f"http://127.0.0.1:{PORT}"
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        log.close()


@pytest.fixture(scope="module")
def page(dev_server):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _skip_or_fail("playwright not installed")
    chrome = _chrome_path()
    if chrome is None:
        _skip_or_fail("no system Chrome/Chromium found")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome, headless=True)
        page = browser.new_page()
        console_errors: list[str] = []
        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.goto(dev_server)
        page.wait_for_function("() => window.__sim !== undefined", timeout=15000)
        page.evaluate("() => window.__sim.ready")
        page.console_errors = console_errors  # type: ignore[attr-defined]
        yield page
        browser.close()


def native_stand_qpos(steps: int = STEPS) -> np.ndarray:
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)
    manifest = load_manifest()
    stand = manifest.pose_internal("stand")
    data.ctrl[:] = [stand[j.name] for j in manifest.joints]
    for _ in range(steps):
        mujoco.mj_step(model, data)
    return data.qpos.copy()


def browser_run(page, ctrl: list[float], steps: int) -> dict:
    return page.evaluate(
        """async ([ctrl, steps]) => {
            const sim = window.__sim;
            sim.send({type: 'pause'});
            sim.send({type: 'reset'});
            sim.send({type: 'ctrl', values: ctrl});
            sim.send({type: 'run', steps});
            return await sim.getState();
        }""",
        [ctrl, steps],
    )


def test_no_console_errors_on_load(page):
    assert page.console_errors == [], f"console errors: {page.console_errors}"


def test_stand_matches_native(page):
    manifest = load_manifest()
    stand = manifest.pose_internal("stand")
    ctrl = [stand[j.name] for j in manifest.joints]
    state = browser_run(page, ctrl, STEPS)
    browser_qpos = np.array(state["qpos"])
    native_qpos = native_stand_qpos()
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "browser_vs_native.json").write_text(
        json.dumps({"browser": list(browser_qpos), "native": list(native_qpos)}, indent=1)
    )
    np.testing.assert_allclose(
        browser_qpos,
        native_qpos,
        atol=BROWSER_ATOL,
        err_msg="browser WASM diverged from native MuJoCo for identical commands",
    )


def test_slider_moves_joint(page):
    # Move the R1 slider through the UI and read back ctrl from the worker.
    # Note: range inputs snap to their step grid, so compare against the
    # value the input actually took, not the raw string we assigned.
    applied = page.evaluate(
        """() => {
            const input = document.querySelector('input[data-joint="R1"]');
            input.value = '0.5';
            input.dispatchEvent(new Event('input', {bubbles: true}));
            return Number(input.value);
        }"""
    )
    assert applied == pytest.approx(0.5, abs=0.02), "slider should land near 0.5"
    state = page.evaluate("() => window.__sim.getState()")
    assert state["ctrl"][0] == pytest.approx(applied), "ctrl[0] is channel 0 == R1"


def test_screenshot_artifact(page):
    ARTIFACTS.mkdir(exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "browser_shell.png"))
    assert (ARTIFACTS / "browser_shell.png").stat().st_size > 10_000


def test_no_console_errors_after_interaction(page):
    assert page.console_errors == [], f"console errors: {page.console_errors}"

"""Self-contained HTML report for a fit: overlays and a labelled parameter table.

One file, inline CSS and SVG, no scripts and no network requests, readable on
a phone. Every parameter row says where its value comes from: nominal, fitted
from synthetic data, fitted from a measured run, or measured directly.
"""

from __future__ import annotations

import html
import math

CHANNELS = [("x forward", "mm", 0, 1000.0), ("y left", "mm", 1, 1000.0), ("z up (height)", "mm", 2, 1000.0),
            ("roll", "deg", 3, math.degrees(1.0)), ("pitch", "deg", 4, math.degrees(1.0)),
            ("yaw", "deg", 5, math.degrees(1.0))]
FITTED_CHANNELS = {2, 3, 4}  # height, roll, pitch carry the fit; the others are reported only
BADGES = {"nominal": "nominal", "fitted from synthetic data": "synthetic",
          "fitted from a measured run": "measured", "measured directly": "direct"}
CSS = """
:root{color-scheme:light dark;--fg:#1c1c1e;--bg:#fff;--mute:#6b6b70;--line:#d9d9de;--card:#f5f5f7;
--meas:#8a8a90;--before:#d2452f;--after:#1f6fd0}
@media(prefers-color-scheme:dark){:root{--fg:#f2f2f4;--bg:#111113;--mute:#a0a0a8;--line:#3a3a40;--card:#1c1c20;
--meas:#b0b0b8;--before:#ff7a66;--after:#6aaeff}}
*{box-sizing:border-box}body{margin:0 auto;max-width:900px;padding:16px;font:16px/1.45 system-ui,-apple-system,
"Segoe UI",sans-serif;color:var(--fg);background:var(--bg)}h1{font-size:1.5rem;margin:.2em 0}
h2{font-size:1.15rem;margin:1.6em 0 .4em}p{margin:.5em 0}.mute{color:var(--mute);font-size:.9rem}
.banner{border:2px solid var(--before);border-radius:10px;padding:10px 14px;margin:12px 0;font-weight:600}
.banner.measured{border-color:var(--after)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.card{background:var(--card);border-radius:10px;padding:10px 12px}.card b{display:block;font-size:1.25rem}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
td.n{white-space:nowrap;font-variant-numeric:tabular-nums}td.p{min-width:11.5em}
td:last-child{min-width:15em}
.badge{display:inline-block;border-radius:999px;padding:1px 9px;font-size:.8rem;border:1px solid var(--line);
white-space:nowrap;margin:3px 0}.badge.synthetic{border-color:var(--before);color:var(--before)}
.badge.measured,.badge.direct{border-color:var(--after);color:var(--after)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}
figure{margin:0;background:var(--card);border-radius:10px;padding:8px}figcaption{font-size:.85rem;color:var(--mute)}
svg{width:100%;height:auto;display:block}.axis{stroke:var(--line);stroke-width:1}
.tick{fill:var(--mute);font-size:11px}.meas{fill:none;stroke:var(--meas);stroke-width:2.5;opacity:.75}
.before{fill:none;stroke:var(--before);stroke-width:1.5;stroke-dasharray:5 3}
.after{fill:none;stroke:var(--after);stroke-width:1.5}
.key span{display:inline-block;margin-right:14px}.key i{display:inline-block;width:22px;height:0;
border-top:3px solid;vertical-align:middle;margin-right:5px}
"""


def _number(value, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value:.{digits}g}"


def _chart(t, series, unit: str) -> str:
    """Inline SVG: series = [(css class, values)], shared axes."""
    width, height, left, bottom, top = 320, 150, 40, 18, 6
    values = [v for _, column in series for v in column]
    low, high = min(values), max(values)
    if high - low < 1e-9:
        low, high = low - 1.0, high + 1.0
    pad = 0.06 * (high - low)
    low, high = low - pad, high + pad
    t0, t1 = t[0], t[-1] if t[-1] > t[0] else t[0] + 1.0

    def sx(value):
        return left + (value - t0) / (t1 - t0) * (width - left - 4)

    def sy(value):
        return top + (high - value) / (high - low) * (height - top - bottom)

    step = max(1, len(t) // 240)  # keep the file small
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img">',
             f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}"/>',
             f'<line class="axis" x1="{left}" y1="{height - bottom}" x2="{width - 4}" y2="{height - bottom}"/>',
             f'<text class="tick" x="{left - 4}" y="{top + 9}" text-anchor="end">{_number(high, 3)}</text>',
             f'<text class="tick" x="{left - 4}" y="{height - bottom}" text-anchor="end">{_number(low, 3)}</text>',
             f'<text class="tick" x="{left}" y="{height - 4}">{t0:.1f} s</text>',
             f'<text class="tick" x="{width - 4}" y="{height - 4}" text-anchor="end">{t1:.1f} s · {unit}</text>']
    for css, column in series:
        points = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a, b in zip(t[::step], column[::step]))
        parts.append(f'<polyline class="{css}" points="{points}"/>')
    return "".join(parts + ["</svg>"])


def _rms_cards(before: dict, after: dict) -> str:
    rows = [("Position RMS, all axes", "position_mm", "mm"), ("Attitude RMS, all axes", "attitude_deg", "°"),
            ("Height RMS", "height_mm", "mm"), ("Roll/pitch RMS", "tilt_deg", "°")]
    return '<div class="cards">' + "".join(
        f'<div class="card"><span class="mute">{label}</span><b>{before[key]:.2f} → {after[key]:.2f} {unit}</b>'
        '<span class="mute">before → after the fit</span></div>' for label, key, unit in rows) + "</div>"


def render(result: dict, hidden: dict | None = None, title: str = "Sesame sim-to-real calibration") -> str:
    """HTML for ``FitResult.to_json()``; ``hidden`` adds the true values of a synthetic run."""
    evidence = result["evidence"]
    names = ", ".join(html.escape(run["name"]) for run in result["runs"])
    if evidence == "synthetic":
        banner = ('<div class="banner">Synthetic data. This report validates the pipeline only: the "measured" '
                  "tracks were generated by simulation with hidden parameter changes. No robot was measured.</div>")
    else:
        banner = (f'<div class="banner measured">Fitted from measured run(s): {names}. Values hold for this robot, '
                  "this floor and these motions.</div>")
    out = ["<!doctype html><html lang=en><meta charset=utf-8>",
           '<meta name=viewport content="width=device-width,initial-scale=1">',
           f"<title>{html.escape(title)}</title><style>{CSS}</style>",
           f"<h1>{html.escape(title)}</h1>", banner,
           f'<p class="mute">Runs: {names} · {result["samples"]} compared samples · '
           f'{result["evaluations"]} simulated rollouts.</p>',
           "<h2>Simulation versus measurement</h2>", _rms_cards(result["rms_before"], result["rms_after"]),
           '<p class="mute">The fit matches height, roll and pitch. Forward/sideways position and yaw are shown and '
           "counted in the all-axes numbers but not fitted: they accumulate foot slip, which changes with tiny "
           "differences in both the simulator and the real floor.</p>",
           "<h2>Parameters</h2><div class=scroll><table><tr><th>Parameter<th>Nominal<th>Value"]
    if hidden:
        out.append("<th>Hidden truth")
    out.append("<th>Notes</tr>")
    for p in result["params"]:
        value = _number(p["value"])
        if p["std"] is not None and not math.isnan(p["std"]):
            value += f' ± {_number(p["std"], 2)}'
        truth = ""
        if hidden:
            key = p["name"].split("[")[0]
            shown = hidden.get(p["name"], hidden.get(key))
            truth = f'<td class=n>{_number(shown) if shown is not None else "= nominal"}'
        notes = " ".join(filter(None, [p["physical"], p["note"]]))
        out.append(f'<tr><td class=p>{html.escape(p["label"])}<br>'
                   f'<span class="badge {BADGES[p["status"]]}">{html.escape(p["status"])}</span><br>'
                   f'<span class=mute>{html.escape(p["unit"])} · {html.escape(p["semantics"])}</span>'
                   f'<td class=n>{_number(p["nominal"])}<td class=n>{value}{truth}<td>{html.escape(notes)}</tr>')
    out.append("</table></div>")
    out.append('<p class="mute">Nominal = the value in the current model or manifest; none of those has been '
               "measured. ± is one standard deviation from the fit and assumes the model structure is right.</p>")
    for run in result["runs"]:
        out.append(f'<h2>Run “{html.escape(run["name"])}”</h2>')
        out.append(f'<p class="mute">Position RMS {run["rms_before"]["position_mm"]:.2f} → '
                   f'{run["rms_after"]["position_mm"]:.2f} mm, attitude RMS {run["rms_before"]["attitude_deg"]:.2f} → '
                   f'{run["rms_after"]["attitude_deg"]:.2f}°. Torso motion relative to the rest pose at the start; '
                   f'video-to-command offset {run["time_offset_s"]:+.3f} s.</p>')
        out.append('<p class="key mute"><span><i style="color:var(--meas)"></i>measured</span>'
                   '<span><i style="color:var(--before);border-top-style:dashed"></i>simulated, before</span>'
                   '<span><i style="color:var(--after)"></i>simulated, after</span></p><div class=grid>')
        for label, unit, column, factor in CHANNELS:
            series = [(css, [row[column] * factor for row in run[key]])
                      for css, key in (("meas", "measured"), ("before", "before"), ("after", "after"))]
            fitted = "fitted" if column in FITTED_CHANNELS else "not fitted"
            out.append(f"<figure>{_chart(run['t'], series, unit)}<figcaption>{label} · {fitted}</figcaption></figure>")
        out.append("</div>")
    if result["notes"]:
        out.append("<h2>Notes</h2>" + "".join(f"<p>{html.escape(note)}</p>" for note in result["notes"]))
    return "\n".join(out) + "\n"

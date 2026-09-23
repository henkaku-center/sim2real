# OLED, switch and battery harnesses

Research and proposed representation: 2026-09-24. This is preparation for the
next native CAD stage; the existing assembly has not been modified by this audit.

## Proposed native representation

Use three logical harness groups, independent of whether the physical housing
uses individual sockets, a four-way shell, or two two-way shells:

| Harness | Carrier endpoints | Remote endpoints |
|---|---|---|
| OLED | M12 GND/black, M13 VCC/red, M14 SCL/green, M15 SDA/blue | OLED terminals by printed signal name; physical terminal order must be observed |
| Switch | X15 battery-positive side, X14 converter-input side | Two SPST terminals |
| Battery | X16 positive, X17 negative | Existing battery connector through its mating lead/adapter |

The completed carrier diagram establishes X16–X15, X14–O17 and X17–V17.
Switch wiring therefore runs from battery-positive X15 through the external
switch back to X14 and converter input O17. Wire color does not define polarity.

Each harness should contain:

1. Rigid connector shells and contacts as separate native objects, with pin
   identities and a terminal coordinate frame for each contact.
2. One editable three-dimensional centerline per conductor; circle sweeps for
   the conductor and insulation. Route ends anchored to the terminal frames,
   with short straight exits and editable smooth bends/service loops.
3. Separate stripped ends, crimp or solder terminations and heat-shrink where
   these actually occur. Do not assume a PCB female strip is the cable socket.
4. Recorded physical wire length, diameter, color, endpoint names and evidence.
   Until measured, route length and slack are design assumptions. Moving an
   enclosure-mounted part must not silently imply a physically longer cable.
5. A disconnect state for instructional animation: the cable-side plug moves
   with its harness, while the carrier male header stays fixed. Keep native
   InstructionIds stable; later animation can change the route shape rather
   than pretending a flexible cable is a rigid assembly member.

First place the OLED, switch and battery as independently movable components.
Use provisional cable routes while choosing enclosure positions, then constrain
routes to measured lengths. Include connector withdrawal space, switch lever and
panel hardware envelopes, OLED viewing area and a battery removal path.

## Exact purchased components

Canonical purchase identities are in APS `docs/ii/inventory/data.json`.
All three exact Amazon pages were fetched during this research. None supplied
a usable CAD download in the inspected content. General searches and candidate
repositories have not established an exact-ASIN model; this does not prove none
exists.

| Component | Exact purchase | Evidence and CAD result |
|---|---|---|
| OLED | [B08CTZVVLS](https://www.amazon.co.jp/dp/B08CTZVVLS) | Listing confirms 0.96-inch, four-pin I2C SSD1306, white display. Earlier inspected dimension image gives 25.4 × 26.1 mm PCB and 22 mm horizontal mounting span. Two downloaded generic SSD1306 STEP candidates are not exact matches. |
| Switch | [B0G9M71BBS](https://www.amazon.co.jp/dp/B0G9M71BBS) | Listing confirms two-terminal ON/OFF toggle. Previously inspected image gives approximately 13 × 8 mm body and 33 mm overall. No exact model established. Do not substitute MTS-102/SPDT or a slide switch. |
| Battery | [B0F3JB59B6](https://www.amazon.co.jp/dp/B0F3JB59B6) | Exact listing confirms 7.4 V, 1000 mAh, 2S Li-ion, 51 × 28 × 14 mm and 47 g; connector called only “JST”. No exact CAD found. Prefer an original editable external-envelope model over an unrelated same-capacity pack. |

## Downloaded and checked candidates

Source files are cached locally under `assets/cad/upstream/external-peripherals/`.
Revisions, hashes and geometry details are versioned in
`assets/cad/reports/external-peripheral-candidates.json`.

- [Lucasmoidel/pico-rand](https://github.com/Lucasmoidel/pico-rand/blob/29eee73f5933854b3647caf73e573f7d5364ad77/pcb/ssd1306.step):
  one valid solid, overall 28 × 28 × 11.25 mm, no circular-edge geometry found.
  Too simplified/dimensionally different to accept as the purchased OLED.
- [mikeysklar/kicad-parts](https://github.com/mikeysklar/kicad-parts/blob/00a5dbb9fa79e9a062a3817c039e4682bab80aee/3dmodels/lightblue-ssd1306-ssd1306.step):
  one valid solid, 25 × 27 × 3.52 mm. Header-hole positions are irregular
  (approximately 2.542, 2.590 and 2.539 mm between neighboring centers), so it
  should not drive the purchased module's connector or enclosure dimensions.
- [FreeCAD-library mini toggle 1P2T](https://github.com/FreeCAD/FreeCAD-library/tree/be5e71491051cef75da46831b6fd77c6313cb497/Electronics%20Parts/Switch/Mini%20toggle%20switch%201P2T):
  STEP and native FCStd available, but audited body is 8.6 × 3.9 × 4 mm and has
  three PCB terminals. Reject for the purchased two-terminal panel toggle.

A [3D ContentCentral MTS mini-toggle entry](https://www.3dcontentcentral.com/download-model.aspx?catalogid=171&id=1235647)
surfaced in search with selectable CAD formats/login required. Direct retrieval
timed out; geometry, exact variant and download terms remain unverified. This is
only a lead, not a validated candidate.

The [JST RCY manufacturer page](https://www.jst-mfg.com/product/detail_e.php?series=521)
is a connector-family reference if the installed battery plug is confirmed as
RCY. The seller's generic “JST” wording does not establish RCY, PH, XH or another
series. Neither pitch nor shell sex should be inferred from the word alone.

Downloaded community STEP files remain local comparison assets; their presence
in a repository is not an established redistribution license for our assembly.

## Information needed to finish the physical model

- A close-up of both ends of the OLED lead and of the X-header plugs, showing
  whether housings are separate or combined and the wire order.
- Battery plug and mating-adapter close-up, with pitch or a scale if available.
- Switch termination details: soldered leads/heat-shrink versus removable contacts.
- Approximate actual lead lengths; component placements can remain provisional
  until the enclosure layout is chosen.

Existing album photographs remain supporting evidence; these details were not
established from the earlier album review. These questions concern installed
construction, not permission to use a nominal connector reference.

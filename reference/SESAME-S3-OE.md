# Query OE from the current design

```sh
python3 tools/circuit.py query hub.OE
python3 tools/circuit.py query s3.GPIO7
python3 tools/circuit.py path hub.OE s3.GPIO7
uv run python tools/check_design.py
```

External connections and explicit no-connect evidence belong to the current
routing records and `manifest/circuit-annotations.json`. Firmware assignments
are a separate graph layer. Query those records rather than inferring wires,
pull-ups, module bias or physical acceptance from prose.

Earlier OE wiring proposals are retained in Git history, not as current build
requirements. The graph is displayed through coloured conductors and temporary
obstruction transparency in the existing build guide's final wiring step.

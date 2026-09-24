# Historical CAD construction recipes

These scripts record how the original carrier, imported component candidates,
headers, solder and wiring were constructed. They preserve dimensional and
operation-level information for future animated instructions.

**To open the current model, use `../open_cad.FCMacro`.** The authoritative file is
`assets/cad/Sesame-S3-Assembly.FCStd`; these recipes are not a regeneration pipeline
and must not be run over current native edits.

The old carrier and comparison filenames in these scripts describe their original
inputs. Those separate documents were consolidated by `consolidate_cad.py` on
2026-09-24. Source hashes are embedded in `AssemblyMetadata` and retained in the
current instruction snapshot. Some source candidates were local uploads; the
assembly embeds their geometry and does not depend on those separate files.

Active opening, snapshot export and geometry checks live directly under `tools/`.

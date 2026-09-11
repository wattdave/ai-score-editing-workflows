# Bridge Development

Read this file when changing the ManuScript bridge or recovering from a bridge
version mismatch.

- The installed bridge is built from
  `src/sibelius_websocket_cli/manuscript/sibwscli.plg`.
- After `install-plugin`, the user must restart Sibelius before the new plug-in
  code is loaded.
- Batch plug-in edits together and update `GetBridgeVersion` when the bridge
  contract changes, because every plug-in update requires that restart.
- Use `docs/manuscript-object-tree.md`, `docs/manuscript-constants.md`,
  `docs/commands.md`, and `SPEC.md` as the local API authority. Known guide
  discrepancies include `utils.CalculateDegree` and `return_value` versus
  `returnValue`.
- Exercise bridge changes against a scratch copy of a score before using a real
  score.

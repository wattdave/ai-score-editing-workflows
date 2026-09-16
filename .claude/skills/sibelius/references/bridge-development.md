# Bridge Development

Read this file when changing the ManuScript bridge or recovering from a bridge
version mismatch.

- The installed bridge is built from
  `src/sibelius_websocket_cli/manuscript/sibwscli.plg`.
- After `install-plugin`, restart Sibelius before the new plug-in code is
  loaded. The agent can do this end-to-end through the Sibelius application
  menu: choose **Sibelius → Quit Sibelius**, confirm it has exited, then let
  the CLI relaunch it for the next score command. Do not delegate this routine
  restart to the user unless a save/discard choice requires their direction.
- Batch plug-in edits together and update `GetBridgeVersion` when the bridge
  contract changes, because every plug-in update requires that restart.
- Use `docs/manuscript-object-tree.md`, `docs/manuscript-constants.md`,
  `docs/commands.md`, and `SPEC.md` as the local API authority. Known guide
  discrepancies include `utils.CalculateDegree` and `return_value` versus
  `returnValue`.
- Exercise bridge changes against a scratch copy of a score before using a real
  score.

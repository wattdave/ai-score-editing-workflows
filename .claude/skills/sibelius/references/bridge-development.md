# Bridge Development

Read this file when changing the ManuScript bridge or recovering from a bridge
version mismatch.

- The installed bridge is built from
  `src/ai_score_editing/manuscript/sibwscli.plg`.
- After `install-plugin`, restart Sibelius before the new plug-in code is
  loaded. The agent can do this end-to-end through the Sibelius application
  menu: choose **Sibelius → Quit Sibelius**, confirm it has exited, then let
  the CLI relaunch it for the next score command. Do not delegate this routine
  restart to the user unless a save/discard choice requires their direction.
- Batch plug-in edits together and update `GetBridgeVersion` when the bridge
  contract changes, because every plug-in update requires that restart.
- Use Avid's ManuScript Language Guide and `SPEC.md` as the API authority.
  `docs/avid-reference.md` links the guide, maps chapters to the gitignored
  local transcriptions (`docs/manuscript-object-tree.md` and others; use
  them when present), and lists where the guide is wrong, including
  `utils.CalculateDegree` and `return_value` versus `returnValue`.
- A method lives on the object whose section lists it in the guide's
  Object Reference (for example `CurrentTimeSignature` is on
  `SystemStaff`, not `Score`). The lint test does not check receivers, and a
  wrong one fails only at runtime with "Unknown method".
- A timeout followed by `busyError` usually means a ManuScript runtime error
  dialog is blocking Sibelius. Screenshot it, report the error, and ask the
  user to dismiss it; writes made before the failing line persist.
- Exercise bridge changes against a scratch copy of a score before using a real
  score.

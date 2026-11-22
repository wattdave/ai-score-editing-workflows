# Sibelius 2026 API review and plan

Reviewed 2026-11-22 against the ScoreBridge plug-in at bridge v64. The
installed Sibelius is 26.11. Avid has published a *ManuScript Language
Guide* for 2026.11 (dated 11/16/2026), but no 2026.11 release notes could be
found on avid.com yet. The newest release page is 2026.8 (August 20, 2026).

## Sources

- [ManuScript Language Guide 2026.11](https://resources.avid.com/SupportFiles/Sibelius/2026.11/ManuScript_Language_Guide.pdf),
  compared with the
  [2026.6](https://resources.avid.com/SupportFiles/Sibelius/2026.6/ManuScript_Language_Guide.pdf),
  [2026.2](https://resources.avid.com/SupportFiles/Sibelius/2026.2/ManuScript_Language_Guide.pdf) and
  [2024.8](https://resources.avid.com/SupportFiles/Sibelius/2024.8/ManuScript_Language_Guide.pdf)
  editions. Every identifier in each edition was listed and the lists were
  diffed, so additions are complete; changed wording of existing entries
  was not compared.
- Release pages: [February 2026 (2026.2)](https://www.avid.com/resource-center/sibelius-february-2026-release),
  [May 2026 (2026.5)](https://www.avid.com/resource-center/sibelius-may-2026-release),
  [June 2026 (2026.6)](https://www.avid.com/resource-center/sibelius-june-2026-release),
  [August 2026 (2026.8)](https://www.avid.com/resource-center/sibelius-august-2026-release).

## What is new since the guide this repository was checked against

"First in" is the first compared edition that has it: 2026.2 means added
after 2024.8 (the 2025 editions were not compared), 2026.11 means added
after 2026.6 (2026.8 has no guide at the usual address).

| First in | Addition | Where in the guide |
| --- | --- | --- |
| 2026.2 | `Score.AutoRespaceEnabled` (read/write; Auto-Respace Note Spacing) | Score, Variables |
| 2026.2 | `Score.CustomParts` (DynamicPartCollection in custom order, read only) | Score, Variables |
| 2026.2 | `Sibelius.GetCurrentScoreViewType()`: `ViewTypePage` (0) or `ViewTypePanorama` (1) | Sibelius, Methods |
| 2026.2 | `Sibelius.RestoreOriginalItemAfterSingleBarSelection` (preference, read/write) | Sibelius, Variables |
| 2026.2 | Command IDs `activate_deactivate_staff_filter`, `staff_filter_voice_1`..`4`, `staff_filter_player_1`/`2`, `notate_glissando_chromatic`/`diatonic` | Command IDs |
| 2026.6 | `EngravingRules.CrossStaffAccidentals`, `AvoidCrossStaffBeamCorners`, `CrossStaffHideBarRests` | EngravingRules |
| 2026.6 | `InstrumentType.StartingFretOfNthString`, `SetStartingFretOfNthString` (tablature) | InstrumentType |
| 2026.11 | Sibelius Connect **Keypad State**: `getKeypadState` (one `command` or all 79), `subscribeKeypadState`, `unsubscribeKeypadState` | Sibelius Connect |
| 2026.11 | Command IDs `toggle_metronome_on_off`, `change_order_parts`, `AudioEngineOptions` | Command IDs |

Nothing new touches lyrics, text, notes or the playback sound objects
(`SoundInfo`, `Staff.SetSoundID`), and the Connect handshake, `invokeCommands`
and `invokePlugin` sections are unchanged apart from the Keypad State
section. The guide still shows `return_value` in its example; the field is
`returnValue`.

## Candidates

Effort: S is under a day, M one to three days, counting tests and a live
check. "Bridge bump" means a new `GetBridgeVersion`, `install-plugin` and a
Sibelius restart.

1. **Mixer state check in the audio commands** (done in this change).
   Read `Staff.MuteMode`, `Solo`, `Volume`, `Pan` (Staff, Variables; all
   documented and already in the Staff query allow-list since bridge v62)
   and warn in `playback-sounds`, `export-stem` and `rehearsal-mixes` about a
   muted or half-muted staff, a fader at 0, or Solo left on. S, no bridge
   bump. It only warns: the guide does not say whether `SaveAsAudio` honours
   Mute or Solo.
2. **Set Mixer state** (`set-staff-mixer` batch operation or a `mixer`
   command): write `Staff.MuteMode` (`Muted` 0, `HalfMuted` 1, `NotMuted` 2),
   `Solo`, `Volume` (0-127), `Pan` (-100 to 100), `Distance` (reverb %), all
   documented read/write. Use: unmute a staff before an export, an a cappella
   copy without the piano. S plus bridge bump. **Live probe first:** whether
   one undo reverts a Mixer change made in `invokePlugin`, and whether
   `SaveAsAudio` honours Mute/Solo (export one staff muted and compare).
   A Sibelius MCP tool should reuse the MuseScore `set_staff_playback`
   parameter names (`staves`, `play`, `voices`) or `test_mcp_parity.py` needs an
   entry.
3. **Set a staff's playback sound** (Cantai assignment): `Staff.SetSoundID(soundID)`
   and `Staff.SetSound(styleID[, set SoundStage])` (Staff, Methods). Would
   remove the manual Cantai set-up before each rehearsal-mix batch, copying
   the `actualSoundId` that `playback-sounds` reports from a staff that is
   already right. M plus bridge bump. **Live probe first:** which sound ID
   strings Cantai accepts, whether `SetSoundID` beats a Mixer override
   (`SoundIdOverrideIfAny`), and whether the change is undoable.
4. **Auto-Respace / Auto-Optimize switches in `set-layout`**:
   `Score.AutoRespaceEnabled` (2026.2) and `Score.AutoOptimizeEnabled`
   (Score, Variables, read/write); add to `LayoutRead` and `set-layout`, so
   `auto-layout` can report and set them. S plus bridge bump. Documented
   well enough to implement; a check on a scratch score that the menu
   options follow is still wise because `set-layout` already has ordering
   quirks.
5. **Click track for rehearsal mixes**: command ID `toggle_metronome_on_off`
   (2026.11). Its state cannot be read (the Keypad State list may or may not
   include it), and whether `SaveAsAudio` records the click is not
   documented. **Live probe only;** not worth implementing blind.
6. **Keypad state read** (`getKeypadState`, Sibelius Connect, 2026.11): a
   read-only message outside the plug-in, so no bridge bump. Could show the
   active note value or articulation before an `invoke` that depends on it.
   The reply's shape and the 79 property names are not documented. **Live
   probe** with `sibelius-cli raw '{"message":"getKeypadState"}'` on a
   scratch session, then decide. S after the probe; value is low for choir
   work.
7. **Reset space around staves**: `Staff.ResetSpaceAroundStaff(above, below[, from bar[, to bar]])`
   (older API, not in the bridge). A batch operation for the lyric-spacing
   step of score polishing, next to `hide-empty-staves`. S plus bridge bump;
   documented well, check on a scratch score.
8. **Page or Panorama view in `inspect`**: `Sibelius.GetCurrentScoreViewType()`.
   Low value (exports do not depend on it). S plus bridge bump; do it with
   another bump, not on its own.

Not worth doing for choir work: `Score.CustomParts`, the cross-staff
engraving rules (piano accompaniments only), the tablature fret methods,
`change_order_parts`, the staff-filter commands, and `AudioEngineOptions`
(opens a dialog).

## Order

Probe 2 and 3 together on one scratch score (one Sibelius restart covers
both), then implement 2, 3 and 4 in one bridge bump (v65). 7 and 8 can ride
along. 5 and 6 stay probes until someone needs them.

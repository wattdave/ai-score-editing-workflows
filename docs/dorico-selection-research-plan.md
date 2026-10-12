# Dorico selection research plan

Status: Phase 0 done (2026-10-11); Phase 1 partly done (Smith, Liszt, Sohn, Akinola); Phases 2-3 open. PR #88 (delete-bars on all
back ends) is merged.

## Why

Several Dorico edits act on "the selection", and a range of bars is the
useful unit. PR #88 found that selecting an exact number of bars is not
obvious (a tie over a barline pulls the next bar in, `Edit.SelectMore` is not
a fixed step) and built one tool for it, `score._extension_plan`, used by
`delete-bars` and `copy-passage`. This plan widens that in two directions:
check the rules beyond the one score they were measured on, and find out
which other commands can serve repository operations through a range
selection.

## What is known (from PR #88)

Measured on a copy of the Fugue 16 example, Dorico 6.2.31. See "Selecting
bars" in `docs/dorico.md`.

- A selection holds whole items of one staff. `Edit.DeleteBars` removes every
  bar it touches.
- `EventEdit.NavigateRightExtendBar` moves the end to the next barline, then
  pulls in every item of that staff starting before it, whole.
- Replaying that on the events read predicted 24 of 24 trials, and
  `copy-passage` is exact on five ranges where the old recipe lost 5 notes on
  one.
- The Remote Control API reports nothing about extent, so extent is measured
  by effect: select, run the command, read through Lua, undo.

Not known: anything about other time signatures, pickups, multi-staff
selections, lyrics, tuplets, or any command other than `DeleteBars`, `Copy`
and `Paste`.

## Method

The harness used so far (`seltest.py` and `copytest.py` in a scratchpad)
selects, runs a command, reads the events through Lua (`read_partial`, no
MusicXML export), compares with a baseline, and undoes until the events match
the baseline. Reads through the `dorico-cli` commands export MusicXML through
UI scripting and are slow and visible, so research uses the harness only.

Ground rules:
- Work on a copy of a project in the scratchpad, never the user's score.
- Never save. Undo to the baseline after every trial, and stop if it fails.
- `dorico-cli undo` takes at most 20 steps per call.
- Record each result as a table row: recipe, bars or items affected, undo
  steps, restored yes or no.
- Do not restart Dorico without asking while the user is present.

## Phase 0: make the harness a script in the repo

Goal: `scripts/dorico_selection_probe.py`, so every later phase is
repeatable and a Dorico upgrade can re-run it.

- Takes a project, a recipe (a list of commands with placeholders for an
  item or bar) and a measure: removed events, added events, changed
  properties, or undo steps.
- Reads event blocks from `bridge.overview(flow)["layout"]["blocks"]`.
- Maps voice streams to staves with the existing placement probe, not a
  hard-coded table.
- Adds the rules to `scripts/dorico_upgrade_check.py`, or a sibling, so a
  Dorico update that changes selection behaviour is noticed.

Done when: the five PR #88 ranges and 24 delete trials reproduce from the
script on the Fugue 16 copy.

Done: `scripts/dorico_selection_probe.py` has `bars` (model against measured
`Edit.DeleteBars`), `copy` (planned and, with `--old`, the old recipe) and
`run` (any command after a planned selection; measures removed, added or
changed events and the undo steps). On the Fugue 16 copy: 32 of 32 delete
trials predicted, five of five planned copies exact, the old recipe loses 5
notes on bars 6-9. Staff placement comes from `service.snapshot`, and the
Upgrade checklist step 6b runs it. Not done: property comparison beyond
position, duration, pitch, type and stream.

## Phase 1: widen the rules

Question: do the PR #88 rules hold on other scores, and where do they break?

| Case | Score | What to look for |
| --- | --- | --- |
| Changing time signatures | Liszt Liebestraume; Las Posadas (3/4, 2/4, 6/8) imported from MusicXML | the planner uses `BarMap.position` and `locate`, so bar lengths should be fine; check |
| Pickup bar and split bars | `tests/fixtures/dorico-pickup-split-bars.musicxml` | whether "bar 1" is the pickup and how the selection treats it |
| Lyrics and a choir | Smith Preces and Responses | lyrics are events in the stream; do they change the extent or `DeleteBars`? |
| Several staves in one selection | Wiese Unshaken (large) | does an extend from a note on staff 1 reach other staves? PR #88 only saw one staff matter |
| Tuplets, grace notes, cross-staff notes | Akinola Prelude | items with zero or odd durations in the "ends before the barline" test |
| Staff silent in the range | any | anchor choice when no note starts the range |
| Bar rests and multirests | any | the "full bar on the first step" rule, and consolidated bars |
| Repeats, endings | Sohn Triumphant | do repeat barlines act as barlines for the step? |

Output: a table of predicted versus measured extents per score, and an
update to the rules in `docs/dorico.md`. A mismatch means the model or its
scope changes (for example "items of the staff" may really be "items of the
selected voices").

Done when: the model predicts at least 95% of trials on every score tried
or each miss has a documented cause.

### Phase 1 results so far (2026-10-11)

Liszt Liebestraume (pickup bar, then 6/8, 1536 per bar; two Piano staves),
`bars --bars 5,20 --steps 6` and a one-step scan of every bar of staff 1.

- Counting only notes and rests, the model is right everywhere except two
  barlines. Counting every event was wrong: a line or slur crossing the
  edit is re-created with a new id, so it looked "removed" from the bar
  before. `Edit.DeleteBars` bars-removed must be measured from notes and
  rests (the script now does).
- Misses: a selection whose extend step reaches the end of **bar 8** goes on
  into bar 9 (bar 6 with 3 steps, bar 7 with 2, bar 8 with 1: all end in 9),
  and one reaching the end of **bar 18** goes on to bar 20. Both staves
  show it, so it is not one staff's items. The events show nothing crossing
  either barline (checked all streams, notes, rests, lines). Staff 2 has
  same-pitch notes meeting at the bar 8/9 barline, but the MusicXML export
  has no tie there, and treating same-pitch notes as tied, or pulling in
  every staff's items, did not fix the prediction (`--scope`, `--ties`).
  Cause not found. Next: look at the project in Dorico (the Properties
  panel on the notes at those barlines, system/frame breaks, a bar
  repeat or multi-bar region) and test whether it depends on the layout.
- **Smith Preces and Responses** (flow 2: five choir staves, a pickup, 3
  bars, lyrics): the first run missed 7 of 30. A melisma lyric event
  ("forth_") runs past a barline and drags the next bar in, and a step past
  the flow's last bar stops there. With both rules the model predicted 30
  of 30, and `plan` showed `score._extension_plan` exact on all 6 ranges
  once it counted lyric events (fixed in the same change, with a test).
- **Akinola and Sohn could not be read, and now can.** Two bugs in this
  repository's back end, not Dorico's. (1) The placement probe made a
  dynamic on a note to see which staff it landed on, but where a dynamic
  already sat at that position (a tutti `p` at the start of most voices)
  Dorico changed it in place and nothing new appeared, so the probe gave
  up on the first voice. It now uses a note at a position with no dynamic
  on any staff and leaves a voice unplaced when it has none. (2) Dorico
  lists instruments in id order, not score order (Sohn: Tubular Bells
  before the other percussion; unplayed percussion instruments with no
  notes), so neither the strict placement reading nor matching the
  MusicXML parts by order works. When both fail, staves are now named from
  the voices probed onto them (`layout.resolve(..., loose=True)`); a staff
  with nothing probed has no name.
- **Planner against `Edit.DeleteBars`** (`plan --span 2`, every range of
  1-2 bars): Smith 6/6, **Sohn 60/65**, **Akinola 96/103** (7 misses, and 6 ranges
  with no plan: bars 1, 2 and 48 hold no note or rest event on any staff,
  so there is nothing to select; the bars are probably empty or covered by
  a multi-bar rest).
  Misses are all overshoots, like Liszt's: the plan's last bar is reached
  but more bars are removed (Sohn 2-3 removed 2-8, 6-7 removed 6-10;
  Akinola 52-53 removed 52-55), or nothing is removed (Sohn 1-2 and 13-14
  on staff 25: only rests? "measured None" counts notes and rests only).
  Cause not yet found; Sohn bars 2-8 look like a multi-bar rest or
  consolidation, which the model does not know about.
- **Part layouts and player names (2026-10-11).** The Export MusicXML
  dialog lists one layout per player, named `NN_<player name>`. NN is the
  player's place in the score, not the instrument id: for the first 28
  instruments of Sohn it equals id + 1, but players added later (the third
  trumpet, horns 3 and 4, percussion, Tubular Bells) sit mid-score with
  ids far from their NN. The bridge's instrument `name` is the player's
  name, so a player with several instruments (a percussion kit) repeats it.
  Player names were unique in all five scores tried (Fugue, Liszt, Smith,
  Akinola, Sohn), but **Dorico allows two players with the same name**:
  `Project.Player.Duplicate` (Setup mode) numbers the copy ("Piano 1",
  "Piano 2"), and `Project.Player.Rename?PlayerID=<n>&Name=<text>` (the
  text is taken literally, no URL decoding) then set both to "Piano 1". The
  export dialog showed `01_Piano 1` and `02_Piano 1`, and the bridge two
  instruments named "Piano 1". So any join on player name must refuse a
  name that appears twice; NN stays unique.
- **One-figure test scores** (`scripts/make_selection_fixtures.py`, a
  two-staff piano in 4/4 imported from MusicXML; each figure sits alone in
  its bars between control bars): a tie over one barline, a whole note held
  over three bars, a grace note before the downbeat, eighth triplets, a
  lyric melisma over a barline, three empty bars on both staves, a staff
  silent for two bars while the other plays, the same ties and long notes on
  the second staff only, and bars that open with a half rest or a quarter
  rest so the first note starts late. 216 + 54 `bars` trials, 4 steps from
  each bar: **all predicted.** So none of these figures, alone, causes the
  Sohn, Akinola or Liszt overshoots. Two fixes came out of it: (1) bars
  that hold no events (empty bars) are invisible to a measure that looks at
  vanished notes, so the probe now counts removed bars by how far the later
  events moved up; (2) only items that start inside the selection are pulled
  in: a lyric extender that began before the anchor is not (the planner now
  agrees).
- **The real-score overshoots are still unexplained.** Sohn's viola (staff
  3) and piccolo (staff 8) misses are at bars 2, 4, 6, 8 and 13 (steps go 1
  to 2 bars too far); the strings' rows around two-bar notes are suspects but
  the synthetic equivalents pass. Liszt's bar 8 and bar 18 barlines are
  unchanged by the new measurement. Candidates not yet tested in isolation:
  several voices on one staff (rests in the second voice), cue notes,
  divisi or section players, hidden or condensed staves (many Sohn staves
  answer `kCommandNotAllowed` when selected, probably because they are
  hidden in the full-score layout), and notes shortened rather than removed
  when `Edit.DeleteBars` crosses them (so the extent read from vanished ids
  can be off).
- The probe's setup was hit twice by races in the export dialog scripting
  (`entire contents` while a dialog closed); those scripts are now wrapped
  in `try`.
- Not yet run: the pickup fixture, Las Posadas, Wiese, a look at the Sohn and Akinola misses, the rest of Smith's
  flows (most are one bar). Opening a project from an older Dorico shows a
  "will be updated" dialog (OK button, drive it with osascript) and the
  open can then take minutes. After it opens, raise its window (Dorico
  frontmost, then AXRaise) so the Remote Control API addresses it.

## Phase 2: other commands, one at a time

For each: select a range with the PR #88 planner, run the command, measure
the effect, undo. Results are yes, partly or no, with the reason.

Order by value to the existing Sibelius-style operations:

1. `Edit.TransposeSelection`. Serves `transpose`. Questions: does it ask for
   an interval through a dialog or a parameter? Does it move key signatures
   in the range? How does it spell notes compared with the Lua approach in
   `bridge.lua`?
2. `Edit.AddBarNumberChange` and `Edit.AddBarNumbersToSelection`. Serve
   `set-bar-number`, which is refused on Dorico (`NOT_ON_DORICO`). Question:
   is there a command form that avoids the dialog?
3. `Edit.SplitFlowAtSelection`. Would serve splitting a long piece, for
   example a verse boundary. Questions: what is split, what happens to the
   time signature and key at the split, how many undo steps?
4. `Page.MoveBarsToNextSystem` and `Page.MoveBarsToPreviousSystem`. Serve a
   "keep these bars together" layout request. Question: does a bar range
   work, and does the result show up in Lua reads at all?
5. `Edit.ChangeBarConsolidation` and `Edit.ToggleBarConsolidation`
   (multirests).
6. `Edit.Cut`, as the delete-and-keep-the-clipboard variant of `delete-bars`.
7. `NoteInput.CreateBarRepeatRegion`, `NoteInput.AddRepeatsToSelection`.

Each item gets a short section in `docs/dorico.md` with the measured
behaviour, the undo-step count, and what the operation would look like in the
batch format. Commands that need a dialog, or a parameter the command list
does not document, are recorded as blocked rather than guessed at.

Done when: each listed command is marked yes, partly or no with evidence,
and the top two or three have a proposed operation.

## Phase 3: consolidate

- Move `_extension_plan` out of `score.py` into its own module
  (`dorico/selection.py`) with the harness's rules as tests, so every
  range-based operation shares it.
- Decide whether `copy-passage` should accept ranges across several staves
  (it currently resolves one op per staff).
- Implement the operations Phase 2 supports, each as its own change with
  live checks in the style of PR #88.

## Risks

- Behaviour is validated on Dorico 6.2.31 only; a minor update could change
  it. Phase 0's script is the mitigation.
- Some commands only work through dialogs, which scripting cannot drive.
- Large projects make Lua reads slower; keep probes to one flow.
- Undo restores events but not necessarily every property. The harness
  compares ids and positions only, so a command that changes properties
  needs a property comparison added before it is trusted.

## Out of scope

Sibelius and MuseScore selection behaviour (their back ends select ranges
through their own plug-in APIs and are checked in PR #88), and any change to
the user's real scores.

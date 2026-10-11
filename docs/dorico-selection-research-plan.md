# Dorico selection research plan

Status: Phase 0 done (2026-10-11); Phases 1-3 open. PR #88 (delete-bars on all
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
- Not yet run: the pickup fixture, Las Posadas, Smith, Wiese, Akinola,
  Sohn. Opening a project from an older Dorico version shows a "will be
  updated" dialog (button OK, drive it with osascript) and a progress
  dialog that waits for it; the load of a 1 MB project took about 5 minutes.
- Blocked at 2026-10-11 ~14:00: the Mac's screen locked while the user was
  away, after which Dorico's bridge stopped answering. Resume by unlocking
  and checking Dorico for a dialog.

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

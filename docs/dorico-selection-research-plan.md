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
  the second staff only, a second voice on a staff (half notes under a whole
  note, and a tie over the barline in voice 2 under quarter notes), and bars that open with a half rest or a quarter
  rest so the first note starts late. 216 + 54 + 42 `bars` trials, 3-4 steps from
  each bar: **all predicted.** So none of these figures, alone, causes the
  Sohn, Akinola or Liszt overshoots. Two fixes came out of it: (1) bars
  that hold no events (empty bars) are invisible to a measure that looks at
  vanished notes, so the probe now counts removed bars by how far the later
  events moved up; (2) only items that start inside the selection are pulled
  in: a lyric extender that began before the anchor is not (the planner now
  agrees).
- **Slurs and hairpins are items too (found 2026-10-11, late).** A slur or
  hairpin that starts inside the selection is pulled in with everything it
  spans: `Edit.DeleteBars` then removes every bar it touches. Fixture bars
  51-53 (a slur from bar 51 to bar 53): from bar 50 or 51 one step already
  removes bars through 53; from bar 52 (after the slur starts) it does not.
  A hairpin from bar 40 to bar 42 behaves the same way. Neither is readable
  from Lua, so the probe now takes them from a MusicXML export
  (`bars --slurs`). With that, 30/30 fixture trials are predicted. (An
  earlier "hairpin predicted fine" run was against the wrong project: after
  `open`, check `lastBarWithMusic` in `dorico-cli overview` to see which
  project the API is addressing.) `Edit.Delete` on the selection shows the
  selected notes are exactly what the model says; it is `DeleteBars` that
  removes the extra bars.
- **Sohn, with slurs modelled and export parts matched to staves by name**
  (`bars --slurs`; the export lists parts in score order, Dorico's staves
  are in creation order, so ordinal numbering put slurs on the wrong
  staves): the piccolo is predicted in 12/12 trials, the viola 14/15,
  Violin I 8/9, Double Bass 21/21 (bars 2-15, 1-3 steps). The first step
  now matches everywhere it can be tried. The two remaining misses
  (viola bar 8 and Violin I bar 9, both at 3 steps) are over-predictions:
  measured 12, predicted 14. Slurs were the main cause of the Sohn
  overshoots. Not yet re-run: Liszt and Akinola.
  A slur's end snaps to the start of the whole Dorico note (the export
  splits a note tied over a barline), the slur's last note is selected
  whole (the next step starts from its end), and the bars touched run to
  the last note's start bar.
- **Condensed players refuse the extend step (strong correlation, cause
  not isolated).** In Sohn `EventEdit.Select` works on every staff with
  notes, but `EventEdit.NavigateRightExtendBar` answers `kCommandNotAllowed`
  on Flute 1 and 2, Oboe 1 and 2, Clarinet 1, Bassoon 1, Horn 1 and 2,
  Trumpet 1 and Timpani 1, and works on Violin I, Viola, Double Bass, the
  Piccolo and the Tuba: every refusing staff is one of a pair or group of
  same-family players, every working staff stands alone or is a string
  section. That is what Dorico's condensing would do in the full score.
  Setting the layout's `hideEmptyStaves` to `never` changes nothing, so
  hidden staves are not the cause. For these staves `delete-bars` must use
  its fallback (one bar at a time); a way to turn condensing off for the
  edit has not been tried.
- `DoricoClient` now connects with `ping_interval=None`: the Sohn snapshot
  does a 40 s MusicXML export during which Dorico does not answer
  websocket pings, and the default keepalive closed the connection.
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

### Result: `Edit.TransposeSelection` (2026-10-12) is blocked

With a bar selected, the command opens a modal Transpose dialog (Quality or
Number of Divisions, interval, direction, octaves, key-signature and respelling
options, OK/Cancel). Parameters on the command (`?Interval=2&Direction=kUp`)
were not taken: the dialog opened all the same, and the API call hung until it
was dismissed (the bridge then answered again). Its Cancel button is not in
the accessibility tree; it was closed by clicking at its screen position. Per
this plan that is "blocked", not guessed at. The existing per-note `transpose`
(Lua, diatonic respelling) stays; what the command would add is key
signatures and chord symbols in the range.

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

- **`delete-bars` now tries the plan and falls back (2026-10-12).** A planned
  selection is checked after the fact (a later note must move up by exactly
  the bars removed); on a mismatch or a rejected step it is undone to a
  snapshot of the notes and rests and the bars go one at a time. Unit test
  with a fake client; live on the slur fixture. The model still wants slurs
  (a rejected plan costs an extra delete and undo), and condensed players
  skip straight to the fallback.

- **The slur and hairpin rule, worked out (2026-10-12).** Fixture figures for
  a slur from beat 3 to the first note of the next bar, across several bars,
  onto a whole note, and from a whole note (bars 57-70) isolated it. A slur
  or hairpin that starts inside the selection is pulled in with its span:
  - **Bars touched** run up to just before the line's end position. A slur
    ending on the first note of a bar does not touch that bar (Liszt's
    staff 2 over-predictions).
  - **The next step** starts from the end of the line's last note when the
    line ends inside a longer note (a note tied over a barline, which the
    export splits: Sohn's viola), and from the end position itself when it
    ends on a note's start.
  - **Which staff:** slurs belong to their staff. Hairpins are on staff 1 in
    the export of a piano, and a hairpin of the piano's other staff is pulled
    in only when it starts within the anchor note itself (Liszt staff 2 bar
    18 versus bar 8); lines starting in the stepped-over range are not.
    Octave shifts, brackets and dashes made Liszt worse when modelled; pedal
    lines changed nothing there.
  - Results with `bars --slurs`: fixture 54/54 and 72/72 on other anchors;
    Sohn Violin I, Viola, Piccolo 33/33 (first fixed 7/15 on the viola);
    Liszt 136/138 (122/138 without slurs). Still wrong: Liszt staff 2 bar 17
    at 2 and 3 steps (a hairpin starting in the second stepped bar is
    pulled in there but not at bar 8). Akinola was not re-run with the final
    rule.
  - Export parts are matched to staves by name, since the export lists parts
    in score order and Dorico's staves are in creation order.

- **Hairpins touch the bar after the one they end in when they end on its last
  position (2026-10-12, Akinola).** A slur ending on a barline does not touch
  the next bar, but a hairpin whose stop sits at the end of a bar does (the
  Akinola hairpins at bars 46-47, 49-50 and 53-54 all reached one bar further
  than the slur rule predicted, on every staff). With that, Akinola goes from
  192/370 to 240/370 `bars --slurs` trials (bars 7-53, 1-2 steps, all staves):
  122 trials are the condensed players' `kCommandNotAllowed`, so of the 248 Dorico
  answered, 240 match (97%, from 77%). The 8 left are 2-step trials at
  bars 8, 15, 47 and 52 on Oboe-range staves 11 and 17-19. Liszt is
  unchanged at 136/138. A restart of Dorico was needed first: after many
  projects and window changes the placement probe put every voice of Akinola
  on one staff (cause not found), and a restart cleared it.

- **`delete-bars` live on Akinola (2026-10-12).** Bars 46-47 (the planner's three
  candidate plans on staves 1-3, two extend steps each): every plan overshot by
  a bar (the bar 46-47 hairpin ends at the bar's last position, which the
  planner cannot see), each was undone, and the per-bar route removed exactly
  the two bars: a later note moved up by 3072 as expected, 205 notes went, and
  four undo steps restored all 5561 notes. The result reported
  `"via": "per-bar after the planned selection failed"`, `"attempts": 3`.
  This confirms the retry-and-fallback loop on a real score; the planner would
  need hairpin knowledge (an export read) to get it right first time.

- **`Edit.Cut` (Phase 2, item 6; 2026-10-12): partly, and not what the plan guessed.**
  Cut on a staff's bar selection is *not* a variant of `delete-bars`: it removes
  the selected notes, leaves the bars in place (implicit rests, no events,
  nothing moves) and keeps the notes on the clipboard. Pasting them elsewhere
  keeps the notes' ids (a move, not a copy). So it serves a new `move-passage`
  operation, built on `copy-passage` (same fields; cut for copy; one more undo
  step) and checked by the notes that vanished: the cut notes must be gone and
  every other note of both staves still there (a cut that reached further
  than planned is undone and refused; unit-tested, not provoked on a real
  score). Live: Liszt staff 1 bars 5 and 8 to bars 12 and 20 (10 and 11
  notes), Akinola staff 1 bar 46 to bar 30 (3 notes), each verified and undone
  back to the exact baseline. Selections taken without extend steps did not
  drag the neighbouring hairpins in.

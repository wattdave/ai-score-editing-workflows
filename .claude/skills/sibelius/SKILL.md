---
name: sibelius
description: Apply user-described changes to the score open in Sibelius (transpose, edit lyrics, read notes, etc.) via this repo's CLI. Use when the user asks to inspect or modify a score, e.g. "transpose it into D major", "check the lyrics for spelling errors", "what notes are in bar 3", or "/sibelius".
---

# Driving Sibelius

All interaction goes through `uv run sibelius-websocket-cli ...` (run from the
repo root). It talks to Sibelius Connect on localhost:1898 and, for score
reads/writes, to the bundled `sibwscli` ManuScript bridge plug-in.

## The choreography (always, in this order)

1. **Confirm the target score.** Run `score-info` and check `fileName` against
   what the user means. The bridge acts on the *frontmost* score window;
   with several files open, the wrong one silently gets the edit. If
   `fileName` doesn't match, ask the user to bring the right score to front.
2. **Read before writing.** Fetch the region you're about to change
   (`read`, `read-lyrics`, `score-info`) — both to plan the change and to have
   a before-image for verification. For lyrics, **assess the actual body lyric
   typography in the file first** (export PNG and visually inspect font and size;
   never trust score metadata or paragraph styles blindly).
3. **Write.** Write subcommands (`set-lyric`, `transpose`, `set-key`, …)
   automatically back up first: timestamped `.sib` copy next to the original
   (authoritative) plus a best-effort in-file version. Never bypass this.
4. **Verify by reading back** and tell the user what changed, including the
   backup file path printed on stderr. What the bridge can't verify
   (key signatures, clefs — initial ones don't appear in bar iteration),
   ask the user to confirm on screen.

## Connection and approval realities

- One approval dialog per Sibelius launch (session tokens die with the
  process); another if the declared plug-in list changes. When a command
  hangs on "Waiting for connection approval", tell the user to click OK in
  Sibelius — don't kill it early (timeout is 120 s).
- Exit 2 = can't connect: Sibelius not running or Sibelius Connect disabled
  (Preferences → Input Devices).
- Exit 1 with "bridge plug-in not reachable" or a version-mismatch error:
  run `install-plugin`, then the user must restart Sibelius. Any edit to
  `src/sibelius_websocket_cli/manuscript/sibwscli.plg` needs the same restart
  — batch plug-in changes and bump `GetBridgeVersion` when editing it.

## Command cheat sheet

Reads: `score-info` (title/file/key/time sigs), `staves`, `selection`,
`read [--staff N] [--from A] [--to B] [--bars A-B] [--abc]` (notes with MIDI pitch/name/tie, lyrics with
text, addressed by staff/bar/index; with `--abc` or `read-abc`, formats into compact, token-efficient ABC notation with aligned lyrics),
`read-lyrics [--staff N] [--bars A-B] [--words] [--verse N]` (0 = all;
`--words` formats into hyphenated words grouped by staff and verse/bar),
`check-lyrics [--staff N] [--bars A-B] [--verse N]` (lints lyrics for horizontal/vertical collisions, missing vowels,
cross-voice typos/divergence, and untexted passages with multi-verse awareness).

Writes (auto-backup):
- Score structure: `add-staff --instrument <name|styleId> [--position bottom|top|auto] [--full-name ...] [--save]`, `add-bars [--count N] [--save]`, `set-staff-name --staff N [--full <name>] [--short <name>] [--save]`, `set-score-info [--title <text>] [--composer <text>] [--lyricist <text>] [--save]`, `set-break --bar N --type system|page|none [--save]`.
- Music entry: `add-notes --staff N --bar B [--pos ticks] (--pitches <list> --dur <duration> | --notes <sequence>) [--voice 1-4] [--tied] [--save]`, `add-abc --staff N [--bar B] [--pos ticks] "<abc snippet>" [--save]` (inserts notes, rhythms, ties, and `w:` lyrics).
- Score editing: `save` (save active score in Sibelius),
`reset-design [--lyrics] [--save]` (clear formatting/font overrides),
`set-lyric --staff --bar --index --text [--save]`,
`transpose --from-note C --to-note D --up|--down [--from-bar --to-bar
--top-staff --bottom-staff] [--octaves N] [--save]` (whole score by default; both
directions live-verified), `set-key --bar --key [--minor] [--save]`,
`copy-passage --from-bar --to-bar --top-staff [--bottom-staff] --dest-staff
--dest-bar [--save]` (faithful copy incl. ties/articulations — and lyrics, which the
user may want stripped with `DeleteObject` afterwards),
`set-note --staff --bar --index --old-pitch --new-pitch [--save]` (repitch one note,
MIDI numbers), `flip-stem --staff --bar --index [--save]`,
`nudge --staff --bar --index --dx --dy [--save]`,
`export [--format musicxml|mxl|pdf|midi|png] [--out] [--file
some.sib]`, `backup [--name]`.

Escape hatches: `do undo`, raw command IDs via `invoke` (fire-and-forget:
success responses are meaningless — see docs/commands.md for all 627), any
bridge method via `plugin sibwscli <Method> --args '<json>'`.

## Task patterns

**Lyric proofreading / spell-check:**
1. **CRITICAL FIRST STEP: Assess Body Lyric Typography in the File (File Style vs. Metadata):**
   - **Do NOT trust score metadata or House Style definitions!** `GetScoreInfo` metadata (`mainTextFontName`) only reports the score's default text font, NOT the font or size used for typed lyrics. Furthermore, in many scores and templates, the underlying House Style definition for `Lyrics line 1` is set to a sans-serif font (e.g. Quicksand, Arial, Helvetica) even when the user typed the score's lyrics in a serif font (e.g. Times New Roman, Plantin) at a specific point size (e.g. 9.5 pt / `95`).
   - **Why ManuScript loses font tags on read:** In Sibelius ManuScript, reading lyrics via `ReadLyrics` (`obj.Text`) only returns bare text strings without formatting tags. The CLI cannot automatically know whether the typed lyrics on the page are serif, sans-serif, 9.5 pt, or 11 pt from `ReadLyrics` alone.
   - **Visual and empirical assessment:** Always export a PNG first: `export --format png --out /tmp/check.png` (or inspect an existing rendering). Inspect the rendered body lyrics visually to identify:
     * **Font family / classification:** Serif (e.g. Times New Roman) vs. Sans-serif.
     * **Point size:** Gauge scale against adjacent notes and staves. A standard default is 11.0 pt (`110`), but choral and hymn scores frequently use 9.5 pt (`95`), 10.0 pt (`100`), or 8.5 pt (`85`).
   - Decide the exact `--font "<FontFamily>"` and `--font-size <TenthsOfPoint>` to use for all edits in this score before modifying any text.
2. **Lint & Spell-check:**
   - Run `check-lyrics [--bars A-B]` to flag collisions, missing vowels, and cross-voice lyric divergence.
   - Run `read-lyrics --words [--verse N] [--bars A-B]` to inspect complete words grouped by staff and verse in a clean, human-readable format.
3. **Execute Targeted Corrections (`set-lyric`):**
   - Run `read-lyrics --staff N [--bars A-B]` to get exact syllable addresses (`staff`, `bar`, `index`, `position`, `text`).
   - Apply each correction explicitly passing the assessed file font and size:
     `set-lyric --staff S --bar B --index I --text "<correction>" --font "<FontFamily>" --font-size <TenthsOfPoint> [--save]`
     *(Example: `set-lyric --staff 1 --bar 12 --index 2 --text "jah!" --font "Times New Roman" --font-size 95`)*
   - **STRICT FORBIDDEN FLAGS:**
     * **NEVER pass `--raw` for lyric corrections!** Passing `--raw` strips all font and size formatting tokens and writes a bare string to `obj.Text`. In Sibelius, writing bare text causes the syllable to fall back to the text style's House Style definition (`Lyrics line 1`), which turns serif lyrics into sans-serif!
     * **Do NOT rely on bare `set-lyric` auto-detection:** Because `ReadLyrics` cannot read font tags from existing syllables, un-annotated `set-lyric` falls back to `score-info` metadata and `110` (11.0 pt), which may mismatch the file's actual typeface and point size.
   - **CAUTION on `reset-design`:** In Sibelius, `reset-design` strips formatting overrides and reverts text objects to their underlying House Style definition. If the score template's text style defines `Lyrics line 1` as a sans-serif font while lyrics were typed in a serif font, running `reset-design` will wipe out all serif styling across the score. Never execute `reset-design` during automated proofreading unless explicitly instructed by the user to adopt the raw house style.
4. **Layout & Collision Tweaks:**
   - For layout/collision fixes, use `nudge --staff S --bar B --index I --dy -32 [--save]` to adjust baselines or `--dx` to clear barlines.
5. **Mandatory Post-Update Visual Verification:**
   - Re-export PNG (`export --format png --out /tmp/verify.png`) and view the rendered page.
   - Verify that the edited syllables match the surrounding text in typeface, stroke weight, and point size.
   - Save the score (`save`). Addresses are only valid against the read they came from; re-read after every write.

**Copy a passage to another staff (e.g. "apply SA pickup to TB, down an
octave"):** read the destination first (know what gets overwritten) and check
whether the source passage carries lyrics/text the destination staff doesn't
use elsewhere — if so, ASK the user before copying whether to bring them
along (paste copies everything). Then `copy-passage` → `transpose` scoped to
the destination staff/bars with `--from-note X --to-note X --octaves N` for
pure octaves → strip unwanted pasted items with DeleteObject (delete
higher indexes first; each deletion shifts later addresses) → read back.

**Transpose to a key:** current key from `score-info` `keySignatures`
(empty = C major / no signature) → confirm direction with the user if
ambiguous → `transpose --from-note <cur> --to-note <target> --up|--down` →
read back a bar to check pitches → ask the user to confirm the key signature
on screen.

**Visual/layout fixes (collisions, stems, spacing):** the read commands can't
see engraving, but you can: `export --format png --out /tmp/check.png` (pages
land as check_0001.png etc.), Read the image, judge, adjust, re-export, look
again. Layout tools: `invoke select_all reset_note_spacing select_none` or
`increase_spacing` for global spacing; `nudge --staff --bar --index --dx --dy`
(1/32 spaces) for targeted moves of any addressed object (e.g. colliding
lyrics — nudging one syllable often just moves the collision; free space on
both sides); `flip-stem` for stem direction. Iterate in small steps and
re-render between each.

### Engraving & Typography Visual Checklist (4-Point Review)

Whenever exporting and visually inspecting score pages, always evaluate the following 4 engraving criteria:
1. **Baseline continuity**: Ensure lyric baselines remain level within each system and across phrase boundaries. Look for unprompted `verse1` $\leftrightarrow$ `verse2` style hopping where a voice steps up or down mid-phrase. When a refrain/chorus is sung in unison, all voices should share `verse1` (`line 1`). Use `set-lyric-style --staff S --bar B --index I --style verse1` to unify lines.
2. **Typographical uniformity**: Verify font family and point size remain uniform across all lyrics. Syllables must not revert to default application sans-serif fonts when the score uses serif. Updates must match the file's typed style, NOT the metadata or template House Style default. When modifying lyrics in ManuScript, always explicitly specify `\f<FontName>\\s<TenthsOfPoint>\` (e.g. `--font "Times New Roman" --font-size 95`). Never pass `--raw`.
3. **Phrase-aware system breaks**: Place system and page breaks at musical phrase endings and rests, not across tied notes or mid-pickup. Placing a break across a tied note forces an extender line (`—`) to start the new system, which displaces subsequent pickup syllables down to a lower tier.
4. **Extender line clearance**: Check tied notes across barlines to verify that lyric extender lines do not collide with or displace subsequent pickup lyrics.

### ManuScript Styled-String Formatting Rules

- Formatting tokens use backslash syntax: `\f<FontFamily>\` (e.g. `\fTimes New Roman\`) and `\s<TenthsOfPoint>\` (e.g. `\s95\` = 9.5 pt, `\s110\` = 11.0 pt; the argument is in tenths of a point, NOT 1/32 space units).
- Each formatting token is enclosed in backslashes. When combining multiple commands, concatenate them with double backslashes between them: `\f<FontName>\\s<TenthsOfPoint>\` (e.g. `\fTimes New Roman\\s95\text`). A single backslash (e.g. `\fFont\s95\text`) causes Sibelius to parse `s95\text` as literal unformatted text.
- In Python code or CLI strings, `\f` is ASCII formfeed (`\x0c`). Always escape backslashes (`"\\fTimes New Roman\\\\s95\\"` or `"\x5cfTimes New Roman\x5c\x5cs95\x5c"`) to prevent corrupted byte encoding over WebSocket JSON.
- **NEVER use `--raw` on `set-lyric`**: Passing `--raw` writes bare text to `obj.Text`. In ManuScript, bare text strips character formatting and triggers fallback to the text style's House Style definition (`Lyrics line 1`), which in many scores is sans-serif even when the file's lyrics are serif.
- **Assess file style first, not metadata**: `GetScoreInfo` metadata (`mainTextFontName`) only reports the whole-score default text font, and `ReadLyrics` cannot read character formatting from `LyricItem`. Always visually assess the score's actual body lyric font and point size from an exported PNG and explicitly supply `--font "<FontFamily>" --font-size <TenthsOfPoint>` (e.g. `--font "Times New Roman" --font-size 95`).

## Trust the local docs, not the Avid guide

The ManuScript Language Guide has proven wrong in specifics (documented
`utils.CalculateDegree` doesn't exist; `return_value` vs `returnValue`).
Ground any new bridge work in `docs/manuscript-object-tree.md`,
`docs/manuscript-constants.md`, `docs/commands.md`, and `SPEC.md`, and
live-probe on a scratch copy of the score before touching real music.


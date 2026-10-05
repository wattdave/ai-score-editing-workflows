---
name: tenor-playback-repair
description: Sibelius only. Diagnose and repair octave-high playback in a Sibelius tenor line imported from MusicXML, while preserving the original score.
---

# Tenor Playback Repair

Use this skill when a tenor line looks correctly notated but plays an octave too high after a MusicXML import. Do not use it for ordinary pitch or clef edits.

## Safe diagnosis

1. Confirm the active score with `inspect`; read one short representative Tenor passage (`read --staff N --bars A-B`, a few bars only) and record its MIDI pitches.
2. Export a temporary MusicXML copy. Grep the Tenor part's `<attributes>` rather than reading the whole file: the intended octave-treble representation has one `<clef-octave-change>-1</clef-octave-change>` and no `<transpose>` element.
3. Import that MusicXML as a separate, unsaved test score. Never overwrite the original during the round trip.
4. Export the test score to MIDI. Run `scripts/inspect_midi_pitches.py` on the MIDI file. For a written opening A4 tenor note, correct sounding playback is MIDI 57 (A3), not 69 (A4).

## Delivering a repair

- If the imported test score has the correct Tenor MIDI octave, save it under a distinct `*-tenor-playback-fixed.sib` name and leave the original intact.
- Visually review the imported score before presenting it: MusicXML round trips can alter staff spacing, system breaks, lyric placement, and text formatting.
- Do not transpose the stored Tenor notes just to repair playback; that changes the printed music. Repair the clef/instrument playback interpretation instead.
- Report the original and repaired files, plus the verified MIDI pitch evidence.

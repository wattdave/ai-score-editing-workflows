# Music-Edit Workflows

Read the destination range before every targeted music edit and read it again
afterward.

## Transpose to a key

1. Read `score-info.keySignatures`; an empty list represents C major or no
   explicit signature.
2. If upward versus downward motion is musically ambiguous, confirm the
   direction with the user.
3. Run `transpose --from-note <current> --to-note <target> --up|--down` with a
   staff/bar scope when the request is not for the whole score.
4. Read back a representative bar to verify pitches. Initial key signatures do
   not appear during bar iteration, so ask the user to confirm the signature on
   screen.

Use `--from-note X --to-note X --octaves N` for a pure octave transposition.

## Copy a passage

1. Read the destination to record what will be overwritten.
2. Check whether the source contains lyrics or text absent from the destination
   staff. If it does, ask whether those objects should also be copied because
   paste carries them with the music.
3. Run `copy-passage` with the source bars/staves and destination staff/bar.
4. Apply any requested transposition to only the destination range.
5. Remove unwanted copied objects with `DeleteObject`, deleting higher indexes
   first because each deletion shifts subsequent addresses.
6. Read the destination again.

## Targeted note and key edits

- Use `set-note --staff --bar --index --old-pitch --new-pitch` to repitch one
  addressed note. Pitches are MIDI numbers; `old-pitch` guards the target.
- Use `set-key --bar --key [--minor]` for a key-signature change.
- Use `add-notes` or `add-abc` for new music. Consult the command's `--help`
  for durations, positions, voices, ties, and save behavior.

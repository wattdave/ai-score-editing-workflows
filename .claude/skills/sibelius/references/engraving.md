# Engraving and Visual Review

Read this file for collisions, lyric typography, stems, spacing, or other
changes whose result is visible rather than fully represented by bridge reads.

## Render and iterate

Export PNG pages with:

```bash
uv run sibelius-websocket-cli export --format png --out /tmp/check.png
```

Numbered pages are written as `check_0001.png`, `check_0002.png`, and so on.
Inspect the relevant page, make one scoped adjustment, re-export, and inspect
again.

Available layout operations include:

- `nudge --staff S --bar B --index I --dx X --dy Y` for an addressed object's
  horizontal or vertical offset in 1/32 spaces. Moving one colliding syllable
  can transfer the collision, so inspect both sides afterward.
- `flip-stem --staff S --bar B --index I` for stem direction.
- `invoke select_all reset_note_spacing select_none` or `increase_spacing` for
  global note spacing.
- `set-lyric-style --staff S --bar B --index I --style verse1` when a unison
  refrain should use lyric line 1 consistently.

## Review checklist

1. **Baseline continuity:** compare lyric baselines within each system and
   across phrase boundaries; look for unintended verse-line changes.
2. **Typography:** compare font family, size, and weight with surrounding body
   lyrics. Follow [lyrics.md](lyrics.md) before changing lyric text.
3. **Phrase-aware breaks:** place system or page breaks at phrase endings or
   rests, rather than across tied notes or pickups.
4. **Extender clearance:** inspect ties across barlines for extender lines that
   collide with or displace following pickup lyrics.

Report what was visually verified. For properties the bridge does not expose,
ask the user to confirm the rendered or on-screen result.

# Avid reference material

The ManuScript and Sibelius Connect reference is Avid's *ManuScript
Language Guide*. Avid owns that text, so this repository links to it rather
than copying it:

- [ManuScript Language Guide, Sibelius 2026.6](https://resources.avid.com/SupportFiles/Sibelius/2026.6/ManuScript_Language_Guide.pdf)
  (current minimum version)
- [ManuScript Language Guide, Sibelius 2024.8](https://resources.avid.com/SupportFiles/Sibelius/2024.8/ManuScript_Language_Guide.pdf)
  (the edition the notes below were checked against)

## Local copies

Bridge work goes faster with the guide as searchable Markdown. These paths
are gitignored, so you can keep your own transcriptions there; skills and
docs refer to them when present. Chapter titles are stable across editions,
though page numbers move.

| Local path | Guide chapter |
| --- | --- |
| `docs/manuscript-object-tree.md` | Chapter 4, Object Reference |
| `docs/commands.md` | Chapter 5, Command IDs |
| `docs/sibelius-connect.md` | Chapter 6, Sibelius Connect |
| `docs/manuscript-constants.md` | Chapter 7, Global Constants |

To recreate one, download the PDF and ask your assistant to transcribe that
chapter to the path above.

## Where the guide is wrong

Found by running code against Sibelius; not in Avid's text.

- **`LyricItem` has no font properties.** `InitialFontName`, `InitialFontSize`
  and `TextWithFormattingAsString` exist on `Text`/`SystemTextItem` only;
  reading them from a `LyricItem` raises 'No field named' (bridge v13). The
  guide lists no object that reads a text style's font; `text-styles` probes
  a throwaway `Text` instead.
- **`Staff.SoundIDAtPosition` does not exist.** The method is
  `SoundInfoAtPosition([bar number,[position,[nth repeat]]])`; the documented
  name raises "Method SoundIDAtPosition not found". Verified 2026-09-24.
- **`CurrentTimeSignature` is on `SystemStaff`, not `Score`.** In general a
  method lives on the object whose section lists it; a wrong receiver fails
  only at runtime with "Unknown method".
- **`utils.CalculateDegree`** and **`return_value` versus `returnValue`**
  differ from the guide; see `docs/sibelius-protocol.md` and the bridge plug-in for the forms
  that work.
- **The "Hierarchy of Objects" diagram** (start of chapter 4) is an image
  that does not extract as text; rebuild the tree from the containment
  relationships in each object's section.
- **`Transpose` interval types** must be 0 to 10 (chapter 7 constants);
  see `docs/sibelius-protocol.md` for the argument combinations that work.

# MusicXML 4.0 schema

Used by `scripts/validate_musicxml.py` so validation does not depend on any
score editor being installed.

- Source: https://github.com/w3c/musicxml, tag `v4.0`, `schema/musicxml.xsd`,
  `schema/xml.xsd`, `schema/xlink.xsd`.
- License: W3C Community Final Specification Agreement; the notice is in the
  header of `musicxml.xsd`, which is unchanged apart from the change below.
- Only change: the two `schemaLocation` attributes of `musicxml.xsd` point to
  the sibling `xml.xsd` and `xlink.xsd` instead of `http://www.musicxml.org/...`,
  so validation works offline (`xmllint --nonet`).

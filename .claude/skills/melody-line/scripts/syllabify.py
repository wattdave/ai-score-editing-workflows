"""Words -> 'syl-la-ble' text for melody_lib.write_xml, using pyphen (en_US). Author hyphens are kept.
Overrides: {word_lowercase: "pre-split"} for words pyphen splits wrongly."""
import re
import pyphen

_dic = pyphen.Pyphen(lang="en_US", left=2, right=3)


def syllabify(text, overrides=None):
    overrides = overrides or {}
    out = []
    for tok in text.split():
        m = re.match(r"^([^A-Za-z']*)(.*?)([^A-Za-z']*)$", tok)
        pre, core, post = m.groups()
        parts = []
        for piece in core.split("-"):
            key = piece.lower()
            parts.append(overrides.get(key) or (piece if len(piece) < 5 and "'" not in piece else _dic.inserted(piece)))
        out.append(pre + "-".join(parts) + post)
    return " ".join(out)

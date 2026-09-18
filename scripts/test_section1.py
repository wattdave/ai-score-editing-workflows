import xml.etree.ElementTree as ET
from scripts.assemble_clamavi import (
    create_base_score,
    add_tutti_unison_measure,
    make_pitch_note,
    make_rest_note,
    DIVISIONS,
)

root, parts = create_base_score()

# Measure 0 (pickup, 1/8)
s0 = [make_pitch_note("C", 4, 192, "eighth", lyric_text="Cla", lyric_syl="begin", accent=True)]
a0 = [make_rest_note(192, "eighth")]
t0 = [make_rest_note(192, "eighth")]
b0 = [make_rest_note(192, "eighth")]
add_tutti_unison_measure(parts, 0, "0", (1, 8), s0, a0, t0, b0, is_pickup=True)

# Measure 1 (3/4)
s1 = [make_pitch_note("B", 4, 1152, "half", alter=-1, is_dotted=True, lyric_text="ma", lyric_syl="middle")]
r1 = [make_rest_note(1152, is_measure_rest=True)]
add_tutti_unison_measure(parts, 1, "1", (3, 4), s1, r1, r1, r1)

print("Test section 1 executed successfully.")

"""Score position units shared by every back end.

Positions and durations are 1/256 of a quarter note (a whole note is 1024).
MuseScore's own 480 ticks per quarter stay in the ``musescore`` package.
"""

UNITS_PER_QUARTER = 256
UNITS_PER_WHOLE = 1024

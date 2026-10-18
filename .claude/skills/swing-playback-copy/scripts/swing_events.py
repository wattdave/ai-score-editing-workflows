"""Re-time a straight-eighth melody as 2:1 swing written in compound meter (4/4 -> 12/8, 3/4 -> 9/8).

Events are (onset, duration, midi_pitch | None) in quarter-note beats of the straight score, on a half-beat grid.
Use the result with a MusicXML writer in the compound meter (see SKILL.md); durations come back in quarter-note
lengths of the *swung* score, so a 12/8 bar is 6.0 long.
"""

SINGLE = (48, 36, 24, 18, 12, 6, 3)  # note values (in 12ths of a quarter) that need no tie


def swing(events, phase=0.0):
    """Each beat becomes 1.5 quarter-lengths; an off-beat eighth starts 1.0 after its beat.
    `phase` is the beat position (0-1) of the first event: a pickup starts mid-beat."""
    def sw(t):
        n, f = int(t // 1), t - int(t // 1)
        if abs(f) > 1e-6 and abs(f - 0.5) > 1e-6:
            raise ValueError(f"off-grid time {t}")
        return n * 1.5 + (1.0 if f > 0.25 else 0.0)

    base = sw(phase)
    return [(sw(s + phase) - base, sw(s + d + phase) - sw(s + phase), p) for s, d, p in events]


def swing_playback(events, phase=0.0, bar_q=6.0, pickup_q=0.0):
    """swing() plus the fixes Cantai playback needs.

    Tied notes drone in playback, so no note is tied inside a bar: a duration that is not one note value (30 or
    42 twelfths, say) is played as the largest single value and the rest is rested (a small breath). A note
    crossing a barline keeps the one tie it needs when both halves are single values. The final note becomes one
    dotted half with the rest of the bar rested out.
    """
    out = []
    for s_, d_, p_ in swing(events, phase):
        if p_ is None:
            out.append((s_, d_, p_))
            continue
        D = int(round(d_ * 12))
        start, edge = s_ - pickup_q, None
        if start >= 0:
            nb = (int(start // bar_q + 1e-9) + 1) * bar_q + pickup_q
            if s_ + d_ > nb + 1e-6:
                edge = nb
        elif s_ + d_ > pickup_q + 1e-6:
            edge = pickup_q
        if edge is None:
            ok = D in SINGLE
        else:
            a, b = int(round((edge - s_) * 12)), int(round((s_ + d_ - edge) * 12))
            ok = a in SINGLE and b in SINGLE
        if ok:
            out.append((s_, d_, p_))
            continue
        if edge is None:
            single = max(v for v in SINGLE if v <= D)
        else:
            a = int(round((edge - s_) * 12))
            single = (a + max(v for v in SINGLE if v <= D - a)) if a in SINGLE and D - a >= 3 else \
                max(v for v in SINGLE if v <= min(D, a))
        out += [(s_, single / 12, p_), (s_ + single / 12, d_ - single / 12, None)]
    s_, d_, p_ = out[-1]
    if p_ is not None and d_ > 3:
        out[-1:] = [(s_, 3.0, p_), (s_ + 3.0, d_ - 3.0, None)]
    return out

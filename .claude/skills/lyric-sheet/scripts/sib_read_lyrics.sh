#!/bin/zsh
# Open one .sib in Sibelius, save its lyrics, then close it again.
#
#   sib_read_lyrics.sh SLUG /path/to/score.sib [OUTDIR]
#
# Writes OUTDIR/SLUG.json (every lyric with syllableType), SLUG.words.txt
# (--words view) and SLUG.staves.txt. OUTDIR defaults to ./lyrics-raw.
# Read-only: it never saves the score. One score at a time; Sibelius is slow
# to open some files (up to ~2 minutes) and old-format files raise an
# "Update Score" dialog that blocks every later open, so this script answers it.
slug="$1"; f="$2"; out="${3:-lyrics-raw}"
[ -n "$slug" ] && [ -f "$f" ] || { echo "usage: sib_read_lyrics.sh SLUG score.sib [OUTDIR]" >&2; exit 2; }
here="${0:A:h}"
mkdir -p "$out"
if command -v sibelius-cli >/dev/null 2>&1; then cli=(sibelius-cli); else cli=(uv run --project "$here" sibelius-cli); fi

open -a /Applications/Sibelius.app "$f"
cur=""
for i in {1..60}; do
  sleep 2
  "$here/sib_windows.sh" update-ok >/dev/null 2>&1
  cur=$("${cli[@]}" score-info 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("fileName",""))' 2>/dev/null)
  [ "$cur" = "${f:A}" ] && break
done
if [ "$cur" != "${f:A}" ]; then
  echo "NOT-OPEN $slug (Sibelius reports: ${cur:-nothing})"
  "$here/sib_windows.sh" close "$f" >/dev/null 2>&1
  exit 3
fi
"${cli[@]}" --expect-file "${f:A}" read-lyrics > "$out/$slug.json" 2>&1
"${cli[@]}" --expect-file "${f:A}" read-lyrics --words > "$out/$slug.words.txt" 2>&1
"${cli[@]}" --expect-file "${f:A}" staves > "$out/$slug.staves.txt" 2>&1
"$here/sib_windows.sh" close "$f" >/dev/null 2>&1
sleep 2
echo "OK $slug: $(wc -l < "$out/$slug.words.txt" | tr -d ' ') lines"

#!/bin/zsh
# Markdown lyric book -> Word, then render it to PDF and page images to check.
#
#   md_to_docx.sh "Book.md" ["Book.docx"] [--check]
#
# Single newlines inside a stanza stay line breaks (hard_line_breaks), and
# headings become real Word Heading 1/2 styles, so the recipient can restyle
# them in a template. --check renders to PDF with LibreOffice and writes
# page images (pdftoppm) next to the output, for you to look at.
# Needs: brew install pandoc; for --check: brew install --cask libreoffice poppler
md="$1"; shift
docx=""; check=0
for a in "$@"; do [ "$a" = "--check" ] && check=1 || docx="$a"; done
[ -f "$md" ] || { echo "usage: md_to_docx.sh book.md [book.docx] [--check]" >&2; exit 2; }
[ -n "$docx" ] || docx="${md%.md}.docx"
command -v pandoc >/dev/null || { echo "pandoc missing: brew install pandoc" >&2; exit 3; }
pandoc -f markdown+hard_line_breaks -t docx -o "$docx" "$md" || exit 4
echo "wrote $docx"
if [ "$check" = 1 ]; then
  command -v soffice >/dev/null || { echo "soffice missing: brew install --cask libreoffice" >&2; exit 5; }
  outdir="$(dirname "$docx")"
  soffice --headless --convert-to pdf --outdir "$outdir" "$docx" >/dev/null 2>&1 || exit 6
  pdf="${docx%.docx}.pdf"
  pdfinfo "$pdf" 2>/dev/null | grep Pages
  pdftoppm -jpeg -r 70 "$pdf" "${docx%.docx} page" && echo "page images: ${docx%.docx} page-*.jpg (open them and look)"
fi

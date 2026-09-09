# *Cuando por el oriente* — Revision 2 Editorial Notes

**Score File:** `Cuando por el oriente revision 2.sib`  
**Date:** September 9, 2026  
**Musical Tradition:** *Los Pastores* (New Mexico Traditional Folk Song / Pastorela)

---

## 1. Summary of Changes

### A. Syllable Realignment & Cross-Verse Disentanglement
During original data entry in Sibelius, several syllables had been swapped between verses across rhythmic positions, creating nonsense words:
* **Bar 7 (pos 512):** Verse 3 had received `via` while Verse 4 had `flo`, turning *flo-res* and *via-dores* into the non-word *via-res*. Realigned so Verse 3 reads **`flo-res`** and Verse 4 reads **`via-dores`**.
* **Bar 10 (pos 1152) & Bar 11 (pos 0):** Verse 4 had received `bres` and Verse 5 had received `do`, scrambling *hom-bres* and *dan-zan-do* into *hom-do* and *danzan-bres*. Realigned to their proper positions: **`hom-bres`** (Verse 4) and **`dan-zan-do`** (Verse 5).
* **Bar 3 (pos 1280) Collision:** A severe 6-syllable overlap occurred where duplicate `'un` and misplaced `de'un` collided at the same timestamp. Cleaned up and distributed properly: `de'un` at pos 1152 and `buey` at pos 1280.
* **Bar 2 (pos 1024) Missing Syllable:** Verse 2 had an untexted half note. Fixed elision on beat 2 (`la'au-`) and placed `-ro-` on pos 1024, resolving cleanly to `-ra` on beat 4 (*“la aurora”*).

### B. Text Corrections & Orthography
Corrected corrupted words, restored diacritics, and completed the historical poetic rhyme schemes (*-ores / -undo*):
* **Verse 1:**
  * Restored **`1.`** verse numbering prefix to line 1 (`1.Cuan`), matching verses 2–5 (`2.Ve`, `3.Pre`, etc.).
  * Fixed `ermosa` $\rightarrow$ **`hermosa`** (Bar 1).
  * Fixed `Quien` $\rightarrow$ **`Quién`** with proper accent (Bar 11).
  * Corrected `quen granjeas` $\rightarrow$ **`que granjeas`** (*“¡Lo que granjeas!”*, Bar 12).
* **Verse 2:**
  * Capitalized **`Virgen`** (*“Caminaba la Virgen”*).
  * Syllabification and punctuation adjusted for vocal phrasing (*“¡con qué alegría!”*, *“alma mía,”*).
* **Verse 3:**
  * Fixed corrupted `se-ñor-ea` $\rightarrow$ **`se-ñor-es`** (Bar 8), restoring the rhyme scheme: *flores / señores / fundo / mundo*.
  * Added missing accent: `Segun` $\rightarrow$ **`Según`** (Bar 9).
* **Verses 4 & 5:**
  * Adjusted capitalization and punctuation (*“Los animales”*, *“hombre-Dios”*, final full stop at *“tengo.”*).

### C. Typography & Engraving Consistency
* **Font Normalization:** All lyric verses were previously rendering with mismatched typefaces—some syllables had local overrides to Plantin (serif), clashing with the score’s intended modern sans-serif.
* Applied `reset_design` across all lyric text items to eliminate manual font overrides. All 5 verses now render cleanly and consistently in **Quicksand** across all systems and pages.

---

## 2. Complete Corrected Text (5 Verses)

```text
Verse 1:
Cuando por el oriente sale la hermosa estrella,
¡Quién fuera tras de ella! ¡Lo que granjeas!

Verse 2:
Caminaba la Virgen ¡con qué alegría!
Diciendo: Niño mío, luz, alma mía,
vamos a ver la aurora del claro día.

Verse 3:
A pisar estas flores vengan señores,
que según me fundo, ya se acabaron
los tontos en este mundo.

Verse 4:
¡Qué prodigio ver tan joviales
a los animales dando reverencia
al hombre-Dios en su presencia!

Verse 5:
Danzando y bailando con alegría
a Belén caminemos de noche y día;
que yo gusto y contento en el alma tengo.
```

---

## 3. Key Source References & Links

1. **John Donald Robb Musical Trust & Archives**
   * *Hispanic Folk Songs of New Mexico* (John Donald Robb, 1954 / UNM Press).
   * Ethnomusicological field recordings documenting the *pastorelas* and folk hymns of New Mexico, including *Cuando por el oriente*.
   * Archive portal: [https://robbtrust.org](https://robbtrust.org)
   * UNM Digital Repository: [https://digitalrepository.unm.edu/robb_field_recordings/](https://digitalrepository.unm.edu/robb_field_recordings/)

2. **The Boston Camerata**
   * *New Britain: The Roots of American Folksong* (Erato / Apex, Joel Cohen, Director).
   * Contains the definitive 1988/1989 early-music ensemble performance and historical liner notes for the 1953 New Mexico transcription of *Cuando por el oriente*.
   * Official site: [https://bostoncamerata.org](https://bostoncamerata.org)

3. **Mudcat Café Folk Song & Ballad Database**
   * Active forum and index of the Digital Tradition Folk Song Database preserving transcribed verses and variants of New Mexican *pastorelas* and Spanish villancicos.
   * Repository: [https://mudcat.org](https://mudcat.org)

4. **Fundación Joaquín Díaz & Biblioteca Digital Hispánica (BNE)**
   * Historical repositories preserving 18th- and 19th-century Spanish *pliegos de cordel* (*“Seguidillas Espirituales y Alegres para celebrar el sagrado Nacimiento”*), preserving the original octosyllabic/heptasyllabic poetic structures from which these Mexican and New Mexican variants descend.
   * Cancionero Tradicional: [https://funjdiaz.net](https://funjdiaz.net)
   * BNE Digital: [https://bdh.bne.es](https://bdh.bne.es)

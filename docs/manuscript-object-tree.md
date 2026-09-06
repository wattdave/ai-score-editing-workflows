# ManuScript Object Reference (Sibelius 2024.8)

**Source:** [ManuScript Language Guide, Sibelius 2024.8](https://resources.avid.com/SupportFiles/Sibelius/2024.8/ManuScript_Language_Guide.pdf), Chapter 4 "Object Reference", PDF pages 50–139 (roman pages l–cxxxix).

**Note:** The "Hierarchy of Objects" diagram on page 50 is a graphic image in the PDF and does not extract as text; the tree below is reconstructed from the containment relationships documented throughout the chapter. Everything else in this file is extracted directly from the chapter text.

## Object Hierarchy (containment/derivation overview)

```
Sibelius (global application object)
├── Score (Sibelius.ActiveScore, Sibelius.NthScore, for each on Sibelius)
│   ├── SystemStaff (one per score; holds system-wide objects)
│   │   └── Bar → SpecialBarline, SystemTextItem, SystemSymbolItem, RehearsalMark, ...
│   ├── Staff (one or more; for each on Score)
│   │   └── Bar (contains BarObject objects)
│   │       └── BarObject (base class) — derived types:
│   │           BarRest, Clef, Comment, GuitarFrame, GuitarScaleDiagram,
│   │           InstrumentChange, KeySignature, Line (CrescendoLine etc.),
│   │           LyricItem, NoteRest (contains Note objects), RehearsalMark,
│   │           SymbolItem / SystemSymbolItem, Text / SystemTextItem,
│   │           TimeSignature, Tuplet, AnnotationItem
│   ├── Selection (Score.Selection)
│   ├── Barlines → Barline
│   ├── BracketsAndBraces → Bracket
│   ├── DocumentSetup
│   ├── EngravingRules
│   ├── SystemObjectPositions
│   ├── DynamicPartCollection → DynamicPart
│   ├── InstrumentTypeList → InstrumentType
│   ├── HitPointList → HitPoint
│   └── VersionHistory → Version → VersionComment
├── PluginList → Plugin
├── ComponentList → Component (house styles, manuscript papers)
├── Folder → File
├── Syllabifier
└── Accessibility
Helper/value objects: DateTime, Dictionary, SparseArray, SoundInfo, TreeNode, Utils (utils.plg)
```

---

## All Objects (global methods)

Methods available on every object / globally in ManuScript.

### Methods
- `AddToPluginsMenu("menu text","function name")` — Adds one menu item to the Plug-ins menu that calls the given function; callable only once per plug-in.
- `Asc(expression)` — Returns the ASCII value of a single-character string.
- `CharAt(expression,position)` — Returns the character at the given zero-based position.
- `Chr(expression)` — Returns the character (string) with the given ASCII value (e.g. `Chr(34)` for `"`).
- `Cmd(command name)` — Alias for `Sibelius.FindCommandID()`; use with `Sibelius.Execute()` to run commands by name.
- `CreateArray()` — Returns a new (old-style) array object.
- `CreateHash()` — Returns a new (old-style) hash-table object.
- `GetInterpreterOption(optionName)` — Returns a boolean: whether the interpreter option is enabled.
- `GetValidationError(object)` — Returns the validation error, if any, of the given object.
- `ExitPlugin()` — Exits the plug-in cleanly without opening the plug-in editor.
- `InterpreterOptionExists(optionName)` — Returns True if the interpreter option exists in this Sibelius version.
- `IsObject(expression)` — Returns True if the expression evaluates to an object (not null/boolean/string/number).
- `IsValid(object)` — Returns True if the object is valid; False if it no longer exists (was deleted).
- `JoinStrings(expression, delimiter)` — Concatenates an array of strings into one string, separated by delimiter.
- `Length(expression)` — Number of characters in the value of the expression.
- `Round(expression)` — Nearest integer to the value.
- `RoundDown(expression)` — Nearest integer less than the value.
- `RoundUp(expression)` — Nearest integer greater than the value.
- `SetInterpreterOption(optionName,[optionValue])` — Enables/disables an interpreter option (per plug-in; persists while the plug-in remains loaded).
- `SplitString(expression,[delimiter,][trimEmpty])` — Splits a string into an array by delimiter (default space); trimEmpty (default False) ignores multiple delimiters.
- `StopPlugin([message])` — Stops the plug-in, optionally showing message; opens the plug-in editor at the line reached.
- `StyleCmd(command name)` — Alias for `Sibelius.FindCommandID()`.
- `Substring(expression,start,[length])` — Returns a substring from zero-based start (to end, or of given length).
- `Trace(expression)` — Sends text to the plug-in trace window.
- `ValidationChecking(enable[, object1[, object2]...])` — Enables validation checking globally, or only for the listed object types in the current plug-in.

### User Properties
All objects (except the `Sibelius` object, old-style arrays from `CreateArray()`, old-style hashes from `CreateHash()`, and `null`) can have user properties assigned to them.

---

## Accessibility

Accessed from the Sibelius object.

### Methods
None.

### Variables
- `ScoreDescription` — boolean, read/write — True if Sibelius's built-in score description functionality is enabled.

---

## AnnotationItem

Represents an annotation. Has no methods or variables, but may be referenced elsewhere (e.g. filtering).

### Methods
None.

### Variables
None.

---

## Bar

A Bar contains BarObject objects. `for each variable in` produces the BarObjects in the bar; `for each type variable in` produces the BarObjects of the given type.

### Methods
- `AddBarNumber(new bar number[,format[,extra_text[,prepend[,skip this bar]]]])` — Adds a bar number change at the start of the bar; returns the BarNumber object created.
- `AddChordSymbolFromPitches(position,pitches[,instrument style])` — Adds a chord symbol from an array of pitches; returns the GuitarFrame object or null.
- `AddClef(pos,concert pitch clef[,transposed pitch clef])` — Adds a clef at the position (style IDs like "clef.treble"); returns the Clef object.
- `AddComment(sr,text[,color[,maximized]])` — Adds a comment at the given sr position (color -1 to skip color while setting maximized).
- `AddCommentWithName(sr,text,username[,color[,maximized]])` — As AddComment, displaying the given username.
- `AddGraphic(file name,pos[,below staff[,x displacement[,y displacement[,size ratio]]]])` — Adds a graphic above/below the bar (offsets in mm, size ratio up to 5x staff height); returns True if successful.
- `AddGraphicToBlankPage(file name,nth page,x offset,y offset[,size ratio])` — Adds a graphic to the nth blank page after this bar (offsets 0.0–1.0 relative to page); returns True if successful.
- `AddGuitarFrame(position,chord name[,instrument style[,fingerings])` — Adds a chord symbol by name; position in 1/256th quarters; returns the GuitarFrame object or null.
- `AddInstrumentChange(pos,styleID[,add_clef[,show_text[,text_label[,show_warning[,warning_label,[full_instrument_name[,short_instrument_name]]]]]])` — Adds an instrument change; returns the InstrumentChange object created.
- `AddKeySignatureFromText(pos,key name,major key[,add double barline[,hidden[,one staff only]]])` — Adds a key signature by text name (e.g. "Cb"); returns the KeySignature object.
- `AddKeySignature(pos,num sharps,major key[,add double barline[,hidden[,one staff only]]])` — Adds a key signature by sharps (+1..+7), flats (–1..–7), 0 (no accidentals) or –8 (atonal); returns the KeySignature object.
- `AddLine(pos,duration,line style[,dx[,dy[,voicenumber[,hidden]]]])` — Adds a line (style ID like "line.staff.hairpin.crescendo" preferred); returns the Line object created.
- `AddLiveTempoTapPoint(position)` — Adds a Live Tempo tap point at the position (1/256th quarters).
- `AddLyric(position,duration,text[,syllable type[,number of notes,voicenum]]])` — Adds a lyric (position/duration in 1/256th quarters); returns the LyricItem created.
- `AddNote(pos,sounding pitch,duration,[tied[,voice[,diatonic pitch[,string number]]]])` — Adds a note (adds to an existing NoteRest at that position, else creates one); returns the Note object created.
- `AddPageNumber([blank page offset])` — Creates and returns a page number change at the end of the bar (also creates a page break); optional 1-based blank-page offset.
- `AddPageNumberAtStartOfBar()` — Creates and returns a page number change at the start of the bar (no forced page break).
- `AddRehearsalMark([consecutive[,mark[,new prefix and suffix[,prefix[,suffx[,override defaults]]]]])` — Adds a rehearsal mark above the bar, optionally overriding appearance/numbering.
- `AddSpecialBarline(barline type[,pos])` — Adds a special barline (start repeats snap to the bar start; others to the end).
- `AddSymbol(pos,symbol index or name)` — Adds a symbol at the position (indices preferred over names); returns the Symbol object or null.
- `AddText(pos,text,style[,voicenum])` — Adds text at the position using the given text style (staff style for normal staff, system style for system staff); returns the Text object.
- `AddTextToBlankPage(xPos,yPos,text,style,pageOffset)` — Adds text using a blank-page text style; pageOffset positive after a special page break, negative before bar 1; returns the Text object.
- `AddTimeSignature(top,bottom,allow cautionary,rewrite music[,use symbol])` — Adds a time signature; returns an error string (empty if no error).
- `AddTimeSignatureReturnObject(top,bottom,allow cautionary,rewrite music[,use symbol])` — As above but returns the time signature object created, or null.
- `AddTuplet(pos,voice,left,right,unit[,style[,bracket[,fullDuration]]])` — Adds a tuplet (unit in 1/256th quarters, e.g. 128 for eighth-note triplet); returns the Tuplet created (test against null).
- `Bar[array element]` — Returns the nth item in the bar (from 0).
- `Clear([voice number])` — Clears the bar of all items (or just the given voice), leaving a bar rest.
- `ClearNotesAndModifiers([voice number])` — Clears notes, rests, tuplets and slurs (or just the given voice), replacing with a bar rest.
- `Delete()` — Deletes the entire bar from the score (affects all staves).
- `DeletePageNumber([blank page offset])` — Deletes the page number change at the end of the bar (or on a following blank page).
- `GetClefAt(pos)` — Returns the Clef object current at the rhythmic position.
- `GetKeySignatureAt(pos)` — Returns the KeySignature object current at the rhythmic position.
- `GetInstrumentTypeAt(pos)` — Returns the InstrumentType used by the bar at the rhythmic position.
- `GetPageNumber([blank page offset])` — Returns the page number change object at the end of the bar, or null.
- `InsertBarRest(voice number[,rest type])` — Inserts a bar rest (rest type: WholeBarRest (default), BreveBarRest, OneBarRepeat, TwoBarRepeat, FourBarRepeat); returns True if successful.
- `NthBarObject(n)` — Returns the nth object in the bar (from 0).
- `RemoveLiveTempoTapPoint(position)` — Removes a Live Tempo tap point at the position (1/256th quarters).
- `ResetSpaceAroundBar(above,below)` — Resets Space Above/Below Staff for this bar.
- `Respace()` — Respaces the notes in this bar.

### Variables
- `BarNumber` — integer, read only — Internal bar number (runs consecutively from 1).
- `BarObjectCount` — integer, read only — Number of objects in the bar.
- `BreakType` — constant, read/write — Break at end of bar: MiddleOfSystem, EndOfSystem, MiddleOfPage, EndOfPage, NotEndOfSystem, EndOfSystemOrPage or SpecialPageBreak.
- `ExternalBarNumber` — integer, read only — Deprecated (Sibelius 5); use ExternalBarNumberString.
- `ExternalBarNumberString` — string, read only — External bar number including bar number/format changes.
- `GapAfter` — spaces, read/write — Gap after the bar.
- `GapBefore` — spaces, read/write — Gap before the bar.
- `InMultirest` — constant, read only — Where the bar falls in a multirest: NoMultirest, StartsMultirest, EndsMultirest, MidMultirest.
- `Length` — read only — The rhythmic length of the bar.
- `MusicRestartsOnPage` — constant, write only — After a SpecialPageBreak, set MusicRestartsOnNextLeftPage or MusicRestartsOnNextRightPage.
- `NthBarInSystem` — integer, read only — Position of the bar within its system (first bar = 0).
- `NumBlankPages` — integer, read/write — Number of blank pages following the bar's special page break.
- `NumBlankPagesBefore` — integer, read/write — Number of blank pages preceding the bar's special page break (effective in bar 1 only).
- `OnHiddenStave` — boolean, read only — True if the bar is hidden by Hide Empty Staves.
- `OnNthPage` — integer, read only — Zero-based page number of the bar in the current part.
- `OnNthPageExternal` — string, read only — External (displayed) page number of the bar's page.
- `OnNthSystem` — integer, read only — Zero-based system number (relative to its page) of the bar.
- `ParentStaff` — Staff, read only — The staff containing this bar.
- `SectionEnd` — boolean, read/write — Corresponds to the Section end checkbox in Properties.
- `Selected` — boolean, read only — True if the entire bar is currently selected.
- `SpecialPageBreakType` — constant, read only — The type of the special page break.
- `SplitMultirest` — boolean, read/write — When True, a multirest intersecting the bar is split.
- `Time` — milliseconds, read only — Time at which the bar starts in the score.

---

## Barline

Accessed from a Barlines object.

### Methods
None.

### Variables
- `BottomStave` — Staff, read only — Staff at which the barline ends, relative to the current part.
- `BottomStaveNum` — integer, read only — Number of the bottom staff included in the barline.
- `TopStave` — Staff, read only — Staff at which the barline starts, relative to the current part.
- `TopStaveNum` — integer, read only — Number of the top staff included in the barline.

---

## BarObject

Base class for objects in a bar (Clef, Line, NoteRest, Text, etc.); the methods/variables below apply to all derived types.

### Methods
- `Delete()` — Deletes the item (NoteRests become a rest of similar duration). See "Deleting Multiple Objects from a Bar".
- `Deselect()` — Removes the object from the parent score's selection list; returns True if removed.
- `FreezeMagneticLayoutPositions()` — Freezes the object's Magnetic Layout position (sets Dx/Dy, then disables Magnetic Layout for it).
- `GetIsInVoice(voicenum)` — Returns True if the object is in the given voice.
- `GetPlayedOnNthPass(n)` — Returns True if the object plays back on the nth pass.
- `NextItem([voice[, item type]])` — Returns the next item in the parent bar (optionally by voice 0–4 and type), or null.
- `PreviousItem([voice[, item type]])` — As NextItem, but searches backwards.
- `RemoveVoice(voicenum)` — Removes the object from the given voice, leaving remaining voices.
- `ResetPosition([horizontal[, vertical]])` — Performs Layout > Reset Position (optionally horizontal/vertical only).
- `ResetDesign()` — Performs Layout > Reset Design on the object.
- `Select()` — Appends the object to the score's selection list (clears any passage selection first).
- `SetAllVoices()` — Sets the object to be in all voices (no effect on some types e.g. NoteRests).
- `SetVoice(voicenum[,clear other voices])` — Sets the object's voice, optionally removing all other voices.
- `ShowInAll()` — Shows the object in the score and all relevant parts.
- `ShowInParts()` — Hides the object in the score, shows it in all relevant parts.
- `ShowInScore()` — Hides the object in parts, shows it in the full score.
- `SetPlayedOnNthPass(n, do play)` — Sets whether the object plays back on the nth pass.
- `TimeOnNthPass(n)` — Returns the object's time in ms on the nth pass, or –1 on error.

### Variables
- `CanBeInMultipleVoices` — boolean, read only — True if the object can be in more than one voice.
- `Color` — 24-bit RGB integer, read/write — Object color (object must be selected to write).
- `ColorAlpha` — 0–255, read/write — Alpha component of color (object must be selected to write).
- `ColorRed` — 0–255, read/write — Red component (object must be selected to write).
- `ColorGreen` — 0–255, read/write — Green component (object must be selected to write).
- `ColorBlue` — 0–255, read/write — Blue component (object must be selected to write).
- `CueSize` — boolean, read/write — True if the object is cue-size in the current part or score.
- `CurrentTempo` — bpm, read only — Tempo at the object's location.
- `DrawOrder` — 0–32, read/write — Drawing layer (1 bottom to 32 top; 0 = default layer for the type).
- `Dx` — 1/32 spaces, read/write — Horizontal graphic offset from the Position field.
- `Dy` — 1/32 spaces, read/write — Vertical graphic offset from the center staff line (positive up).
- `HasCustomDrawOrder` — boolean, read only — True if set to a non-default layer.
- `Hidden` — boolean, read/write — True if the object is hidden in the current part or score.
- `OnNthBlankPage` — integer, read only — 0 if on a music page, else the 1-based blank page number.
- `ParentBar` — Bar, read only — The Bar containing this object.
- `Position` — read only — Rhythmic position of the object in the bar.
- `Selected` — boolean, read only — True if the object is currently selected.
- `Time` — milliseconds, read only — Time of the object in the score (first pass); –1 on error.
- `Type` — string, read only — Type of the object, e.g. "NoteRest", "Clef".
- `UsesMagneticLayout` — constant, read/write — Magnetic Layout state; set with AlwaysDodge, SuppressDodge or DefaultDodge.
- `UsesMagneticLayoutSettingOverridden` — boolean, read only — True if Magnetic Layout settings are overridden.
- `VoiceNumber` — 0–4, read only — 0 if in more than one voice, else 1–4.
- `Voices` — bit field, read/write — Sibelius's internal bit field of voices the object belongs to.

### Deleting Multiple Objects from a Bar
Build a list of items first, then delete in reverse order — deleting while iterating can desynchronize the iterator.

---

## BarRest

Derived from BarObject.

### Methods
None.

### Variables
- `PauseType` — constant, read/write — Fermata type: PauseTypeNone (0), PauseTypeSquare (1), PauseTypeRound (2), PauseTypeTriangular (3).
- `RestType` — constant, read only — WholeBarRest (0), BreveBarRest (1), OneBarRepeat (2), TwoBarRepeat (3), FourBarRepeat (4); create via `bar.InsertBarRest()`.

---

## Bracket

Accessed from a BracketsAndBraces object.

### Methods
None.

### Variables
- `BottomStave` — Staff, read only — Staff at which the bracket ends, relative to the current part.
- `BottomStaveNum` — integer, read only — Number of the bottom staff included.
- `BracketType` — constant, read only — BracketFull, BracketBrace or BracketSub.
- `TopStave` — Staff, read only — Staff at which the bracket starts.
- `TopStaveNum` — integer, read only — Number of the top staff included.

---

## Barlines

Accessed from a Score object; the barline groupings in the score. `for each barline in` iterates all barlines; array access `[n]` returns the nth barline or null.

### Methods
- `AddBarline(top staff number, bottom staff number)` — Creates a barline spanning the staves (relative to current part); returns the Barline or null.
- `ClearAll()` — Removes all barlines from the score.
- `DeleteNthBarline(index)` — Removes the barline identified by index.

### Variables
- `NumChildren` — integer, read only — Number of unique barlines in the score.

---

## Brackets and Braces

Accessed from a Score object; describes brackets, sub-brackets and braces. `for each bracket in` iterates; `[n]` returns the nth bracket or null.

### Methods
- `AddBracket(type, top staff number, bottom staff number)` — Creates a bracket (BracketFull 0, BracketBrace 1, BracketSub 2) spanning the staves; returns the Bracket.
- `ClearAll()` — Removes all brackets/sub-brackets/braces from the current part; returns the number removed.
- `DeleteNthBracket(n)` — Deletes the nth bracket; returns True if successful.

### Variables
- `NumChildren` — integer, read only — Number of child brackets, sub-brackets and braces.

---

## Clef

Derived from BarObject.

### Methods
None.

### Variables
- `ClefStyle` — string, read only — Name of this clef (may vary with Transposing Score state).
- `ConcertClefStyleId` — string, read only — Concert pitch identifier of the clef style.
- `ConcertClefStyle` — string, read only — Concert pitch name of this clef.
- `StyleId` — string, read only — Style identifier (passable to `Bar.AddClef`); may vary with Transposing Score.
- `TransposingClefStyle` — string, read only — Transposing score name of this clef.
- `TransposingClefStyleId` — string, read only — Transposing score identifier of the clef style.

---

## Comment

Derived from BarObject. Create using BarObject (Bar.AddComment).

### Methods
None.

### Variables
- `Maximized` — boolean, read/write — True if the comment is maximized.
- `Text` — string, read/write — The comment's text.
- `TextWithFormatting` — array, read only — Array of text segments and font/style change tokens (e.g. "\B\", "\b\").
- `TextWithFormattingAsString` — string, read only — Comment text including any font/style changes.
- `TimeStamp` — DateTime, read only — Date the comment was created or last edited.
- `UserName` — string, read only — Username of the user who created or last edited the comment.

---

## ComponentList

Array obtained from `Sibelius.HouseStyles` or `Sibelius.ManuscriptPapers`; usable in `for each` or with `[n]` to access Component objects.

### Methods
None.

### Variables
- `NumChildren` — integer, read only — Number of components.

---

## Component

Represents a Sibelius "component": a house style or manuscript paper.

### Methods
None.

### Variables
- `Name` — string, read only — Name of the component.

---

## DateTime

Returns information about the current date and time.

### Methods
None.

### Variables (all read only)
- `Seconds` — Seconds part of the time.
- `Minutes` — Minutes part of the time.
- `Hours` — Hours part of the time.
- `DayOfMonth` — Day of the month, 1-based.
- `Month` — Month of the year, 1-based.
- `Year` — The year.
- `NthDayOfWeek` — Day of the week, 0-based.
- `NthDayOfYear` — Day of the year, 0-based.
- `LongDate` — Human-readable date, e.g. "1st May 2008".
- `ShortDate` — Human-readable date, e.g. "01/05/2008".
- `LongDateAndTime` — e.g. "1st May 2008 14:07".
- `ShortDateAndTime` — e.g. "01/05/2008 14:07".
- `TimeWithSeconds` — Human-readable time (guide shows e.g. "14:07").
- `TimeWithoutSeconds` — Human-readable time (guide shows e.g. "14:07:23").

---

## Dictionary

Created with `CreateDictionary(name1, value1, ... nameN, valueN)`. Iterate values with `for each n in Dictionary` (or `for each Value n in`), names with `for each Name n in`, pairs with `for each Pair n in` (n.Name / n.Value).

### Methods
- `CallMethod(methodname,param1,...paramN)` — Calls the named method in the dictionary with the given parameters.
- `GetMethodNames()` — Returns a sparse array of the dictionary's method names.
- `GetPropertyNames()` — Returns a sparse array of all user property names (same as `_propertyNames`).
- `MethodExists(methodname)` — Returns True if the method exists in the dictionary.
- `PropertyExists(propertyname)` — Returns True if the user property exists in the dictionary.
- `SetMethod(methodname,Self,method)` — Binds a method (found in the plug-in Self) to the dictionary under methodname.

### Variables
None.

### Converting old-style hash tables
- `Hash.ConvertToDictionary()` — Returns a new Dictionary populated with strings converted from the old-style Hash.

---

## DocumentSetup

Accessed from a Score object; corresponds to Layout > Document Setup. Units default to millimeters — set `Units` first if you want another unit; set `PageSize` before adjusting PageWidth/PageHeight (setting PageSize overrides custom width/height).

### Methods
None.

### Variables (all read/write)
- `AboveTopStaveGap` — Top staff margin on each page (in Units).
- `AboveTopStaveGapAfterFirstPage` — Top staff margin on pages after the first (set FirstPageHasUniqueVerticalStaveMargins first).
- `BelowBottomStaveGap` — Bottom staff margin on each page.
- `BelowBottomStaveGapAfterFirstPage` — Bottom staff margin on pages after the first.
- `FirstPageHasUniqueVerticalStaveMargins` — True if the first page has different top/bottom staff margins ("After first page" checkbox).
- `Orientation` — OrientationPortrait (0) or OrientationLandscape (1); changing swaps top/bottom with left/right margins.
- `PageHeight` — Page height (in Units).
- `PageSize` — Page size constant (see "PageSize Values"); PageSizeCustom cannot be set directly.
- `PageWidth` — Page width (in Units).
- `MarginType` — PageMarginsSame (0), PageMarginsMirrored (1), PageMarginsDifferent (2).
- `PageBottomMargin` — Bottom page margin.
- `PageLeftMargin` — Left page margin.
- `PageRightMargin` — Right page margin.
- `PageTopMargin` — Top page margin.
- `RightPageLeftMargin` — Left margin for right-hand pages (setting it sets MarginType to PageMarginsDifferent).
- `RightPageRightMargin` — Right margin for right-hand pages (setting it sets MarginType to PageMarginsDifferent).
- `StaffLeftMarginFullNames` — Margin left of staves showing full instrument names.
- `StaffLeftMarginNoNames` — Margin left of staves showing no instrument names.
- `StaffLeftMarginShortNames` — Margin left of staves showing short instrument names.
- `StaffSize` — Staff size (in Units).
- `Units` — Units of measurement: DocumentSetupUnitsmm (0), DocumentSetupUnitsInches (1), DocumentSetupUnitsPoints (2); always returns 0 (mm).
- `UnitsInDocumentSetupDialog` — Units currently shown in the Document Setup dialog (values as Units).

---

## DynamicPartCollection

Accessed from a Score object; contains DynamicPart objects. First entry is always the full score; parts follow in creation order. ManuScript can access only one part at a time (the "current" DynamicPart of the Score). Avoid modifying staves/bars/objects not in `Score.CurrentDynamicPart` (creates invisible part overrides); DynamicPart objects are never re-used after deletion. `for each` iterates all valid parts (full score first); `[n]` returns the nth part (0 = full score) or null.

### Methods
- `CreateDefaultParts()` — Creates the default set of dynamic parts (as the New Part button); returns False if the score has no staves.
- `CreatePartFromStaff(staff)` — Creates a dynamic part from the Staff; returns the new DynamicPart or null.
- `DeletePart(dynamic part)` — Deletes the part; returns True/False (fails for the active part, full score, or a part of another score).

### Variables
- `NumChildren` — integer, read only — Number of DynamicPart objects returned by iteration.

---

## DynamicPart

Accessed from a DynamicPartCollection. `for each` returns the Staff objects in the part, top to bottom (may return a Staff not in Score.CurrentDynamicPart).

### Methods
- `AddStaffToPart(staff)` — Adds the staff to the bottom of the part; returns False on failure (errors on full score, duplicate staff, or foreign staff).
- `DeleteStaffFromPart(staff)` — Deletes the staff from the part; returns False on failure (errors on full score, absent staff, last staff, or foreign part).
- `IncludesStaff(staff)` — Returns True if the staff is contained in this part.

### Variables
- `IsFullScore` — boolean, read only — True for the full score only (not for score subsets).
- `IsScoreSubset` — boolean, read only — True if the part is a score subset (inclusion depends on the IncludeScoreSubsetsInDynamicPartCollection interpreter option).
- `IsSelectedInPartsWindow` — boolean, read only — True if the part is selected in the Parts window.
- `StaveCount` — integer, read only — Number of staves in the part.
- `ParentScore` — Score, read only — The Score containing this part.

---

## EngravingRules

Accessed from the Score object; corresponds to selected settings in House Style > Engraving Rules.

### Methods
- `BarNumberFrequency(BarNumberFrequencyCategory, [customFrequency])` — Sets bar number frequency: EverySystem (0), NoBarNumbers (1), EveryNthBar (2) with optional customFrequency in bars.

### Variables (all read/write)
- `AdjustTranspositionIfKeySigWraps` — boolean — Adjust note spelling for transposing instruments in remote keys.
- `BarlineJoinSystemEnd` — boolean — Join barlines at end of systems.
- `BarlineSingleStaves` — boolean — Barline at start of single staves.
- `BeamThickness` — spaces — Beam thickness (Beams and Stems page).
- `BarlineWidth` — spaces — Width of normal barlines.
- `CautionaryNaturalsInKeySignatures` — boolean — Key changes show cautionary naturals.
- `CueNoteScale` — percentage — Scaling of cue-sized notes relative to normal notes.
- `DashedBarlineGap` — spaces — Gap between dashes of dashed barlines.
- `DashedBarlineLength` — spaces — Length of dashes of dashed barlines.
- `DashedBarlineWidth` — spaces — Width of dashed barlines.
- `DottedBarlineGap` — spaces — Gap between dots of dotted barlines.
- `DottedBarlineWidth` — spaces — Width of dotted barlines.
- `DoubleBarlineSeparation` — spaces — Distance between lines in double/triple barlines.
- `DoubleBarlineWidth` — spaces — Width of lines in double/triple barlines.
- `DoubleTremoloStyle` — constant — DoubleTremolosTouchingStems (0), DoubleTremolosBetweenStems (1), DoubleTremolosOuterTremoloTouchingStems (2).
- `ExtraSpacesAboveForSystemObjectPositions` — number — Extra spaces above for System Object Positions.
- `ExtraSpacesBelowVocalStaves` — number — Extra spaces below vocal staves (for lyrics).
- `ExtraSpaceBetweenGroupsOfStaves` — number — Extra spaces between groups of staves.
- `FinalBarlineSeparation` — spaces — Distance between the two lines in final/repeat barlines.
- `FinalBarlineThinWidth` — spaces — Width of the thin line in final/repeat barlines.
- `FinalBarlineWidth` — spaces — Width of the thick line in final/repeat barlines.
- `GraceNoteScale` — percentage — Scaling of grace notes relative to normal notes.
- `InstrumentNamesFirstSystem` — constant — Names on first system: InstrumentNamesFull (0), InstrumentNamesShort (1), InstrumentNamesNone (2).
- `InstrumentNamesNewSections` — constant — Names at start of new sections (same values).
- `InstrumentNamesSubsequentSystems` — constant — Names on subsequent systems (same values).
- `JustifyGrandStaveInstruments` — boolean — Justify both staves of grand staff instruments.
- `JustifyMultiStaveInstruments` — boolean — Justify all staves of multi-staff instruments.
- `LegerLineThickness` — spaces — Thickness of leger lines.
- `RepeatBarlineAllDots` — boolean — Repeats with dots in all staff spaces.
- `RepeatBarlineDoubleThick` — boolean — Double thick lines for coincident repeats.
- `RepeatBarlineWings` — boolean — Wings on repeat barlines.
- `RespellRemoteKeysInTransposingScore` — boolean — Respell remote key signatures in transposing score.
- `ShowNameOfPrevailingInstrumentChangeAtStartOfSystems` — boolean — Change instrument names at start of system after instrument changes.
- `SlurMiddleThickness` — spaces — Default thickness of the middle of slurs.
- `SlurOutlineWidth` — spaces — Thickness of slur ends.
- `SmallStaffSizeScale` — percentage — Scaling of small staves relative to normal staves.
- `SpacesBetweenStaves` — number — "spaces between staves" value.
- `SpacesBetweenSystems` — number — "spaces between systems" value.
- `StaffJustificationPercentage` — percentage — "Justify staves when page is at least n% full".
- `StaffLineWidth` — spaces — Width of a staff line.
- `StemThickness` — spaces — Thickness of stems.
- `ThickBarlineWidth` — spaces — Width of thick barlines.
- `TieMiddleThickness` — spaces — Thickness of the middle of ties (Ties 1 page).
- `TieOutlineWidth` — spaces — Thickness of tie ends (Ties 1 page).

---

## File

Retrievable using `for each` on a Folder.

### Methods
- `Delete()` — Deletes the file; returns True if successful.
- `Rename(newFileName)` — Renames the file; returns True if successful.

### Variables (all read only)
- `CreationDate` — DateTime — File's creation date and time, local time.
- `CreationDateAndTime` — string — Date and time the file was last modified, in GMT.
- `ModificationDate` — DateTime — File's modification date and time, local time.
- `Name` — string — Complete pathname, no extension.
- `NameWithExt` — string — Complete pathname with extension.
- `NameNoPath` — string — Just the file's name, no extension.
- `Path` — string — Just the path to the file.
- `Type` — string — "File" for file objects.

---

## Folder

Retrievable from Sibelius object methods. `for each variable in` produces the Sibelius files as File objects; `for each type variable in` produces files of the given type (extension, e.g. SIB, MID, OPT; on Mac also the corresponding macOS Type). Both recurse into subfolders.

### Methods
- `FileCount(Type)` — Returns the number of files of the given type in the folder.

### Variables (all read only)
- `FileCount` — Number of Sibelius files in the folder.
- `FileCountAllTypes` — Number of files of all types.
- `Name` — Name of the folder.
- `Type` — "Folder" for folder objects.

---

## GuitarFrame

Derived from BarObject. Represents chord symbols (Create > Chord Symbol) whether or not they show a chord diagram; named GuitarFrame for historical reasons.

### Methods
- `CopyOutSuffixes()` — Returns an array of suffix elements in the chord (empty for unrecognised chords). Possible values: halfdim, dim, add6/9, 6/9, sus2/4, aug, omit5, alt, omit3, b13, maj13, #11, add13, 13, maj11, 11, dim13, #9, dim11, b9, maj9, b6, add9, #5, maj7, b5, dim9, #4, dim7, nc, sus9, 9, sus4, 7, add4, 6, sus2, 5, add2, m, maj, /.
- `GetChromaticPitchesOfChordInClosePosition(consider root)` — Returns chromatic pitches of the chord in close position; if consider root is True (default False), pitches are offset by the root's chromatic value.
- `GetEndStringForNthBarre(barreNum)` — String number on which the nth barré ends.
- `GetPitchOfNthString(stringNum)` — MIDI pitch of the given open string.
- `GetPositionOfFingerForNthBarre(barreNum)` — Fret position occupied by the nth barré.
- `GetPositionOfFingerOnNthString(stringNum)` — Finger position dot on the string relative to the top of the frame; 0 = open, –1 = not played.
- `GetStartStringForNthBarre(barreNum)` — String number from which the nth barré begins.
- `IsNthStringPartOfBarre(stringNum)` — True if the given string is part of a barré.
- `NthStringHasClosedMarkingAtNut(nth string)` — True if there's an X marking at the top/left of the string.
- `NthStringHasOpenMarkingAtNut(nth string)` — True if there's an O marking at the top/left of the string.

### Variables
- `BassAsString` — string, read/write per guide layout — Note name of the altered bass note (e.g. "F").
- `ChordNameAsStyledString` — string, read only — Chord name as it appears in the score (e.g. "Cm7").
- `ChordNameAsPlainText` — string, read only — Chord name as it appears when editing (plain text, e.g. "Cmmaj7").
- `ChromaticRoot` — 0–11, read only — Chromatic pitch of the root (C = 0).
- `ChromaticBass` — 0–11, read only — Chromatic pitch of the altered bass note.
- `DiatonicRoot` — 0–6, read only — Diatonic pitch of the root (0 = C, 1 = D...).
- `DiatonicBass` — 0–6, read only — Diatonic pitch of the altered bass note.
- `Fingerings` — string, read/write — Fingerings string, one character per string.
- `FrameIsVisible` — boolean, read only — True if showing a guitar chord diagram.
- `Horizontal` — boolean, read/write — True if the diagram is horizontally orientated.
- `LowestVisibleFret` — integer, read/write — Top fret shown; –1 resets to default.
- `NumBarresInChord` — integer, read only — Number of unique barrés in the diagram.
- `NumberOfFrets` — integer, read/write — Number of frets (horizontal lines); –1 resets to default.
- `NumberOfStrings` — integer, read only — Number of strings (vertical lines).
- `NumPitchesInClosePosition` — integer, read only per guide context — Number of unique pitches in close position with no duplicates.
- `Recognized` — boolean, read only — True if a recognized chord type (False = shown red in score).
- `RootAsString` — string, read/write per guide layout — Note name of the root (e.g. "C#").
- `ScaleFactor` — percentage, read/write — Scale factor of the diagram.
- `ShowFingerings` — boolean, read only — True if the fingerings string is displayed.
- `SuffixText` — string, read only — Suffix part of the chord symbol, or empty if not recognized.
- `TextIsVisible` — boolean, read only — True if showing a text chord symbol.
- `TransposingChromaticRoot` — read only — Chromatic pitch of the root at transposed pitch (regardless of Transposing Score state).
- `TransposingChromaticBass` — read only — Chromatic pitch of the altered bass at transposed pitch.
- `TransposingDiatonicRoot` — read only — Diatonic pitch of the root at transposed pitch.
- `TransposingDiatonicBass` — read only — Diatonic pitch of the altered bass at transposed pitch.
- `TransposingRootAsString` — read only — Root pitch string at transposed pitch.
- `TransposingBassAsString` — read only — Altered bass pitch string at transposed pitch.
- `VisibleComponents` — constant, read/write — TextOnly, FrameOnly, FrameAndText or InstrumentDependent.

---

## GuitarScaleDiagram

Derived from BarObject; guitar scale diagrams as created by Create > Guitar Scale Diagram.

### Methods
- `GetDotFingeringsOnNthString(nth string)` — Array of strings of the text entered on the dots of a string.
- `GetDotSymbolsOnNthString(nth string)` — Array of dot appearance values: DotStyleCircle, DotStyleFilledCircle, DotStyleSquare, DotStyleFilledSquare, DotStyleDiamond, DotStyleFilledDiamond.
- `GetPitchesOfDotsOnNthString(nth string)` — Array of pitches of all dots on a string, ascending.
- `GetPitchOfNthString(stringNum)` — MIDI pitch of the given open string.

### Variables
- `Fingerings` — string, read/write — Fingerings string, one character per string; use "–" for no fingering.
- `Horizontal` — boolean, read/write — True if horizontally orientated.
- `LowestVisibleFret` — integer, read/write — Top fret shown; –1 resets to default.
- `NumberOfFrets` — integer, read/write — Number of frets; –1 resets to default.
- `NumberOfStrings` — integer, read only — Number of strings.
- `Root` — 0–11, read only — Chromatic pitch of the scale's root (C = 0).
- `ScaleFactor` — percentage, read/write — Scale factor of the diagram.
- `ScaleType` — constant, read only — Type of the diagram (see "GuitarScaleDiagram Type Values").
- `ShowFingerings` — boolean, read only — True if the fingerings string is displayed.

---

## HitPointList

Retrievable as the `HitPoints` variable of a score; usable in `for each` or with `[n]`. HitPoints are stored in time order; use `ShiftTimes` to move all by the same amount.

### Methods
- `Clear()` — Removes all hit points from the score.
- `CreateHitPoint(timeMs,label)` — Creates a hit point at the given time (ms) with a label; returns its index.
- `Remove(index)` — Removes the given hit point number.
- `ShiftTimes(timeMs)` — Adds (or, if negative, subtracts) the given time to all hit points.

### Variables
- `NumChildren` — integer, read only — Number of hit points.

---

## HitPoint

Individual element of the HitPointList.

### Methods
None.

### Variables
- `Bar` — Bar, read only — Bar in which this hit point occurs.
- `Label` — string, read/write — Name of the hit point.
- `Position` — read only — Position within the bar of the hit point.
- `Time` — milliseconds, read/write — Time of the hit point (changing it may reorder the HitPointList).

---

## InstrumentChange

Derived from BarObject; information about instrument changes in the score.

### Methods
None.

### Variables
- `FullInstrumentName` — string, read/write — Full instrument name of the change.
- `FullInstrumentNameWithFormatting` — string, read/write — Full instrument name including font/style changes.
- `FullStaffName` — string, read/write — Full staff name of the change.
- `FullStaffNameWithFormatting` — string, read/write — Full staff name including font/style changes.
- `ShortInstrumentName` — string, read/write — Short instrument name of the change.
- `ShortInstrumentNameWithFormatting` — string, read/write — Short instrument name including font/style changes.
- `ShortStaffName` — string, read/write — Short staff name of the change.
- `ShortStaffNameWithFormatting` — string, read/write — Short staff name including font/style changes.
- `StyleIdword` — string, read only — Style ID of the new instrument.
- `TextLabel` — string, read only — Text shown above the staff at the instrument change.

---

## InstrumentTypeList

List of InstrumentType objects common to a score. `for each type variable in` returns each type in alphabetical order by style ID; `[n]` returns the nth type or null.

### Methods
None.

### Variables
- `NumChildren` — integer, read only — Number of unique instrument types in the list.

---

## InstrumentType

Information about an individual instrument type.

### Methods
- `Clone()` — Makes an exact copy of the instrument type.
- `PitchOfNthString(string num)` — Pitch of a given string on a tablature staff (string 0 = lowest).

### Variables
- `Balance` — 0–100, read only — Default balance.
- `Category` — integer, read only — Staff type category: 0 pitched, 1 percussion, 2 tablature.
- `ChromaticTransposition` — semitones, read/write — Transposition of transposing instruments (e.g. –2 for B-flat Clarinet).
- `ChromaticTranspositionInScore` — semitones, read only — Transposition in a concert pitch score (octave-transposing instruments, e.g. 12 piccolo, –12 guitar).
- `ComfortableRangeHigh` — MIDI pitch, read only — Highest comfortable note.
- `ComfortableRangeLow` — MIDI pitch, read only — Lowest comfortable note.
- `ConcertClefStyleId` — string, read only — Style ID of the instrument's normal clef.
- `DefaultSoundId` — string, read only — Default sound ID used by the instrument.
- `DiatonicTransposition` — steps, read/write — Diatonic transposition (e.g. –1 for B-flat Clarinet).
- `DiatonicTranspositionInScore` — steps, read only — Diatonic transposition in a concert pitch score.
- `DialogName` — string, read/write — Name shown in the Create > Instruments dialog.
- `FullName` — string, read only — Name shown on systems with full instrument names.
- `HasBracket` — boolean, read only — True if the instrument has a bracket.
- `HasKeySignatureOrTuning` — boolean — True if the Key signature / Tuning checkbox is on in Edit Staff Type.
- `InstrumentTypeForChordDiagrams` — string — Style ID of the tab instrument type used for chord diagram tunings.
- `IsVocal` — boolean, read only — True if the Vocal staff option is on (dynamics default above the staff).
- `NumStaveLines` — integer, read only — Number of staff lines.
- `NumStrings` — integer, read only — Number of strings on a tablature staff.
- `OtherClefStyleId` — string, read only — Clef style ID of the second staff of grand staff instruments.
- `Pan` — –127..127, read only — Default pan setting.
- `ProfessionalRangeHigh` — MIDI pitch, read only — Highest playable note for a professional player.
- `ProfessionalRangeLow` — MIDI pitch, read only — Lowest playable note for a professional player.
- `ShortName` — string, read only — Name shown on systems with short instrument names.
- `StyleId` — string, read only — Style ID of the instrument.
- `TransposingClefStyleId` — string, read only — Clef style ID used when Transposing Score is enabled.

---

## KeySignature

Derived from BarObject.

### Methods
None.

### Variables (all read only)
- `AsText` — string — Name of the key signature.
- `IsOneStaffOnly` — boolean — True if the key signature belongs to one staff only.
- `Major` — boolean — True if a major key.
- `Sharps` — integer — Number of sharps (positive) or flats (negative).

---

## Line

Anything creatable from Create > Line (CrescendoLine, DiminuendoLine, etc.). Derived from BarObject.

### Methods
None.

### Variables
- `Duration` — 1/256th quarters, read/write — Total duration of the line.
- `EndBarNumber` — integer, read only — Bar number in which the line ends.
- `EndPosition` — read only — Position within the final bar at which the line ends.
- `RhDx` — 1/32 spaces, read/write — Horizontal offset of the right-hand side of the line.
- `RhDy` — 1/32 spaces, read/write — Vertical offset of the right-hand side from the center staff line (positive up).
- `StyleId` — string, read only — Identifier of the line style.
- `StyleAsText` — string, read only — Name of the line style.

---

## LyricItem

Derived from BarObject.

### Methods
None.

### Variables
- `Duration` — 1/256th quarters, read/write — Total duration of the lyric line.
- `NumNotes` — integer, read/write — Number of notes occupied by the lyric (also set Duration to match).
- `StyleAsText` — string, read/write — Text style name.
- `StyleId` — string, read/write — Text style identifier.
- `SyllableType` — constant, read/write — EndOfWord or MiddleOfWord (affects justification and hyphens).
- `Text` — string, read/write — The lyric text.

---

## NoteRest

Derived from BarObject. Contains Note objects in increasing diatonic pitch order; `for each` returns the notes.

### Methods
- `AddAcciaccaturaBefore(sounding pitch,[duration[,tied[,voice[,diatonic pitch[,string number[,force stem dir]]]]]])` — Adds a slashed grace note before this NoteRest; returns the Note created.
- `AddAppoggiaturaBefore(sounding pitch,[duration[,tied[,voice[,diatonic pitch[,string number[,force stem dir]]]]]])` — As above, without stem slash.
- `AddNote(pitch[,tied[,diatonic pitch[,string number]]])` — Adds a note with the given MIDI pitch (60 = middle C), e.g. to build a chord; returns the Note created.
- `Delete()` — Deletes all notes in the NoteRest, converting the chord into a rest of similar duration.
- `FlipStem()` — Flips (toggles) the stem of this NoteRest.
- `GetArticulation(articulation number)` — Returns True/False whether the given articulation is set (see "Articulations" constants).
- `NoteRest[array element]` — Returns the nth note in the chord by increasing diatonic pitch (from 0).
- `RemoveNote(note)` — Removes the given Note object.
- `SetArticulation(articulation number,set)` — Turns the given articulation on or off.
- `Transpose(degree, interval type[,keep double accs])` — Transposes the whole NoteRest by degree (0-based) and interval type; keep double accs defaults True.

### Variables
- `ArpeggioDx` — 1/32 spaces, read/write — Horizontal offset of the arpeggio line.
- `ArpeggioType` — constant, read/write — ArpeggioTypeNone, ArpeggioTypeNormal, ArpeggioTypeUp, ArpeggioTypeDown.
- `ArpeggioTopDy` — 1/32 spaces, read/write — Vertical offset of the top of the arpeggio line.
- `ArpeggioBottomDy` — 1/32 spaces, read/write — Vertical offset of the bottom of the arpeggio line.
- `ArpeggioHidden` — boolean, read/write — True if the arpeggio line is hidden.
- `Articulations` — read/write — Copies the full articulation set between NoteRests.
- `Beam` — constant, read/write — StartBeam, ContinueBeam, NoBeam or SingleBeam.
- `CrossStaff` — integer, read only per context — 0 Not Crossed, 1 Crossed Above, 2 Crossed Below; –1/–2 if crossed with no staff available.
- `DoubleTremolos` — 0–7, read/write — Double tremolo strokes starting at this note (set on the first of two equal-duration notes).
- `Duration` — read only — Duration of the NoteRest.
- `FallDx` — 1/32 spaces, read/write — Horizontal offset of a fall.
- `FallType` — constant, read/write — FallTypeNone, FallTypeNormal, FallTypeDoit.
- `FeatheredBeamType` — constant, read/write — FeatheredBeamNone (0), FeatheredBeamAccel (1), FeatheredBeamRit (2).
- `GraceNote` — boolean, read only — True if a grace note.
- `HasStemlet` — boolean, read only — True if showing a stemlet.
- `Highest` — Note, read only — Highest Note object in the chord.
- `IsAcciaccatura` — boolean, read only — True if a grace note with slash.
- `IsAppoggiatura` — boolean, read only — True if a grace note without slash.
- `Lowest` — Note, read only — Lowest Note object in the chord.
- `NoteCount` — integer, read only — Number of notes in the chord.
- `ParentTupletIfAny` — Tuplet or null, read only — Innermost tuplet intersecting the NoteRest.
- `PositionInTuplet` — read only — Position relative to the parent tuplet's duration/scale (or within the bar if no tuplet).
- `RestPosition` — read/write — Vertical position of a rest.
- `ScoopDx` — 1/32 spaces, read/write — Horizontal offset of a scoop or plop.
- `ScoopType` — constant, read/write — ScoopTypeNone, ScoopTypeNormal, ScoopTypePlop.
- `StemFlipped` — boolean, read only — True if the stem is flipped.
- `StemletType` — constant, read/write — StemletCustomOff, StemletCustomOn or StemletUseDefault.
- `Stemweight` — read only — Stem weight taking beams into account; special constants StemweightUp/Down/FlipUp/FlipDown; < 0 means stem points up.
- `SingleTremolos` — –1..7, read/write — Tremolo strokes on the stem (–1 = "z on stem").

---

## Note

Only found in NoteRests; corresponds to individual noteheads.

### Methods
- `Delete()` — Removes a single note from a chord.
- `Transpose(degree, interval type[,keep double accs])` — Transposes and returns this Note (individual notes cannot be transposed diatonically).

### Variables
- `Accidental` — constant, read only — The accidental (Sharp, Flat, etc.).
- `AccidentalStyle` — constant, read/write — NormalAcc, HiddenAcc, CautionaryAcc or BracketedAcc.
- `Bracketed` — read/write — Bracketed state of the note (F9 Keypad layout).
- `Color` — 24-bit RGB, read/write — Note color (promoted to the parent NoteRest when all notes match; NoteRest-attached objects not supported).
- `ColorAlpha` — 0–255, read/write — Alpha component of the note color.
- `ColorRed` — 0–255, read/write — Red component.
- `ColorGreen` — 0–255, read/write — Green component.
- `ColorBlue` — 0–255, read/write — Blue component.
- `DiatonicPitch` — integer, read/write — Diatonic pitch, 7 per octave (35 = middle C). Changing from full score respells score+part; from a part, respells part only; sounding pitch never differs.
- `IsAccidentalVisible` — boolean, read only — True if the note's accidental is visible (Keypad button lit).
- `Hidden` — boolean, read/write — True if the individual note is hidden.
- `LvTie` — boolean, read/write — True if the note has an L.V. tie.
- `Name` — string, read only — The pitch of the note as a string.
- `NoteStyle` — index, read/write — Notehead style index (see "Note Style Names").
- `NoteStyleName` — string, read/write — Notehead style name (nonexistent names are ignored).
- `OriginalDeltaSr` — 1/256th quarters, read/write — Live start position (Playback panel); positive or negative.
- `OriginalDuration` — 1/256th quarters, read/write — Live duration (Playback panel).
- `OriginalVelocity` — 0–127, read/write — Live velocity (Playback panel).
- `ParentNoteRest` — NoteRest, read only — The NoteRest holding this note.
- `Pitch` — MIDI pitch, read only — 60 = middle C.
- `Slide` — boolean, read/write — True if the note has a slide.
- `SlideStyleId` — string, read/write — Slide line style (e.g. "line.staff.gliss.straight", ".wavy", "line.staff.plain", "line.staff.port.straight"; custom styles allowed).
- `StringNum` — integer, read only — String number on a tablature staff (–1 if none; 0 = bottom string).
- `Tied` — boolean, read/write — True if tied to the following note.
- `TiedInto` — boolean, read/write — True if a tie-into object is attached to the left of the note.
- `TieIntoStyle` — string, read/write — Tie-into style: Solid, Dashed, Dotted (nonexistent names ignored).
- `TieStyle` — string, read/write — Tie style: Solid, Dashed, Dotted (nonexistent names ignored).
- `WrittenAccidental` — constant, read only — The accidental, taking transposition into account.
- `WrittenDiatonicPitch` — integer — Written diatonic pitch, taking transposition into account if Score.TransposingScore is True (35 = middle C).
- `WrittenName` — string, read only — Written pitch as a string (taking transposition into account).
- `WrittenPitch` — MIDI pitch, read only — Written pitch, taking transposition into account if Score.TransposingScore is True (60 = middle C).
- `UseOriginalDeltaSrForPlayback` — boolean, read/write — True if the Live start position should be used for Live Playback.
- `UseOriginalDurationForPlayback` — boolean, read/write — True if the Live duration should be used for Live Playback.
- `UseOriginalVelocityForPlayback` — boolean, read/write — True if the Live velocity should be used for Live Playback.

---

## PageNumberChange

Gets/sets the attributes of a page number change at the end of a bar or on a blank page.

### Methods
- `SetFormatChangeOnly(format change only)` — If True, same as unchecking "New page number": numbering continues consecutively while allowing visibility changes.
- `SetHideOrShow(page number visibility)` — Takes a Page number visibility constant to set visibility of this change and subsequent pages.
- `SetPageNumber(page number)` — Assigns the new integer page number.
- `SetPageNumberFormat(format)` — Takes one of the four Page number format constants.

### Variables (all read only)
- `BarNumber` — integer — Bar number of the change.
- `HideOrShow` — constant — One of the three Page number visibility constants.
- `PageNumber` — integer — Page number as an integer (e.g. Roman "x" = 10).
- `PageNumberAsString` — string — Page number change as shown on the page.
- `PageNumberBlankPageOffset` — integer — Blank page offset of the change, or 0 if none.
- `PageNumberFormat` — constant — One of the four Page number format constants.

---

## PluginList

Array obtained from `Sibelius.Plugins`; usable in `for each` or with `[n]` to access Plugin objects.

### Methods
- `Contains(pluginName)` — Returns True if a plug-in with the given name is installed.

### Variables
- `NumChildren` — integer, read only — Number of plug-ins.

---

## Plugin

Represents an installed plug-in.

### Methods
- `MethodExists(method)` — Returns True if the method exists in this Plugin object.
- `DataExists(data)` — Returns True if the data exists in this Plugin object.
- `DialogExists(dialog)` — Returns True if the dialog exists in this Plugin object.

### Variables (all read only)
- `File` — File — File the plug-in was loaded from.
- `Name` — string — Name of the plug-in.

---

## RehearsalMark

Derived from BarObject; found in the system staff only. Has an internal number and a visible text representation.

### Methods
None.

### Variables
- `Mark` — number — Internal number of the mark (default consecutive from zero; user can set specific numbers).
- `MarkAsText` — string — Textual representation as drawn in the score (per Engraving Rules; numerical or alphabetical).

---

## Score

Obtained via the Sibelius object (e.g. `Sibelius.ActiveScore`). Contains one SystemStaff and one or more Staff objects. `for each` returns each staff (not the system staff); `for each type in` returns objects chronologically top-to-bottom then left-to-right (excluding system staff).

### Methods
- `AddBars(n)` — Adds n bars to the end of the score.
- `ApplyStyle(style file,"style",["style"])` — Imports named styles from a house style (.lib) file: ENGRAVINGRULES, DOCSETUP, HOUSE, TEXT, SYMBOLS, LINES, NOTEHEADS, CLEFS, DICTIONARY, SPACINGRULE, DEFAULTPARTAPPEARANCE, INSTRUMENTSANDENSEMBLES, MAGNETICLAYOUTOPTIONS or ALLSTYLES (ENGRAVINGRULES/DOCSETUP/HOUSE/ALLSTYLES are mutually exclusive).
- `ClefStyleId(clef style name)` — Returns the identifier of the named clef style, or empty string.
- `CreateInstrument(style ID[,change names,["full name",["short name"]]])` — Creates an instrument by style ID; returns True/False.
- `CreateInstrumentAtBottom(...)` — As CreateInstrument, always below all existing instruments.
- `CreateInstrumentAtBottomReturnStave(...)` — As above but returns the Staff created, or null.
- `CreateInstrumentAtTop(...)` — As CreateInstrumentAtBottom, but above all existing instruments.
- `CreateInstrumentAtTopReturnStave(...)` — As above but returns the Staff created, or null.
- `CreateInstrumentReturnStave(...)` — Like CreateInstrument but returns the Staff created (top stave for multi-staff instruments), or null.
- `ExportHouseStyle(filename)` — Exports the house style to the default "House Style" folder or a full path.
- `ExportPartsAsPDF(filename[,single file[,part IDs[,include score]]])` — Exports parts as PDF (filename tokens: %f, %t, %p, %n, %o, %d, %h); single file defaults True; part IDs is a sparse array or 0 for all; include score defaults False.
- `ExportScoreAsPDF(filename)` — Exports the full score as PDF (same filename tokens).
- `ExtractParts([show_dialogs[,parts path[,open parts]]])` — Extracts parts, optionally silently, into a folder, optionally opening them (default True).
- `FreezeMagneticLayoutPositions()` — Freezes Magnetic Layout positions for every object in the score.
- `GetLocationTime(bar number[,position[,pass]])` — Time in ms of a bar/position (first pass unless pass given); –1 if invalid.
- `GetVersions()` — Returns the score's VersionHistory object. (Listed twice in the guide.)
- `HideEmptyStaves(startStaveNum,endStaveNum,startBarNum,endBarNum)` — Hides empty staves in the range (1-based, active part).
- `InsertBars(n,barNum[,length])` — Inserts n bars before barNum, optionally irregular of the given length.
- `InternalPageNumToExternalPageNum(pagenum)` — Returns the external page number string for an internal page number.
- `IsScoreSubset()` — Returns True if the current active score view is a score subset.
- `LineStyleId(line style name)` — Returns the identifier of the named line style, or empty string.
- `NoteStyleIndex(notehead style name)` — Returns the index of the named note style, or –1.
- `NthStaff(staff index from 1)` — Returns the nth staff of the score or current dynamic part.
- `OptimizeStaffSpacing(from staff number[, to staff number[,from bar[,to bar]]])` — Layout > Optimize Staff Spacing for the range (defaults: bottom staff, bar 1, last bar).
- `PlayLiveTempo(play)` — Switches Play > Live Tempo on/off.
- `RemoveAllHighlights()` — Removes all highlights in the score.
- `RemoveVideo()` — Removes an attached video from the score.
- `RenameTextStyle("old name","new name")` — Renames a text style.
- `Save(filename)` — Saves the score, overwriting any previous file of the same name.
- `SaveAs(filename,type[,use_defaults,foldername])` — Saves in a format; types: SIBL, EMF, BMP, PICT, PDF, PNG, Midi, TIFF, MUSICXML, MXL (XML still valid, saved as .musicxml).
- `SaveAsAudio(filename[,include all staves[,play from start[,bit depth[,sample rate]]]])` — Exports WAV (PC)/AIFF (Mac); VST/AU-only playback configs; returns True/False.
- `SaveAsCompressedAudio(filename[,include all staves[,play from start[,bit rate[,sample rate]]]])` — Exports MP3; same conditions; returns True/False.
- `SaveAsEarlierVersion(versionIdentifier, filename[, foldername])` — Saves in an earlier Sibelius format (see Sibelius.EarlierVersionNames / EarlierVersionIdFromName).
- `SaveAsSibelius2(filename[,foldername])` — Saves in Sibelius 2 format (may alter aspects of the score).
- `SaveAsSibelius3(filename[,foldername])` — Saves in Sibelius 3 format.
- `SaveAsSibelius4(filename[,foldername])` — Saves in Sibelius 4 format.
- `SaveAsSibelius5(filename[,foldername])` — Saves in Sibelius 5 format.
- `SaveAsSibelius6(filename[,foldername])` — Saves in Sibelius 6 format.
- `SaveAsSibelius7(filename[,foldername])` — Saves in Sibelius 7 format.
- `SaveAsSibelius7_5(filename[,foldername])` — Saves in Sibelius 7.5 format.
- `SaveAsSibelius8(filename[,foldername])` — Saves in Sibelius 8 format.
- `SaveAsSibelius8_5(filename[,foldername])` — Saves in Sibelius 8.1 format (as stated in the guide).
- `SaveAsSibelius8_6(filename[,foldername])` — Saves in Sibelius 8.6 format.
- `SaveAsSibelius2020_1(filename[,foldername])` — Saves in Sibelius 2020.1 format (listed twice in the guide).
- `SaveCopyAs(filename[,foldername])` — Saves a copy without updating the score's filename in Sibelius.
- `SetPlaybackPos(bar number,sr)` — Sets the playback line to a bar and rhythmic position.
- `ShowEmptyStaves(startStaveNum,endStaveNum,startBarNum,endBarNum)` — Shows empty staves hidden by Hide Empty Staves in the range.
- `StaveTypeId(stave type name)` — Returns the identifier of the named stave type, or empty string.
- `SystemCount(page num)` — Number of systems on a page (first page = 1).
- `SymbolExists(symbol)` — Returns True if the symbol index or name is found in the score.
- `SymbolIndex(symbol name)` — Returns the index of the named symbol, or –1.
- `TextStyleId(text style name)` — Returns the identifier of the named text style, or empty string.
- `ViewLiveTempo(view)` — Switches View > Live Tempo on/off.

### Variables
- `Arranger` — string, read/write — Arranger from File > Score Info.
- `Artist` — string, read/write — Artist from File > Score Info.
- `AutoOptimizeEnabled` — boolean, read/write — Activates the Auto-Optimize Staff Spacing layout option.
- `Barlines` — Barlines, read only — Barline groupings in the score.
- `BarPlaybackOrder` — sparse array, read/write — Bar playback order per repeat structure; set with an array of bar numbers, or null to restore automatic order.
- `BarPlaybackOrderString` — string, read/write — Playback order as a string, e.g. "1–8, 1–5, 9–12"; null restores automatic order.
- `BracketsAndBraces` — BracketsAndBraces, read only — Brackets/braces in the score.
- `Composer` — string, read/write — Composer from File > Score Info.
- `ComposerDates` — string, read/write — Composer's dates from File > Score Info.
- `Copyist` — string, read/write — Copyist from File > Score Info.
- `Copyright` — string, read/write — Copyright from File > Score Info.
- `CurrentDynamicPart` — DynamicPart, read/write — Current dynamic part (does not change display; use Sibelius.ShowDynamicPart).
- `CurrentPlaybackPosBar` — integer — Bar number where the playback line is located.
- `CurrentPlaybackPosSr` — integer — Rhythmic position within the bar of the playback line.
- `Dedication` — string, read/write — Dedication from File > Score Info.
- `DocumentSetup` — DocumentSetup, read only — Layout > Document Setup settings.
- `DynamicParts` — DynamicPartCollection, read only — Dynamic parts (always up to date).
- `EditingLocked` — boolean, read/write — True when the score is locked against edits.
- `EnableScorchPrinting` — boolean, read/write — "Allow printing and saving" in Export Scorch Web Page.
- `EngravingRules` — EngravingRules, read only — Engraving Rules settings.
- `FileName` — string, read only — The filename of the score.
- `FocusOnStaves` — boolean, read/write — True if View > Focus on Staves is enabled.
- `HitPoints` — HitPointList, read/write — The score's hit points.
- `InstrumentChanges` — string, read/write — "Instrument changes" from File > Score Info.
- `InstrumentTypes` — InstrumentTypeList — The score's instrument types.
- `IsDynamicPart` — boolean, read only — True if the current active score view is a part.
- `LiveMode` — boolean, read/write — True if Play > Live Playback is on.
- `Lyricist` — string, read/write — Lyricist from File > Score Info.
- `MagneticLayoutEnabled` — boolean, read/write — True if Magnetic Layout is on.
- `MainMusicFontName` — string, read/write — Main music font (e.g. "Opus").
- `MainTextFontName` — string, read/write — Main text font (e.g. "Times New Roman").
- `MusicTextFontName` — string, read/write — Music text font (e.g. "Opus Text").
- `NumberOfPrintCopies` — integer, read/write — Number of copies to print.
- `OpusNumber` — string, read/write — Opus number from File > Score Info.
- `OriginalProgramVersion` — integer — Sibelius version the score was created in: major*1000 + minor*100 + revision*10 (e.g. 8.3.1 → 8310).
- `OtherInformation` — string, read/write — More information from File > Score Info.
- `PageCount` — integer, read only — Number of pages.
- `PartName` — string, read/write — Part Name from File > Score Info.
- `Publisher` — string, read/write — Publisher from File > Score Info.
- `Redraw` — boolean, write only — True to redraw after each change, False to disallow redrawing.
- `ScoreDuration` — milliseconds, read only — Duration of the score.
- `ScoreEndTime` — milliseconds, read only — Duration plus score start time.
- `ScoreHeight` — millimeters, read only — Page height of the score.
- `ScoreStartTime` — milliseconds, read only — Timecode of first bar value.
- `ScoreWidth` — millimeters, read only — Page width of the score.
- `Selection` — Selection, read only — The score's selection (list of selected objects).
- `ShowMultiRests` — boolean, read/write — True if Layout > Show Multirests is on.
- `StaffCount` — integer, read only — Number of staves.
- `StaffHeight` — millimeters, read only — Staff height.
- `Subtitle` — string, read/write — Subtitle of the score.
- `SystemCount` — integer, read only — Number of systems in the score.
- `SystemObjectPositions` — SystemObjectPositions, read only — House Style > System Object Positions settings.
- `SystemStaff` — SystemStaff, read only — The score's system staff.
- `Title` — string, read/write — Title from File > Score Info.
- `TransposingScore` — boolean, read/write — True if Notes > Transposing Score is on.
- `UsingManualBarPlayOrder` — boolean, read only — True if Manual repeats playback is chosen.
- `YearOfComposition` — string, read/write — Year of composition from File > Score Info.

---

## Selection

`for each` returns every BarObject in the selection; `for each type in` returns objects of the type (system-staff objects included for system selections).

### Methods
- `Clear()` — Removes any existing selections from the active score.
- `ClipboardContainsData([clipboard Id])` — True if the given clipboard contains data (0/none = Sibelius's internal clipboard).
- `Copy([clipboard Id])` — Copies the selection to Sibelius's internal clipboard (0/none) or a numbered temporary clipboard scoped to this Selection.
- `Delete([remove staves])` — Deletes the selected music; wholly selected staves are removed (True/omitted) or hidden (False).
- `ExcludeStaff(staff number)` — Removes an individual stave from an existing passage selection.
- `HideSelectedEmptyStaves()` — Hides empty staves in the selection (Hide Empty Staves).
- `IncludeStaff(staff number)` — Adds a non-consecutive stave to an existing passage selection.
- `Paste([clipboard Id[,reset positions]])` — Pastes from a clipboard to the start of the selection (overwrites; one copy only); reset positions True resets object positions; returns True if successful.
- `PasteToPosition(stave num, bar num, position[, clipboard Id[,reset positions]])` — Pastes from a clipboard to a specific location.
- `RestoreSelection()` — Restores the selection recorded with StoreCurrentSelection.
- `Respace` — Respaces all notes in the selection.
- `RespaceIncludeHiddenNotes` — Respaces including hidden notes.
- `RespaceIgnoreHiddenNotes` — Respaces excluding hidden notes.
- `SelectPassage(start barNum[,end barNum[,top staveNum[,bottom staveNum[,start pos[,end pos]]]]])` — Makes a passage selection (positions may be snapped to a NoteRest).
- `SelectSystemPassage(start barNum[,end barNum[,start pos[,end pos]]])` — Makes a system selection (positions may be snapped to a NoteRest).
- `StoreCurrentSelection()` — Stores the current selection internally for RestoreSelection.
- `Transpose(degree, interval type[,keep double accs[,transpose keys]])` — Transposes the selected music (0-based degrees; keep double accs and transpose keys default True).

### Variables (all read only)
- `BottomStaff` — Number of the bottom staff of a passage.
- `FirstBarNumber` — Internal bar number of the first bar of a passage.
- `FirstBarNumberString` — External bar number of the first bar (with format changes).
- `FirstBarSr` — Position of the start of the passage in the first bar.
- `IsPassage` — True if a passage selection (vs multiple selection).
- `IsSystemPassage` — True if the selection includes the system staff.
- `LastBarNumber` — Internal bar number of the last bar of a passage.
- `LastBarNumberString` — External bar number of the last bar (with format changes).
- `LastBarSr` — Position of the end of the passage in the last bar.
- `TopStaff` — Number of the top staff of a passage.

Note: temporary clipboards belong to the Selection object; use Sibelius's internal clipboard (0) to transfer data between two different scores.

---

## Sibelius

Predefined variable representing the Sibelius program; used to open/close scores, show dialogs, and get Score objects. `for each` returns each open score.

### Methods
- `AppendLineToFile(filename,text[,use_unicode])` — Appends a line of text (with line feed); returns True if successful.
- `AppendLineToRTFFile(filename,text)` — Appends a line to an RTF file; formatting via `\B\ \I\ \U\ \n\ \b\ \i\ \u\ \ffontname\ \spoints\`.
- `AppendTextFile(filename,text[,use_unicode])` — Appends text (Unicode by default, Latin-1 if use_unicode False); returns True if successful.
- `CalculateDegree(source pitch, dest pitch, upward interval)` — Returns the 0-based degree between two note names (e.g. "C#","G",False → 3).
- `CalculateInterval(source pitch, dest pitch, upward interval)` — Returns an Interval Type usable with NoteRest.Transpose / Selection.Transpose.
- `Close(show dialogs)` — Closes the current score or part view (saving warnings shown if True).
- `CloseAllWindows(show dialogs)` — Closes all open document windows.
- `CloseAllWindowsForScore(score, showDialogs)` — Closes all windows associated with the score.
- `CloseDialog(dialogName,pluginName,returnValue)` — Closes a plug-in dialog programmatically, returning the boolean returnValue.
- `CloseWindow(show dialogs)` — Closes the current window (all its tabs).
- `CommandExists(CommandID)` — True if the CommandID is available for execution.
- `CreateFolder(foldername)` — Creates a folder; returns the Folder object or null.
- `CreateProgressDialog(caption,min value,max value)` — Creates the progress dialog (slider for long operations).
- `CreateRTFFile(filename)` — Creates an RTF file (destroying any existing file); returns True if successful.
- `CreateTextFile(filename)` — Creates a plain text file (destroying any existing file); returns True if successful.
- `DestroyProgressDialog()` — Destroys the progress dialog.
- `EarlierVersionIdFromName(versionName)` — Returns an internal version identifier for Score.SaveAsEarlierVersion (input from Sibelius.EarlierVersionNames).
- `EnableControlById(plugin,dialog,controlID,enable)` — Enables/disables a control on a plug-in dialog by ID.
- `EnableNthControl(nth control, enable)` — Enables/disables a control by 0-based creation order (EnableControlById recommended instead).
- `Execute(CommandID)` — Executes the specified command (any command in the Home tab Commands list); combine with Cmd() to use names.
- `FileExists(filename)` — True if the file exists.
- `FolderExists(foldername)` — True if the folder exists.
- `FindCommandId(Command Name)` — Translates a command name (case-insensitive, current language) to a CommandId string, or empty string.
- `FindCommandName(Id)` — Translates a CommandId or StyleId to its Name in the current language, or empty string.
- `FindStyleId(Style Name)` — Translates a style name (case-insensitive, current language) to a StyleId string, or empty string.
- `GetDocumentsFolder()` — Returns the user's My Documents (Windows) / Documents (Mac) folder.
- `GetElapsedCentiSeconds(timer number)` — Time since ResetStopWatch, in 1/100 s.
- `GetElapsedMilliSeconds(timer number)` — Time since ResetStopWatch, in ms.
- `GetElapsedSeconds(timer number)` — Time since ResetStopWatch, in seconds.
- `GetFile(file path)` — Returns a new File object for a path.
- `GetFolder(file path)` — Returns a new Folder object for a path.
- `GetListOfCommandNamesInCategory(Localized Command Category Name)` — Sparse array of localized command names in the category, alphabetical.
- `GetNotesForChord(chord name)` — Array of MIDI pitches for the named chord symbol.
- `GetNotesForGuitarChord(chord name)` — Array of interleaved MIDI pitch/string number pairs for the named guitar chord.
- `GetScoresFolder()` — Folder object for the default Scores folder.
- `GetSyllabifier()` — Returns a new Syllabifier object.
- `GetUserApplicationDataFolder()` — Returns the user's Application Data (Windows) / Application Support (Mac) folder.
- `GetUserSibeliusFolder()` — Path to the user's Sibelius scores folder (Documents\Scores by default).
- `GoToEnd()` — Moves the playback line to the end of the score.
- `GoToStart()` — Moves the playback line to the start of the score.
- `IsDynamicPartOpen(dynamic part)` — True if the part (and its Score) is valid and visible in a window.
- `IsFontFamilyInstalled(font name)` — True if a font with the name exists on the system.
- `LaunchApplication(path[,parameters[,hide]])` — Launches an external application with optional parameters (sparse array or string); hide True prevents focus.
- `LiveTempoTap()` — Equivalent to tapping a beat during Live Tempo recording.
- `MakeSafeFileName(filename)` — Returns a "safe" filename (illegal characters removed, truncated to 31 chars).
- `MessageBox(string)` — Shows a message box with an OK button.
- `MoveActiveViewToBar(bar number[,position])` — Brings the internal bar number (and optional position) into view (Go to Bar).
- `MoveActiveViewToSelection([start of selection])` — Brings the selection into view (start by default; end if False).
- `New([manuscript paper])` — Creates and shows a new score (blank, or from the named manuscript paper); returns the Score object.
- `NthScore(score index from 0)` — Returns the nth open score, or null.
- `Open(filename [,quiet])` — Opens and displays the file (extension required); quiet True suppresses errors; returns True/False.
- `Play()` — Plays the current score from the playback line.
- `PlayFromSelection()` — Plays from the current selection.
- `PlayFromStart()` — Plays from the start of the score.
- `PrependScreenreaderText(string)` — Prepends string to the default screen reader description.
- `Print(number of copies[, dynamic part[, showdialog]])` — Prints the score or given part with default settings; returns True/False (showdialog deprecated in Sibelius 7).
- `PrintAllDynamicParts([score])` — Prints all dynamic parts (not the full score); returns True/False.
- `RandomNumber()` — Returns a random number between 0 and 32,767.
- `RandomSeed(start number)` — Restarts the random number sequence from the given number.
- `RandomSeedTime()` — Restarts the random number sequence based on the current time.
- `RefreshDialog()` — Refreshes control data on the active plug-in dialog; returns True if successful.
- `ResetStopWatch(timer number)` — Resets the given stop watch (integer > 0).
- `ReadTextFile(filename)` — Reads the file into an array of strings, one per line (ANSI unless UTF-16 BOM).
- `ScreenreaderText(string)` — Replaces the default screen reader description with string.
- `SelectFileToOpen(caption,file,initial_dir,default extension,default type,default type description)` — Shows an open-file dialog; returns a File object (initial_dir has no effect on Mac).
- `SelectFileToSave(caption,file,initial_dir,default extension,default type,default type description)` — Shows a save-file dialog; returns a File object. Types include EMF/emf, BMP/bmp, PICT/pict, SIBE/sib, Midi/mid, SIBS/lib, SCMS/opt, TEXT/html, TIFF/tif, PNG/tif (as printed in the guide).
- `SelectFolder([caption])` — Lets the user select a folder; returns a Folder object.
- `SetCurrentScoreViewType(view type)` — Switches between ViewTypePage (0) and ViewTypePanorama (1).
- `SetFocusToControl(pluginName,dialogName,controlID)` — Sets focus to a specific control in a plug-in dialog.
- `ShowDialog(dialogName,pluginName)` — Shows a plug-in dialog; returns True/False depending on the closing button.
- `ShowDynamicPart(dynamic part[, newWindow])` — Shows the given part (new tab by default, new window if True); returns True/False.
- `ShowTraceWindow()` — Shows (or brings to front) the Plug-in Trace Window.
- `StartLiveTempoRecording()` — Starts recording Live Tempo.
- `StopLiveTempoRecording()` — Stops recording Live Tempo.
- `Stop()` — Stops playback of the current score.
- `UpdateProgressDialog(progress pos,status message)` — Updates the progress dialog; returns 0 if the user clicked Cancel.
- `YesNoMessageBox(string)` — Shows a Yes/No message box; returns True if Yes.

### Variables
- `ActiveScore` — Score, read/write — The active Score object; setting it activates the score's current dynamic part (null on failure).
- `ApplicationLanguage` — string, read only — Language of the running Sibelius, always in English (e.g. English, German).
- `ApplicationLanguageIsoString` — string, read only — Two-letter ISO 3166 language identifier (en, de, fr...).
- `AvailableCommands` — sparse array — All available CommandIDs, alphabetical.
- `CommandCategories` — sparse array — All command categories in the local language, system order.
- `CurrentTime` — string, read only — Current time, hh:mm:ss (locale-based).
- `CurrentDateShort` — string, read only — Current date, dd/mm/yyyy (locale-based).
- `CurrentDateLong` — string, read only — Current date, dd MM yyyy (locale-based).
- `CurrentDate` — DateTime, read only — Current date and time in local time.
- `EarlierVersionNames` — sparse array — Names of earlier Sibelius versions usable with SaveAsEarlierVersion.
- `FontFamilies` — sparse array, read only — Names of all available font families on the system.
- `HouseStyles` — ComponentList — The available house styles.
- `LocalizedApplicationLanguage` — string, read only — Current language in its localized form (e.g. "Deutsch").
- `ManuscriptPapers` — ComponentList — The available manuscript papers.
- `OSVersionString` — string — The current OS as a string (Windows 95 ... Windows 10, Mac OS X ... macOS Catalina), or "Unknown system version".
- `PathSeparator` — string — Path separator character ("\" Windows, "/" Mac).
- `Plugins` — PluginList — The installed plug-ins.
- `Playing` — boolean, read only — True if a score is currently playing.
- `ProgramVersion` — integer — Running Sibelius version: major*1000 + minor*100 + revision*10 (3.1.3 → 3130).
- `ScoreCount` — integer, read only — Number of scores being edited.
- `SuppressDefaultScreenreaderText` — boolean, read/write — Suppress the default score description for screen readers.
- `ViewAnnotations` — boolean, read/write — View > Invisibles > Annotations state.
- `ViewAttachmentLines` — boolean, read/write — View > Invisibles > Attachment Lines state.
- `ViewBarNumbers` — boolean, read/write — View > Invisibles > Bar Numbers state.
- `ViewComments` — boolean, read/write — View > Invisibles > Comments state.
- `ViewHandles` — boolean, read/write — View > Invisibles > Handles state.
- `ViewHiddenObjects` — boolean, read/write — View > Invisibles > Hidden Objects state.
- `ViewHighlights` — boolean, read/write — View > Invisibles > Highlights state.
- `ViewLayoutMarks` — boolean, read/write — View > Invisibles > Layout Marks state.
- `ViewNoteVelocities` — boolean, read/write — View > Live Playback Velocities state.
- `ViewNoteColors` — integer, read/write — View > Note Colors setting: None (0), Notes out of Range (1), Pitch Spectrum (2), Voice Colors (3).
- `ViewPageMargins` — boolean, read/write — View > Invisibles > Page Margins state.
- `ViewPlaybackLine` — boolean, read/write — View > Invisibles > Playback Line state.
- `ViewReplayMarker` — boolean, read/write — View > Invisibles > Replay Line state.

---

## SoundInfo

Information about the playback of a given staff. Obtain via `staff.SoundInfoAtPosition(bar, pos, nthRepeat)`; movable around the staff.

### Methods
- `Clone()` — Returns a new SoundInfo with the same credentials.
- `CreateAt([barNumber,[position,[nthRepeat]]])` — Returns a new SoundInfo at the location (defaults: bar 1, bar start, first pass).
- `MoveTo([barNumber,[position,[nthRepeat]]])` — Moves the existing SoundInfo to a new location on the current staff.
- `MoveToNext()` — Moves to the next sound change event; returns false (without moving) if none.
- `MoveToPrevious()` — Moves to the previous sound change event; returns false (without moving) if none.

### Variables
- `ActualSoundId` — string, read only — Actual sound ID at the current location.
- `BarNum` — integer, read only — Current location's bar number.
- `IsDrumStave` — boolean, read only — True if the current location is on a drum staff.
- `NthRepeat` — integer, read/write — Nth repeat (pass) of the current location's bar.
- `NumTimesBarPlayed` — integer, read only — Number of times the bar at the location is played.
- `PatchName` — string, read only — Patch name in use at the location.
- `Position` — read/write — Current location's position within the bar.
- `RequestedSoundId` — string, read only — Requested sound ID at the location.
- `SoundChangeIndex` — integer, read only — Index in the bar play sequence (differentiates identical sound changes).
- `SoundSetName` — string, read only — Name of the sound set in use at the location.
- `StaveNum` — integer, read only — 1-based stave number.

---

## SparseArray

Created with `CreateSparseArray(a1,a2,...an)`; `for each` iterates its contents.

### Methods
- `Concat(array1, array2 ... arrayN)` — Concatenates sparse arrays to this one, returning a one-level-deep copy (original unmodified).
- `Join([separator])` — Returns the array as a string, populated elements separated by separator (default comma).
- `Push(value1, ... valueN)` — Pushes one or more values to the end.
- `Pop()` — Returns and removes the last element.
- `Reverse()` — Reverses the array in place (only needed elements populated).
- `Slice(start[,end])` — New sparse array from start up to (not including) end; negative indices count from the end.

### Variables
- `Length` — integer, read/write — Length of the array.
- `ValidIndices` — sparse array — The populated (non-null) indices of the array.

### Converting old-style arrays
- `Array.ConvertToSparseArray()` — Returns a new SparseArray populated with strings from the old-style Array.

---

## SpecialBarline

Derived from a Bar object (per the guide); found only in system staves.

### Methods
None.

### Variables
- `BarlineType` — string — Name of the special barline type.
- `BarlineInternalType` — numeric ID — Maps to one of the SpecialBarline global constants.

---

## Staff

A normal stave or the system staff (the system staff holds objects that apply to all staves). A Staff contains Bar objects. `for each` returns each object in the staff; `for each type in` returns items of the type in chronological order.

### Methods
- `AddClef(pos,concert pitch clef[,transposed pitch clef])` — Adds a clef at the position (style IDs like "clef.treble").
- `AddLine(pos,duration,line style,[dx,[dy,[voicenumber,[hidden]]]])` — Adds a line to the staff (see Bar.AddLine).
- `AddNote(pos,sounding pitch,duration,[tied[,voice[,diatonic pitch[,string number]]]])` — Adds a note (position in 1/256th quarters from the start of the score; adds bars if needed); returns the Note, or null for very short notes in tuplets (prefer Tuplet.AddNote for tuplets).
- `AddStaffAbove(ossia,[start bar number[,end bar number[,start pos[,end pos]]]])` — Adds a staff above (ossia True for small staff; hidden outside the range via "No instrument (hidden)"); returns the Staff or null.
- `AddStaffBelow(ossia,[start bar number[,end bar number[,start pos[,end pos]]]])` — Adds a staff below; see AddStaffAbove.
- `AddSymbol(pos,symbol index or name)` — Adds a symbol to the staff (see Bar.AddSymbol).
- `CurrentKeySignature(bar number)` — Returns the KeySignature valid at the bar.
- `NthBar(n)` — Returns the nth bar in the staff, counting from 1.
- `ResetSpaceAroundStaff(above,below[,from bar[,to bar]])` — Resets Space Above/Below Staff for the bar range (defaults bar 1 to last bar).
- `ScaleFactorChange(StaveScaleFactor, startBarNum, endBarNum)` — Sets the Staff Size property: NormalSize (0), MediumSize (1), SmallSize (2), ExtraSmallSize (3).
- `SetSound(styleID[,set SoundStage])` — Changes the initial playback sound to the default for the instrument styleID; optionally leaves SoundStage unchanged.
- `SetSoundID(soundID)` — Changes the initial playback sound to the given soundID.
- `SoundIDAtPosition([bar number,[position,[nth repeat]]])` — Returns a new SoundInfo at the location (defaults: bar 1, bar start, first pass).
- `Staff[array element]` — Returns the nth bar (counting from 1), e.g. `Staff[1]`.

### Variables
- `BankHigh` — 0–127 or –1, read/write — MIDI controller 0 (coarse bank); –1 sends no message.
- `BankLow` — 0–127 or –1, read/write — MIDI controller 32 (fine bank); –1 sends no message.
- `BarCount` — integer, read only — Number of bars in the staff.
- `BarNumber` — integer, read only — Internal bar number (consecutive from 1).
- `Channel` — 1–16, read/write — MIDI channel number of the staff.
- `Distance` — percentage, read/write — Reverb "distance" (Mixer), scaling the Performance dialog reverb settings.
- `FullInstrumentName` — string, read/write — Full instrument name (empty for unnamed staff).
- `FullInstrumentNameWithFormatting` — string, read/write — Full instrument name including font/style changes.
- `FullStaffName` — string, read/write — Initial full staff name.
- `FullStaffNameWithFormatting` — string, read/write — Initial full staff name including font/style changes.
- `NumStavesInSameInstrument` — integer, read only — Number of staves belonging to the instrument this staff came from.
- `InitialClefStyle` — string, read only — Name of the initial clef (depends on Transposing Score state).
- `InitialClefStyleId` — string, read only — Style identifier of the initial clef.
- `InitialInstrumentType` — InstrumentType — Instrument type at the start of the staff.
- `InitialKeySignature` — KeySignature, read only — Key signature at the start of the staff.
- `InitialStyleId` — string, read only — Style identifier of the staff (usable with Score.CreateInstrument).
- `InstrumentName` — string, read only — Full instrument name as displayed in Instruments and Staves (e.g. "[Piano]" for unnamed staves).
- `IsSystemStaff` — boolean, read only — True if this staff is a system staff.
- `IsVocalStaff` — boolean, read only — True if the staff's instrument type has the Vocal staff option on.
- `MuteMode` — constant, read/write — Muted, HalfMuted or NotMuted (Mixer mute button).
- `Pan` — –100..100, read/write — MIDI stereo panning position (positive right).
- `ParentScore` — Score, read only — The staff's parent Score.
- `ShortInstrumentName` — string, read/write — Short instrument name (empty for unnamed staff).
- `ShortInstrumentNameWithFormatting` — string, read/write — Short instrument name including font/style changes.
- `ShortStaffName` — string, read/write — Initial short staff name.
- `ShortStaffNameWithFormatting` — string, read/write — Initial short staff name including font/style changes.
- `ShowInFocusOnStaves` — boolean, read/write — True if this staff shows in Focus on Staves (cannot be False unless True for another staff).
- `Solo` — boolean, read/write — True if the staff plays back in "solo" mode.
- `SoundIdOverrideIfAny` — string, read only — Sound ID override set in the Mixer, or empty string.
- `Small` — boolean, read/write — True if the staff is small (e.g. ossia).
- `StaffNum` — integer, read only — Staff number from 1 at the top of the current part (0 for SystemStaff).
- `Volume` — 0–127, read/write — Overall MIDI volume (Mixer fader).

---

## Syllabifier

Wrapper around Sibelius's internal syllabification engine.

### Methods
- `AbbreviateUsingApostrophe(useApostrophe)` — When abbreviating, replace combined vowels with an apostrophe (e.g. Veg'-ta-bles); recalculates if needed.
- `GetNthSyllable(n)` — After Syllabify, returns each syllable as a string.
- `NthSyllableEndsWord(n)` — After Syllabify, returns whether the syllable is at the end of a word.
- `Syllabify(textToSyllabify[, language[, abbreviate = False]])` — Breaks a string into syllables; returns the syllable count, or 0 on error/unknown language (language ID or localized name; auto-detected if omitted).

### Variables (all read only)
- `AbbreviateUsingApostrophe` — Whether the engine abbreviates combined syllables with an apostrophe (write via the method of the same name).
- `AvailableLanguageIds` — Array of three-letter non-translatable language IDs (ENG, GER, LAT...).
- `AvailableLanguages` — Array of available syllabification languages as localized strings.
- `NumberOfSyllables` — Number of syllables from the last Syllabify call.
- `SyllabifiedString` — Resultant hyphenated string from the last Syllabify call.

---

## SymbolItem and SystemSymbolItem

Derived from BarObject. Symbols on the system staff are of type SystemSymbolItem, not SymbolItem.

### Methods
None.

### Variables
- `Index` — integer, read only — Index in the symbol list (position in Create > Symbol, from zero left-to-right, top-to-bottom).
- `Name` — string, read only — Name of the symbol (may be translated in non-English versions).
- `Size` — constant, read/write — NormalSize, CueSize, GraceNoteSize or CueGraceNoteSize.

---

## SystemObjectPositions

Accessed from a Score object; corresponds to House Style > System Object Positions.

### Methods
- `GetNthStaffShowsSystemObjects(staffNum)` — True if the staff (relative to the current part) shows system objects above it.
- `SetNthStaffShowsSystemObjects(staffNum, show)` — Sets whether the staff shows system objects above it (no effect for the top staff or if the maximum is met).
- `Clear([removeBelowBottomStaff])` — Clears all system object positions except the compulsory top-staff one; optionally clears "Below bottom staff" too.

### Variables
- `NumStavesShowingSystemObjects` — integer, read only — Number of staves showing system object positions.
- `ShowSystemObjectsBelowBottomStaff` — boolean, read/write — True if system objects show below the bottom staff.

---

## SystemStaff, Staff, Selection, Bar and all BarObject-derived Objects (common variables)

### Variables
- `IsALine` — boolean — True if the object is a line object (a variable, unlike the IsObject() method).
- `Type` — string — Type name: "SystemStave", "Stave", "MusicSelectionList", "Bar" for the first four; also a member of all objects that occur in bars.

---

## SystemStaff

One per score; holds objects applying to all staves (SpecialBarlines, system text). Does not appear in the score; only the following Staff members are supported.

### Methods
- `CurrentKeySignature(bar number)` — Returns the KeySignature valid at the bar.
- `CurrentTimeSignature(bar number)` — Returns the TimeSignature valid at the bar.
- `NthBar(n)` — Returns the nth bar (from 1).
- `SystemStaff[array element]` — Returns the nth bar (from 1), e.g. `SystemStaff[1]`.

### Variables (all read only)
- `BarCount` — Number of bars in the staff.
- `InitialKeySignature` — KeySignature at the start of the staff.
- `IsSystemStaff` — Returns True for a SystemStaff.

---

## Text and SystemTextItem

Derived from BarObject. System-staff text objects are of type SystemTextItem, not Text.

### Methods
None.

### Variables
- `EraseBackground` — boolean, read/write — True if the item's background is erased; writing creates an override of the text style value.
- `EraseBackgroundOverridden` — boolean, read/write — True if the item overrides the style's EraseBackground; set False to clear the override (setting True has no effect).
- `InitialFontName` — string, read only — Font name at the start of a styled string.
- `InitialFontSize` — SUs (1/32 space), read only — Font size if uniform, or –1 if multiple sizes are used.
- `JumpAtEndOfBar` — boolean, read/write — True if a system text object has "Jump at bar end" set (always False for staff text).
- `StyleAsText` — string, read/write — Text style name.
- `StyleId` — string, read/write — Text style identifier.
- `Text` — string, read/write — The text.
- `TextWithFormatting` — array, read only — Array of text segments and font/style change tokens.
- `TextWithFormattingAsString` — string, read only — Text including any font/style changes.

---

## TimeSignature

Derived from BarObject.

### Methods
None.

### Variables
- `AllowCautionary` — boolean, read/write — True if set to show a cautionary at the end of the previous system.
- `Denominator` — integer, read only — Bottom number.
- `Numerator` — integer, read only — Top number.
- `Text` — string, read only — Time signature as text; compare against CommonTimeString / AllaBreveTimeString; others are of form "4\n4".

---

## TreeNode

Used internally for arrays/hashes (CreateArray/CreateHash) and global data. Each TreeNode has a label, a piece of data and a list of children (also TreeNodes); normally access resolves to the data.

### Methods
- `WriteToString` — Returns a string representing the TreeNode structure (data in double quotes, children in `{ }`).

### Variables
- `Label` — The label of this TreeNode.
- `NumChildren` — Number of child TreeNodes.

---

## Tuplet

Derived from BarObject.

### Methods
- `AddNestedTuplet(posInTuplet, left, right, unit[, style[, bracket[,fullDuration]]])` — Nests a tuplet inside this one at a position relative to the outer tuplet's duration/scale; returns the Tuplet (test against null on bad parameters).
- `AddNote(posInTuplet, pitch, duration[, tied[, diatonic pitch[, string number]]])` — Adds a note to the tuplet in the tuplet's own voice; posInTuplet is relative to the tuplet bracket's duration/scale (e.g. 256 for the second beat of a crotchet triplet).
- `utils.SplitTuplet(tuplet,splitpoint)` — Splits the tuplet (and any nest) at the split point relative to the parent bar (provided by utils.plg).

### Variables
- `Bracket` — constant — Bracket type of the tuplet (none, auto, etc.).
- `FullDuration` — boolean — True if the bracket spans the tuplet's entire duration.
- `Left` — integer, read only — Left side of the ratio (e.g. 3 in 3:2).
- `ParentTupletIfAny` — Tuplet or null, read only — Innermost tuplet this tuplet intersects.
- `PlayedDuration` — read only — True rhythmic duration of the tuplet (e.g. a minim for a crotchet triplet).
- `PositionInTuplet` — read only — Position relative to the parent tuplet's duration/scale (or the parent Bar if no tuplet).
- `Right` — integer, read only — Right side of the ratio (e.g. 2 in 3:2).
- `Style` — constant — Tuplet style (number, ratio, ratio + note...).
- `Text` — string, read only — Text shown above the tuplet.
- `Unit` — integer, read only — Unit used for the tuplet (e.g. 256 for a triplet of quarter notes).

---

## Utils

Sibelius installs `utils.plg`, a library of methods callable from other plug-ins (not run as a plug-in itself; not in the Plug-ins menu).

### Methods
- `utils.AbsoluteValue(value)` — Absolute value of a number.
- `utils.AddFractions(x,y)` — Adds two fractions (arrays); returns result array.
- `utils.BinaryString(x)` — Binary string (e.g. "101010") for number x.
- `utils.bwAND(x, y)` — Bitwise AND.
- `utils.bwOR(x, y)` — Bitwise inclusive OR.
- `utils.bwXOR(x, y)` — Bitwise exclusive XOR.
- `utils.CapableOfDeletion()` — True if the object can be deleted with Delete() (checks Sibelius version).
- `utils.CaseInsensitiveComparison(s1, s2)` — True if the strings match ignoring case.
- `utils.CastToBool(x)` — Casts x to Boolean.
- `utils.CastToInt(x)` — Casts x to integer.
- `utils.CastToStr(x)` — Casts x to string.
- `utils.CombineArraysOfBool(arr1, arr2)` — Concatenates two Boolean arrays.
- `utils.CombineArraysOfInt(arr1, arr2)` — Concatenates two integer arrays.
- `utils.CombineArraysOfString(arr1, arr2)` — Concatenates two string arrays.
- `utils.CopyTextFile(source, dest)` — Copies a text file; returns True if successful.
- `utils.CreateArrayBlanket(value, size)` — Array of size elements, each set to value.
- `utils.DeleteStaff(score, nth staff, retain selection)` — Deletes an entire staff and content; returns True if successful.
- `utils.DenaryValue(x)` — Base-10 number from binary string x.
- `utils.DivideFractions(x,y)` — Divides fraction x by y (arrays); returns result array.
- `utils.ExtractFileName(filename)` — Returns just the filename portion of a path+filename string.
- `utils.Format(str, [val1,val2,...])` — Replaces successive `%s` in str with the arguments.
- `utils.FormatTime(ms)` — Formats milliseconds as mm'ss.z (z = centiseconds).
- `utils.FractionAsDecimal(x)` — Decimal equivalent of fraction x (array).
- `utils.FractionDenominator(x)` — Denominator of fraction x.
- `utils.FractionNumerator(x)` — Numerator of fraction x.
- `utils.GetAppDir()` — Path of the Sibelius executable.
- `utils.GetArrayIndex(arr, value)` — Index of value in arr, or –1.
- `utils.GetBits(x)` — Array of powers of two summing to x.
- `utils.GetGlobalApplicationDataDir()` — Path of the system's global application data area.
- `utils.GetLocationTime(score, barNum, position)` — Precise time (ms) of a location (for Sibelius 4 compatibility; else use Score.GetLocationTime).
- `utils.GetMillisecondsFromTime(time)` — Milliseconds portion of a ms time value.
- `utils.GetMinutesFromTime(time)` — Minutes portion of a ms time value.
- `utils.GetObjectTime(score,obj)` — Precise time (ms) an object occurs, considering tempo etc. (Sibelius 4 compatibility; else use BarObject.Time).
- `utils.GetPluginId(plug-in)` — Returns a plug-in's unique ID (from `PluginUniqueID = "..."` in its Initialize), or empty string.
- `utils.GetSibeliusPluginsFolder()` — Path of the Plugins folder (wrapper around deprecated GetPluginsFolder()).
- `utils.GetSibMajorVersion()` — Major version number of Sibelius.
- `utils.GreatestCommonDivisor(m,n)` — Greatest common divisor of two non-zero integers.
- `utils.IsInArray(arr, value)` — True if value exists in arr.
- `utils.IsNumeric(str[, integer only])` — True if str is numeric (optionally integers only).
- `utils.LowerCase(str)` — ANSI string in lowercase.
- `utils.MakeFraction(x,y)` — Creates a fraction (array) with numerator x and denominator y.
- `utils.max(x,y)` — Greater of two numbers.
- `utils.min(x,y)` — Lesser of two numbers.
- `utils.MultiplyFractions(x,y)` — Multiplies fractions (arrays); returns result array.
- `utils.PatternCount(pattern,str)` — Number of times pattern occurs in str.
- `utils.Pos(subStr,str)` — Zero-based position of the first instance of subStr in str, or –1.
- `utils.PosReverse(subStr,str)` — Zero-based position of the last instance of subStr, or –1.
- `utils.RaisePower(x,y)` — Raises x to the yth power (y a positive integer).
- `utils.Replace(inStr,toFind,replaceWith,replaceAll)` — Replaces a substring (first instance, or all if replaceAll is True).
- `utils.ReverseArrayOfBool(arr)` — Reverses an array of Booleans.
- `utils.ReverseArrayOfInt(arr)` — Reverses an array of integers.
- `utils.ReverseArrayOfString(arr)` — Reverses an array of strings.
- `utils.RoundToNDecimalPlaces(number,precision)` — String of the number rounded to precision decimal places (string-based to avoid rounding errors).
- `utils.SetDefaultIfNotInArray(value, arr, DefaultIndex)` — Returns value if present in arr, else arr[DefaultIndex].
- `utils.shl(x,y)` — Bitwise left-shift x by y bits.
- `utils.shr(x,y)` — Bitwise right-shift x by y bits.
- `utils.SortArray(arr,show progress)` — Case-insensitive alphabetic sort, optional progress bar.
- `utils.SortArrayCustom(arr,show progress,plug-in name,method)` — Sort with a custom comparison routine (method taking strA, strB, returning 1 or 0) in the named plug-in.
- `utils.SortArrayNumeric(arr,show progress)` — Ascending numeric sort, optional progress bar.
- `utils.SplitTuplet(tuplet,splitpoint)` — Splits a tuplet (and nest) at the split point relative to the parent bar.
- `utils.StartComponentManager(componentName,callbackFunc)` — Returns filenames found in a named folder following Sibelius's component precedence (user > global > app dir); callbackFunc scans a directory for files of a given extension.
- `utils.SubtractFractions(x,y)` — Subtracts fraction y from x (arrays); returns result array.
- `utils.UpperCase(str)` — ANSI string in uppercase.

---

## VersionHistory

Each Score has a VersionHistory (via `score.GetVersions()`), which provides a list of Version objects.

### Methods
- `AddVersion([name[,comment]])` — Adds a new Version (optional name/comment); returns it, or null.
- `DeleteNthVersion(n)` — Deletes the nth Version; returns True if successful.
- `GetNthVersion(n)` — Returns the nth Version object.

### Variables
- `NumChildren` — integer — Number of versions in the score's VersionHistory.

---

## Version

Accessed via a Score's VersionHistory object.

### Methods
- `AddComment(text)` — Adds a comment; returns the VersionComment created.
- `Close()` — Closes all open views of the version; returns True if anything was closed.
- `GetNthComment(n)` — Returns the nth comment as a VersionComment, or null if out of range.
- `DeleteNthComment(n)` — Deletes the nth comment; returns True if successful, or null if out of range.
- `OpenAndReturnScore()` — Opens the version (if not open) and returns its Score object.

### Variables
- `EndDate` — DateTime, read only — Version's end date. (`IsOpen` — read only — True if the version is currently open, documented on the same line in the guide.)
- `Name` — string, read/write — Name of the version.
- `NumComments` — integer, read only — Number of comments in the version.
- `StartDate` — DateTime, read only — Version's start date.

---

## VersionComment

Accessed using Version objects.

### Methods
None.

### Variables
- `Text` — string, read/write — Text of the comment (changes cannot be undone).
- `TimeStamp` — DateTime — Time at which the comment was created.
- `UserName` — string, read only — Name of the user who created the comment.

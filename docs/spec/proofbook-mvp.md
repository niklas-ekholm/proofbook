# ProofBook MVP — build specification

**Status**: ready to build. Derived from issues #2–#13 on the wayfinding map ([#1](https://github.com/niklas-ekholm/proofbook/issues/1)) and ADR-0001 through ADR-0005.

This document is the hand-off. It says what to build and what has already been decided, so the build session does not re-litigate settled questions. Where a decision has an ADR, the ADR holds the reasoning and this spec holds only the rule; read `CONTEXT.md` first for the glossary — its terms are used here precisely and are not redefined.

Every decision below is **provisional for the MVP** and expected to be revisited once the plugin has been used in anger. Do not generalise beyond what is written. Where this spec is silent, prefer the smaller thing.

---

## 1. What ProofBook is

A Glyphs 4 palette plugin that browses a `proofbook` folder beside the open Glyphs file, displays a selected proof-page in the Edit view, and manages proof-pages as files: create, rename, move, duplicate, delete, tag status and ownership, and edit a note.

**Governing principle: minimal UI, maximum transparency in storage.** The proof-book must be operable from a text editor and legible to an agent reading the directory. When a UI argument has no clear winner, the option that keeps the folder plainer wins.

**Hard constraints:**

- Proof-pages are plain text, editable in any editor. Not negotiable.
- Glyphs 4 only. No Glyphs 3 compatibility (G3 is pinned to Python 3.11, G4 requires 3.14+; they are effectively a fork).
- Read-only in one specific sense: **editing text in the Edit view never writes back to the proof-page file.** ProofBook writes files only through its own explicit operations.
- ProofBook reads a folder it does not own. It never writes without being asked, never moves what it did not create, and never overwrites a designer's work.

**Out of scope for the MVP**: PDF proof export; viewing a proof-page across all masters and interpolations; any undo beyond the Trash; distribution through the Plugin Manager; ordering other than alphabetical.

---

## 2. Architecture

**ADR-0005 is binding.** ProofBook is split in two:

- **The core** — a package that imports nothing from `GlyphsApp`, `AppKit`, `vanilla` or `objc`, and performs **no syscalls**. It parses and formats filenames, reads and writes the frontmatter header, flattens a listing into display rows, resolves collisions, and decides which paths need background reads.
- **The adapter** — the `PalettePlugin` subclass and its vanilla view. It performs every syscall, owns the worker thread, raises dialogs, and draws.

The core takes a directory listing as **input data** (names, `st_flags`) and returns rows plus **intents** — `rename(src, dst)`, `read_background(paths)`, `write_text(path, bytes)`, `trash(path)`, `make_dir(path)`, `copy(src, dst)`. It does not open, stat, or rename anything itself. The adapter performs the intents and feeds the results back.

Suggested core modules (a suggestion, not a requirement): `names.py` (the filename grammar), `frontmatter.py` (the header), `tree.py` (listing → rows), `ops.py` (verbs → intents, collision resolution).

### Layout

```
ProofBook.glyphsPalette/Contents/     at the repository root
  Info.plist              NSPrincipalClass = ProofBookPalette
                          PyMainFileNames = ["plugin.py"]
  MacOS/plugin            stock PyObjC loader (ad-hoc/linker-signed, freely copyable)
  Resources/plugin.py     the adapter
  Resources/proofbook/    the core package
tests/                    unittest suite over the core
```

**The core ships inside the bundle.** No build step, no symlink: the repo *is* the bundle, and the bundle sits at the repository root, so the symlink in `Plugins/` points at the clone itself. `plugin.py` puts its own directory on `sys.path` before importing `proofbook`. It **appends**, never inserting at the front: the Glyphs interpreter is shared, and every palette ships a `Resources/plugin.py` that the front of `sys.path` would let this bundle shadow process-wide.

*(**Verified in Glyphs 4**: the palette draws `core 0.0.1`, a string that only exists if the append resolved and the core imported. Runtime confirmed as Python 3.14.6, vanilla present. This was the last mechanical assumption in the architecture; it is no longer open.)*

`tests/test_bundle_layout.py` parses `plugin.py` to hold the two rules nothing outside Glyphs can check: the `sys.path` call precedes the `import proofbook`, and the `try: import vanilla` guard is still at module scope.

No `.xib` and no `.nib`. They are optional in Glyphs 4 and are not used.

### Tests

Stdlib `unittest`, run as `python3 -m unittest discover tests` with no install step and no Glyphs. **Tests build nothing on the filesystem** — no temp directories, no proof-book fixtures; the core is fed listings as data. The one exception is the bundle's own source, which the layout tests read in place. The suite must cover, at minimum:

- All three legal filename shapes, plus a subject containing hyphens, plus case-insensitive status matching, plus a name that fits no shape.
- Frontmatter round-trips: canonical in → canonical out; lenient forms (one-line `note:`, odd indent) normalising on write; unknown keys preserved in order with the note block last; malformed input flagged read-only and never rewritten; line endings preserved; body passed through byte-for-byte.
- The collision rule producing `caps-2-DONE-NE.txt`, incrementing until free.
- Listing → rows: depth, alphabetical order, empty folders present, non-`.txt` files absent.

---

## 3. Storage

### Folder discovery

A folder named exactly `proofbook`, beside the open Glyphs file. Resolved from `self.windowController().document().font` — **never `Glyphs.currentDocument`**; there is one palette instance per document window.

The folder is created **only by an explicit action**: the empty state's *Create proof-book* button, or *New proof-page* when the folder is absent. Loading the plugin, expanding the palette, and switching windows never touch the disk.

`font.filepath` is `None` for an unsaved font. Subscribe to `DOCUMENTWASSAVED` and re-resolve on fire, so the unsaved empty state clears itself with no user action. **Save As uses the same path with no special case**: the font moves, the proof-book does not follow, and ProofBook drops to the empty state if no `proofbook` folder sits beside the new location.

### Membership

`.txt` files and all folders are shown. Everything else is **silently ignored** — no warning, no "unrecognised files" section. Empty folders are shown. Subfolders nest arbitrarily and carry no metadata of their own. Everything is ordered alphabetically.

The extension is the membership test; the naming grammar is only a tagging convention. A `.txt` that fits no shape is still a proof-page, shown untagged.

### Filename grammar (ADR-0001)

Three legal shapes:

```
common-words.txt              untagged: TODO, no owner
common-words-WIP.txt          tagged, unowned
common-words-WIP-NE.txt       tagged and owned
```

- **Parsed right-to-left**: strip `.txt`; if the last segment is a recognised status, the preceding text is the subject; if the last two segments are `<status>-<owner>`, the preceding text is the subject. Otherwise the whole stem is the subject. Subjects may therefore contain hyphens.
- **An owner is only read from the position after a recognised status.** The closed set anchors the parse, so `caps-ink.txt` is never mistaken for an owner.
- Status is one of `TODO`, `WIP`, `DONE`. **Matched case-insensitively**, written uppercase. The known cost is accepted deliberately: `things-done.txt` reads as subject `things`, status `DONE` — a visibly wrong status fixed by renaming, never data loss. Do not "fix" this with case-sensitivity without revisiting ADR-0001's trade.
- Owner is 1–4 letters, no digits, no hyphens, no spaces. Matched case-insensitively, written uppercase.
- No version numbers. Versions belong to Glyphs files.
- Status and owner are **independent**: a page may be tagged and unowned. A page may not be owned and untagged.

**One file is one proof-page.** `caps-WIP-NE.txt` and `caps-WIP-MP.txt` are two proof-pages, not two revisions of one. Copy-and-rename to take over someone's page is a human agreement; the plugin does not enforce it.

### Frontmatter (ADR-0003)

```
---
note: |
  Caps look heavy against the lowercase in Bold.
  Revisit after the weight axis is fixed.
---
HAMBURGEFONSTIV
handgloves
```

A hand-rolled `Key: value` parser and writer, ~30 lines, shaped as **valid YAML** so editors highlight it. No import that can fail — `PyYAML` is absent from the Plugin Manager index entirely, and `tomllib` is read-only.

- **Fences**: a header exists only if line 1 is exactly `---`, ending at the next `---`. Everything after is proof text, `---` lines included.
- **Write strictly**: always `note: |` with 2-space-indented continuation lines. One form only. This keeps colons out of scalar position and de-fangs a note line reading `---`.
- **Read leniently**: any consistent indent (strip the common prefix), or a one-line `note: value` (split on the first colon, value verbatim). Both normalise to canonical form on the next write.
- Blank lines inside the note belong to it; leading and trailing ones are trimmed.
- **Unknown keys are preserved verbatim**, written first in original order, note block always last.
- **Malformed** — no closing fence, or bytes that are not UTF-8 — means the whole file is proof text. The row displays normally (status and owner come from the filename), and the note pane shows the broken header **read-only**. Never overwrite bytes you did not understand; never hide the page.
- **An emptied note removes the header entirely**, fences included, unless unknown keys remain.
- UTF-8 strict; BOM tolerated on read, dropped on write. **Preserve the file's dominant line ending.** The body passes through byte-for-byte — no whitespace tidying, no trailing-newline normalisation. A note edit must diff only the header.
- No frontmatter at all is valid. A header with no proof text after it is also valid.

Status and owner never appear in frontmatter. **Nothing is stored twice.**

---

## 4. The palette

### Rows (ADR-0002)

A **flat `vanilla.List2` with indentation computed in Python.** ProofBook flattens the folder tree into a row list, each row carrying a depth; the subject cell indents by depth and folder rows draw their own disclosure glyph. Expansion state is a Python set of folder paths; toggling re-sets the whole row list.

A proof-page row shows:

- **Status swatch** on the left: `TODO` an empty outline, `WIP` amber, `DONE` green.
- **Subject** as plain text, hyphens rendered as spaces.
- **Owner** as an initials pill on the right; absent when the page has no owner.
- **Tooltip**: the raw filename. This is the *only* place the filename appears in the palette — transparency on demand, not on screen.

An untagged page renders identically to an explicitly-`TODO` one: outline swatch, subject read from the whole stem, no pill.

**Folder rows toggle expansion and never become the selection.** Selection always names a real proof-page.

Above the tree: a thin **coverage bar** (done/wip proportions) with `N of M done` beneath it.

*(**Verified in Glyphs 4**: the swatches, the pills, the coverage bar and its count all draw, and the tree browses a real proof-book at 18pt rows. Three things were settled by seeing it rather than reasoning about it. The palette keeps **one left margin** — the 13pt the section header sets — which cost the tree its default `NSTableViewStyleInset`, and with it the rounded inset selection highlight; §10 has why no drawing inside a cell could reach that margin instead. A folder's caret is the **system chevron**, the same one the palette header draws, because a hand-drawn arrowhead beneath it reads as a tree drawn by someone else. And rows are **18pt**, not the 24 macOS gives a table: that height is sized for a row with an icon in it, and a proof-book worth browsing is long.)*

Below the tree: a **collapsible note pane**, its collapsed state remembered. A thin footer toolbar carries a `+ New proof-page` button.

**Palette height** is a range with the tree scrolling inside it: `minHeight` ~180, and a `maxHeight` of 80% of the screen's visible height, capped at 1200. The cap is measured rather than round — about as tall as the palette goes on a 1920x1243 display with the other panels collapsed — but it is only a cap. The ceiling itself is relative, because the palette is resized solely by the pill along its foot: a height stored on a large display and reopened on a smaller one puts that pill below the fold of a sidebar that scrolls, where the only handle the palette has cannot be reached. The stored height is the designer's intent and is clamped when read, never rewritten, so reconnecting the display restores it. A proof-book large enough to matter runs well past what 400 could show, and on a large display that was scrolling through space the screen had spare. Height never tracks content. Collapsing the note pane changes what is visible, not the palette's height. Override the `ViewHeight` persistence key, which otherwise derives from the *localised* palette name.

*(**Verified in Glyphs 4**: the tree browses a real proof-book — nesting, expansion, tooltips, ordering, membership — and the palette drags across its range with the height surviving a relaunch. Getting the drag working took four wrong attempts and two crashes; §10 has what it turned on. One residual Glyphs quirk: `mouseDragged:` stores the height with the section's chrome added while `setController:` restores it without, so a palette dragged to the very top comes back ~17pt short. Not worth compensating for — the correction would have to guess the same constant.)*

### vanilla

Assumed present. The `try: import vanilla` guard lives at **module scope** — never inside `PalettePlugin.init`, whose `settings()` and `start()` calls are unguarded in the SDK (verified in #6: `plugins.py:971`). On `ImportError`, fall back to the ~15-line AppKit view reading *Install vanilla via Plugin Manager*. There is nothing on disk to inspect — Glyphs injects vanilla into `sys.path` at runtime — so the import attempt is the only detection mechanism.

**Both paths are verified in Glyphs 4.** Flipping `PROOFBOOK_FORCE_NO_VANILLA` in the adapter raises the `ImportError` for real; the palette then reports `vanilla: MISSING` and draws the AppKit fallback, with no crash dialog. Keep that flag working — it is the only way to exercise the fallback on a machine where vanilla is installed.

### Empty states

- **Unsaved font**: "Font not saved", one line explaining a proof-book lives beside the file, no button.
- **No proof-book yet**: "No proof-book yet", one line saying a folder named `proofbook` will be created beside the `.glyphs` file, and a *Create proof-book* button.

Neither empty state has a context menu.

---

## 5. Selection and the Edit view

Selecting a proof-page strips the frontmatter and pushes the remaining text into the Edit view via `tab.text`.

**The ProofBook tab**: if the current tab is one ProofBook opened **and still holds exactly what ProofBook put there**, its text is replaced; otherwise a new tab is opened (`font.newTab(text)`). ProofBook holds a reference to the tab it opened **and the exact text it pushed there** — both are needed for that test and for the refresh in §6. Use `tab.redraw()`, not `forceRedraw()`.

**A tab stops being ProofBook's the moment its text is the designer's.** A tab the designer opened is never written to, and neither is one ProofBook opened that has since been typed into — the designer who cleared a proof-page and wrote for an hour has forgotten where the tab came from, and losing that to a click on a row is the worst thing this plugin can do. It is the same test both times, so the two paths cannot disagree: **is the text still exactly what we pushed?** Text restored to exactly that — by an undo, say — matches again and is ProofBook's again; nothing can be lost by replacing text that is identical. The cost is one extra tab per typing episode, not one per click, because the tab that replaces it becomes the ProofBook tab in its turn.

**What ProofBook remembers is what it reads back, not what it wrote.** The Edit view stores glyphs, not characters, so `tab.text` need not return the string assigned to it: an unencoded glyph comes back as `/name`, and a trailing newline may not survive. Re-read `tab.text` after the push and keep *that* as the token. A token that can never match disowns the tab on every selection, which is a new tab per click, silently.

Keeping the read-back value is what makes the round trip stop mattering: ProofBook compares the tab against what the tab last said, so a push that comes back as `/adieresis` or loses its trailing newline still matches itself. *(**Unverified in Glyphs**, and now the only two assumptions left here. One: that the read-back is **synchronous** — the token is read on the same runloop turn as the write, and a tab that had not taken the assignment yet would hand back the previous page's text, leaving a token that matches something no longer on screen. Two: that `tab.text` is **stable** across reads of a tab nobody has touched. Nothing here assumes the round trip is the identity, but a token is worthless if it cannot match itself; if either fails, the token has to be whatever comparison does hold, never an assumption that it matched.)*

---

## 6. Lifecycle

### Refresh

Re-read the listing when the palette's window **becomes key**, and immediately after any write ProofBook itself performs. Nothing else: no FSEvents watcher, no polling timer, no visible refresh button. The designer leaves Glyphs to pull or edit, and coming back *is* the trigger.

**Never touch the filesystem from `UPDATEINTERFACE`** — it fires on every redraw. Tear down callbacks in `__del__` or Glyphs crashes.

State is per-palette-instance and in-memory: selection, expansion, scroll position. Nothing is shared across windows and nothing survives a window close.

### On refresh

- **The displayed page changed on disk**: re-push the text **only if the ProofBook tab's text is still exactly what ProofBook put there** — the same test §5 makes before replacing a tab. If the designer has typed in that tab, the text is theirs; leave it. Nothing has to be *un*remembered for that: the question is asked afresh every time rather than latched, so a tab holding the designer's text fails it here and on the next selection too — and text they restore to exactly what was pushed is ProofBook's again, which latching would have thrown away. **The question is also asked before the page is read**, not after: this runs on every become-key and after every rename, and the read is the main-thread one ADR-0004 is about, so a tab that is not ProofBook's must cost no download to rule out. A refresh writes into that tab wherever it sits in the tab bar, and **never opens one**: unlike a selection, it answers no question the designer just asked, and a proof-page arriving in front of someone who is not in Glyphs is not a refresh. Unchanged is left alone too — a re-push is a redraw, and this runs on every switch back to the window.
- **The selected page is gone**: clear the selection, empty the note pane, and **leave the Edit view tab exactly as it is.** Deleting a file should not blank a tab that may still be being read. An external rename reads as a delete plus an add; the MVP makes no attempt to track identity across a rename it did not perform.

### Note writes

The note pane has no save button. It commits **on blur, on selection change, and on the window resigning key.** The last is load-bearing: it guarantees a draft reaches disk before the become-key refresh reads the file back, so a refresh can never clobber an uncommitted note. No per-keystroke writes. A commit that finds the file gone drops the draft and says so, rather than recreating the file.

---

## 7. Cloud storage (ADR-0004)

**The tree reads no file contents at all, and no file read ever happens on the main thread.** This is an invariant, stated because it is free today and expensive to retrofit.

- Placeholders carry the **`SF_DATALESS`** flag (`0x40000000`) in `os.lstat().st_flags`. Statting does not trigger a download (3011 Google Drive files in 0.2s). Plain Python — no PyObjC, no per-provider code.
- Everything the tree displays comes from filenames, so a fully-dataless proof-book renders instantly.
- **Bulk download is explicit, never automatic.** A one-line hint above the tree, shown only while true: *"18 of 24 pages not downloaded — Download all"*. It becomes a progress readout — *"downloading 42 of 300…"* — with a **Cancel** that sets a flag the worker checks between files. No modal sheet. The scope of "all" is the whole proof-book recursively, collapsed folders included.
- **Selection routes by the flag**: a materialised file is read inline; a dataless one goes through the worker, and the Edit view updates when it lands.
- **Failure on selection**: a `vanilla.dialogs` message naming the file — *"Could not read `caps-WIP-NE.txt`; it may not be downloaded yet"* — and the **ProofBook tab is left untouched**. The row stays selected.
- **Failure during bulk download** never aborts the run; the worker continues and reports a count: *"downloaded 280 of 300; 20 failed"*.
- A scan during a download simply runs; rows flipping from dataless to local **is** the progress feedback. The one thing that cancels the worker is the proof-book changing underneath it — a different font focused, or Save As.

Renames work on placeholders, so **tagging works fully offline**. A note can only be edited on a selected page, which routing has therefore materialised — there is no read-modify-write against a placeholder anywhere in the design.

---

## 8. Operations

### The status swatch

Clicking it cycles `TODO → WIP → DONE`, which renames the file. Tagging is the highest-frequency action and earns a direct target. A misclick is undone by another click or two around the cycle.

**No implicit owner**: clicking the swatch on an untagged page writes `common-words-WIP.txt` and nothing else. One click stays one click, with no dialog ambushing it.

*(**Verified in Glyphs 4**: the swatch cycles and renames on a real proof-book, the tree and the coverage bar redraw without leaving the window, and the owner pill survives a tag. Four things the reasoning could not settle on its own. **The target is the whole marker column**, not the 9pt circle inside it — the circle is a target a trackpad misses, and the rest of the column is empty. **A tag is not a selection**: the click stops at the cell and never reaches the table, so tagging a row leaves the selection and the Edit view exactly as they were; under §6's rule a tab holding the designer's own text would otherwise earn a new tab per tag. **A folder row still toggles** — it has no status to cycle. And the **collision dialog was walked on a case-only collision**, `dup-WIP.txt` cycling onto an existing `Dup-DONE.txt`: on a case-insensitive volume the rename would otherwise have taken that file with it. *Cancel* left both alone; *Save new* produced one renamed file and never touched the one in the way.)*

### The context menu

**Right-click targets the row under the cursor and never changes the selection or the Edit view** — a right-click that selected would destroy the tab you were reading in order to show you a menu. The cost is paid by a **disabled header item naming the target's subject** (the subject, not the filename), truncated in the middle when long.

**Proof-page row:**

```
caps                              <- target header, disabled
--------------------------------
Status                        >   TODO / WIP / DONE, current one check-marked
Set owner                     >
Edit note                         (or "Add note" when there is none)
--------------------------------
Rename...
Move to                       >
Duplicate
--------------------------------
New proof-page                    (sibling, in this page's folder)
--------------------------------
Reveal in Finder
Move to Trash
```

- **Status** duplicates the swatch cycle deliberately: the cycle cannot jump `TODO → DONE`, and the menu is where a designer discovers what the swatch does at all.
- **Rename** opens a `vanilla.dialogs` modal on the **subject only**, prefilled, **showing the resulting filename** so tag preservation is visible rather than implied. No inline cell editing.
- **Move to** is a submenu of the proof-book's folders, indented, plus the root. No `NSOpenPanel` — a destination outside the proof-book is not offerable. The current parent is **greyed, not omitted**. The item is disabled when the list would be empty.
- **Duplicate** copies the text and **resets every claim**: `TODO`, no owner, **no note**, subject suffixed (`caps-2.txt`). A fixed rule that clears is not a guess; a new file never inherits a progress claim.

**Set owner** submenu (ADR-0001 amendment): owners **discovered in the current proof-book's filenames**, alphabetically; the **last owner set**, sorted to the top, stored under a single **global** `Glyphs.defaults` key and shown even when absent from this book; ***New owner…***, free text validated to 1–4 letters, rejected with a message rather than silently mangled; ***Clear owner***, enabled only when the page has one.

**The plugin never guesses an owner.** No macOS full name, no git `user.name`. Every owner value was either typed by a human or is already in a filename in this proof-book. No registry, no uniqueness check: two collaborators who are both `NE`, or a designer whose initials change, are the designers' business.

**Folder row:**

```
caps                              <- target header, disabled
--------------------------------
New proof-page                    (inside this folder)
New subfolder
--------------------------------
Set status of all pages       >
Set owner of all pages        >
--------------------------------
Rename...
Move to                       >
Duplicate
--------------------------------
Reveal in Finder
Move to Trash
```

- The bulk verbs are **recursive**. Their submenus are the page-row ones with **no check-marks** — a folder has no current value.
- **They confirm, with a count**: *"Set 14 proof-pages in `caps` to `DONE`?"*. A bulk re-tag is the only action in ProofBook with **no undo at all** — a rename leaves nothing in the Trash.
- **Collisions in a bulk re-tag pre-scan, skip, and report**: *"Set 11 proof-pages. 3 skipped — a page with that name already exists."* Never a modal per file; never a numeric suffix, which would invent new subjects during a *tag*.
- **Duplicating a folder** is a recursive copy applying the same reset throughout: every copied page lands `TODO`, no owner, no note. The copy is named `caps-2`.

**Empty space / no selection:**

```
New proof-page                    (proof-book root)
New subfolder
--------------------------------
Reveal proof-book in Finder
```

No header. **Empty space always targets the root**, regardless of what is expanded or selected — which also defines the footer `+ New proof-page` button as exactly this item. **No bulk verbs here**: blank space is the easiest menu to open by accident, and a whole-book re-tag is the largest irreversible action in the plugin. It stays reachable by collapsing to the top-level folders and doing them one at a time.

### Cross-cutting rules

- **One collision behaviour everywhere.** Tag-rename, rename, move and duplicate all raise the same modal: ***Save new*** or ***Cancel***. Never overwrite, never merge. *Save new* is a **rename, not a copy** — still one file — with a numeric suffix appended to the **subject**: `caps-WIP-NE.txt` → `caps-2-DONE-NE.txt`, incrementing until free. The suffix sits in the subject so right-to-left parsing is undisturbed and the page sorts adjacent to its sibling. The dialog names both filenames: the one in the way, and the one that will be written. Folder-on-folder collisions yield `caps-2` and the two stay separate. Bulk re-tag is the single exception (skip-and-report, above).
- **Deletion** uses `NSFileManager.trashItemAtURL_`, never `os.remove`. The item reads *Move to Trash*, not *Delete*. **No confirmation** — the Trash is the confirmation.
- **Except**: deleting a folder confirms when the folder holds **anything at all on disk**, not just proof-pages. A folder that looks empty in the tree can take a `.glyphs` file to the Trash with it. Phrase the count in proof-pages, plus "and other files" when ignored files are present. An empty folder still deletes unconfirmed.
- **A malformed header disables exactly one item.** *Status*, *Set owner*, *Rename*, *Move to* and *Duplicate* are filename operations and stay live. Only *Edit note* is **shown disabled**, reading *Note unreadable — fix the header in a text editor*. Hiding it would read as a bug, and this is the only place a designer could learn why their note vanished from the pane.

---

## 9. Diagnostics

- **Every worker-thread failure marshals back to the UI.** An exception on a background thread otherwise vanishes entirely.
- **One opt-in debug flag**, off by default, logging to the Macro Panel. Not a logging framework.
- Load-time `print()` is invisible in the Macro Panel; do not rely on it. A plugin error surfaces as a modal dialog naming the bundle, with the traceback — Glyphs survives, only the plugin is lost.

---

## 10. Build notes

- **Install**: symlink the bundle into `~/Library/Application Support/Glyphs 4/Plugins/`. Symlinks work (Plugin Manager itself uses them), but **a broken symlink fails completely silently** — no dialog, no log, indistinguishable from not installed. Verify with `ls <link>/Contents/` after creating one.
- **Edit-test loop**: edit → **quit** → relaunch → open a font → look. ~15 seconds. Reload Scripts does not pick up plugin changes, and running `plugin.py` in the Macro Panel raises `objc.error: … is overriding existing Objective-C class`. A palette only instantiates once a document window exists. **This is why the core exists**: everything testable outside Glyphs should be tested there.
- **Reference**: there is no published Glyphs 4 Python API docs site. The `Glyphs4` branch of the official GlyphsSDK and its docstrings are the best available source. Do **not** template from SDK `master` — it is Glyphs-2 vintage. Runtime is Python 3.14.6, confirmed by observation.
- **A resizable palette must return a `GSPaletteView`.** That class is the resize handle: `canResize:` is `|maxHeight - minHeight| > 1.0`, `drawRect:` fills a 28x3 pill at `y = 2`, and `mouseDown:` returns unless the click is at `y < 5.0`. The SDK's `init` casts `theView()` to it and calls `setController_` inside a bare `except: pass`, so a vanilla palette returning `getNSView()` fails that call silently and is fixed at one height with nothing said. Wrap the built view in a `GSPaletteView`, **inset the content by 5pt at the foot** or the handle is invisible and the drag lands on whatever covers it, and **call `setTranslatesAutoresizingMaskIntoConstraints_(False)`** on it — the drag resizes through Auto Layout (`mouseDragged:` writes the height and calls `invalidateIntrinsicContentSize`; `intrinsicContentSize` returns it), and a view built in code ignores its intrinsic size until you say so. None of this is in the SDK docstrings; it was read out of `GlyphsApp.framework` with `nm` and `otool -arch arm64 -tV`.
- **Selector signatures are not yours to change.** PyObjC raises `BadPrototypeError` while building the class — losing the whole plugin, not one method — if a subclass redeclares a signature the runtime already has. The SDK declares `minHeight`/`maxHeight` as `l@:` and `currentHeight` as `L@:` where Glyphs' own properties are `Tq`/`TQ`; the mismatch is harmless, because PyObjC's `l` is a 64-bit C long. Set the range through `self.min` / `self.max` instead.
- Gitignore `plugin (autosave).py` inside the bundle — Glyphs' built-in editor writes it there.
- **A `List2` is on `NSTableViewStyleInset` by default**, which holds every row 17pt in from the view's edge. Nothing drawn inside a cell can undo it — the cell is clipped to the frame the style hands it — so a palette that lines up with the section header Glyphs draws above it needs `setStyle_(NSTableViewStylePlain)` and an intercell spacing of zero. The cost is the rounded inset selection highlight, which belongs to that style. `setRowHeight_` goes after `super().__init__`: vanilla's `_buildColumns` measures the cell and writes a height of its own, last.
- **The drawing can be checked without Glyphs.** Stub `GlyphsApp` and `GlyphsApp.plugins` in `sys.modules`, put the bundle's `Resources` and Glyphs' own vanilla repository on `sys.path`, and `plugin.py` imports under Glyphs' Python 3.14 — enough to instantiate the palette, call `_draw`, render the view into an `NSBitmapImageRep` and *measure* the result in points. That is how the margins above were found. It says nothing about how Glyphs lays the palette out; the edit-test loop is still the only answer to that.

---

## 11. Open, deliberately

Not blockers; revisit after the MVP has been used:

- Whether a flat `List2` with Python-computed indentation stays usable at several hundred rows, and whether deep nesting needs more than expand/collapse.
- Whether the proof-book ever needs a notion of order beyond alphabetical.
- Whether ProofBook needs any undo beyond the Trash — the recursive bulk re-tag has none, and a confirmation dialog is its only guard.
- Distribution through the Plugin Manager (vanilla is declarable as a dependency; the answer does not change between personal use and shipping).

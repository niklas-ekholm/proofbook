# ProofBook MVP — build specification

**Status**: ready to build. Derived from issues #2–#13 on the wayfinding map ([#1](https://github.com/niklas-ekholm/proofbook/issues/1)) and ADR-0001 through ADR-0005. Status and ownership re-specified by map [#37](https://github.com/niklas-ekholm/proofbook/issues/37) and ADR-0006, which supersedes ADR-0001 and amends ADR-0003 and ADR-0004.

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

- **The core** — a package that imports nothing from `GlyphsApp`, `AppKit`, `vanilla` or `objc`, and performs **no syscalls**. It reads the subject off a filename, reads and writes the frontmatter header, flattens a listing into display rows, resolves collisions, and decides from the status cache which paths need background reads.
- **The adapter** — the `PalettePlugin` subclass and its vanilla view. It performs every syscall, owns the worker thread, raises dialogs, and draws.

The core takes a directory listing as **input data** (names, `st_flags`, `mtime`, `size`) plus the cached entries, and returns rows plus **intents** — `rename(src, dst)`, `read_background(paths)`, `write_text(path, bytes)`, `trash(path)`, `make_dir(path)`, `copy(src, dst)`. It does not open, stat, or rename anything itself. The adapter performs the intents and feeds the results back.

Suggested core modules (a suggestion, not a requirement): `names.py` (filename → subject), `status.py` (the closed set, the swatch cycle, the owner shape), `frontmatter.py` (the header), `cache.py` (the status cache's format and staleness), `tree.py` (listing → rows), `ops.py` (rename, move and duplicate → intents, collision resolution).

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

- The filename is the subject: a subject containing hyphens, and a legacy `caps-WIP-NE.txt` reading as the subject *caps WIP NE* with no status.
- The `status` and `owner` keys: lowercase on write, any case on read, `todo` never written, an unrecognised value reading as no status, a repeated known key malformed, and a write dropping any unknown line bearing a known key's name.
- Frontmatter round-trips: canonical in → canonical out; lenient forms (one-line `note:`, odd indent) normalising on write; unknown keys preserved in order with the note block last; malformed input flagged read-only and never rewritten; the header written with `\n` whatever the file uses, and writing twice giving the same bytes; body passed through byte-for-byte.
- The collision rule producing `caps-2.txt`, incrementing until free.
- The status cache: an entry valid while `(mtime, size)` matches; invalid on a mismatch; a placeholder never scheduled for a read; a version mismatch or unparseable cache treated as empty; departed paths pruned.
- Listing → rows: depth, alphabetical order, empty folders present, non-`.txt` files absent.

---

## 3. Storage

### Folder discovery

A folder named exactly `proofbook`, beside the open Glyphs file. Resolved from `self.windowController().document().font` — **never `Glyphs.currentDocument`**; there is one palette instance per document window.

The folder is created **only by an explicit action**: the empty state's *Create proof-book* button, or *New proof-page* when the folder is absent. Loading the plugin, expanding the palette, and switching windows never touch the disk.

`font.filepath` is `None` for an unsaved font. Subscribe to `DOCUMENTWASSAVED` and re-resolve on fire, so the unsaved empty state clears itself with no user action. **Save As uses the same path with no special case**: the font moves, the proof-book does not follow, and ProofBook drops to the empty state if no `proofbook` folder sits beside the new location.

### Membership

`.txt` files and all folders are shown. Everything else is **silently ignored** — no warning, no "unrecognised files" section. Empty folders are shown. Subfolders nest arbitrarily and carry no metadata of their own. Everything is ordered alphabetically.

The extension is the membership test, and the only one: any `.txt` is a proof-page.

### Filenames (ADR-0006)

**The filename is the subject.** Strip `.txt`, and that is the whole rule. Hyphens render as spaces in the palette; the raw filename appears only in the tooltip. The filename carries no status and no owner, and ProofBook never renames a file to tag it.

- No version numbers. Versions belong to Glyphs files.
- A legacy name such as `caps-WIP-NE.txt` is not parsed: its subject is *caps WIP NE* and it has no status. Nothing is migrated — rename such files by hand.

**One file is one proof-page.** Two people working on the same subject own two files, `caps.txt` and `caps-2.txt` say. Copy-and-rename to take over someone's page is a human agreement; the plugin does not enforce it.

### Frontmatter (ADR-0003)

```
---
status: wip
owner: NE
note: |
  Caps look heavy against the lowercase in Bold.
  Revisit after the weight axis is fixed.
---
HAMBURGEFONSTIV
handgloves
```

A hand-rolled `Key: value` parser and writer, ~30 lines, shaped as **valid YAML** so editors highlight it. No import that can fail — `PyYAML` is absent from the Plugin Manager index entirely, and `tomllib` is read-only.

- **Fences**: a header exists only if line 1 is exactly `---`, ending at the next `---`. Everything after is proof text, `---` lines included.
- **Keys** (ADR-0006): `status` is `wip` or `done`, written lowercase and read in any case; `todo` is **never written** — a `todo` page has no `status` key. `owner` is written uppercase, read in any case; the 1–4 letter limit is enforced by the UI, not the reader, so a hand-written `owner: Niklas Ekholm` is shown, truncated in the pill. An unrecognised value (`status: blocked`) reads as no status, not malformed. Status and owner are independent.
- **One header value, both ways** (#43): reading returns a `Document` carrying a `Header` — `status`, `owner`, `note`, `unknown` — and `write(data, header)` takes one back. A caller reads, `_replace`s the field it changes, and writes: read-modify-write, made explicit. `names` no longer has a `tagged` flag.
- **Write strictly**: always `note: |` with 2-space-indented continuation lines. One form only. This keeps colons out of scalar position and de-fangs a note line reading `---`.
- **Read leniently**: any consistent indent (strip the common prefix), or a one-line `note: value` (split on the first colon, value verbatim). Both normalise to canonical form on the next write.
- Blank lines inside the note belong to it; leading and trailing ones are trimmed.
- **Order on write**: `status`, `owner`, then **unknown keys preserved verbatim** in original order, then the note block always last. A write that sets a known key drops any unknown line bearing that key's name.
- **Malformed** — no closing fence, bytes that are not UTF-8, or a known key written twice — means the whole file is proof text. The page is **untaggable**: the row shows the malformed swatch (§4), every header write refuses, and the note pane shows the broken header **read-only**. Never overwrite bytes you did not understand; never hide the page. The designer fixes it in a text editor.
- **A header left with no keys is removed entirely**, fences included — an emptied note on a `todo`, unowned page with no unknown keys.
- UTF-8 strict; BOM tolerated on read, dropped on write. **The header is always written with `\n`**, and `\r\n` reads as well (issue #36). A CRLF file therefore becomes mixed on its first header write — an LF header over a CRLF body — and stays that way. The body passes through byte-for-byte, its own endings included — no whitespace tidying, no trailing-newline normalisation. A note edit must diff only the header.
- No frontmatter at all is valid. A header with no proof text after it is also valid.

The filename never carries status or owner. **Nothing is stored twice.**

### The status cache (ADR-0006)

The tree shows status and owner without reading every file, from a per-book cache that the listing's own `lstat` re-validates for free — on a placeholder too, because eviction does not touch `mtime`.

- One JSON file per book at `~/Library/Application Support/ProofBook/<book-folder-name>-<sha1(abspath)[:8]>.json`. A moved font is a different book and starts cold.
- An entry holds `status`, `owner`, `malformed` (a separate field, never a status value) and the `(mtime, size)` it was validated against. **Never the note.**
- An entry is valid while `(mtime, size)` matches. A `version` mismatch or a cache that will not parse is discarded, never migrated and never an error.
- Written once per walk, only when something changed. Entries for paths that left the listing are pruned. Two windows on one book: last writer wins, no locking.
- `cache.py` in the core decides which entries hold and which paths need reading; the adapter does the I/O.

It is a memo, not a second source of truth: the file always wins.

---

## 4. The palette

### Rows (ADR-0002)

A **flat `vanilla.List2` with indentation computed in Python.** ProofBook flattens the folder tree into a row list, each row carrying a depth; the subject cell indents by depth and folder rows draw their own disclosure glyph. Expansion state is a Python set of folder paths; toggling re-sets the whole row list.

A proof-page row shows:

- **Status swatch** on the left, in one of six states — three answers and three absences of one (#41):

  | State | Swatch |
  |---|---|
  | `todo` | solid grey outline |
  | `wip` | amber |
  | `done` | green |
  | unknown — a placeholder nothing is known about, or a downloaded page that would not read | dashed grey outline |
  | still walking — not yet validated or read | faint outline, pulsing (~1.1s) |
  | malformed | warn-coloured outline, crossed |

  None of the last three may look like `todo`. Row anatomy never changes: size, position and the pill are the same in every state.
- **Subject** as plain text, hyphens rendered as spaces.
- **Owner** as an initials pill on the right; absent when the page has no owner.
- **Tooltip**: the raw filename. This is the *only* place the filename appears in the palette — transparency on demand, not on screen.

A page with no `status` key is `todo`, and renders as one. A page with a `status: todo` written by hand does too.

**Folder rows toggle expansion and never become the selection.** Selection always names a real proof-page.

Above the tree: a thin **coverage bar** — done, then wip, then a **hatched** share for every page whose status is not known (placeholder, still walking, malformed) — with *"N of M done"* beneath it and *"K unknown"* beside that while K > 0. **M is always the whole book**; the denominator never shrinks to what has been read. A wholly unknown book — a cold first open, or a book this machine has never opened — reads as not yet known, not as broken: all pulsing, or all dashed with the download hint (§7).

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

**Not yet listed** is a third state, and it is not an empty state: *"Font not saved"* and *"No proof-book yet"* are conclusions about the folder, and this is the absence of one. It exists only on the very first resolve, before the first listing walk has returned (§6); every later walk draws over the previous listing. Once the listing lands, every row appears as *still walking* until its status is validated or read.

---

## 5. Selection and the Edit view

Selecting a proof-page strips the frontmatter and pushes the remaining text into the Edit view via `tab.text`. The header it parsed for the note pane also refreshes that page's status, owner and cache entry — the one read ProofBook knows happened.

**The ProofBook tab**: if the current tab is one ProofBook opened **and still holds exactly what ProofBook put there**, its text is replaced; otherwise a new tab is opened (`font.newTab(text)`). ProofBook holds a reference to the tab it opened **and the exact text it pushed there** — both are needed for that test and for the refresh in §6. Use `tab.redraw()`, not `forceRedraw()`.

**A tab stops being ProofBook's the moment its text is the designer's.** A tab the designer opened is never written to, and neither is one ProofBook opened that has since been typed into — the designer who cleared a proof-page and wrote for an hour has forgotten where the tab came from, and losing that to a click on a row is the worst thing this plugin can do. It is the same test both times, so the two paths cannot disagree: **is the text still exactly what we pushed?** Text restored to exactly that — by an undo, say — matches again and is ProofBook's again; nothing can be lost by replacing text that is identical. The cost is one extra tab per typing episode, not one per click, because the tab that replaces it becomes the ProofBook tab in its turn.

**What ProofBook remembers is what it reads back, not what it wrote.** The Edit view stores glyphs, not characters, so `tab.text` need not return the string assigned to it: an unencoded glyph comes back as `/name`, and a trailing newline may not survive. Re-read `tab.text` after the push and keep *that* as the token. A token that can never match disowns the tab on every selection, which is a new tab per click, silently.

Keeping the read-back value is what makes the round trip stop mattering: ProofBook compares the tab against what the tab last said, so a push that comes back as `/adieresis` or loses its trailing newline still matches itself. *(**Unverified in Glyphs**, and now the only two assumptions left here. One: that the read-back is **synchronous** — the token is read on the same runloop turn as the write, and a tab that had not taken the assignment yet would hand back the previous page's text, leaving a token that matches something no longer on screen. Two: that `tab.text` is **stable** across reads of a tab nobody has touched. Nothing here assumes the round trip is the identity, but a token is worthless if it cannot match itself; if either fails, the token has to be whatever comparison does hold, never an assumption that it matched.)*

---

## 6. Lifecycle

### Refresh

Re-read the listing when the palette's window **becomes key**, and immediately after any write ProofBook itself performs. **The listing walk runs on the worker** (ADR-0006), statting every entry; while it runs the palette draws the previous listing. The walk then validates the status cache, and every materialised page whose `(mtime, size)` moved is read on the worker. Results redraw on a short **coalesced, cancellable** timer, never per file. Nothing else: no FSEvents watcher, no polling timer, no visible refresh button. The designer leaves Glyphs to pull or edit, and coming back *is* the trigger.

**Never touch the filesystem from `UPDATEINTERFACE`** — it fires on every redraw. Tear down callbacks in `__del__` or Glyphs crashes.

State is per-palette-instance and in-memory: selection, expansion, scroll position. Nothing is shared across windows and nothing survives a window close.

### On refresh

- **The displayed page changed on disk**: re-push the text **only if the ProofBook tab's text is still exactly what ProofBook put there** — the same test §5 makes before replacing a tab. If the designer has typed in that tab, the text is theirs; leave it. Nothing has to be *un*remembered for that: the question is asked afresh every time rather than latched, so a tab holding the designer's text fails it here and on the next selection too — and text they restore to exactly what was pushed is ProofBook's again, which latching would have thrown away. **The question is also asked before the page is read**, not after: this runs on every become-key and after every write, and the read is the main-thread one ADR-0004 is about, so a tab that is not ProofBook's must cost no download to rule out. A refresh writes into that tab wherever it sits in the tab bar, and **never opens one**: unlike a selection, it answers no question the designer just asked, and a proof-page arriving in front of someone who is not in Glyphs is not a refresh. Unchanged is left alone too — a re-push is a redraw, and this runs on every switch back to the window.
- **The selected page is gone**: clear the selection, empty the note pane, and **leave the Edit view tab exactly as it is.** Deleting a file should not blank a tab that may still be being read. An external rename reads as a delete plus an add; the MVP makes no attempt to track identity across a rename it did not perform.
- **A row ProofBook just wrote** shows the value written, optimistically, from the click onwards. If the next walk disagrees, the walk wins, silently — the file is the source of truth.

### Note writes

The note pane has no save button. It commits **on blur, on selection change, and on the window resigning key.** The last is load-bearing: it guarantees a draft reaches disk before the become-key refresh reads the file back, so a refresh can never clobber an uncommitted note. No per-keystroke writes. A commit that finds the file gone drops the draft and says so, rather than recreating the file.

### Header writes

A note commit and a tag both rewrite the whole header, so **every header write happens on the main thread and re-reads the file at the moment of writing** — never from a copy read earlier. A tag on a materialised page reads and writes inline; a tag on a placeholder reads on its own thread (§7) and hands the result back to the main thread, which re-reads and writes. Writes are therefore serialised by the runloop, and neither a tag nor a note can write back a header the other has since changed.

---

## 7. Cloud storage (ADR-0004)

> **Built in #25** (the gate, the worker, placeholder selection and the bulk
> download), and the status cache in #47 — **not yet verified in Glyphs**.

The download line is two rows above the tree — the count, then a mini
*Download all* / *Cancel* button beneath it — because the palette is too
narrow for both on one line. A run that ends reports its count in an alert —
*"downloaded 280 of 300; 20 failed"*; a cancelled one says nothing, because
the designer asked for it to stop. **Three pages in a row that never answer
stop the run** with *"the network is not answering"*: offline every read hangs
and leaves a thread blocked in it, and the rest of the run would be hours of
the same.

**No read that could block on a network ever happens on the main thread, and the tree never reads a placeholder.** A cold placeholder read does not fail offline, it **hangs** (#38), so there is no failure to catch: ProofBook decides before reading.

- Placeholders carry the **`SF_DATALESS`** flag (`0x40000000`) in `os.lstat().st_flags`. Statting does not trigger a download (3011 Google Drive files in 0.2s). Plain Python — no PyObjC, no per-provider code. It is the only flag the listing reads.
- The tree's statuses come from the status cache (§3), validated by that same `lstat`. A cloud-synced book opened before on this machine shows every status with no downloads; one never opened shows every placeholder's status as unknown.
- **Bulk download is explicit, never automatic.** A one-line hint above the tree, shown only while true: *"18 of 24 pages not downloaded — Download all"*. It counts **placeholders only** — a malformed or unreadable page is not in it — so it reaches zero when the download finishes, and it is the remedy for unknown statuses too. It becomes a progress readout — *"downloading 42 of 300…"* — with a **Cancel** that sets a flag the worker checks between files. No modal sheet. The scope of "all" is the whole proof-book recursively, collapsed folders included.
- **Selection routes by the flag**: a materialised file is read inline; a placeholder is read on **its own short-lived thread**, under the same cap and deadline as a tag (below), and the Edit view updates when it lands.
- **Failure on selection**: a `vanilla.dialogs` message naming the file — *"Could not read `caps.txt`; it may not be downloaded yet"* — and the **ProofBook tab is left untouched**. The row stays selected.
- **A failed read during a refresh** is silent and uncounted: nobody asked a question, and one unreadable file would otherwise alert on every become-key.
- **Failure during bulk download** never aborts the run; the worker continues and reports a count: *"downloaded 280 of 300; 20 failed"*.
- A scan during a download simply runs; rows flipping from placeholder to local **is** the progress feedback. The one thing that cancels the worker is the proof-book changing underneath it — a different font focused, or Save As.

**Tagging a placeholder downloads it** (#42): one page is implicit, many pages is a question.

- A swatch click or a context-menu status/owner verb on a placeholder downloads and tags it. The row updates optimistically, and the read fills the cache.
- The read runs on **its own short-lived thread**, never the shared worker queue — one offline click would otherwise wedge every read for the session. A second tag on a page already in flight is refused; concurrent tag-reads are **capped** at a small number, and past the cap ProofBook refuses with the reason rather than queueing.
- **The deadline is on the notification, not the read.** No completion in ~10s and ProofBook says the page could not be downloaded, so it was not tagged. **The attempt is abandoned**: the row reverts at once, and if the read finishes later it only fills the cache — it never writes. The thread may leak; the notice stays true.
- A placeholder that turns out malformed once downloaded is refused with the reason and the row reverts.
- **Bulk tagging asks first**, naming how many pages need downloading (§8).

A note can only be edited on a selected page, which routing has therefore materialised, so the note pane never reads a placeholder.

---

## 8. Operations

### The status swatch

Clicking it cycles `todo → wip → done`, which writes the `status` key (§6, *Header writes*). Tagging is the highest-frequency action and earns a direct target. A misclick is undone by another click or two around the cycle.

**No implicit owner**: clicking the swatch on a `todo` page writes `status: wip` and nothing else. One click stays one click, with no dialog ambushing it.

On a **malformed** page the swatch refuses, with the reason, once, on the click, in the note pane's voice. On a **placeholder** it downloads and tags (§7). On a row **still walking**, the click waits on nothing: the tag reads the file itself, by the same routing.

*(**Verified in Glyphs 4** under ADR-0001's renaming. The target and tag-is-not-a-selection findings carry over to header writes; the collision half no longer applies to tagging. The swatch cycled and renamed on a real proof-book, the tree and the coverage bar redraw without leaving the window, and the owner pill survives a tag. Four things the reasoning could not settle on its own. **The target is the whole marker column**, not the 9pt circle inside it — the circle is a target a trackpad misses, and the rest of the column is empty. **A tag is not a selection**: the click stops at the cell and never reaches the table, so tagging a row leaves the selection and the Edit view exactly as they were; under §6's rule a tab holding the designer's own text would otherwise earn a new tab per tag. **A folder row still toggles** — it has no status to cycle. And the **collision dialog was walked on a case-only collision**, `dup-WIP.txt` cycling onto an existing `Dup-DONE.txt`: on a case-insensitive volume the rename would otherwise have taken that file with it. *Cancel* left both alone; *Save new* produced one renamed file and never touched the one in the way.)*

### The context menu

**Right-click targets the row under the cursor and never changes the selection or the Edit view** — a right-click that selected would destroy the tab you were reading in order to show you a menu. The cost is paid by a **disabled header item naming the target's subject** (the subject, not the filename), truncated in the middle when long.

**Proof-page row:**

```
caps                              <- target header, disabled
--------------------------------
Status                        >   todo / wip / done, current one check-marked
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

- **Status** duplicates the swatch cycle deliberately: the cycle cannot jump `todo → done`, and the menu is where a designer discovers what the swatch does at all.
- **Rename** opens a `vanilla.dialogs` modal on the subject, prefilled, **showing the resulting filename**. No inline cell editing.
- **Move to** is a submenu of the proof-book's folders, indented, plus the root. No `NSOpenPanel` — a destination outside the proof-book is not offerable. The current parent is **greyed, not omitted**. The item is disabled when the list would be empty.
- **Duplicate** copies the text and **resets every claim**: removes the `status`, `owner` and `note` keys, **keeps unknown keys verbatim**, and suffixes the subject (`caps-2.txt`). A fixed rule that clears is not a guess; a new file never inherits a progress claim. On a malformed page it is **disabled** — the claims cannot be reset in a header ProofBook cannot parse.

**Set owner** submenu: owners **discovered in the status cache** for the current proof-book, alphabetically — on a partly-known book the list covers only the pages known so far; the **last owner set**, sorted to the top, stored under a single **global** `Glyphs.defaults` key and shown even when absent from this book; ***New owner…***, free text validated to 1–4 letters, rejected with a message rather than silently mangled; ***Clear owner***, enabled only when the page has one.

**The plugin never guesses an owner.** No macOS full name, no git `user.name`. Every owner value was either typed by a human or is already in a header in this proof-book. No registry, no uniqueness check: two collaborators who are both `NE`, or a designer whose initials change, are the designers' business.

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
- **They confirm, with a count**: *"Set 14 proof-pages in `caps` to `done`?"*. A bulk re-tag is the only action in ProofBook with **no undo at all** — a header write leaves nothing in the Trash. When the folder holds placeholders, the confirmation also names how many pages must be downloaded first (§7).
- **Malformed pages in a bulk re-tag are skipped and reported**: The report names how many were skipped and why, and the confirmation counts them too. Never a modal per file, and one broken file never refuses the whole folder.
- **Duplicating a folder** is a recursive copy applying the same reset throughout: every copied page lands `todo`, no owner, no note, unknown keys kept. A malformed page inside is copied **byte for byte** and counted in a report afterwards, rather than stopping the copy. The copy is named `caps-2`.

**Empty space / no selection:**

```
New proof-page                    (proof-book root)
New subfolder
--------------------------------
Reveal proof-book in Finder
```

No header. **Empty space always targets the root**, regardless of what is expanded or selected — which also defines the footer `+ New proof-page` button as exactly this item. **No bulk verbs here**: blank space is the easiest menu to open by accident, and a whole-book re-tag is the largest irreversible action in the plugin. It stays reachable by collapsing to the top-level folders and doing them one at a time.

### Cross-cutting rules

- **One collision behaviour everywhere.** Rename, move and duplicate all raise the same modal (tagging no longer renames, so it cannot collide): ***Save new*** or ***Cancel***. Never overwrite, never merge. *Save new* is a **rename, not a copy** — still one file — with a numeric suffix appended to the subject: `caps.txt` → `caps-2.txt`, incrementing until free, so the page sorts adjacent to its sibling. The dialog names both filenames: the one in the way, and the one that will be written. Folder-on-folder collisions yield `caps-2` and the two stay separate.
- **Deletion** uses `NSFileManager.trashItemAtURL_`, never `os.remove`. The item reads *Move to Trash*, not *Delete*. **No confirmation** — the Trash is the confirmation.
- **Except**: deleting a folder confirms when the folder holds **anything at all on disk**, not just proof-pages. A folder that looks empty in the tree can take a `.glyphs` file to the Trash with it. Phrase the count in proof-pages, plus "and other files" when ignored files are present. An empty folder still deletes unconfirmed.
- **A malformed header disables every header operation.** *Status*, *Set owner*, *Edit note* and *Duplicate* are **shown disabled**, each saying the header is unreadable and is fixed in a text editor. *Rename*, *Move to*, *Reveal in Finder* and *Move to Trash* are filename operations and stay live. Hiding the disabled items would read as a bug, and they are where a designer learns why the page will not take a tag.

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
- Whether the *not yet listed* state (§4) is right as built in #48: one dim line in the coverage strip, *"Reading the proof-book…"*, with no bar and no rows. It is distinct from both empty states and usually lasts under a second; the prototype for #41 covered rows, not the moment before there are any, so this is a first guess to look at in Glyphs.
- Whether iCloud hangs offline as Dropbox does (#38 measured Dropbox only). The design holds either way; see ADR-0006.
- Distribution through the Plugin Manager (vanilla is declarable as a dependency; the answer does not change between personal use and shipping).

# Proof-page metadata is split between the filename and frontmatter

A proof-page's status and owner live in its filename (`<subject>-<STATUS>-<OWNER>.txt`, parsed right-to-left so subjects may contain hyphens); its note lives in frontmatter inside the file, stripped before the text reaches the Edit view. Nothing is stored in both places. The rule deciding the split: a fact you need to see *without opening the file* belongs in the name, and a fact you need to *read* belongs in the file.

## Considered options

A root manifest (`proofbook.json`) was recommended first and rejected: the proof-book is versioned in git, reorganised heavily, and written by several collaborators across machines, so one shared file conflicts on every status change and path-keyed entries orphan silently on every move made in Finder. Per-page sidecars localise the conflicts but still detach on a hand-move and double the file count in a folder browsed by hand. Putting everything in the filename cannot hold a free-text note; putting everything in frontmatter hides status and ownership from Finder, `ls`, and any agent listing the directory.

## Consequences

Changing a status is a **rename**, so git records status history as renames and `git blame` attributes note lines. Because the subject sorts first, a status change does not reorder an alphabetical listing. One file is one proof-page: two people working on the same subject own two separate pages, and the convention that a copy is renamed to the copier's initials is a human agreement the plugin does not enforce.

The frontmatter *format* (YAML, TOML, or a hand-rolled line-based header) is deliberately left open; it depends on what is importable inside Glyphs 4's Python, and the plugin must write it, not only read it.

These decisions are provisional for the MVP and expected to be revisited once it has been used.

## The filename grammar, refined

Three shapes are legal: `subject.txt`, `subject-STATUS.txt`, and `subject-STATUS-OWNER.txt`. Status and owner are independent — a page may be tagged with no owner — but an owner is only ever read from the position *after* a recognised status, so the closed set `TODO`/`WIP`/`DONE` anchors the parse and a short trailing subject word is never mistaken for initials. An owner segment is 1-4 letters, uppercased on write.

Status words are matched **case-insensitively**, which is a deliberate trade: `things-done.txt` reads as the subject `things` with status `DONE`, not as a subject that happens to end in an English word. Matching case-sensitively would remove the ambiguity, and it was rejected because a human hand-naming a file should not have to know that capitalisation is load-bearing. The failure is a visibly wrong status on one row, fixed by renaming the file; nothing is lost. Do not "fix" this with case-sensitivity without revisiting that trade.

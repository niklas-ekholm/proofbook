# Proof-page metadata lives in the frontmatter

> Supersedes ADR-0001 wholly. Charted on map #37.

A proof-page's status, owner and note are all keys in its frontmatter header (ADR-0003), and **the filename is the subject**: strip `.txt`, and that is the whole rule. ProofBook never renames a file to tag it. Nothing is stored twice.

```
---
status: wip
owner: NE
note: |
  Caps look heavy against the lowercase in Bold.
---
```

## Why the filename stopped carrying status

ADR-0001 put status and owner in the name so they could be seen without opening the file. That made a page's identity — its path — also one of its mutable properties, and three features had to work around it independently: the collision rule (`caps-2-DONE-NE.txt`), the Edit view's tab token, and the note pane, which shipped a bug where a swatch click moved the file out from under a draft (`ebc0990`).

Git is what settles it. A rename is not recorded in the object store, only reconstructed at diff time, so `git log <path>` **loses a page's history at every status change** unless `--follow` is passed — and `--follow` takes one file, never a folder. Two collaborators tagging the same page produce a rename/rename conflict, which resolves worse than a one-line content conflict. A status change shows as `0 insertions, 0 deletions`, unreadable in review. In the header, a status change is a one-line diff that `log`, `blame` and review all read.

The cost is accepted: Finder and `ls` no longer show status. Nothing is migrated — no real proof-book carried the old names; legacy names survive only in test fixtures, and a `caps-WIP-NE.txt` now simply has the subject *caps WIP NE*.

## The keys (#43)

- **Values are lowercase on write, any case on read.** `todo` is **never written**: a TODO page carries no `status` key, and a page with no header reads as TODO and unowned.
- **`owner` is written uppercase and limited to 1–4 letters by the UI** (the pill has to fit), not by the parser: a hand-written `owner: Niklas Ekholm` is shown, truncated.
- **Order**: `status`, `owner`, then unknown keys verbatim in original order, then the note block last.
- **An unrecognised value** (`status: blocked`) reads as no status — not malformed. **A repeated known key is malformed**, by ADR-0003's argument for a repeated `note`. A write that sets a known key drops any unknown line bearing that key's name, or the file would read as malformed after the write.
- Status and owner are fully **independent**; a page may be owned with no status.

**A malformed header makes a page untaggable**, not merely un-notable. ProofBook must not rewrite bytes it could not parse, so the swatch refuses with the reason, once, on the click, and the page is fixed in a text editor. There is no escape hatch in the plugin.

## Status without reading: the cache (#39)

The tree can no longer take status from a listing, and ADR-0004 forbids reading a placeholder — #38 measured a cold placeholder read **blocking indefinitely** offline, with no failure to catch. The mechanism that replaces the filename is a per-book cache validated by `lstat`.

**Eviction does not touch `mtime`** (6015 iCloud placeholders stamped 2002–2026), and `lstat` works on a file that cannot be read. So a cached status is re-validated for free on a placeholder, the cache survives eviction, and **a dataless book you have opened before shows every status, indefinitely, with no downloads.** It cannot go stale undetected: a collaborator's change moves `(mtime, size)` and the entry drops to unknown rather than confidently wrong.

- One JSON file per book: `~/Library/Application Support/ProofBook/<book-folder-name>-<sha1(abspath)[:8]>.json`. Not `Glyphs.defaults`, which is a shared plist rewritten wholesale.
- An entry holds `status`, `owner`, `malformed` (a separate field, not a status value) and the `(mtime, size)` it was validated against. **Never the note** — the designer's prose stays in the folder they can see.
- Invalidated by a `(mtime, size)` mismatch; a `version` mismatch or an unparseable file is discarded, never migrated and never an error. Written once per walk, only when something changed; entries for paths that left the listing are pruned. Two windows on one book: last writer wins, no locking.
- The core's `cache.py` owns the format and the staleness decision — given the entries and a listing, which are valid and which paths need reading — so it is testable with no filesystem (ADR-0005). The adapter does the I/O.

## What is read, and when (#40)

- **A placeholder is never read to fill in the tree.** It is read only when a designer's click on that one page asks for it — a selection (ADR-0004) or a tag (below) — or through the explicit bulk download. `st_flags & SF_DATALESS` from the listing's own `lstat` is the gate. The listing needs no other flag.
- **Every materialised page whose `(mtime, size)` moved is read, on the worker.** The steady state is zero reads.
- **The listing walk itself moves off the main thread.** The palette draws the previous listing meanwhile; on the very first resolve there is none, so a third state exists, distinct from both empty states.
- Redraws are coalesced on a short, cancellable timer. Selection fills in a status for free from the read it already does.
- **After ProofBook's own write the row updates optimistically**; if the next walk disagrees, the walk wins, silently.
- The download hint (ADR-0004) is unchanged in wording and counts **placeholders only**; a malformed or unreadable page is not in it, so the count reaches zero when the download finishes.

## Tagging a placeholder (#42)

**One page is implicit, many pages is a question** — ADR-0004's own line. A swatch click on a placeholder downloads and tags it, as selection already does, and the read populates the cache. The row updates optimistically, and because an offline read hangs rather than failing, **the deadline goes on the notification**: no completion in ~10s and ProofBook says *"«caps» could not be downloaded, so it was not tagged."*

- A tag's read on a placeholder runs on **its own short-lived thread**, never the shared worker queue, or one offline click wedges every read for the session. A second tag on a page in flight is refused; concurrent tag-reads are capped, and past the cap ProofBook refuses with the reason rather than queueing.
- **A tag on a materialised page is read and written on the main thread**, by the same `SF_DATALESS` routing ADR-0004 gives selection. **Every header write happens on the main thread**, re-reading the file at the moment of writing — a placeholder tag's thread hands its result back rather than writing. So a tag and a note commit are serialised by the runloop, and neither can write back a header the other has since changed.
- A placeholder that turns out malformed once downloaded is refused with the reason, and the optimistic row reverts.
- **Bulk tagging asks first**, naming how many pages need downloading, through the existing offer.

## How an unknown status looks (#41)

The swatch says everything; row anatomy never changes. Six swatch states, three answers and three absences of one:

| State | Swatch |
|---|---|
| `todo` | solid grey outline |
| `wip` | amber |
| `done` | green |
| placeholder, status unknown | dashed grey outline |
| still walking | faint outline, pulsing |
| malformed | warn-coloured outline, crossed |

The coverage bar keeps the **whole book** as its denominator and hatches the unknown share, captioned *"N of M done"* with *"K unknown"* beside it while K > 0. A wholly unknown book reads as not yet known, not as broken. The risk — four outline-ish circles at 9pt — was looked at in the prototype and accepted.

## Considered options

Keeping status in the filename and fixing each symptom locally was the status quo, and the git argument rules it out: no local fix gives a folder `git log` its renames back. A root manifest and per-page sidecars were rejected in ADR-0001 for reasons that still hold (a shared file conflicts on every change; sidecars detach on a hand-move). Keeping owner in the filename while status moved would have halved the benefit and kept the grammar.

## Unmeasured

**iCloud offline.** #38 measured Dropbox with no network — writes succeed, a read hangs — but iCloud's offline pass ran after the network had returned. Parity is assumed, not measured. The design does not depend on it: no read is attempted without the `SF_DATALESS` gate, a tag's read is contained on its own thread, and the deadline is on the notification. If iCloud fails offline where Dropbox hangs, the notification simply fires sooner.

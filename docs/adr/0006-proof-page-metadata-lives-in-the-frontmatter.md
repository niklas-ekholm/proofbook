# Proof-page metadata lives in the frontmatter

> Supersedes ADR-0001 wholly, and amends ADR-0003, ADR-0004 and ADR-0005.
> Charted on map #37. The rules are in the spec (§3–§8); this holds the why.

A proof-page's status, owner and note are all keys in its frontmatter header (ADR-0003), and **the filename is the subject**. ProofBook never renames a file to tag it. Nothing is stored twice.

## Why the filename stopped carrying status

ADR-0001 put status and owner in the name so they could be seen without opening the file. That made a page's identity — its path — also one of its mutable properties, and three features had to work around it independently: the collision rule (`caps-2-DONE-NE.txt`), the Edit view's tab token, and the note pane, which shipped a bug where a swatch click moved the file out from under a draft (`ebc0990`).

Git is what settles it. A rename is not recorded in the object store, only reconstructed at diff time, so `git log <path>` **loses a page's history at every status change** unless `--follow` is passed — and `--follow` takes one file, never a folder. Two collaborators tagging the same page produce a rename/rename conflict, which resolves worse than a one-line content conflict. A status change shows as `0 insertions, 0 deletions`, unreadable in review. In the header, a status change is a one-line diff that `log`, `blame` and review all read.

Accepted costs: Finder and `ls` no longer show status, and nothing is migrated — no real proof-book carried the old names, so legacy names are renamed by hand.

## The consequence that is new: a malformed header makes a page untaggable

While status lived in the name, a broken header cost only the note. Now ProofBook must not rewrite bytes it could not parse, so every header operation refuses on such a page, and the page is fixed in a text editor. ProofBook offers no escape hatch. (#43)

## Status without reading, because a placeholder read can hang

The tree can no longer take status from a listing, and a placeholder cannot be read to find it. #38 measured a cold placeholder read on Dropbox with no network: it does not fail, it **blocks indefinitely**, so there is no error to catch and no timeout that makes it safe. Writes, by contrast, succeed offline in 1–7ms. The expensive half of read-modify-write is the read, and ProofBook must decide before attempting one — `SF_DATALESS` from `lstat` is the only gate, and statting never downloads.

What replaces the filename is a per-book **status cache** (#39), and one measurement makes it work: **eviction does not touch `mtime`** (6015 iCloud placeholders stamped 2002–2026), while `lstat` works on a file that cannot be read. So a cached status is re-validated for free on a placeholder, the cache survives eviction, and a book this machine has opened before shows every status indefinitely with no downloads. It cannot go stale undetected — a collaborator's change moves `(mtime, size)` and the entry drops to unknown rather than confidently wrong. It is a memo, not a second source of truth.

It lives under Application Support rather than `Glyphs.defaults`, a plist shared with every plugin and rewritten wholesale. It never holds the note, so the designer's prose stays in the folder they can see. Reading only visible rows was rejected: the coverage bar needs every page anyway. (#40)

## One page is implicit, many pages is a question

ADR-0004 accepted that selecting a placeholder downloads it, because a click asked for it. Tagging one is the same case (#42): refusing would decline to change a status the row is already showing from the cache, for a reason invisible until clicked. Many pages at once is the automatic bulk download ADR-0004 refuses, so it asks first.

Because an offline read hangs, any single-page placeholder read — a tag or a selection — runs on **its own short-lived thread**, never the shared worker, or one offline click wedges every read for the session; concurrent ones are capped. The deadline goes on the **notification**, not the read. When it fires the attempt is **abandoned**: the row reverts, and a read that finishes later only fills the cache, never writes — a notice saying a page was not tagged has to stay true. Rejected: leaving the correction to the next walk, which is a status that undoes itself minutes later and gets reported as *"the plugin randomly loses my statuses"*.

A note commit and a tag both rewrite the whole header, so **every header write happens on the main thread, re-reading the file at the moment of writing**. The runloop serialises them with no lock. Reading inline is safe there only because the gate has already said the file is materialised.

## How unknown looks

The swatch carries every condition and row anatomy never changes (#41, variant A of the prototype at `ce28635`). Two alternatives were built beside it and judged on sight: one kept the swatch as a status only, moving the new conditions into the row and letting the coverage denominator shrink to what had been read; the other gave a placeholder no swatch at all and moved the counts into the notice line. The coverage bar keeps the whole book as its denominator and hatches what is unknown. The accepted risk is several outline-ish circles at 9pt.

## Considered options

Keeping status in the filename and fixing each symptom locally was the status quo, and the git argument rules it out: no local fix gives a folder's `git log` its renames back. A root manifest and per-page sidecars were rejected in ADR-0001 for reasons that still hold — a shared file conflicts on every change, and sidecars detach on a hand-move.

## Unmeasured

**iCloud offline.** #38's iCloud offline pass ran after the network had returned, so only Dropbox's hang is measured. Parity is assumed. The design does not depend on it: no read is attempted past the `SF_DATALESS` gate without a click, such a read is contained on its own thread, and the deadline is on the notification. If iCloud fails offline where Dropbox hangs, the notification simply fires sooner.

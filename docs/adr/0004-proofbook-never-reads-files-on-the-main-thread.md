# ProofBook never reads files on the main thread

> **Amended by [ADR-0006](0006-proof-page-metadata-lives-in-the-frontmatter.md)** (2026-09-24).
> The invariant stands. What ADR-0006 spends is the half this ADR credited to
> ADR-0001 — *the tree reads no file contents at all* — because status and
> owner now live inside the file. The tree fills in status from a cache
> re-validated by `lstat` and from reads of materialised pages on the worker,
> never from a placeholder. Issue #25, postponed on 2026-09-06, is reopened as
> a prerequisite; until it lands ProofBook still reads inline on the main
> thread. The passages below that ADR-0006 overturned are marked in place.

A proof-book often lives in Dropbox, Google Drive or iCloud Drive, where files are **dataless placeholders**: reading one triggers a synchronous download that blocks for seconds online and, offline, indefinitely (#38). ProofBook therefore holds one invariant: **no read that could block on a network ever happens on the main thread.** A file the `SF_DATALESS` flag says is materialised may be read inline; every other read goes through a background thread. *(Originally also: "the tree reads no file contents at all", built from a directory listing and the filename grammar alone. ADR-0006 retired that half — see the banner.)*

This is not speculative. While standing up the plugin skeleton (issue #6), Glyphs itself blocked for over three minutes at 0% CPU, unresponsive and with no progress indication, doing exactly this class of work: recursively reading 461 Google Drive scripts serially on the main thread at startup.

## What the measurements showed

Both Google Drive and iCloud mark placeholders with the `SF_DATALESS` stat flag (`0x40000000`), readable from plain Python via `os.lstat().st_flags` — no PyObjC, no `NSURL` resource keys, no per-provider code. Statting does **not** trigger a download: 3011 Google Drive files (2990 of them dataless) statted in 0.2 seconds; 3040 iCloud files in 5.5. Dropbox was not available to test but uses the same macOS File Provider mechanism.

So the split decided in ADR-0001 — status and owner in the filename, the note inside the file — had already solved most of this by accident. Everything the tree displays comes from names, which are free. *(Superseded: ADR-0006 moved status and owner into the file. The same free `lstat` now validates a per-book status cache instead, and since eviction does not touch `mtime`, the cache survives it.)*

## Considered options

There is no portable API to trigger a download without reading: `startDownloadingUbiquitousItemAtURL:` is iCloud-only, and the File Provider equivalents need the provider's domain and item identifiers. Materialisation is triggered by reading, so the only lever is *which thread reads*. Python releases the GIL during file I/O, so a `threading.Thread` doing the reads leaves Glyphs' UI fully responsive; UI updates are marshalled back to the main thread.

Doing the reads synchronously and accepting a brief hang was considered for the single-file case (selecting a proof-page is user-initiated, one file, and the designer just clicked the thing). It was rejected once a worker thread had to exist anyway for the bulk download: routing by the `SF_DATALESS` flag — materialised files read inline, dataless ones through the worker — costs almost nothing and removes the last main-thread read that can block on a network.

## Consequences

Bulk download is an **explicit** action, never automatic: ProofBook reads a folder it does not own, and silently pulling a colleague's entire proof-book onto a laptop on a hotel connection is not its call. It is offered by a one-line hint above the tree, shown only while it is true — "18 of 24 pages not downloaded" — which becomes a progress readout with a Cancel while the worker runs. A failed file never aborts the run; the worker reports a count at the end.

*(Superseded by ADR-0006: tagging is no longer a rename, and is no longer offline on a placeholder.)* A tag is now a header write, which is read-modify-write, so tagging a placeholder downloads it — implicitly, because one click on one page asked for it, on the same terms as selection. The read runs on its own short-lived thread and the notification carries a ~10s deadline, since offline the read hangs rather than failing. Tagging many pages asks first, through the bulk offer above.

What still holds: the become-key refresh asks whose the Edit view tab is *before* it reads, so a page is re-read for the Edit view only when a ProofBook tab still holds exactly what ProofBook pushed into it — a page already materialised once, for a designer who is looking at it. Because a note can only be edited on a selected page, and selecting materialises it, the note pane never reads a placeholder.

The invariant is free today and expensive to retrofit. Its real work is on the feature nobody has written yet — searching notes across a proof-book, say — which it forces someone to think about rather than write casually as a loop over files.

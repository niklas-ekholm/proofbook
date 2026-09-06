# ProofBook never reads files on the main thread

A proof-book often lives in Dropbox, Google Drive or iCloud Drive, where files are **dataless placeholders**: reading one triggers a synchronous download that blocks for seconds, or fails offline. ProofBook therefore holds one invariant: **the tree reads no file contents at all**, and **no file read ever happens on the main thread**. The tree is built from a directory listing and the filename grammar alone; every read of file contents goes through a background worker thread.

This is not speculative. While standing up the plugin skeleton (issue #6), Glyphs itself blocked for over three minutes at 0% CPU, unresponsive and with no progress indication, doing exactly this class of work: recursively reading 461 Google Drive scripts serially on the main thread at startup.

## What the measurements showed

Both Google Drive and iCloud mark placeholders with the `SF_DATALESS` stat flag (`0x40000000`), readable from plain Python via `os.lstat().st_flags` — no PyObjC, no `NSURL` resource keys, no per-provider code. Statting does **not** trigger a download: 3011 Google Drive files (2990 of them dataless) statted in 0.2 seconds; 3040 iCloud files in 5.5. Dropbox was not available to test but uses the same macOS File Provider mechanism.

So the split decided in ADR-0001 — status and owner in the filename, the note inside the file — had already solved most of this by accident. Everything the tree displays comes from names, which are free.

## Considered options

There is no portable API to trigger a download without reading: `startDownloadingUbiquitousItemAtURL:` is iCloud-only, and the File Provider equivalents need the provider's domain and item identifiers. Materialisation is triggered by reading, so the only lever is *which thread reads*. Python releases the GIL during file I/O, so a `threading.Thread` doing the reads leaves Glyphs' UI fully responsive; UI updates are marshalled back to the main thread.

Doing the reads synchronously and accepting a brief hang was considered for the single-file case (selecting a proof-page is user-initiated, one file, and the designer just clicked the thing). It was rejected once a worker thread had to exist anyway for the bulk download: routing by the `SF_DATALESS` flag — materialised files read inline, dataless ones through the worker — costs almost nothing and removes the last main-thread read that can block on a network.

## Consequences

Bulk download is an **explicit** action, never automatic: ProofBook reads a folder it does not own, and silently pulling a colleague's entire proof-book onto a laptop on a hotel connection is not its call. It is offered by a one-line hint above the tree, shown only while it is true — "18 of 24 pages not downloaded" — which becomes a progress readout with a Cancel while the worker runs. A failed file never aborts the run; the worker reports a count at the end.

Because a status or owner change is a **rename**, and renames work on placeholders, tagging a page works fully offline on a book that has never been downloaded. The become-key refresh (spec §6) is the one thing that could quietly take that back: a refresh runs after every rename as well, and re-reading the displayed page there would put a download behind tagging. It cannot, because the refresh asks whose the Edit view tab is *before* it reads: a page is re-read only when there is a ProofBook tab still holding exactly what ProofBook pushed into it, which is a page that has already been materialised once, for a designer who is looking at it. A proof-book nobody has selected a page in is never read at all. Because a note can only be edited on a selected page, and selecting materialises it, there is no read-modify-write against a placeholder.

The invariant is free today and expensive to retrofit. Its real work is on the feature nobody has written yet — searching notes across a proof-book, say — which it forces someone to think about rather than write casually as a loop over files.

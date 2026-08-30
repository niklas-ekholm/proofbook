# ProofBook's logic lives in a Glyphs-free core

ProofBook is split in two. A **core** package imports nothing from `GlyphsApp`, `AppKit` or `vanilla` and performs no syscalls: it parses and formats filenames, reads and writes the frontmatter header, flattens a directory listing into display rows, resolves collisions, and decides which paths are dataless. A thin **adapter** — the `PalettePlugin` subclass and its vanilla view — supplies the core with data, performs the file operations the core asks for, owns the worker thread, and draws.

The core is exercised by a `unittest` suite that runs under plain `python3`, with no Glyphs, no install step, and no filesystem.

## Why

Standing up the skeleton (issue #6) measured the edit-test loop: there is no reload-without-restart, so every change costs a quit, a relaunch, and reopening a font; a palette will not instantiate without an open document; load-time `print()` is invisible in the Macro Panel; and a failure surfaces only as a modal traceback. That is the *entire* feedback channel, and it is available only to someone sitting in front of Glyphs.

Meanwhile ADR-0001, ADR-0003 and ADR-0004 loaded ProofBook with logic that has nothing to do with Glyphs: the right-to-left filename parse over `<subject>-<STATUS>-<OWNER>.txt`, the lenient-read/strict-write normalisation of the `Key: value` header, the numeric-suffix-in-the-subject collision rule, and the `SF_DATALESS` routing. This is where the bugs will be, it is all string-and-path work, and none of it needs a running font editor to be proven correct.

The build session is expected to be agent-driven, with the designer running the result. An agent cannot launch Glyphs, cannot read a modal dialog, and cannot observe a palette. Without a seam its only available signal is "it loaded without a modal", which says nothing about whether a note round-trips.

## The line, and why it falls there

The core takes a directory listing as **input data** — names, flags — and returns rows and **intents**: *rename X to Y*, *read these paths off the main thread*. It does not open, rename, or stat anything itself.

The alternative was a core that owns the filesystem and is tested against temp directories. It was rejected because of ADR-0004: the no-read-on-the-main-thread invariant is about *threads*, and a core that owns the filesystem must own the worker too, dragging `threading` and its timing into the one part of the system that should be trivially deterministic. Splitting it this way puts the *decision* to read in the background inside the core, where it is a testable branch on a stat flag, and leaves *where that read runs* in the adapter, where it belongs.

`unittest` over pytest for one reason only: tests run outside Glyphs, where a dependency would be harmless in principle, but the build session should never have to negotiate an install to find out whether the header parser works.

## Consequences

The core lives inside the bundle at `Contents/Resources/`, imported by the plugin after it adds its own directory to `sys.path`. There is no build step and no symlink: the repo *is* the bundle. A copy step an agent can forget is precisely how "passes its tests, fails in Glyphs" happens, and #6 found that a broken symlink in `Plugins/` fails silently — no dialog, no log.

The adapter stays deliberately thin, because it is the part nobody can test without quitting Glyphs. Anything that can be moved across the line should be.

Diagnostics follow the same split. The worker thread must marshal every failure back to the UI — an exception on a background thread otherwise vanishes entirely, and ADR-0004 already promises a count at the end of a bulk run. Beyond that, one opt-in debug flag logging to the Macro Panel, off by default: enough for the designer to paste evidence back to a build session, and not a logging framework.

The spec names the round-trip cases the suite must cover — a lenient header normalising on write, all three legal filename shapes, and the `caps-2-DONE-NE.txt` collision — because those are the decisions most likely to be quietly re-litigated by whoever writes the code.

# The palette view is built with vanilla, and the tree is a flat list

ProofBook builds its palette view with `vanilla` rather than a `.xib` loaded through `self.loadNib()`, and renders the proof-book's nested folders as a **flat `List2` whose rows carry a depth**, indented in Python, with expansion state held as a set of folder paths. The decision looks like a dependency trade-off and is not: **vanilla ships no `NSOutlineView` wrapper** — its only hierarchical widget is `vanillaBrowser` (`NSBrowser`, a Finder column browser) — so the tree is hand-wired whichever route is taken, and the routes then separate on everything else.

## Considered options

A `.xib` has no runtime dependency, which is why it looked like the safe route. But its `NSOutlineView` still needs a data source written in Python, so it buys no less work — and it adds an Interface Builder round-trip on top of the full quit-and-relaunch that every plugin edit already costs in Glyphs 4. Plain AppKit in Python keeps the zero-dependency property and was proven to load, but re-implements text fields, buttons, and alerts by hand. Hosting a hand-wired `NSOutlineView` inside a vanilla `Group` would give real disclosure triangles, at the cost of an `NSOutlineViewDataSource` in PyObjC *and* the loss of `List2`'s cell classes, turning the status swatch and owner pill into manual `NSTableCellView` work.

vanilla wins on what it hands over for free: `List2` cell classes for the swatch, subject, and owner pill; `List2`'s `menuCallback` for the context menu that carries most of ProofBook's verbs; and `vanilla.dialogs.ask` for the filename-collision modal. Its dependency is real but not fragile — vanilla is expected of most Glyphs plugins, sits in the Plugin Manager index with no `maxVersion` cap, and can be declared as a dependency if ProofBook is ever distributed.

## Consequences

Glyphs injects vanilla into `sys.path` at runtime, so there is nothing on disk to inspect: a module-scope `try: import vanilla` is the only way to detect its absence, and it must stay at module scope — the SDK calls `settings()` and `start()` unguarded from `PalettePlugin.init`. When the import fails, a small hand-built AppKit view says *Install vanilla via Plugin Manager* instead of Glyphs raising a modal error dialog on every document open. This makes the answer identical for personal use and for distribution.

The flat list keeps one widget vocabulary and one plain row model — a list of rows, legible in a spec and to an agent, which is the transparency the proof-book itself is designed for. It also means folder rows exist in the same list as proof-pages: they toggle expansion and never become the selection, so the selection always names a real proof-page. Very deep or very large proof-books re-render the whole row list on every toggle; that cost is untested and accepted for the MVP.

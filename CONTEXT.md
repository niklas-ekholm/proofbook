# ProofBook

ProofBook is a Glyphs 4 palette plugin for organising the proofs a type designer works through while developing a typeface. It answers a coverage question: has every relevant letter combination, common word, and custom requirement been designed carefully, in every master and interpolation?

## Language

**proof-page**:
A single plain text file holding a manageable set of words or letter combinations — small enough that a designer looking at it can focus.
_Avoid_: proof, page, sample, test, specimen

**proof-book**:
The folder of proof-pages sitting beside a Glyphs file. One proof-book belongs to one font and grows as that font develops.
_Avoid_: proof set, collection, library, suite

**ProofBook**:
The Glyphs 4 palette plugin that browses a proof-book and displays a proof-page in the Edit view.
_Avoid_: the plugin, the tool

**status**:
A proof-page's design progress, one of `todo`, `wip`, or `done`. A proof-page that has never been touched is `todo`.
_Avoid_: state, stage, progress, phase

**annotation**:
A single free-text note attached to a proof-page, written and read in ProofBook's sidebar.
_Avoid_: note, comment, description, label

**Edit view**:
Glyphs' text-editing tab, where a selected proof-page's content is displayed.
_Avoid_: editor window, canvas, edit tab

**coverage**:
The degree to which a typeface's relevant combinations have been designed and reviewed across all masters and interpolations. The reason proof-books exist.
_Avoid_: completeness, testing, QA

**owner**:
The person responsible for a proof-page, identified by their initials. Exactly one per proof-page; a second person working on the same subject owns a separate proof-page.
_Avoid_: author, editor, assignee, creator

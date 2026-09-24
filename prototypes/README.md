# Prototypes

Throwaway artifacts made to answer a wayfinder ticket. Not the plugin.

`palette-sidebar.html` is four palette layouts side by side, made for [#4](https://github.com/niklas-ekholm/proofbook/issues/4). Open it in a browser. It is what ADR-0002's flat list and the row anatomy in spec §4 were argued from, and it answers no question the spec does not already record — keep it as the working, not as a reference.

`row-states.html` answers [#41](https://github.com/niklas-ekholm/proofbook/issues/41): three variants of the palette's rows and coverage bar, switchable with `?variant=A|B|C` and crossed with `?scenario=` so each is judged in bulk as well as sprinkled. Open it in a browser. Once status comes out of the filename ([#43](https://github.com/niklas-ekholm/proofbook/issues/43)) a row can exist before its status does, and three new conditions — placeholder, still-walking, malformed — have to be told apart from each other and from `todo`, which is an answer rather than the absence of one. The variants disagree about *where* that information lives: on the swatch, in the row's typography, or up in the chrome.

The loading skeleton from [#6](https://github.com/niklas-ekholm/proofbook/issues/6) used to live here. [#14](https://github.com/niklas-ekholm/proofbook/issues/14) promoted it to `ProofBook.glyphsPalette/` at the repository root, where it is no longer a throwaway: the repo *is* the installable bundle.

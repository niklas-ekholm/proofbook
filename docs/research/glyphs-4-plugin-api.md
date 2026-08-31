# What is a Glyphs 4 palette plugin, concretely?

Research for ProofBook (issue #2). Established by reading primary sources only; no
Glyphs installation was run.

**Date of research:** 2026-08-29

## Confidence markings

- **CONFIRMED** — established from a Glyphs 4 primary source (the Glyphs 4 handbook, the
  `Glyphs4` branch of the official SDK, the Glyphs 4.0 release notes, or a Glyphs-team post
  about Glyphs 4).
- **INFERRED** — established from a Glyphs 3 primary source, with no Glyphs 4 source
  contradicting it. The Glyphs 4 SDK branch usually also carries the same file unchanged,
  which raises confidence but is not the same as documentation.
- **UNKNOWN** — could not be established.

## Primary sources used

| Short name | URL |
|---|---|
| SDK-G4 | <https://github.com/schriftgestalt/GlyphsSDK/tree/Glyphs4> (branch `Glyphs4`, read at commit `0f5422d`, 2026-07-18) |
| SDK-G3 | <https://github.com/schriftgestalt/GlyphsSDK/tree/Glyphs3> (branch `Glyphs3`) |
| Handbook | <https://handbook.glyphsapp.com/single-page/> — states "Glyphs 4 is a professional Mac application for creating OpenType fonts", i.e. this is the **Glyphs 4** handbook |
| RelNotes | <https://updates.glyphsapp.com/Glyphs4.0-4000.html> ("What's new in Glyphs", Glyphs 4.0) |
| Forum-Migrate | <https://forum.glyphsapp.com/t/updating-python-scripts-and-plug-ins-for-glyphs-4/36793> — "Updating Python scripts and plug-ins for Glyphs 4", by Florian Pircher (Glyphs team), 2026-07-26 |
| News-G4 | <https://glyphsapp.com/news/glyphs-4-create-love-the-process> |
| Tutorial | <https://glyphsapp.com/learn/plugins> ("Writing plug-ins") |
| PkgIndex | <https://raw.githubusercontent.com/schriftgestalt/glyphs-packages/glyphs3/packages.plist> (the live Plugin Manager package index; see Q3) |

A crucial methodological note: **the official SDK has a dedicated `Glyphs4` branch**
(<https://github.com/schriftgestalt/GlyphsSDK/tree/Glyphs4>), alongside `Glyphs3` and a stale
`master`. Diffing `Glyphs3 → Glyphs4` is therefore a direct, first-party statement of what the
Glyphs team changed for Glyphs 4 — this is the strongest evidence available short of running
the app, and much of what follows rests on it.

---

## 1. Plugin type and base class for an Edit-view sidebar panel

**CONFIRMED — Palette plug-ins survive Glyphs 4 unchanged in name, type and base class.**

The Glyphs 4 handbook lists six plug-in types and describes them thus:

> Palette plug-ins (`.glyphsPalette`) add entries to the Palette (Window → Palette). See
> Palette for details.
>
> — Handbook, "Plug-ins" section

And the Palette itself:

> Open the Palette sidebar with the sidebar button in the top-right corner of the window, or
> choose Window → Palette (Cmd-Opt-P). Glyphs includes four sections: Dimensions, Fit Curve,
> Layers, and Transformations. **Plug-ins can add additional sections to the Palette.**
>
> — Handbook, "Palette" section

So: the plugin type is a **Palette plug-in**, bundle suffix **`.glyphsPalette`** (note: *not*
`.glyphsPlugin` — that suffix is reserved for General plug-ins), and it appears as a
collapsible section in the right-hand sidebar shared by Edit View and Font View.

The Python base class is **`PalettePlugin`**, imported from `GlyphsApp.plugins`. In the
`Glyphs4` branch the template is:

```python
from GlyphsApp import Glyphs, GSEditViewController, UPDATEINTERFACE
from GlyphsApp.plugins import PalettePlugin

class ____PluginClassName____ (PalettePlugin):
    dialog = objc.IBOutlet()
    ...
```

— SDK-G4, `Python Templates/Palette/____PluginName____.glyphsPalette/Contents/Resources/plugin.py`

`PalettePlugin` subclasses the Objective-C class `BasePalettePlugin`, looked up at runtime
(`objc.lookUpClass("BasePalettePlugin")`) — SDK-G4,
`ObjectWrapper/GlyphsApp/plugins.py`.

### Did Glyphs 4 rename, replace or restructure it? No.

Diffing the SDK's `Glyphs3` branch against its `Glyphs4` branch for the whole Palette template:

```
 ObjectWrapper/GlyphsApp/plugins.py       | 602 +++++++++++--------- (type annotations)
 .../Palette/.../Contents/Info.plist      |   6 -                    (see Q2)
```

`Python Templates/Palette/README.md`, `plugin.py` and `IBdialog.xib` are **byte-identical**
between the two branches. Within `plugins.py`, the `PalettePlugin` class diff is entirely
PEP-484 type annotations, defensive `return 0` / `return None` fallbacks, `round()` on the
height getters, and two corrected PyObjC selector signatures
(`setCurrentHeight_` went from `b'@::L'` to `b'v@:L'`). **No method was added, removed or
renamed.** The lifecycle is still `settings()` → `start()` → `__del__()`, and the plugin still
exposes `title()`, `sortID()`, `theView()`, `minHeight()`, `maxHeight()`,
`currentHeight()`/`setCurrentHeight_()`, `windowController()`/`setWindowController_()`.

Corroborating, the Objective-C/Swift side of the Glyphs 4 SDK still declares the protocol
`GlyphsPalette` with the same members (`interfaceVersion`, `loadPlugin`, `minHeight`,
`maxHeight`, `currentHeight`, `theView`, `windowController`) — SDK-G4,
`Xcode Templates/Glyphs Dev/Glyphs Palette Plugin.xctemplate/___PACKAGENAMEASIDENTIFIER___.swift`.
(New in the Glyphs 4 branch: a Swift variant of the Xcode template alongside the ObjC one.)

And the Glyphs team's own migration guide opens with:

> Many scripts and plug-ins continue to run in Glyphs 4 just as they did in Glyphs 3. However,
> some code needs to be updated to work in Glyphs 4 as well.
>
> — Forum-Migrate

Its list of required changes contains **nothing about palette or plugin base classes** (see Q5
for what it does contain).

**Verdict for the spec:** ProofBook is a `.glyphsPalette` bundle whose principal class
subclasses `GlyphsApp.plugins.PalettePlugin`. This is safe to write against.

---

## 2. Bundle layout and required `Info.plist` keys

**CONFIRMED** (layout and keys read directly from the Glyphs 4 SDK template).

Layout of `Python Templates/Palette/____PluginName____.glyphsPalette/` on SDK-G4:

```
____PluginName____.glyphsPalette/
└── Contents/
    ├── Info.plist
    ├── MacOS/
    │   └── plugin              (prebuilt binary loader, shipped by the SDK; do not write it)
    └── Resources/
        ├── plugin.py           (your code)
        ├── IBdialog.xib        (source)
        └── IBdialog.nib        (compiled; what actually gets loaded)
```

`Info.plist` on the `Glyphs4` branch, verbatim key set:

```xml
<key>CFBundleDevelopmentRegion</key>   <string>en</string>
<key>CFBundleExecutable</key>          <string>plugin</string>
<key>CFBundleIdentifier</key>          <string>com.____Developer____.____PluginClassName____</string>
<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
<key>CFBundleName</key>                <string>____PluginName____</string>
<key>CFBundleShortVersionString</key>  <string>____BundleVersionString____</string> <!-- 1.0 -->
<key>CFBundleVersion</key>             <string>____BundleVersion____</string>       <!-- 123 -->
<key>NSHumanReadableCopyright</key>    <string>Copyright, ____Developer____, ____YEAR____</string>
<key>NSPrincipalClass</key>            <string>____PluginClassName____</string>
<key>PyMainFileNames</key>             <array><string>plugin.py</string></array>
```

The two load-bearing, Glyphs-specific keys are:

- **`NSPrincipalClass`** — the name of your Python class. Must match the class in `plugin.py`,
  must be unique across all installed plugins, and ASCII-only (Tutorial).
- **`PyMainFileNames`** — an array naming the Python file(s) to execute. On the Glyphs 3 and 4
  branches this is `plugin.py` (a `Resources`-relative name). On the ancient `master` branch it
  was `../MacOS/main.py` with a `main.py` shim; that shim and the `PkgInfo` file were already
  gone by the `Glyphs3` branch. **Do not copy the `master`-branch layout.**

The `Glyphs3 → Glyphs4` Info.plist diff removes exactly four keys:

```
-  <key>UpdateFeedURL</key>          <string>____OnlineUrlToThisPlist____</string>
-  <key>productPageURL</key>         <string>____ProductPageURL____</string>
-  <key>productReleaseNotes</key>    <string>____LatestReleaseNotes____</string>
```
(`UpdateFeedURL`, `productPageURL`, `productReleaseNotes` — the old self-update mechanism.)
Distribution metadata now lives in the Plugin Manager package index instead (Q3/Q8).

Additionally, RelNotes records a new capability: **"Min/MaxSystemVersion for plugins" (3824)**
— i.e. Glyphs 4 can read min/max *macOS* version keys from a plugin. The exact key names are
**UNKNOWN**; not needed for ProofBook.

Glyphs 3.2 and later allow **multiple plug-in classes in one `.glyphsPlugin` bundle** so they
can share resources (Tutorial). Not contradicted for Glyphs 4, but ProofBook needs only one
class, so this is out of scope.

---

## 3. Which Python, and how third-party modules reach a plugin

**CONFIRMED — Glyphs 4 requires Python 3.14 (or later) and drops 3.11/3.12.**

> Glyphs 4 supports Python 3.14 and later.
>
> — Forum-Migrate (Glyphs team)

Release notes corroborate and add nuance:

- "Add Python 3.14 compatibility" (build 3840)
- "Drop support for python 3.11 and 3.12" (3854)
- "Properly fix loading of python (still supporting python 3.13–3.15)" (3861)

— RelNotes

This is a real break with Glyphs 3, which is pinned at 3.11 by design:

> If I'll update the GlyphsPython for Glyphs 3, it would make it difficult to run older
> versions of Glyphs 3 … So the python version is stuck. But … you can make different versions
> of your plugins for Glyphs 3 and 4 and add both to the package file.
>
> — Georg Seifert (Glyphs developer), Forum-Migrate

The package index confirms the split mechanically: the `Python` module entry with
`minVersion = "3800"` points at `GlyphsPython/releases/download/**python-3.14**/GlyphsPython.zip`,
while the `py311` entry is capped at `maxVersion = "3799"` (PkgIndex). **Glyphs 4 builds are
3800 and up; Glyphs 3 is ≤ 3799.**

### Third-party modules (e.g. `vanilla`)

**CONFIRMED — same mechanism as Glyphs 3: the Plugin Manager's Modules tab.**

> Some plug-ins require specific modules to be installed; install these from the Modules tab in
> the Plugin Manager.
>
> — Handbook, "Installing Plug-ins"

> Glyphs needs to be relaunched for newly installed plug-ins and modules to be available.
>
> — Handbook, "Plugin Manager"

Modules install into the user's Glyphs *Scripts* folder (the index entry gives
`path = "Lib/vanilla"` from `https://github.com/schriftgestalt/vanilla`), which is on the
plugin's import path.

Two Glyphs-4-specific facts about `vanilla`:

- Its package-index entry carries **no `maxVersion`** (PkgIndex), unlike `RoboFab` and the
  `py311` Python runtime which are both capped at `3799`. So `vanilla` is offered to Glyphs 4.
- The Glyphs 4 SDK ships **type stubs for vanilla** at `ObjectWrapper/typing/vanilla/` — a
  first-party signal that vanilla is a supported dependency in Glyphs 4.
- RelNotes: "Improve installation of modules from the Pluging Manager" (3869).

**Risk for the spec:** ProofBook must not *assume* vanilla is present. It is a user-installed
module, and a fresh Glyphs 4 install has neither Python nor vanilla until the user visits
Plugin Manager → Modules. If ProofBook depends on vanilla, its package-index entry and its
README must say so, and it should fail with a legible message rather than a traceback.

### Type checking (nice-to-have, Glyphs 4 only)

Glyphs 4 ships `.pyi` stubs for Pylance/pyright. Recommended `extraPaths` (Forum-Migrate):

```
/Applications/Glyphs 4.app/Contents/Scripts/typing/
/Applications/Glyphs 4.app/Contents/Scripts/GlyphsApp/
/Applications/Glyphs 4.app/Contents/Scripts/
~/Library/Application Support/Glyphs 4/Scripts/
```

These paths are themselves a first-party confirmation of the Glyphs 4 on-disk layout — see Q8.

---

## 4. Building the palette view; height, resizing, stacking

**CONFIRMED — still AppKit `NSView`, via a compiled `.nib` or via vanilla. Nothing new.**

The plugin's job is to hand Glyphs one `NSView`. `PalettePlugin.theView()` simply returns
`self.dialog` (SDK-G4, `plugins.py`). Two documented ways to populate `self.dialog`:

**(a) Interface Builder / `.xib`.** In `settings()`:

```python
self.loadNib('IBdialog', __file__)
self.dialog.setController_(self)
```

— SDK-G4 Palette `plugin.py`. `IBOutlet`s on the class connect to controls in the nib; the
`.xib` must be compiled to `.nib` (the SDK includes a `Compile .xib to .nib.app` helper under
`Python Templates/`).

**(b) vanilla.** From the Glyphs 4 SDK Palette README verbatim:

> We need to create a so called Group that contains a set of objects. Of this group, we can get
> hold of the wrapped `NSView` object to display in Glyphs. Note that due to Vanilla internals,
> we have to create a window first, although that window isn't getting any attention anymore
> later on, and it must contain a `Group()` of the same size. Note that stretching the `Group`
> to the far corners of the windows using `(0, 0, -0, -0)` may not work, so explicitly define
> its size identical to the containing window.
>
> Make sure that the `.dialog` gets defined in the `settings()` class, not at the class root.

```python
self.paletteView = Window((width, height))
self.paletteView.group = Group((0, 0, width, height))
self.paletteView.group.text = TextBox((10, 0, -10, -10), self.name, sizeStyle='small')
self.dialog = self.paletteView.group.getNSView()
```

— SDK-G4, `Python Templates/Palette/README.md` (identical to the Glyphs3 branch)

Note this snippet in the SDK is mislabelled `class ____PluginClassName____(SelectTool)`; that
is a copy-paste error in the official README, present on both branches. For a palette it should
be `(PalettePlugin)`.

**Is there something new in Glyphs 4?** No SwiftUI or declarative path appears anywhere in the
`Glyphs4` SDK branch. The Swift Xcode template is a plain `NSViewController` loading a `.xib`
whose root view is a `GSPaletteView`. **UNKNOWN** whether a SwiftUI-hosted view would work
(`NSHostingView` is just an `NSView`, so it plausibly would, but nothing documents it).

### Height, resizing, stacking

- **Height is declared by the plugin**, in points, via `minHeight()` and `maxHeight()`. If you
  don't set `self.min`/`self.max` in `settings()`, `PalettePlugin.init()` derives both from the
  loaded view's frame height, i.e. **fixed height by default** (SDK-G4 `plugins.py`).
- **Resizable iff `maxHeight > minHeight`.** The Swift template says so outright:
  `var maxHeight: Int { return 265 } // if this is bigger than minHeight, the palette is resizable`.
  The Python template's comment agrees: `return 85 # change this to something bigger to enable
  manually resizing of the palette`.
- **The user's resize is persisted by the plugin itself**, in `NSUserDefaults` under the key
  `"<self.name>.ViewHeight"` — `currentHeight()` / `setCurrentHeight_()` in SDK-G4
  `plugins.py`. Note the key is derived from the palette's *localized display name*, which is a
  latent bug if the name is localized; ProofBook should override these to use a stable key.
- **Programmatic resize** (documented in the SDK Palette README): add a height layout constraint
  in the `.xib`, expose it as an outlet, then `self.heightConstraint.setConstant_(height)` or
  `self.heightConstraint.animator().setConstant_(height)` to animate.
- **Stacking order** in the sidebar is influenced by `sortID()`, which returns `self.sortId`
  (default `0`) — SDK-G4 `plugins.py`. How Glyphs 4 breaks ties between equal `sortId`s, and
  whether the user can reorder sections, is **UNKNOWN**.
- Sections are individually collapsible: "Collapse or expand a section by clicking the chevron
  on the left side of the section name" (Handbook, "Palette").
- Vertical space in the Glyphs 4 sidebar is contested. Florian Pircher, on the Glyphs 4 sidebar
  design: users with "small screens or many plug-in palettes" treat "vertical space [as] a
  premium" — <https://forum.glyphsapp.com/t/glyphs-4-text-preview-and-right-sidebar/36761>.
  **Design consequence for ProofBook:** default to a small `minHeight`, make it resizable, and
  do not assume the panel is visible or expanded.

---

## 5. Setting the Edit view's text

**CONFIRMED — `tab.text` and `font.newTab(text)` are unchanged in Glyphs 4.**

From the Glyphs 4 branch of the object wrapper:

```python
GSEditViewController.text = property(
    lambda self: self.graphicView().displayString_(GSFormatVersionCurrent),
    lambda self, value: self.graphicView().setDisplayString_(value)
)
```
> The text of the tab, either as text, or slash-escaped glyph names, or mixed. OpenType
> features will be applied after the text has been changed.

```python
def __GSFont__addTab__(self, tabText=""):
    if self.parent:
        if isString(tabText):
            return self.parent.windowController().addTabWithDisplayString_(tabText)
        else:
            return self.parent.windowController().addTabWithLayers_(tabText)
    return None
GSFont.newTab = python_method(__GSFont__addTab__)
```

```python
GSFont.currentTab = property(
    lambda self: self.parent.windowController().activeEditViewController(),
    lambda self, value: self.parent.windowController().tabBarControl().selectTabItem_(value)
)
```

— all SDK-G4, `ObjectWrapper/GlyphsApp/__init__.py`

The **setter** for `text` is byte-identical to Glyphs 3 (`setDisplayString_`). The **getter**
changed internally from `displayStringASCIIonly_(False)` to `displayString_(GSFormatVersionCurrent)`,
but the public property signature and semantics are the same. `newTab` and `currentTab` are
identical to the Glyphs 3 branch.

So the ProofBook operation — "show this proof page in the Edit view" — is, in Glyphs 4:

```python
font.currentTab.text = page_text          # reuse the active tab
# or
tab = font.newTab(page_text)              # open a new tab
```

Two Glyphs-4 deltas that touch this area:

- **Redraw:** `tab.forceRedraw()` is gone. Use `tab.redraw()`:
  ```python
  if Glyphs.versionNumber >= 4.0:
      tab.redraw()
  else:
      tab.forceRedraw()
  ```
  — Forum-Migrate. `redraw` is listed among `GSEditViewController`'s functions in SDK-G4.
- **Text selection API additions** (`.. versionadded:: 4` in SDK-G4): `selectedTextRange`,
  `layersRange`, `selectedLayerRange` on `GSEditViewController`. Useful later if ProofBook wants
  to know where the cursor is in a proof page.

**Caveat for a palette specifically:** do not reach for `Glyphs.font`. See Q6.

---

## 6. Reading the open font's file path; save / close / switch

### File path — INFERRED (Glyphs 3 source, unchanged on the Glyphs 4 branch)

```python
def __GSFont_filepath__(self):
    if self.parent is not None and self.parent.fileURL() is not None:
        return self.parent.fileURL().path()
    else:
        return self.tempData["filePath"]
GSFont.filepath = property(lambda self: __GSFont_filepath__(self))
```
> **filepath** — On-disk location of GSFont object. :type: str

— SDK-G4 `__init__.py`; identical to the `Glyphs3` branch. Also available:
`GSDocument.filePath` (typed `Optional[str]`).

`filepath` is `None` for a never-saved font. **ProofBook must handle that**: an unsaved document
has no folder to look for proof-pages beside.

### Getting *the right* font from inside a palette — CONFIRMED (SDK-G4 README)

This is the single most important correctness point for a palette plugin, and the Glyphs 4 SDK
states it emphatically:

> `self.windowController()` returns the current window controller. Use
> `self.windowController().document().font` to drill down to the font which is open in the same
> window as the palette. In order to prevent a crash, make sure you always check that neither
> the window controller nor the font is `None`.
>
> **Never** use `Glyphs.currentDocument` to access the font as that would only work with one
> open font.
>
> — SDK-G4, `Python Templates/Palette/README.md`

```python
windowController = self.windowController()
if windowController:
    thisFont = windowController.document().font
    if thisFont:
        ...
```

Each open document window gets its **own instance** of the palette plugin. `Glyphs.font` /
`Glyphs.currentDocument` are global and will give the wrong font. ProofBook's proof-page folder
is derived per-window from `windowController().document().font.filepath`.

### Save / close / switch — CONFIRMED (constants present and documented on the Glyphs 4 branch)

Registered with `Glyphs.addCallback(fn, CONSTANT)` and torn down with `Glyphs.removeCallback(fn)`.
From SDK-G4 `__init__.py` (both the constant values and the docstrings):

| Constant | Notification name | Documented meaning |
|---|---|---|
| `DOCUMENTOPENED` | `GSDocumentWasOpenedNotification` | "is called if a new document is opened" |
| `DOCUMENTACTIVATED` | `GSDocumentActivateNotification` | "is called when the document becomes the active document" |
| `DOCUMENTWASSAVED` | `GSDocumentWasSavedSuccessfully` | "is called when the document is saved. The document itself is passed in `notification.object()`" |
| `DOCUMENTEXPORTED` | `GSDocumentWasExportedNotification` | `notification.object()` is the path to the final font file |
| `DOCUMENTWILLCLOSE` | `GSDocumentWillCloseNotification` | "just before a document will be closed"; info object is the `GSWindowController` |
| `DOCUMENTDIDCLOSE` | `GSDocumentDidCloseNotification` | "after a document was closed"; info object is the `NSDocument` |
| `DOCUMENTCLOSED` | (alias of `WILLCLOSE`) | **deprecated since 3.0.4** — use `DOCUMENTWILLCLOSE` |
| `TABDIDOPEN` / `TABWILLCLOSE` | `TabDidOpenNotification` / `TabWillCloseNotification` | tab opened / closed |

Mapping to ProofBook's needs:

- **saved** → `DOCUMENTWASSAVED` (and re-read `filepath`, since a Save As moves the folder).
- **closed** → `DOCUMENTWILLCLOSE`, not the deprecated `DOCUMENTCLOSED`.
- **switched** → `DOCUMENTACTIVATED`. But note a palette instance is bound to one window, so
  "switching" is often better handled by simply re-reading `self.windowController()` on each
  update rather than by chasing activation events.
- **first appearance** → `DOCUMENTOPENED`.

**Mandatory teardown.** The SDK is blunt: "Delete callbacks when Glyphs quits, otherwise it'll
crash :(" — remove every callback in `__del__()` (SDK-G4 Palette README and `plugin.py`).

---

## 7. Observing selection and document changes

**CONFIRMED — `UPDATEINTERFACE` remains the mechanism, with the same warning.**

```python
@objc.python_method
def start(self):
    Glyphs.addCallback(self.update, UPDATEINTERFACE)

@objc.python_method
def __del__(self):
    Glyphs.removeCallback(self.update)
```

`UPDATEINTERFACE` = `"GSUpdateInterface"`, documented in SDK-G4 as: *"if some thing changed in
the edit view. Maybe the selection or the glyph data."*

The SDK-G4 Palette README's own caution, verbatim:

> For displaying information, you would typically use callbacks that tie in with events being
> fired in Glyphs.app, such as the `GSUpdateInterface` event, which gets fired each time
> anything is being redrawn in the user interface. This can happen quite often, so be careful as
> to how complicated your code becomes.

The canonical `update(sender)` handler pattern, from the Glyphs 4 template:

```python
@objc.python_method
def update(self, sender):
    currentTab = sender.object()
    if isinstance(currentTab, GSEditViewController):   # Edit View
        layer = currentTab.activeLayer()
        ...
    else:                                              # Font View
        currentTab.selectedLayers
```

— SDK-G4 Palette `plugin.py`

**Direct implication for ProofBook:** `UPDATEINTERFACE` fires on every redraw. Do **not** stat
or read the proof-pages folder from inside it. Cache the folder listing, refresh it on
`DOCUMENTWASSAVED` / `DOCUMENTACTIVATED` / an explicit refresh button, or on an `NSTimer` or
FSEvents watcher — but not per redraw.

Other callbacks available in Glyphs 4 (SDK-G4 `__all__`): `MOUSEMOVED`, `MOUSEDRAGGED`,
`MOUSEDOWN`, `MOUSEUP`, `CONTEXTMENUCALLBACK`, `UPDATEEDITVIEWFRAME`, `FILTER_FLAT_KERNING`,
plus the drawing hooks. RelNotes adds two new Glyphs 4 hooks: `showUnicodeInfo:` (3869) and a
"preview drawing callback" (3854) — neither relevant to ProofBook.

---

## 8. Development loop

### Where plugins install from and live

**CONFIRMED — Glyphs 4 uses a versioned Application Support folder, `Glyphs 4`.**

The Glyphs team's own recommended pyright paths include
`~/Library/Application Support/**Glyphs 4**/Scripts/` and `/Applications/**Glyphs 4.app**/`
(Forum-Migrate). The handbook states "The Plugins folder is located next to the Scripts folder",
so the plugins folder is:

```
~/Library/Application Support/Glyphs 4/Plugins/
```

**Marked CONFIRMED for the parent path `Glyphs 4`, INFERRED for the `/Plugins` leaf** — the
handbook describes the Plugins folder only relative to the Scripts folder and never prints the
absolute path. (The Glyphs 3 path was `~/Library/Application Support/Glyphs 3/Plugins`; the
older tutorial page at glyphsapp.com/learn/plugins still says
`~/Library/Application Support/Glyphs/Plugins`, which is Glyphs 2 vintage and stale.)

Installation, per the Glyphs 4 handbook:

> Install plug-ins from the Plugin Manager with a single click. … Manually install a plug-in by
> dragging and dropping it onto the Glyphs app icon in the Dock. Installed plugins are moved to
> the Plugins folder. **Do not manually move plug-ins to the Plugins folder since that interferes
> with the security system of the Mac.** … Uninstall a plug-in by deleting it from the Plugins
> folder.

That warning is a genuine constraint on a dev loop: the sanctioned way to install a
locally-built `.glyphsPalette` is drag-onto-Dock-icon, not `cp` into the folder.

### Reloading without restarting

**Sources conflict. Treat "no restart" as UNCONFIRMED.**

- Handbook (Glyphs 4), "Installing Plug-ins": *"Plug-ins are loaded when Glyphs launches, so
  Glyphs needs to be relaunched for newly installed plug-ins to be loaded."*
- Handbook (Glyphs 4), "Plugin Manager": *"Glyphs needs to be relaunched for newly installed
  plug-ins and modules to be available. Newly installed **scripts** can be loaded without
  relaunching Glyphs by holding down the Option key and choosing Script → Reload Scripts
  (Cmd-Opt-Shift-Y)."* — i.e. the script reload gesture explicitly does **not** extend to plugins.
- News-G4 (marketing page for Glyphs 4): *"Many plug-ins now install instantly, without the need
  to restart."*

The two are reconcilable if the news page means *installation* of Plugin-Manager plugins rather
than *reloading edited code*, but that is inference, not documentation. **For the spec, assume a
relaunch is needed after editing plugin code.**

Two mitigations, both from primary sources:

- **Symlink/alias trick.** Georg Seifert (Glyphs developer):
  > I put an alias to the plugin into the Plugin folder. Then you don't need to reinstall. Then
  > hold Opt key and right click on the app icon and "Force Quit" and another normal click on
  > the app icon. So restarting takes only a few seconds. If you are working on an algorithm,
  > you can put the code in a script as that doesn't need a restart.
  >
  > — <https://forum.glyphsapp.com/t/develop-plugins-without-restarting/11592> (2019; Glyphs 2
  > era, so **INFERRED** for Glyphs 4, and it may now collide with the handbook's
  > "do not manually move plug-ins" warning)
- **Edit plugin code in the app.** News-G4, describing the redesigned Scripting window:
  *"The window allows you to edit any Python code in every installed script and plug-in!"* — plus
  breakpoints and step-through debugging, and installable `ruff` / `pyright`. Whether editing
  there also *reloads* the plugin is **UNKNOWN**.

A practical corollary: prototype ProofBook's folder-scanning and text-setting logic as a plain
`.py` **script** first (scripts reload with Cmd-Opt-Shift-Y and need no restart), then move the
proven logic into the palette bundle.

### Where errors and `print()` output go

**CONFIRMED (Glyphs 4 handbook).**

> **Console Output** — "Use system console for script output" directs the log output of plug-ins
> and scripts to the system console instead of the Macro Panel console (Window → Macro Panel,
> Cmd-Opt-M). Select this option for debugging a plug-in or script when the Macro Panel is
> inaccessible.
>
> — Handbook, Settings → Addons

So: **`print()` and tracebacks go to the Macro Panel** (Window → Macro Panel, Cmd-Opt-M) by
default, and can be redirected to the **system console** (Console.app) with a setting in
Settings → Addons. The latter is the one to use while debugging plugin *startup*, since a
plugin that fails during `init()`/`settings()` may crash before the Macro Panel is usable.

Note the naming drift in Glyphs 4: News-G4 calls it the "Scripting window (⌘⌥M)" while the
handbook calls it the "Macro Panel (Cmd-Opt-M)". Same shortcut, so almost certainly the same
window renamed.

`PalettePlugin` also gets `self.logToConsole(...)` and `self.logError(...)` helpers attached as
class extensions (SDK-G4 `plugins.py`), and Glyphs 4 adds an "Error dialog for crashed plugins"
(RelNotes 3845).

### Distribution (for later)

Glyphs 4 plugins are listed in the same package index as Glyphs 3 ones, gated by build number:

> For now, both Glyphs 3 and Glyphs 4 use the same index with min/max version guards.
>
> — Florian Pircher, Forum-Migrate

`minVersion` / `maxVersion` take the **build number** (Glyphs 4 = 3800+). Newer entries use
`archiveURL` (a stable zip URL) instead of git cloning; the server must answer GET and HEAD,
send an `ETag`, and honour `If-None-Match` with a 304 (Forum-Migrate). Note the live index
appears to be the **`glyphs3` branch** of `schriftgestalt/glyphs-packages`, not `master` —
`master` is a much older, smaller file with no `scripts`/`modules` sections.

---

## Risks and open questions

Things the ProofBook spec **cannot** safely assume:

1. **Plugins folder leaf path is inferred, not documented.**
   `~/Library/Application Support/Glyphs 4/` is confirmed from a Glyphs-team post; the `/Plugins`
   subfolder name is inferred from the handbook's "next to the Scripts folder". Verify in
   ticket #6.

2. **Reload-without-restart is contradicted between sources.** The Glyphs 4 handbook says a
   relaunch is required; the Glyphs 4 marketing page says many plugins install without restart.
   Plan the dev loop around a restart, and treat anything faster as a bonus. Also unresolved:
   whether the redesigned Scripting window's "edit any Python code in every installed plug-in"
   also reloads it.

3. **"Do not manually move plug-ins to the Plugins folder"** (Glyphs 4 handbook) conflicts with
   the long-standing developer practice of symlinking a build into that folder. Unclear whether
   the macOS security system objects to a symlink, or only to a copied bundle. Untested.

4. **No published Glyphs 4 Python API documentation site yet, confirmed as an open question by
   users.** <https://forum.glyphsapp.com/t/glyphs-4-python-api-documentation/37021> asks "Is
   there already an API Documentation for Glyphs 4? If not, when will it be released?" and, at
   time of reading, has no answer. `docu.glyphsapp.com` does contain "Added in version 4.1"
   markers, so it appears to be tracking Glyphs 4, but it does not state which version it
   targets and offers no version selector. **The docstrings inside the SDK `Glyphs4` branch are
   the more reliable reference**, and are what this document cites.

5. **Palette keyboard shortcut is self-contradictory in the Glyphs 4 handbook**: the "Palette"
   chapter says Cmd-Opt-P, the "Plug-ins" chapter says Cmd-Shift-P. Cosmetic, but a reminder
   that the handbook has not been fully re-checked for Glyphs 4.

6. **The official SDK Palette README contains a copy-paste error** — its vanilla example
   declares `class ____PluginClassName____(SelectTool)` in a Palette document. Present on both
   the Glyphs3 and Glyphs4 branches. Do not copy it verbatim.

7. **`currentHeight` persistence key is derived from the localized palette name**
   (`self.name + ".ViewHeight"`). If ProofBook ever localizes its name, saved heights are lost or
   collide. Override `currentHeight`/`setCurrentHeight_` with a stable key.

8. **`sortID` tie-breaking and user reordering are undocumented.** We cannot promise where in the
   sidebar stack ProofBook lands.

9. **SwiftUI / `NSHostingView` in a palette is untested and undocumented.** Nothing in the
   Glyphs 4 SDK suggests it is supported; nothing forbids it. Assume `.xib` or vanilla.

10. **Python 3.11 vs 3.14 is a hard fork for compatibility.** A single bundle can target both
    only if its code runs on 3.11 *and* 3.14 and avoids every API listed in Forum-Migrate. The
    Glyphs team's own recommendation is to ship **separate Glyphs 3 and Glyphs 4 builds** guarded
    by `minVersion`/`maxVersion`. ProofBook should decide early whether it is Glyphs-4-only.

11. **`vanilla` is not guaranteed present.** It is a user-installed module. Whether the ProofBook
    palette uses vanilla or a `.xib` is therefore a real dependency decision, not just a style
    one. (A `.xib` has no runtime dependency beyond Python itself.)

12. **`font.filepath` is `None` for an unsaved document**, so ProofBook has no proof-pages folder
    to resolve. The spec needs a defined empty state for this.

13. **Not verified by running anything.** Every claim here is from reading. In particular, the
    behaviour of `UPDATEINTERFACE` firing frequency, the actual crash-on-missing-`removeCallback`
    claim, and whether one palette instance really exists per window were all read, not observed.
    Ticket #6 should confirm.

14. **Documentation is silent on** whether a palette can be programmatically shown/expanded, and
    on how a palette behaves in the Font View window versus the Edit View window (the template
    handles both in `update()`, implying a single sidebar shared across views — but this is not
    stated).

### Sources that were checked and found unhelpful

- <https://glyphsapp.com/learn/plugins> ("Writing plug-ins" tutorial) — still describes the
  Glyphs 2-era path `~/Library/Application Support/Glyphs/Plugins` and makes no mention of
  Glyphs 4. **Stale; do not cite for paths.**
- The SDK `master` branch — predates Glyphs 3; its Palette `Info.plist` still uses the
  `../MacOS/main.py` shim and a `PkgInfo` file. **Do not use as a template.**
- <https://forum.glyphsapp.com/t/plugins-not-working-in-glyphs-4/36899> — reports crashes from
  several third-party plugins under Glyphs 4, with the reply that "They are being gradually
  updated to G4." Confirms churn exists but names no API cause.
- <https://github.com/thierryc/glyphs3-to-glyphs4-skill> (announced at
  <https://forum.glyphsapp.com/t/looking-for-testers-a-glyphs-3-glyphs-4-plug-in-migration-skill/36801>)
  — a **community**, not first-party, agent skill for auditing G3→G4 plugin migrations. Listed
  here only as a pointer; its checklist (bundle metadata, PyObjC selectors/decorators/outlets,
  lifecycle methods, hard-coded Glyphs 3 paths) is a reasonable independent corroboration of
  which areas move, but none of its claims were relied on above.

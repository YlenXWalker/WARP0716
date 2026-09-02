# Standalone Item Collection patch

Target client: 2025-07-16 Ragexe.

Select these patches in this order:

1. `Enable Item Collection UI (Standalone QJS-only)`
2. `Item Collection Stock Menu Button`

The first patch owns the native 760x540 window, search edit control, dynamic
item art, category filtering, scroll/selection input, and COUI transport. The
second adds an independent launcher beside the stock menu and prompts for New
UI or Classic icon styling. Neither patch selects or requires RO Global UI,
Auto Hunt, or AutoCombat.

Empty Item or Combo filter results are explicitly rejected before the
decrementing selection loop. This prevents the former Ready-filter crash where
`rowCount=0` underflowed to `0xFFFFFFFF` while scanning 400-byte combo
rows.

The client contract is a fixed 64-byte `0x0BF8` request with `COUI` magic
and a variable-length `0x0BEF` authoritative snapshot. Deploy the separate
rAthena Item Collection source patch and SQL schema on the server; the client
contains no collection authority or direct database access.

When asset copying is enabled, fixed BMPs are installed below
`data/texture/�����������̽�/item_collection/` and the launcher states below
`uirenewal/menuicon/`. Runtime item art continues to resolve through
`collection/<identified-resource>.bmp`, then the stock
`item/<identified-resource>.bmp`, then the packaged fallback.
While a schema-changing snapshot is pending, the window draws the supplied
166x124 `chrome/loading.bmp` NOW LOADING frame. The matching
`nowloading.act` and `nowloading.spr` sources are staged and deployed
unchanged; the QJS-owned frame intentionally uses the static BMP safety path.

Deterministic validation:

```powershell
.\win32\WARP_console.exe -using .\profiles\item_collection_standalone_test.yml
.\tools\verify_item_collection_standalone.ps1
```

The build/profile gate proves patch application and PE structure. Final
acceptance still requires live checks for Classic/New launcher placement,
open/close, search focus, mouse scrollbar drag, item selection without
flicker, mutations, relog persistence, and clean exit.

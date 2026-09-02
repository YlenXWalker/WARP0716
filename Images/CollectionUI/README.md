# Item Collection UI assets

Production bitmap pack for the accepted white standalone Item Collection UI.

Fixed chrome and controls deploy to
`data\texture\À¯ÀúÀÎÅÍÆäÀÌ½º\item_collection\`. Dynamic 75x100 item
art remains in the existing `collection\<identified-resource>.bmp`
namespace and is never copied or renamed by this patch.

Ten supplied menu-button files deploy to
`data\texture\À¯ÀúÀÎÅÍÆäÀÌ½º\uirenewal\menuicon\`: 45x41 New UI and
32x34 Classic BMPs. The native button consumes normal, mouse-on, and pressed;
base, disabled, and press aliases are retained for compatibility.

## Target

- Native logical window: 760×540.
- Fits an 800×600 client with 20 px horizontal and 30 px vertical clearance.
- All dynamic collection artwork is drawn 1:1 at 75×100.
- Game assets are 24-bpp, uncompressed `BI_RGB` BMPs.
- Exact `#FF00FF` is the color key for irregular controls/icons. Opaque body, title, and card art are never color-keyed.

## Collection-owned assets

| Asset | Size | Purpose |
|---|---:|---|
| `chrome/title_bar_760.bmp` | 760×17 | Approved AutoHunt title bar, extended only through its repeat-safe center. |
| `chrome/bg_collection.bmp` | 760×523 | White opaque body with native blue-gray edge. |
| `chrome/loading.bmp` | 166×124 | Safe static NOW LOADING frame displayed while a snapshot is pending. |
| `chrome/nowloading.act/.spr` | Source pair | Supplied native animation sources staged for provenance; runtime uses the BMP safety frame. |
| `icons/icon_collection.bmp` | 16×16 | Title icon. |
| `icons/badge_locked.bmp` | 16×16 | Missing-card semantic overlay. |
| `icons/badge_complete.bmp` | 16×16 | Completed-item semantic overlay. |
| `icons/category_*.bmp` | 16×16 / 24×24 | Native item-category selector icons for all 15 supported families. |
| `menuicon/bt_itemcollection*.bmp` | 45×41 / 32×34 | User-approved Item Collection states and compatibility aliases for New UI and Classic. |

Rebuild the collection-owned chrome/badges and validate the staged native
category icons with:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\tools\build_collection_ui_assets.ps1
powershell.exe -ExecutionPolicy Bypass -File .\tools\build_item_collection_menu_buttons.ps1
```

The build also writes `preview/contact-sheet.png` and validates every BMP as 24-bpp RGB.

## Reused assets

`reused/` contains byte-identical copies of stock controls selected for production use:

- blank four-state, horizontally tileable generic buttons;
- four-state close button;
- search edit background and four-state magnifier button;
- scrollbar track/thumb/arrows;
- three-state plus/minus steppers;
- Zeny icon;
- optional native completion ribbon;
- native 75×100 missing-art fallback.

`reused/PROVENANCE.md` records the exact loose/GRF source for every copied file. Button text such as Deposit, Withdraw, Activate Bonus, Submit, tabs, and filters is deliberately not baked into BMPs.

## Runtime contract

Item art is resolved without a manual image table:

```text
ItemId
  -> CItemInfoManager
  -> identified resource stem
  -> collection\<resource>.bmp
  -> item\<resource>.bmp when no 75×100 collection art exists
```

Use `reused/artwork/fallback_question_mark.bmp` only when both the resolved
75×100 collection artwork and the native item icon are missing. Draw collection
art as an opaque 75×100 image; native item icons are centered at their stock
size. Use color-key drawing only for irregular controls and semantic badges.

The shell is shared by Items, Combo Collections, and Total Bonuses. The Items
tab dropdown selects All, Card, Weapon, Armor, Shield, Headgear, Garment, Shoes,
Accessory, Consumable, Etc, Ammo, Pet, Shadow, and Cash categories. All labels,
progress, panel borders, selection, status pills, counts, fees, Zeny values,
and bonuses remain runtime-rendered.

See `layout.yml` for coordinates and `asset-manifest.yml` for the loading contract.

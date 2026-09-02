# Item Collection reused asset provenance

Created 2026-08-31 for the Item Collection BMP build. This directory contains 44 source-derived BMP files only. Every bitmap was copied byte-for-byte: no resizing, palette conversion, color correction, text removal, or re-encoding was performed.

Packed source archive:

- `maindata.grf`
- SHA-256: `43E4237A7426F0CE4F93C666E650F6E03D46652743E4728375E29610F8B77BF8`

The logical Korean directory `data\texture\유저인터페이스` is surfaced by the local CP949 path as `data\texture\À¯ÀúÀÎÅÍÆäÀÌ½º`.

## Asset families

| Staged family | Files | Original source | Native format | State and text notes |
|---|---:|---|---|---|
| `buttons/generic/` | 12 | `maindata.grf::data\texture\À¯ÀúÀÎÅÍÆäÀÌ½º\basic_interface\btn_{out,over,press,disable}_{left,mid,right}.bmp` | Each tile is 6x20, 24-bpp RGB BMP | Complete normal/hover/pressed/disabled nine-slice family. Blank; no embedded label. Tile the middle segment to the required width and render labels at runtime. |
| `close/` | 4 | Loose client data: `data\texture\À¯ÀúÀÎÅÍÆäÀÌ½º\uirenewal\questui\btn_close_{normal,mouseon,pressed,disabled}.bmp` | 16x16, 24-bpp RGB BMP | Complete icon-only family with no text. |
| `search/` | 5 | Loose client data: `data\texture\À¯ÀúÀÎÅÍÆäÀÌ½º\uirenewal\questui\searchbar_bg.bmp` and `btn_searchbar_{normal,_mouseon,pressed,disabled}.bmp` | Field 121x18; buttons 26x18; 24-bpp RGB BMP | Blank search field plus complete magnifier-button family. The source hover filename intentionally contains the double underscore: `btn_searchbar__mouseon.bmp`. |
| `scrollbar/` | 14 | Track/thumb: `maindata.grf::data\texture\À¯ÀúÀÎÅÍÆäÀÌ½º\lapine\scrollbar_*.bmp`; arrows: loose `uirenewal\questui\btn_scroll_arrow_{up,down}.bmp` | Track caps 9x9, track middle 9x3; all thumb slices 9x3; arrows 9x12; 24-bpp RGB BMP | Tileable track plus complete out/over/press thumb states. Arrow bitmaps are icon-only and have one visual state each. |
| `steppers/` | 6 | `maindata.grf::data\texture\À¯ÀúÀÎÅÍÆäÀÌ½º\cashshop\btn_{plus,minus}_{normal,over,press}.bmp` | 19x8, 24-bpp RGB BMP | Complete three-state plus/minus family; no disabled state. |
| `currency/icon_zeny.bmp` | 1 | `maindata.grf::data\texture\À¯ÀúÀÎÅÍÆäÀÌ½º\basic_interface\rodexsystem\renewal\icon_zeny.bmp` | 28x25, 24-bpp RGB BMP | Icon-only Zeny bag/coin; no embedded label. |
| `status/badge_complete.bmp` | 1 | `maindata.grf::data\texture\À¯ÀúÀÎÅÍÆäÀÌ½º\achievement_re\badge_complete.bmp` | 20x30, 24-bpp RGB BMP | Completion ribbon icon with no embedded text. |
| `artwork/fallback_question_mark.bmp` | 1 | `maindata.grf::data\texture\유저인터페이스\collection\사과.bmp` (local path display: `...\collection\»ç°ú.bmp`) | 75x100, 24-bpp RGB BMP | Native question-mark collection artwork. Only the staged filename was normalized; pixel bytes are unchanged. Do not confuse it with `collection\apple_.bmp`, which is the real Apple artwork. |

## Item category icons

The 15 `icons/category_*.bmp` files preserve pixels from native client assets.
The All icon reuses `icons/icon_collection.bmp`; the remaining icons use these
representative item resources: Poring Card, Knife, Cotton Shirt, Guard, Poring
Hat, Muffler, Sandals, Rosary, Red Potion, Jellopy, Arrow, Poring Egg,
Beginner's Shadow Armor, and Battle Manual Box. Card, Headgear, Ammo, Shadow,
and Cash originated as palette BMPs and were losslessly re-encoded as 24-bpp
BI_RGB to satisfy the runtime pack contract; the other ten files remain native
24-bpp copies. These are visual category markers only and do not define
collection membership or rewards.

## Item Collection menu button

The user supplied and approved ten final BMPs on 2026-09-01. Exact copies are
staged under `source/menuicon/` and copied unchanged to `menuicon/` by
`tools/build_item_collection_menu_buttons.ps1`.

- New UI: base, disabled, normal, mouse-on, press, and pressed (45x41)
- Classic: disabled, normal, mouse-on, and pressed (32x34)

All ten files are 24-bpp BI_RGB. The native button uses normal, mouse-on, and
pressed for each theme; the other filenames remain deployed as compatibility
aliases. `bt_itemcollection.bmp` and `bt_itemcollection_disabled.bmp` are
byte-identical; `bt_itemcollection_old_disabled.bmp` and
`bt_itemcollection_old_mouseon.bmp` are also byte-identical. No pixel,
palette, dimension, filename, or compression change is made after staging.

## Excluded after visual review

- Text-bearing `Deposit`, `Withdraw`, `OK`, `Cancel`, `Reset`, `Close`, `COMPLETED`, and `SOLD OUT` bitmaps were not staged because they prevent runtime localization or carry the wrong semantics.
- Cash Shop category tabs contain embedded category glyphs/text and were not staged.
- Inventory `bt_itemdeal_lock_*` and `renew_questui\bt_lock*` are not padlock badges (they depict trade/visibility controls), so they were excluded.
- Fluent emoji lock/check assets were excluded because they do not match the Ragnarok UI pixel language.

No source checkout file, live-client file, or GRF archive was modified while producing this set.

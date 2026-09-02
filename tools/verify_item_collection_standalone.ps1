param(
	[string]$Exe = (Join-Path $PSScriptRoot '..\Outputs\item_collection_standalone_test.exe')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$scripts = @(
	'Scripts\Patches\CustomSlashCommand.qjs',
	'Scripts\Patches\ItemCollectionUI.qjs',
	'Scripts\Patches\ItemCollectionStockMenuButton.qjs'
)

foreach ($relative in $scripts) {
	$path = Join-Path $root $relative
	$bytes = [IO.File]::ReadAllBytes($path)
	if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and
		$bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
		throw "$relative has a UTF-8 BOM"
	}
	$text = [IO.File]::ReadAllText($path)
	if ([regex]::IsMatch($text, '(?<!\r)\n')) {
		throw "$relative is not CRLF-only"
	}
	$text | node --check -
	if ($LASTEXITCODE -ne 0) {
		throw "Node syntax check failed: $relative"
	}
}

$core = [IO.File]::ReadAllText((Join-Path $root 'Scripts\Patches\ItemCollectionUI.qjs'))
$launcher = [IO.File]::ReadAllText((Join-Path $root 'Scripts\Patches\ItemCollectionStockMenuButton.qjs'))
$profile = [IO.File]::ReadAllText((Join-Path $root 'profiles\item_collection_standalone_test.yml'))

foreach ($token in @(
	'var ItemCollectionUIStatic',
	'ItemCollectionUI.MenuButton.v1',
	'collection\\%s.bmp',
	'item\\%s.bmp',
	'a.emit(0x85, 0xC9); a.jcc(0x84, "selection_done");',
	'loading: resource("chrome\\loading.bmp")',
	'$copyItemCollectionAssets'
)) {
	if (-not $core.Contains($token)) {
		throw "Missing core contract: $token"
	}
}
foreach ($token in @(
	'ItemCollectionUI.MenuButton.v1',
	'ItemCollectionStockMenuButtonStatic',
	'Item Collection Launcher',
	'bt_itemcollection_old_normal.bmp',
	'bt_itemcollection_normal.bmp'
)) {
	if (-not $launcher.Contains($token)) {
		throw "Missing launcher contract: $token"
	}
}
if ($core.Contains('ROGlobalZeroMenu.ItemCollectionRoute.v1') -or
	$launcher.Contains('ROGlobalZeroMenu') -or
	$launcher.Contains('AutoCombatUI.MenuButton')) {
	throw 'Standalone launcher depends on RO Global UI or AutoCombat'
}
if ($core.Contains('Requesting the account collection snapshot...')) {
	throw 'Obsolete loading text remains'
}
if ($profile.IndexOf('ItemCollectionUI') -gt
	$profile.IndexOf('ItemCollectionStockMenuButton')) {
	throw 'Profile patch order is invalid'
}

& (Join-Path $PSScriptRoot 'verify_collection_ui_assets.ps1')
if ($LASTEXITCODE -ne 0) {
	throw 'Collection asset verification failed'
}
python (Join-Path $PSScriptRoot 'verify_item_collection_standalone.py') $Exe
if ($LASTEXITCODE -ne 0) {
	throw 'Standalone PE verification failed'
}

Write-Output 'ITEM_COLLECTION_STANDALONE_SOURCE_OK patches=2 qjs=3 dependency=none'

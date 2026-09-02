param(
	[string]$PackRoot = (Join-Path $PSScriptRoot '..\Images\CollectionUI')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Drawing

$resolvedPackRoot = [System.IO.Path]::GetFullPath($PackRoot)
$script:validationFailures = [System.Collections.Generic.List[string]]::new()

function Add-ValidationFailure {
	param([string]$Message)

	$script:validationFailures.Add($Message) | Out-Null
}

function Get-PackRelativePath {
	param([string]$Path)

	if ($Path.StartsWith($resolvedPackRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
		return $Path.Substring($resolvedPackRoot.Length).TrimStart('\').Replace('\', '/')
	}
	return $Path
}

function Test-BitmapDimensions {
	param(
		[string]$Path,
		[int]$ExpectedWidth,
		[int]$ExpectedHeight
	)

	if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
		Add-ValidationFailure "Missing required BMP: $(Get-PackRelativePath $Path)"
		return $false
	}

	$bitmap = $null
	try {
		$bitmap = [System.Drawing.Bitmap]::new($Path)
		if ($bitmap.Width -ne $ExpectedWidth -or $bitmap.Height -ne $ExpectedHeight) {
			Add-ValidationFailure (
				"Wrong dimensions for {0}: expected {1}x{2}, got {3}x{4}" -f
				(Get-PackRelativePath $Path),
				$ExpectedWidth,
				$ExpectedHeight,
				$bitmap.Width,
				$bitmap.Height
			)
			return $false
		}
		return $true
	}
	catch {
		Add-ValidationFailure "Could not decode $(Get-PackRelativePath $Path): $($_.Exception.Message)"
		return $false
	}
	finally {
		if ($null -ne $bitmap) {
			$bitmap.Dispose()
		}
	}
}

function Test-WindowsBitmapHeader {
	param([System.IO.FileInfo]$File)

	$relativePath = Get-PackRelativePath $File.FullName
	$bytes = [System.IO.File]::ReadAllBytes($File.FullName)
	if ($bytes.Length -lt 34) {
		Add-ValidationFailure "Truncated BMP header: $relativePath"
		return
	}
	if ($bytes[0] -ne 0x42 -or $bytes[1] -ne 0x4D) {
		Add-ValidationFailure "Not a Windows BM bitmap: $relativePath"
		return
	}

	$dibHeaderSize = [System.BitConverter]::ToUInt32($bytes, 14)
	if ($dibHeaderSize -lt 40) {
		Add-ValidationFailure "Unsupported pre-BITMAPINFOHEADER DIB in ${relativePath}: $dibHeaderSize bytes"
		return
	}

	$bitsPerPixel = [System.BitConverter]::ToUInt16($bytes, 28)
	$compression = [System.BitConverter]::ToUInt32($bytes, 30)
	if ($bitsPerPixel -ne 24) {
		Add-ValidationFailure "BMP is not 24-bpp: $relativePath ($bitsPerPixel bpp)"
	}
	if ($compression -ne 0) {
		Add-ValidationFailure "BMP is not BI_RGB compression=0: $relativePath (compression=$compression)"
	}
}

if (-not (Test-Path -LiteralPath $resolvedPackRoot -PathType Container)) {
	throw "Collection UI asset root does not exist: $resolvedPackRoot"
}

$ownedAssets = [ordered]@{
	'chrome\title_bar_760.bmp' = @(760, 17)
	'chrome\bg_collection.bmp' = @(760, 523)
	'chrome\loading.bmp' = @(166, 124)
	'icons\icon_collection.bmp' = @(16, 16)
	'icons\badge_locked.bmp' = @(16, 16)
	'icons\badge_complete.bmp' = @(16, 16)
}

$categoryAssets = [ordered]@{
	'icons\category_all.bmp' = @(16, 16)
	'icons\category_card.bmp' = @(24, 24)
	'icons\category_weapon.bmp' = @(24, 24)
	'icons\category_armor.bmp' = @(24, 24)
	'icons\category_shield.bmp' = @(24, 24)
	'icons\category_headgear.bmp' = @(24, 24)
	'icons\category_garment.bmp' = @(24, 24)
	'icons\category_shoes.bmp' = @(24, 24)
	'icons\category_accessory.bmp' = @(24, 24)
	'icons\category_consumable.bmp' = @(24, 24)
	'icons\category_etc.bmp' = @(24, 24)
	'icons\category_ammo.bmp' = @(24, 24)
	'icons\category_pet.bmp' = @(24, 24)
	'icons\category_shadow.bmp' = @(24, 24)
	'icons\category_cash.bmp' = @(24, 24)
}

$menuAssets = [ordered]@{
	'menuicon\bt_itemcollection.bmp' = @(45, 41)
	'menuicon\bt_itemcollection_disabled.bmp' = @(45, 41)
	'menuicon\bt_itemcollection_normal.bmp' = @(45, 41)
	'menuicon\bt_itemcollection_mouseon.bmp' = @(45, 41)
	'menuicon\bt_itemcollection_press.bmp' = @(45, 41)
	'menuicon\bt_itemcollection_pressed.bmp' = @(45, 41)
	'menuicon\bt_itemcollection_old_disabled.bmp' = @(32, 34)
	'menuicon\bt_itemcollection_old_normal.bmp' = @(32, 34)
	'menuicon\bt_itemcollection_old_mouseon.bmp' = @(32, 34)
	'menuicon\bt_itemcollection_old_pressed.bmp' = @(32, 34)
}

$menuSourceAssets = [ordered]@{
	'source\menuicon\bt_itemcollection.bmp' = @(45, 41)
	'source\menuicon\bt_itemcollection_disabled.bmp' = @(45, 41)
	'source\menuicon\bt_itemcollection_normal.bmp' = @(45, 41)
	'source\menuicon\bt_itemcollection_mouseon.bmp' = @(45, 41)
	'source\menuicon\bt_itemcollection_press.bmp' = @(45, 41)
	'source\menuicon\bt_itemcollection_pressed.bmp' = @(45, 41)
	'source\menuicon\bt_itemcollection_old_disabled.bmp' = @(32, 34)
	'source\menuicon\bt_itemcollection_old_normal.bmp' = @(32, 34)
	'source\menuicon\bt_itemcollection_old_mouseon.bmp' = @(32, 34)
	'source\menuicon\bt_itemcollection_old_pressed.bmp' = @(32, 34)
}

$ownedDimensionsValid = @{}
foreach ($ownedAsset in $ownedAssets.GetEnumerator()) {
	$ownedPath = Join-Path $resolvedPackRoot $ownedAsset.Key
	$ownedDimensionsValid[$ownedAsset.Key] = Test-BitmapDimensions `
		-Path $ownedPath `
		-ExpectedWidth $ownedAsset.Value[0] `
		-ExpectedHeight $ownedAsset.Value[1]
}
foreach ($categoryAsset in $categoryAssets.GetEnumerator()) {
	$categoryPath = Join-Path $resolvedPackRoot $categoryAsset.Key
	$null = Test-BitmapDimensions -Path $categoryPath -ExpectedWidth $categoryAsset.Value[0] -ExpectedHeight $categoryAsset.Value[1]
}
foreach ($menuAsset in $menuAssets.GetEnumerator()) {
	$menuPath = Join-Path $resolvedPackRoot $menuAsset.Key
	$null = Test-BitmapDimensions -Path $menuPath -ExpectedWidth $menuAsset.Value[0] -ExpectedHeight $menuAsset.Value[1]
}
foreach ($menuSourceAsset in $menuSourceAssets.GetEnumerator()) {
	$menuSourcePath = Join-Path $resolvedPackRoot $menuSourceAsset.Key
	$null = Test-BitmapDimensions -Path $menuSourcePath -ExpectedWidth $menuSourceAsset.Value[0] -ExpectedHeight $menuSourceAsset.Value[1]
}

$sourceTitlePath = Join-Path $resolvedPackRoot 'source\title_bar_470.bmp'
$sourceTitleDimensionsValid = Test-BitmapDimensions -Path $sourceTitlePath -ExpectedWidth 470 -ExpectedHeight 17

$fallbackPath = Join-Path $resolvedPackRoot 'reused\artwork\fallback_question_mark.bmp'
$null = Test-BitmapDimensions -Path $fallbackPath -ExpectedWidth 75 -ExpectedHeight 100

foreach ($animationAsset in @(
	@('chrome\nowloading.act', 'AC'),
	@('chrome\nowloading.spr', 'SP')
)) {
	$animationPath = Join-Path $resolvedPackRoot $animationAsset[0]
	if (-not (Test-Path -LiteralPath $animationPath -PathType Leaf)) {
		Add-ValidationFailure "Missing loading animation source: $($animationAsset[0])"
		continue
	}
	$magic = [Text.Encoding]::ASCII.GetString(
		[IO.File]::ReadAllBytes($animationPath), 0, 2
	)
	if ($magic -ne $animationAsset[1]) {
		Add-ValidationFailure "Invalid loading animation magic: $($animationAsset[0])"
	}
}

$reusedRoot = Join-Path $resolvedPackRoot 'reused'
if (-not (Test-Path -LiteralPath $reusedRoot -PathType Container)) {
	Add-ValidationFailure 'Missing reused asset directory: reused/'
}
else {
	$reusedBitmaps = @(Get-ChildItem -LiteralPath $reusedRoot -Recurse -File -Filter '*.bmp')
	if ($reusedBitmaps.Count -ne 44) {
		Add-ValidationFailure "Expected exactly 44 reused BMPs, found $($reusedBitmaps.Count)"
	}
}

$badExtractionNames = @(
	Get-ChildItem -LiteralPath $resolvedPackRoot -Recurse -Force |
		Where-Object { $_.Name.StartsWith('+', [System.StringComparison]::Ordinal) }
)
foreach ($badExtractionName in $badExtractionNames) {
	Add-ValidationFailure "Extraction-only leading '+' remains in: $(Get-PackRelativePath $badExtractionName.FullName)"
}

$allBitmaps = @(Get-ChildItem -LiteralPath $resolvedPackRoot -Recurse -File -Filter '*.bmp')
if ($allBitmaps.Count -eq 0) {
	Add-ValidationFailure 'No BMP assets were found.'
}
foreach ($bitmapFile in $allBitmaps) {
	Test-WindowsBitmapHeader -File $bitmapFile
}

$targetTitlePath = Join-Path $resolvedPackRoot 'chrome\title_bar_760.bmp'
if ($sourceTitleDimensionsValid -and $ownedDimensionsValid['chrome\title_bar_760.bmp']) {
	$sourceTitle = [System.Drawing.Bitmap]::new($sourceTitlePath)
	$targetTitle = [System.Drawing.Bitmap]::new($targetTitlePath)
	try {
		$leftMismatch = $null
		:LeftPixels for ($pixelY = 0; $pixelY -lt 17; $pixelY++) {
			for ($pixelX = 0; $pixelX -le 59; $pixelX++) {
				if ($targetTitle.GetPixel($pixelX, $pixelY).ToArgb() -ne $sourceTitle.GetPixel($pixelX, $pixelY).ToArgb()) {
					$leftMismatch = "($pixelX,$pixelY)"
					break LeftPixels
				}
			}
		}
		if ($null -ne $leftMismatch) {
			Add-ValidationFailure "Derived title does not preserve source left x=0..59; first mismatch at $leftMismatch"
		}

		$rightMismatch = $null
		:RightPixels for ($pixelY = 0; $pixelY -lt 17; $pixelY++) {
			for ($targetX = 675; $targetX -le 759; $targetX++) {
				$sourceX = 385 + ($targetX - 675)
				if ($targetTitle.GetPixel($targetX, $pixelY).ToArgb() -ne $sourceTitle.GetPixel($sourceX, $pixelY).ToArgb()) {
					$rightMismatch = "target ($targetX,$pixelY), source ($sourceX,$pixelY)"
					break RightPixels
				}
			}
		}
		if ($null -ne $rightMismatch) {
			Add-ValidationFailure "Derived title does not preserve source right x=385..469 at target x=675..759; first mismatch at $rightMismatch"
		}

		$repeatMismatch = $null
		$repeatWidth = 325
		:RepeatPixels for ($pixelY = 0; $pixelY -lt 17; $pixelY++) {
			for ($targetX = 60; $targetX -le 674; $targetX++) {
				$sourceX = 60 + (($targetX - 60) % $repeatWidth)
				if ($targetTitle.GetPixel($targetX, $pixelY).ToArgb() -ne $sourceTitle.GetPixel($sourceX, $pixelY).ToArgb()) {
					$repeatMismatch = "target ($targetX,$pixelY), expected repeat source ($sourceX,$pixelY)"
					break RepeatPixels
				}
			}
		}
		if ($null -ne $repeatMismatch) {
			Add-ValidationFailure "Derived title center is not built exclusively from repeated source x=60..384; first mismatch at $repeatMismatch"
		}
	}
	finally {
		$sourceTitle.Dispose()
		$targetTitle.Dispose()
	}
}

$bodyPath = Join-Path $resolvedPackRoot 'chrome\bg_collection.bmp'
if ($ownedDimensionsValid['chrome\bg_collection.bmp']) {
	$body = [System.Drawing.Bitmap]::new($bodyPath)
	try {
		$whiteArgb = [System.Drawing.Color]::FromArgb(255, 255, 255).ToArgb()
		$bodyMismatch = $null
		:BodyPixels for ($pixelY = 2; $pixelY -le 520; $pixelY++) {
			for ($pixelX = 2; $pixelX -le 757; $pixelX++) {
				if ($body.GetPixel($pixelX, $pixelY).ToArgb() -ne $whiteArgb) {
					$bodyMismatch = "($pixelX,$pixelY)"
					break BodyPixels
				}
			}
		}
		if ($null -ne $bodyMismatch) {
			Add-ValidationFailure "Collection body interior x=2..757, y=2..520 is not exact white; first mismatch at $bodyMismatch"
		}
	}
	finally {
		$body.Dispose()
	}
}

foreach ($keyedIconRelativePath in @(
	'icons\icon_collection.bmp',
	'icons\badge_locked.bmp',
	'icons\badge_complete.bmp'
)) {
	if (-not $ownedDimensionsValid[$keyedIconRelativePath]) {
		continue
	}

	$keyedIconPath = Join-Path $resolvedPackRoot $keyedIconRelativePath
	$keyedIcon = [System.Drawing.Bitmap]::new($keyedIconPath)
	try {
		$hasExactMagenta = $false
		:IconPixels for ($pixelY = 0; $pixelY -lt $keyedIcon.Height; $pixelY++) {
			for ($pixelX = 0; $pixelX -lt $keyedIcon.Width; $pixelX++) {
				$pixel = $keyedIcon.GetPixel($pixelX, $pixelY)
				if ($pixel.R -eq 255 -and $pixel.G -eq 0 -and $pixel.B -eq 255) {
					$hasExactMagenta = $true
					break IconPixels
				}
			}
		}
		if (-not $hasExactMagenta) {
			Add-ValidationFailure "Color-keyed icon contains no exact #FF00FF pixel: $($keyedIconRelativePath.Replace('\', '/'))"
		}
	}
	finally {
		$keyedIcon.Dispose()
	}
}

Write-Host 'Owned asset SHA-256:'
foreach ($ownedAsset in $ownedAssets.GetEnumerator()) {
	$ownedPath = Join-Path $resolvedPackRoot $ownedAsset.Key
	if (Test-Path -LiteralPath $ownedPath -PathType Leaf) {
		$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ownedPath).Hash
		Write-Host ("  {0}  {1}" -f $hash, $ownedAsset.Key.Replace('\', '/'))
	}
}
Write-Host 'Category asset SHA-256:'
foreach ($categoryAsset in $categoryAssets.GetEnumerator()) {
	$categoryPath = Join-Path $resolvedPackRoot $categoryAsset.Key
	if (Test-Path -LiteralPath $categoryPath -PathType Leaf) {
		$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $categoryPath).Hash
		Write-Host ("  {0}  {1}" -f $hash, $categoryAsset.Key.Replace('\', '/'))
	}
}
Write-Host 'Item Collection menu-button SHA-256:'
foreach ($menuAsset in $menuAssets.GetEnumerator()) {
	$menuPath = Join-Path $resolvedPackRoot $menuAsset.Key
	if (Test-Path -LiteralPath $menuPath -PathType Leaf) {
		$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $menuPath).Hash
		Write-Host ("  {0}  {1}" -f $hash, $menuAsset.Key.Replace('\', '/'))
	}
}

if ($script:validationFailures.Count -gt 0) {
	Write-Host ''
	Write-Host "Collection UI asset verification failed with $($script:validationFailures.Count) error(s):"
	foreach ($failure in $script:validationFailures) {
		Write-Host "  - $failure"
	}
	throw 'Collection UI asset verification failed.'
}

Write-Host ''
Write-Host (
	'Collection UI asset verification passed: {0} BMPs checked, 44 reused controls, 15 category icons, 10 supplied menu buttons, 6 owned assets, ACT/SPR sources valid.' -f
	$allBitmaps.Count
)

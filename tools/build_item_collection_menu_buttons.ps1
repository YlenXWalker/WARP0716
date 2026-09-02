[CmdletBinding()]
param(
	[string]$PackRoot = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

if ([string]::IsNullOrWhiteSpace($PackRoot)) {
	$PackRoot = Join-Path $PSScriptRoot '..\Images\CollectionUI'
}
$pack = [System.IO.Path]::GetFullPath($PackRoot)
$sourceRoot = Join-Path $pack 'source\menuicon'
$targetRoot = Join-Path $pack 'menuicon'
if (-not (Test-Path -LiteralPath $targetRoot)) {
	New-Item -ItemType Directory -Path $targetRoot | Out-Null
}

$assets = [ordered]@{
	'bt_itemcollection.bmp' = @(45, 41)
	'bt_itemcollection_disabled.bmp' = @(45, 41)
	'bt_itemcollection_mouseon.bmp' = @(45, 41)
	'bt_itemcollection_normal.bmp' = @(45, 41)
	'bt_itemcollection_press.bmp' = @(45, 41)
	'bt_itemcollection_pressed.bmp' = @(45, 41)
	'bt_itemcollection_old_disabled.bmp' = @(32, 34)
	'bt_itemcollection_old_mouseon.bmp' = @(32, 34)
	'bt_itemcollection_old_normal.bmp' = @(32, 34)
	'bt_itemcollection_old_pressed.bmp' = @(32, 34)
}

foreach ($asset in $assets.GetEnumerator()) {
	$sourcePath = Join-Path $sourceRoot $asset.Key
	if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
		throw "Missing supplied Item Collection button: $sourcePath"
	}
	$bytes = [System.IO.File]::ReadAllBytes($sourcePath)
	if ($bytes.Length -lt 34 -or $bytes[0] -ne 0x42 -or $bytes[1] -ne 0x4D) {
		throw "Invalid Windows BMP: $sourcePath"
	}
	$bits = [System.BitConverter]::ToUInt16($bytes, 28)
	$compression = [System.BitConverter]::ToUInt32($bytes, 30)
	if ($bits -ne 24 -or $compression -ne 0) {
		throw "Button must remain 24-bpp BI_RGB: $sourcePath"
	}
	$bitmap = [System.Drawing.Bitmap]::new($sourcePath)
	try {
		if ($bitmap.Width -ne $asset.Value[0] -or
			$bitmap.Height -ne $asset.Value[1]) {
			throw "Wrong button dimensions for $($asset.Key): $($bitmap.Width)x$($bitmap.Height)"
		}
	} finally {
		$bitmap.Dispose()
	}
	Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $targetRoot $asset.Key) -Force
}

Write-Host "Copied and validated 10 supplied Item Collection menu-button BMPs."

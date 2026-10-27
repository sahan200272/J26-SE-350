<#
.SYNOPSIS
  Downloads the pinned official Syncthing release for linux-arm64, verifies it,
  and installs the executable as a native library for the app (A5).

.DESCRIPTION
  1. Downloads syncthing-linux-arm64-<version>.tar.gz and the release's
     sha256sum.txt.asc from the official GitHub release, into a new empty
     temporary directory.
  2. Verifies the tarball's SHA-256 against the line for it in
     sha256sum.txt.asc, and against $PinnedSha256 below. Any mismatch stops the
     script before anything is installed.
  3. Extracts the `syncthing` executable and checks that it is a static
     AArch64 ELF executable (no program interpreter), which can run on Android.
  4. Copies it to android/app/src/main/jniLibs/arm64-v8a/libsyncthing.so. That
     path is git-ignored: the binary is never committed. Android installs it
     into the app's nativeLibraryDir, the only app location it may execute
     from.
  5. Compares the release's LICENSE.txt (MPL-2.0) with the copy the app shows
     (assets/licenses/syncthing_LICENSE.txt), creating that file if missing.

  The signature on sha256sum.txt.asc is not checked (that needs GnuPG and
  Syncthing's release key); the checksum file is fetched over HTTPS from the
  same GitHub release.

.PARAMETER Force
  Download and install even if libsyncthing.so already matches the pinned
  release.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tool\fetch_syncthing.ps1
#>
param([switch]$Force)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest is very slow with it on

# Pinned release: same version as the PC's Syncthing. The hashes were recorded from
# the first verified download (matching the release checksum file); empty means
# "check against the release checksum file only".
$Version = 'v2.1.6'
$PinnedSha256 = 'f054de02462d5d58bd126908f2f92b63aba74f162a5be85e50e96d656e7db47d'  # syncthing-linux-arm64-<version>.tar.gz
$PinnedBinarySha256 = '68d16bb03d9568189cd39a79c32767bba75bd750c612968b3db4d9d6174c1d3a'  # the extracted executable (= libsyncthing.so)
$Asset = "syncthing-linux-arm64-$Version.tar.gz"
$ReleaseUrl = "https://github.com/syncthing/syncthing/releases/download/$Version"

$AppRoot = Split-Path -Parent $PSScriptRoot
$Destination = Join-Path $AppRoot 'android\app\src\main\jniLibs\arm64-v8a\libsyncthing.so'
$LicenseAsset = Join-Path $AppRoot 'assets\licenses\syncthing_LICENSE.txt'

function Get-Sha256([string]$Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

# Returns a description of the ELF file, or throws if it cannot run on Android arm64.
function Assert-StaticArm64Elf([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 64 -or $bytes[0] -ne 0x7F -or $bytes[1] -ne 0x45 -or
        $bytes[2] -ne 0x4C -or $bytes[3] -ne 0x46) {
        throw "$Path is not an ELF file."
    }
    if ($bytes[4] -ne 2 -or $bytes[5] -ne 1) { throw "$Path is not a 64-bit little-endian ELF." }
    $type = [BitConverter]::ToUInt16($bytes, 0x10)
    $machine = [BitConverter]::ToUInt16($bytes, 0x12)
    if ($machine -ne 0xB7) { throw "$Path is not AArch64 (e_machine 0x$('{0:X}' -f $machine))." }
    if ($type -ne 2 -and $type -ne 3) { throw "$Path is not an executable (e_type $type)." }
    $phoff = [BitConverter]::ToUInt64($bytes, 0x20)
    $phentsize = [BitConverter]::ToUInt16($bytes, 0x36)
    $phnum = [BitConverter]::ToUInt16($bytes, 0x38)
    for ($i = 0; $i -lt $phnum; $i++) {
        $pType = [BitConverter]::ToUInt32($bytes, [int]($phoff + $i * $phentsize))
        if ($pType -eq 3) {
            throw "$Path is dynamically linked (has PT_INTERP); it would not run on Android."
        }
    }
    $kind = 'ET_EXEC'
    if ($type -eq 3) { $kind = 'ET_DYN' }
    return "static AArch64 ELF ($kind, $phnum program headers, no PT_INTERP)"
}

if ((Test-Path -LiteralPath $Destination) -and -not $Force -and $PinnedBinarySha256 -and
    (Get-Sha256 $Destination) -eq $PinnedBinarySha256.ToLowerInvariant()) {
    Write-Host "libsyncthing.so is already the pinned $Version executable ($PinnedBinarySha256); use -Force to reinstall."
    exit 0
}

$work = Join-Path ([IO.Path]::GetTempPath()) ("fetch_syncthing_" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $tarball = Join-Path $work $Asset
    $sums = Join-Path $work 'sha256sum.txt.asc'

    Write-Host "Downloading $ReleaseUrl/sha256sum.txt.asc"
    Invoke-WebRequest -UseBasicParsing -Uri "$ReleaseUrl/sha256sum.txt.asc" -OutFile $sums
    Write-Host "Downloading $ReleaseUrl/$Asset"
    Invoke-WebRequest -UseBasicParsing -Uri "$ReleaseUrl/$Asset" -OutFile $tarball

    # sha256sum format: "<64 hex>  <file name>" (inside a PGP clear-signed block).
    $pattern = '^([0-9a-fA-F]{64})\s+\*?' + [Regex]::Escape($Asset) + '\s*$'
    $lines = @(Get-Content -LiteralPath $sums | Where-Object { $_ -match $pattern })
    if ($lines.Count -ne 1) { throw "sha256sum.txt.asc has $($lines.Count) entries for $Asset (expected 1)." }
    $expected = ([Regex]::Match($lines[0], $pattern)).Groups[1].Value.ToLowerInvariant()
    $actual = Get-Sha256 $tarball
    Write-Host "SHA-256 $Asset"
    Write-Host "  release checksum file: $expected"
    Write-Host "  downloaded file:       $actual"
    if ($actual -ne $expected) { throw "SHA-256 mismatch: the download does not match the release checksum file." }
    if ($PinnedSha256 -and $actual -ne $PinnedSha256.ToLowerInvariant()) {
        throw "SHA-256 mismatch: the download does not match the pinned hash $PinnedSha256."
    }
    Write-Host "  OK: matches the release checksum file$(if ($PinnedSha256) { ' and the pinned hash' })."

    $extract = Join-Path $work 'extract'
    New-Item -ItemType Directory -Path $extract | Out-Null
    $folder = "syncthing-linux-arm64-$Version"
    & "$env:SystemRoot\System32\tar.exe" -xzf $tarball -C $extract "$folder/syncthing" "$folder/LICENSE.txt"
    if ($LASTEXITCODE -ne 0) { throw "tar failed with exit code $LASTEXITCODE." }
    $binary = Join-Path $extract "$folder\syncthing"
    $license = Join-Path $extract "$folder\LICENSE.txt"

    $elf = Assert-StaticArm64Elf $binary
    $binarySha = Get-Sha256 $binary
    Write-Host "Executable: $elf, $((Get-Item -LiteralPath $binary).Length) bytes, SHA-256 $binarySha"
    if ($PinnedBinarySha256 -and $binarySha -ne $PinnedBinarySha256.ToLowerInvariant()) {
        throw "SHA-256 mismatch: the executable does not match the pinned hash $PinnedBinarySha256."
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -LiteralPath $binary -Destination $Destination -Force
    Write-Host "Installed $Destination"

    if (-not (Test-Path -LiteralPath $LicenseAsset)) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LicenseAsset) | Out-Null
        Copy-Item -LiteralPath $license -Destination $LicenseAsset
        Write-Host "Created $LicenseAsset from the release's LICENSE.txt"
    } elseif ((Get-Sha256 $license) -ne (Get-Sha256 $LicenseAsset)) {
        Write-Warning "The release's LICENSE.txt differs from $LicenseAsset; review and update the app's copy."
    } else {
        Write-Host "License: the release's LICENSE.txt matches $LicenseAsset"
    }
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}

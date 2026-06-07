$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$outputRoot = Join-Path $repoRoot "dist-nuitka"
$entryScript = Join-Path $repoRoot "src\renderkit\ui\main_window.py"
$initContent = Get-Content (Join-Path $repoRoot "src\renderkit\__init__.py") -Raw
$versionMatch = [regex]::Match($initContent, "__version__\s*=\s*['""]([^'""]+)['""]")
$appVersion = if ($versionMatch.Success) { $versionMatch.Groups[1].Value } else { "0.0.0" }

$nuitkaArgs = @(
    "--remove-output",
    "--mode=standalone",
    "--assume-yes-for-downloads",
    "--enable-plugin=pyside6",
    "--include-module=PySide6",
    "--include-module=PySide6.QtCore",
    "--include-module=PySide6.QtGui",
    "--include-module=PySide6.QtWidgets",
    "--include-qt-plugins=sensible",
    "--include-package=renderkit",
    "--include-data-dir=$repoRoot\src\renderkit\ui\icons=renderkit/ui/icons",
    "--include-data-dir=$repoRoot\src\renderkit\ui\stylesheets=renderkit/ui/stylesheets",
    "--include-data-dir=$repoRoot\src\renderkit\data\ocio=renderkit/data/ocio",
    "--output-dir=$outputRoot",
    "--output-filename=RenderKit",
    "--product-name=RenderKit",
    "--product-version=$appVersion",
    "--file-version=$appVersion",
    "--file-description=RenderKit desktop app",
    "--copyright=Ahmed Hindy",
    "--windows-console-mode=disable"
)

if ($IsWindows) {
    $nuitkaArgs = @("--zig") + $nuitkaArgs
}

& uv --native-tls run --extra packaging python -m nuitka @nuitkaArgs $entryScript
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$platformDir = switch ($true) {
    $IsWindows { "windows"; break }
    $IsLinux { "linux"; break }
    $IsMacOS { "macos"; break }
    default { $null }
}

if ($platformDir -eq $null) {
    Write-Host "Skipping FFmpeg copy: unsupported platform."
} else {
    $vendorFfmpegDir = Join-Path $repoRoot "vendor\ffmpeg\$platformDir"
    if (-not (Test-Path $vendorFfmpegDir)) {
        Write-Host "Skipping FFmpeg copy: $vendorFfmpegDir does not exist."
    }
}

$standaloneDir = Get-ChildItem -Path $outputRoot -Directory -Filter "*.dist" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime |
    Select-Object -Last 1

if ($standaloneDir -eq $null) {
    throw "Could not find Nuitka standalone output."
}

if ($platformDir -ne $null -and (Test-Path $vendorFfmpegDir)) {
    $ffmpegTarget = Join-Path $standaloneDir.FullName "ffmpeg"
    New-Item -ItemType Directory -Path $ffmpegTarget -Force | Out-Null
    Copy-Item -Path (Join-Path $vendorFfmpegDir "*") -Destination $ffmpegTarget -Recurse -Force
    Write-Host "Copied bundled FFmpeg to $ffmpegTarget"
}

$packagePlatform = if ($platformDir -ne $null) { $platformDir } else { "unknown" }
$zipPath = Join-Path $outputRoot "RenderKit-nuitka-$packagePlatform-standalone.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path (Join-Path $standaloneDir.FullName "*") -DestinationPath $zipPath -Force
Write-Host "Packaged Nuitka artifact: $zipPath"

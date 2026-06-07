$ErrorActionPreference = "Stop"

function Join-NativePath {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]] $Parts
    )

    [System.IO.Path]::Combine($Parts)
}

function Compress-NuitkaOutput {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.DirectoryInfo] $PackageRoot,

        [Parameter(Mandatory = $true)]
        [string] $ZipPath
    )

    if ((-not $IsWindows) -and (Get-Command zip -ErrorAction SilentlyContinue)) {
        $zipWorkingDir = $PackageRoot.FullName
        $zipTarget = "."
        if ($PackageRoot.Extension -eq ".app") {
            $zipWorkingDir = $PackageRoot.Parent.FullName
            $zipTarget = $PackageRoot.Name
        }

        Push-Location $zipWorkingDir
        try {
            & zip -qry $ZipPath $zipTarget
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }
        } finally {
            Pop-Location
        }
        return
    }

    $zipSource = if ($PackageRoot.Extension -eq ".app") {
        $PackageRoot.FullName
    } else {
        Join-Path $PackageRoot.FullName "*"
    }
    Compress-Archive -Path $zipSource -DestinationPath $ZipPath -Force
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputRoot = Join-NativePath $repoRoot "dist-nuitka"
$entryScript = Join-NativePath $repoRoot "src" "renderkit" "ui" "main_window.py"
$initContent = Get-Content (Join-NativePath $repoRoot "src" "renderkit" "__init__.py") -Raw
$versionMatch = [regex]::Match($initContent, "__version__\s*=\s*['""]([^'""]+)['""]")
$appVersion = if ($versionMatch.Success) { $versionMatch.Groups[1].Value } else { "0.0.0" }

$iconsDir = Join-NativePath $repoRoot "src" "renderkit" "ui" "icons"
$stylesheetsDir = Join-NativePath $repoRoot "src" "renderkit" "ui" "stylesheets"
$ocioDir = Join-NativePath $repoRoot "src" "renderkit" "data" "ocio"
$nuitkaMode = if ($IsMacOS) { "app-dist" } else { "standalone" }

$nuitkaArgs = @(
    "--remove-output",
    "--mode=$nuitkaMode",
    "--assume-yes-for-downloads",
    "--enable-plugin=pyside6",
    "--include-module=PySide6",
    "--include-module=PySide6.QtCore",
    "--include-module=PySide6.QtGui",
    "--include-module=PySide6.QtWidgets",
    "--include-qt-plugins=sensible",
    "--include-package=renderkit",
    "--include-data-dir=$iconsDir=renderkit/ui/icons",
    "--include-data-dir=$stylesheetsDir=renderkit/ui/stylesheets",
    "--include-data-dir=$ocioDir=renderkit/data/ocio",
    "--output-dir=$outputRoot",
    "--output-filename=RenderKit",
    "--product-name=RenderKit",
    "--product-version=$appVersion",
    "--file-version=$appVersion",
    "--file-description=RenderKit desktop app",
    "--copyright=Ahmed Hindy"
)

if ($IsWindows) {
    $nuitkaArgs = @("--zig", "--windows-console-mode=disable") + $nuitkaArgs
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

$vendorFfmpegDir = $null
if ($null -eq $platformDir) {
    Write-Host "Skipping FFmpeg copy: unsupported platform."
} else {
    $vendorFfmpegDir = Join-NativePath $repoRoot "vendor" "ffmpeg" $platformDir
    if (-not (Test-Path $vendorFfmpegDir)) {
        Write-Host "Skipping FFmpeg copy: $vendorFfmpegDir does not exist."
    }
}

$standaloneDir = Get-ChildItem -Path $outputRoot -Directory -Filter "*.dist" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime |
    Select-Object -Last 1

$appBundleDir = Get-ChildItem -Path $outputRoot -Directory -Filter "*.app" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime |
    Select-Object -Last 1

$packageRoot = if ($IsMacOS -and $null -ne $appBundleDir) { $appBundleDir } else { $standaloneDir }

if ($null -eq $packageRoot) {
    throw "Could not find Nuitka output."
}

if ($null -ne $platformDir -and (Test-Path $vendorFfmpegDir)) {
    $ffmpegTarget = if ($IsMacOS -and $packageRoot.Extension -eq ".app") {
        Join-NativePath $packageRoot.FullName "Contents" "MacOS" "ffmpeg"
    } else {
        Join-Path $packageRoot.FullName "ffmpeg"
    }
    New-Item -ItemType Directory -Path $ffmpegTarget -Force | Out-Null
    Copy-Item -Path (Join-Path $vendorFfmpegDir "*") -Destination $ffmpegTarget -Recurse -Force
    Write-Host "Copied bundled FFmpeg to $ffmpegTarget"
}

$packagePlatform = if ($null -ne $platformDir) { $platformDir } else { "unknown" }
$zipPath = Join-Path $outputRoot "RenderKit-nuitka-$packagePlatform-standalone.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-NuitkaOutput -PackageRoot $packageRoot -ZipPath $zipPath
Write-Host "Packaged Nuitka artifact: $zipPath"

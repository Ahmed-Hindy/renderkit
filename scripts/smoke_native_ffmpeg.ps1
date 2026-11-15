param(
    [Parameter(Mandatory = $true)]
    [string]$PackageDirectory
)

$ErrorActionPreference = 'Stop'
$package = (Resolve-Path -LiteralPath $PackageDirectory).Path
$name = if ($IsWindows) { 'ffmpeg.exe' } else { 'ffmpeg' }
$ffmpeg = Join-Path $package "ffmpeg/$name"
if (-not (Test-Path -LiteralPath $ffmpeg -PathType Leaf)) {
    throw "Bundled FFmpeg was not found at $ffmpeg"
}

$encoders = (& $ffmpeg -hide_banner -encoders 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect bundled FFmpeg encoders.' }
foreach ($codec in @('libx264', 'libx265', 'libaom-av1')) {
    if ($encoders -notmatch [regex]::Escape($codec)) {
        throw "Bundled FFmpeg is missing $codec."
    }
}

$scratch = Join-Path ([System.IO.Path]::GetTempPath()) ("renderkit-smoke-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $scratch | Out-Null
$raw = Join-Path $scratch 'frames.rgb'
$output = Join-Path $scratch 'output.mp4'
try {
    $pixels = [byte[]]::new(16 * 16 * 3 * 2)
    for ($i = 0; $i -lt $pixels.Length; $i += 3) { $pixels[$i] = 255 }
    [System.IO.File]::WriteAllBytes($raw, $pixels)
    & $ffmpeg -v error -y -f rawvideo -s 16x16 -pix_fmt rgb24 -r 24 -i $raw `
        -frames:v 2 -an -c:v libx264 -pix_fmt yuv420p -movflags +faststart $output
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $output -PathType Leaf) -or
        (Get-Item -LiteralPath $output).Length -eq 0) {
        throw 'Bundled FFmpeg could not encode a test video.'
    }
    Write-Output 'Bundled FFmpeg encoders and video output verified.'
} finally {
    Remove-Item -LiteralPath $raw, $output -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $scratch -ErrorAction SilentlyContinue
}

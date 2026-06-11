# RenderKit

RenderKit is a high-performance image-sequence to video toolkit for VFX workflows.
The desktop app is the main end-user path; these docs focus on CLI automation, pipeline use, and API reference.

## Where To Start

- Use the project README for the desktop GUI workflow.
- Use the [Usage Guide](usage.md) for CLI recipes and option tables.
- Use the API reference when embedding RenderKit in another Python tool.

## CLI Highlights

- Convert EXR, TIFF, PNG, and JPEG sequences to MP4.
- Read common Houdini, Maya, and generic frame-pattern styles.
- Recursively batch-convert sequence trees with CSV and JSONL manifests.
- Replace source frame sequences with verified review MP4s and JSONL audit records.
- Convert a single EXR layer/AOV or generate multi-AOV contact sheet movies.
- Apply common color transforms for review output.
- Add frame, layer, and FPS burn-ins.
- Choose H.264, H.265, or AV1 codecs.
- Profile conversions for pipeline tuning.

## Quick Commands

Launch the desktop UI:

```bash
uv run renderkit ui
```

Convert a sequence:

```bash
uv run renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24
```

Generate a multi-AOV contact sheet movie:

```bash
uv run renderkit convert-exr-sequence render.%04d.exr contact_sheet.mp4 --contact-sheet --cs-columns 4
```

Generate a still contact sheet:

```bash
uv run renderkit contact-sheet render.%04d.exr contact_sheet.jpg --columns 4
```

Batch-convert all EXR sequences below a show or shot folder:

```bash
uv run renderkit batch-convert ./shots --out _review_mp4s --fps 24 --overwrite
```

Dry-run a safe replacement cleanup before deleting source frames:

```bash
uv run renderkit replace-sequence-with-mp4 render.%04d.exr review.mp4 --verify --delete-source --dry-run
```

## Source Checkout

```powershell
git clone https://github.com/Ahmed-Hindy/renderkit.git
cd renderkit
uv sync
uv run renderkit --help
```

RenderKit targets Python 3.13.x from VFX Platform CY2026.

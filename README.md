# Product Dataset Studio

Turn a 3D product model into isolated, white-background clips for AI video/image training. You do not need to click around in Blender.

Drop a model in `input\`, pick MP4 and/or PNG, get clips in `output\<model-name>\`.

## Quick start

1. Install [Blender](https://www.blender.org/download/) (4.x) if it is not already installed.
2. Copy your model into `input\` (`.glb`, `.gltf`, `.fbx`, or `.obj`).
3. From this folder, in a terminal:

```powershell
python studio.py --mp4
```

Videos land in `output\<model-name>\` (`orbit_eye.mp4`, `helix.mp4`, …).

Want stills instead, or both:

```powershell
python studio.py --png
python studio.py --mp4 --png
```

Optional checks:

```powershell
python studio.py --demo --preview          # stills of Suzanne, no model needed
python studio.py --preview                 # one still per shot of your model
python studio.py --list                    # shot names
python studio.py --mp4 --shots "orbit_eye,helix"
python studio.py --png --png-interval 1    # a PNG of every frame
python studio.py --mp4 --input "D:\models\bottle.glb"
```

`python studio.py --help` lists every required and optional flag, plus the `config.json` fields. Running `python studio.py` with no arguments prints the same help.

## Why this setup

For product LoRAs and video models, you want many smooth viewpoints of the **same object**, same lighting, no room, no table, no busy background. A Python script inside Blender is the reliable way: it imports the file, frames the object, moves a camera along known paths, and writes H.264 MP4s and/or PNG stills.

PNG sequences (`--png`) are better if you later extract frames for an image LoRA. Use `--mp4 --png` when you want both from one run.

## Default shots (video-gen useful set)

| Clip | What it is | Why it helps |
|---|---|---|
| `orbit_eye` | 360° at ~18° elevation | Core identity / turntable |
| `orbit_high` | 360° at ~42° | Top planes, lids, upper form |
| `orbit_low` | 360° at ~6° | Silhouette and lower lip |
| `helix` | 360° while the camera rises | Many viewpoints in one clip |
| `hero_arc` | Short 3/4 commercial orbit | Natural product-ad motion |
| `dolly_in` | Slow push-in on a 3/4 angle | Scale, material, labels |
| `vertical_three_quarter` | Low → high at a 3/4 azimuth | Complements the horizontal orbits |

Also in `config.json` but off by default: near top-down 360, reverse orbit, tight close orbit, dolly-out, front elevation sweep. Set `"enabled": true` on any of them, or name them with `--shots`.

## Other shot types that are useful (and when)

Horizontal and vertical orbits are the base. These are the next ones that actually help product training:

- **Helix / spiral** — best extra clip. One file covers rotation and height.
- **Short hero arc (90°)** — how product videos usually move; good for video models.
- **Dolly in/out** — zoom with a real camera move (not FOV zoom). Teaches size and detail.
- **Elevation-stacked turntables** — same 360 at low / eye / high. Do not rely on a single equator orbit; the model will be weak on lids and undersides.
- **Close orbit** — fill the frame (~85–90%). Helps materials, logos, and edges.
- **Top-down orbit** — if the product is understood from above (boxes, devices, food, cosmetics).
- **Lighting variation** (same camera, rotate the key light) — useful later for robustness; skipped for now so the object identity stays consistent.
- **Background randomization** — useful for recognition models, **bad** for isolated product LoRAs. This project stays on pure white.

Avoid dutch angles, handheld shake, and busy sets unless you are training a cinematic look, not the product itself.

## Config

Edit `config.json` for resolution, fps, which shots run, and clip length. Engine default is EEVEE (fast). Set `"engine": "CYCLES"` for heavier, more realistic lighting.

White isolation uses a Standard view transform so the backdrop stays actually white (Filmic/AgX would turn it grey).

Most people can ignore this file. Use `--list` and `--shots` first.

## Output

```
output/
  bottle/
    orbit_eye.mp4
    orbit_high.mp4
    ...
    dataset.json          # which file, bounds, clip list
preview/                  # from --preview
```

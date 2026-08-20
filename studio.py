#!/usr/bin/env python3
"""Launch Blender for Product Dataset Studio.

This file finds blender.exe, prints a summary, and starts Blender.
Scene and render code lives in scripts/render_dataset.py.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLENDER_SCRIPT = ROOT / "scripts" / "render_dataset.py"
DEFAULT_CONFIG = ROOT / "config.json"
INPUT_DIR = ROOT / "input"
MODEL_EXTS = {".glb", ".gltf", ".fbx", ".obj"}

BLENDER_CANDIDATES = [
    Path(r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"),
    Path("/Applications/Blender.app/Contents/MacOS/Blender"),
]


HELP_EPILOG = """
What you must provide
  1. Output format: at least one of --mp4, --png, --preview.
     --mp4 and --png together write both. --preview is stills only (no videos).
  2. A model, unless you pass --demo:
       drop a .glb / .gltf / .fbx / .obj in input\\
       or pass --input path\\to\\file.glb
       or pass --input path\\to\\folder
  --list / --help do not need a model or a format.

config.json - scene (all optional; defaults shown)
  resolution            [width, height]     default [1920, 1080]
  fps                   frames per second   default 30
  engine                EEVEE or CYCLES     default EEVEE
  eevee_samples         EEVEE samples       default 64
  cycles_samples        Cycles samples      default 64
  use_gpu               true/false          default true (Cycles)
  lens_mm               camera focal length default 50
  fill                  how large the product is in frame, 0-1   default 0.68
  white_background      true/false          default true
  view_transform        color transform     default Standard (keeps the backdrop white)
  light_brightness      studio light scale  default 1.0
  sun_strength          extra sun light     default 0.0
  exposure              view exposure       default 0.0
  ambient               world ambient       default 0.08
  shots                 list of shot objects (see below)

config.json - each shot
  Required for every shot:
    id                  filename / --shots name, e.g. orbit_eye
    type                orbit | helix | vertical | dolly
    seconds             clip length
  Optional for every shot:
    enabled             true = runs by default. false = only if named in --shots. Default true
    description         shown by --list
    fill                override the scene fill for this shot
  Extra fields by type:
    orbit               elev_deg, azimuth_start_deg, azimuth_end_deg
    helix               azimuth_start_deg, azimuth_end_deg, elev_start_deg, elev_end_deg
    vertical            azimuth_deg, elev_start_deg, elev_end_deg
    dolly               elev_deg, azimuth_deg, fill_start, fill_end

Examples
  python studio.py --mp4
  python studio.py --png
  python studio.py --mp4 --png
  python studio.py --preview
  python studio.py --demo --preview
  python studio.py --list
  python studio.py --mp4 --shots orbit_eye,helix
  python studio.py --mp4 --input D:\\models\\bottle.glb
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio.py",
        usage="python studio.py [--mp4] [--png] [--preview] [options]",
        description=(
            "Turn a 3D product model into isolated white-background shots.\n"
            "Mandatory: an output format, and a model (unless --demo)."
        ),
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    required = parser.add_argument_group(
        "required (pick at least one output; --list is the exception)"
    )
    required.add_argument(
        "--mp4",
        action="store_true",
        help="Mandatory unless --png or --preview. Write MP4 videos.",
    )
    required.add_argument(
        "--png",
        action="store_true",
        help="Mandatory unless --mp4 or --preview. Write PNG stills. Combine with --mp4 for both.",
    )
    required.add_argument(
        "--preview",
        action="store_true",
        help="Mandatory unless --mp4 or --png. One still per shot, no videos.",
    )

    optional = parser.add_argument_group("optional")
    optional.add_argument(
        "--input",
        default="",
        metavar="PATH",
        help="Model file, or a folder of models. Default: input\\",
    )
    optional.add_argument(
        "--output",
        default="",
        metavar="PATH",
        help="Output folder. Default: output\\",
    )
    optional.add_argument(
        "--config",
        default="",
        metavar="PATH",
        help="JSON config path. Default: config.json",
    )
    optional.add_argument(
        "--shots",
        default="",
        metavar="IDS",
        help='Comma-separated shot ids, e.g. "orbit_eye,helix". Default: enabled shots in config.',
    )
    optional.add_argument(
        "--blender",
        default="",
        metavar="PATH",
        help="Full path to blender.exe if it is not found automatically.",
    )
    optional.add_argument(
        "--png-interval",
        type=int,
        default=10,
        metavar="N",
        help="With --png, keep one still every N frames. Default: 10. Use 1 for every frame.",
    )
    optional.add_argument(
        "--list",
        "--list-shots",
        dest="list_shots",
        action="store_true",
        help="Print shot names and exit. Does not render.",
    )
    optional.add_argument(
        "--demo",
        action="store_true",
        help="Render Suzanne instead of a file. Skips the model requirement.",
    )
    optional.add_argument(
        "--save-blend",
        action="store_true",
        help="Save studio.blend next to the output.",
    )
    optional.add_argument(
        "--fixed-lights",
        action="store_true",
        help="Keep lights world-fixed (the far side stays darker).",
    )
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def config_path(args: argparse.Namespace) -> Path:
    if args.config:
        return Path(args.config)
    return DEFAULT_CONFIG


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def find_blender(explicit: str) -> Path:
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path
        raise SystemExit(f"Blender not found at {path}")
    for path in BLENDER_CANDIDATES:
        if path.is_file():
            return path
    found = shutil.which("blender")
    if found:
        return Path(found)
    raise SystemExit(
        "Blender not found. Install Blender, or pass --blender with the full path to blender.exe."
    )


def model_files(args: argparse.Namespace) -> list[Path]:
    if args.demo:
        return []
    if args.input:
        path = Path(args.input)
        if path.is_file():
            return [path]
        if path.is_dir():
            return sorted(
                p for p in path.iterdir() if p.is_file() and p.suffix.lower() in MODEL_EXTS
            )
        return []
    if not INPUT_DIR.is_dir():
        return []
    return sorted(p for p in INPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() in MODEL_EXTS)


def ensure_input_folder() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    hint = INPUT_DIR / "README.txt"
    if not hint.exists():
        hint.write_text(
            "Drop product models here (.glb, .gltf, .fbx, or .obj), then run:\n"
            "  python studio.py --mp4\n"
            "  python studio.py --png\n"
            "  python studio.py --mp4 --png\n",
            encoding="utf-8",
        )


def model_label(args: argparse.Namespace) -> str:
    if args.demo:
        return "1 model: Suzanne (demo) -> output\\demo"
    files = model_files(args)
    if not files:
        return "no models found in input\\"
    word = "model" if len(files) == 1 else "models"
    names = ", ".join(p.name for p in files)
    return f"{len(files)} {word}: {names}"


def shot_labels(args: argparse.Namespace) -> str:
    if args.shots:
        return ", ".join(part.strip() for part in args.shots.split(",") if part.strip())
    path = config_path(args)
    if not path.is_file():
        return "(all enabled shots)"
    cfg = load_config(path)
    names = [s.get("id", "") for s in cfg.get("shots", []) if s.get("enabled", True)]
    if not names:
        return "(none enabled)"
    return ", ".join(names)


def print_shot_list(args: argparse.Namespace) -> None:
    path = config_path(args)
    if not path.is_file():
        raise SystemExit(f"Config not found: {path}")
    cfg = load_config(path)
    print("Shots.  on = runs in a normal render.  off = only if you name it with --shots.")
    print()
    for shot in cfg.get("shots", []):
        state = "on " if shot.get("enabled", True) else "off"
        shot_id = shot.get("id", "")
        desc = shot.get("description", "")
        print(f"  {state}  {shot_id:<28} {desc}")
    print()
    print('Example:  python studio.py --mp4 --shots "orbit_eye,helix"')


def format_summary(args: argparse.Namespace) -> str:
    parts: list[str] = []
    if args.preview:
        parts.append("preview stills (first frame of each shot)")
    if args.mp4:
        parts.append("MP4 video")
    if args.png:
        if args.png_interval == 1:
            parts.append("PNG stills of every frame")
        else:
            parts.append(f"PNG stills (one every {args.png_interval} frames)")
    return " and ".join(parts)


def countdown(seconds: int = 5) -> None:
    print(f"Starting in {seconds} seconds. Press Ctrl+C to cancel.")
    try:
        for remaining in range(seconds, 0, -1):
            print(f"\r{remaining}... ", end="", flush=True)
            time.sleep(1)
        print("\rGo.    ")
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)


def blender_args(args: argparse.Namespace) -> list[str]:
    cmd = ["--background", "--python", str(BLENDER_SCRIPT), "--"]
    if args.demo:
        cmd.append("--demo")
    elif args.input:
        cmd.extend(["--input", args.input])
    if args.output:
        cmd.extend(["--output", args.output])
    cmd.extend(["--config", str(config_path(args))])
    if args.shots:
        cmd.extend(["--shots", args.shots])
    if args.mp4:
        cmd.append("--mp4")
    if args.png:
        cmd.append("--png")
        cmd.extend(["--png-interval", str(args.png_interval)])
    if args.preview:
        cmd.append("--preview")
    if args.save_blend:
        cmd.append("--save-blend")
    if args.fixed_lights:
        cmd.append("--no-lights-follow-camera")
    return cmd


def missing_format_message() -> str:
    return """Pick an output format and run again:

  python studio.py --mp4
  python studio.py --png
  python studio.py --mp4 --png
  python studio.py --preview

python studio.py --help   lists every required and optional flag, plus config.json fields.
"""


def missing_model_message() -> str:
    return (
        "No model found.\n"
        f"  Put a .glb / .gltf / .fbx / .obj in {INPUT_DIR}\n"
        "  or pass --input path\\to\\model.glb\n"
        "  or try the built-in monkey:  python studio.py --demo --preview"
    )


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        build_parser().print_help()
        print()
        print("Nothing to do: pass --mp4, --png, and/or --preview. See required fields above.")
        return 1

    args = parse_args(argv)
    ensure_input_folder()

    if args.list_shots:
        print_shot_list(args)
        return 0

    if not args.mp4 and not args.png and not args.preview:
        print(missing_format_message())
        return 1

    if args.png_interval < 1:
        raise SystemExit("--png-interval must be 1 or greater (1 = every frame).")

    if not args.demo and not model_files(args):
        raise SystemExit(missing_model_message())

    print()
    print(f"Will generate {format_summary(args)} of {model_label(args)}")
    print("Each model writes into its own folder under output\\<model-name>\\")
    print(f"Shots: {shot_labels(args)}")
    if args.fixed_lights:
        print("Lights: world-fixed (the far side stays darker)")
    else:
        print("Lights: follow the camera")
    print()
    if not args.preview:
        countdown()
        print()

    blender = find_blender(args.blender)
    cmd = [str(blender), *blender_args(args)]
    print(f"Blender: {blender}")
    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

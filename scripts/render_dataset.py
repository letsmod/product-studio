"""
Blender background renderer for product training videos.

Run via:

  python studio.py --mp4
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.json"
SUPPORTED = {".glb", ".gltf", ".fbx", ".obj"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render product orbit videos in Blender.")
    parser.add_argument(
        "--input",
        type=str,
        default="",
        help="Model file, or a folder of .glb/.gltf/.fbx/.obj files. Default: the input folder.",
    )
    parser.add_argument("--output", type=str, default=str(ROOT / "output"), help="Output folder")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG), help="JSON config path")
    parser.add_argument("--shots", type=str, default="", help="Comma-separated shot ids to render")
    parser.add_argument("--mp4", action="store_true", help="Write MP4 videos")
    parser.add_argument("--png", action="store_true", help="Write PNG stills")
    parser.add_argument(
        "--png-interval",
        type=int,
        default=10,
        help="With --png, keep one still every N frames. 10 is the default. 1 keeps every frame.",
    )
    parser.add_argument("--list", "--list-shots", dest="list_shots", action="store_true", help="Print shot names and exit")
    parser.add_argument("--preview", action="store_true", help="One still per shot, no videos")
    parser.add_argument("--demo", action="store_true", help="Render Suzanne instead of a file")
    parser.add_argument("--save-blend", action="store_true", help="Save studio.blend next to output")
    parser.add_argument(
        "--lights-follow-camera",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Rotate the studio rig with the camera (default: on). Use --no-lights-follow-camera for world-fixed lights.",
    )
    parser.add_argument("--blender-help", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def blender_argv() -> list[str]:
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1 :]
    return []


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def png_frame_numbers(total_frames: int, every: int) -> list[int]:
    every = max(1, int(every))
    return list(range(1, total_frames + 1, every))


def print_shot_list(config: dict) -> None:
    print("Shots.  on = runs in a normal render.  off = only if you name it with --shots.")
    print()
    for shot in config.get("shots", []):
        state = "on " if shot.get("enabled", True) else "off"
        shot_id = shot.get("id", "")
        description = shot.get("description", "")
        print(f"  {state}  {shot_id:<28} {description}")
    print()
    print('Example:  python studio.py --mp4 --shots orbit_eye,helix')


def reset_scene() -> bpy.types.Scene:
    scene = bpy.context.scene
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for cam in list(bpy.data.cameras):
        bpy.data.cameras.remove(cam)
    for light in list(bpy.data.lights):
        bpy.data.lights.remove(light)
    for world in list(bpy.data.worlds):
        bpy.data.worlds.remove(world)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)
    for img in list(bpy.data.images):
        bpy.data.images.remove(img)
    for group in list(bpy.data.node_groups):
        bpy.data.node_groups.remove(group)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)
    for collection in list(bpy.data.collections):
        if collection != scene.collection:
            bpy.data.collections.remove(collection)
    return scene


def imported_objects(before: set[str]) -> list[bpy.types.Object]:
    return [obj for obj in bpy.data.objects if obj.name not in before]


def import_model(path: Path) -> list[bpy.types.Object]:
    before = {obj.name for obj in bpy.data.objects}
    suffix = path.suffix.lower()
    filepath = str(path)
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=filepath)
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=filepath)
    else:
        raise SystemExit(f"Unsupported file type: {suffix}")

    objects = imported_objects(before)
    if not objects:
        raise SystemExit(f"Import produced no objects: {path}")

    # Drop cameras/lights that often ship inside GLBs. We use our studio.
    keep = []
    for obj in objects:
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            keep.append(obj)
    if not any(obj.type == "MESH" for obj in keep):
        raise SystemExit("Imported file has no mesh geometry.")
    return keep


def add_demo_subject() -> list[bpy.types.Object]:
    bpy.ops.mesh.primitive_monkey_add(size=2.0, location=(0.0, 0.0, 0.0))
    suzanne = bpy.context.active_object
    suzanne.name = "DemoProduct"
    bpy.ops.object.shade_smooth()
    mat = bpy.data.materials.new("DemoMaterial")
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get("Principled BSDF")
    if principled:
        principled.inputs["Base Color"].default_value = (0.72, 0.74, 0.78, 1.0)
        principled.inputs["Roughness"].default_value = 0.35
        if "Specular IOR Level" in principled.inputs:
            principled.inputs["Specular IOR Level"].default_value = 0.4
    suzanne.data.materials.append(mat)
    return [suzanne]


def mesh_objects(objects: list[bpy.types.Object]) -> list[bpy.types.Object]:
    meshes = []
    for obj in objects:
        if obj.type == "MESH":
            meshes.append(obj)
        meshes.extend(child for child in obj.children_recursive if child.type == "MESH")
    # Unique, stable order
    seen = set()
    unique = []
    for obj in meshes:
        if obj.name not in seen:
            seen.add(obj.name)
            unique.append(obj)
    return unique


def world_bbox(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    mins = Vector((math.inf, math.inf, math.inf))
    maxs = Vector((-math.inf, -math.inf, -math.inf))
    found = False
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in mesh_objects(objects):
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            for vert in mesh.vertices:
                point = evaluated.matrix_world @ vert.co
                mins.x = min(mins.x, point.x)
                mins.y = min(mins.y, point.y)
                mins.z = min(mins.z, point.z)
                maxs.x = max(maxs.x, point.x)
                maxs.y = max(maxs.y, point.y)
                maxs.z = max(maxs.z, point.z)
                found = True
        finally:
            evaluated.to_mesh_clear()
    if not found:
        raise SystemExit("Could not compute object bounds.")
    return mins, maxs


def parent_to_root(objects: list[bpy.types.Object]) -> bpy.types.Object:
    root = bpy.data.objects.new("Product", None)
    bpy.context.scene.collection.objects.link(root)
    imported = set(objects)
    roots = [obj for obj in objects if obj.parent not in imported]
    for obj in roots:
        world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world
    return root


def floor_material_roughness(minimum: float = 0.42) -> None:
    """Keep foil/metal from clipping to white under studio lights."""
    for mat in bpy.data.materials:
        if not mat.use_nodes or mat.node_tree is None:
            continue
        tree = mat.node_tree
        for node in list(tree.nodes):
            if node.type != "BSDF_PRINCIPLED":
                continue
            sock = node.inputs.get("Roughness")
            if sock is None:
                continue
            if sock.links:
                incoming = sock.links[0]
                from_socket = incoming.from_socket
                tree.links.remove(incoming)
                math_node = tree.nodes.new("ShaderNodeMath")
                math_node.operation = "MAXIMUM"
                math_node.location = (node.location.x - 200, node.location.y - 90)
                math_node.inputs[1].default_value = minimum
                tree.links.new(from_socket, math_node.inputs[0])
                tree.links.new(math_node.outputs[0], sock)
            else:
                sock.default_value = max(float(sock.default_value), minimum)


def center_product(root: bpy.types.Object, objects: list[bpy.types.Object]) -> dict:
    bpy.context.view_layer.update()
    mins, maxs = world_bbox(objects)
    center = (mins + maxs) * 0.5
    root.location -= center
    bpy.context.view_layer.update()
    mins, maxs = world_bbox(objects)
    size = maxs - mins
    radius = size.length * 0.5
    return {
        "min": list(mins),
        "max": list(maxs),
        "size": list(size),
        "radius": radius,
        "center": [0.0, 0.0, 0.0],
    }


def setup_white_world(scene: bpy.types.Scene, config: dict) -> None:
    """White backdrop in-camera, without the world shader blasting the product."""
    world = bpy.data.worlds.new("StudioWorld")
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    background.inputs["Strength"].default_value = float(config.get("ambient", 0.08))
    output = nodes.new("ShaderNodeOutputWorld")
    links.new(background.outputs["Background"], output.inputs["Surface"])

    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = float(config.get("exposure", 0.0))
    scene.view_settings.gamma = 1.0
    scene.display_settings.display_device = "sRGB"
    scene.render.film_transparent = True
    scene.render.use_motion_blur = False
    scene.render.dither_intensity = 1.0
    scene.render.use_compositing = True
    scene.render.use_sequencer = False
    scene.use_nodes = True

    tree = scene.node_tree
    tree.nodes.clear()
    render_layers = tree.nodes.new("CompositorNodeRLayers")
    render_layers.location = (0, 0)
    alpha_over = tree.nodes.new("CompositorNodeAlphaOver")
    alpha_over.location = (280, 0)
    alpha_over.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)
    composite = tree.nodes.new("CompositorNodeComposite")
    composite.location = (520, 0)
    tree.links.new(render_layers.outputs["Image"], alpha_over.inputs[2])
    tree.links.new(alpha_over.outputs["Image"], composite.inputs["Image"])


def aim_at(obj: bpy.types.Object, look_at: Vector) -> None:
    direction = look_at - obj.location
    if direction.length > 1e-6:
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_area_light(
    name: str,
    location: Vector,
    energy: float,
    size: float,
    look_at: Vector,
    specular: float = 0.45,
) -> bpy.types.Object:
    light_data = bpy.data.lights.new(name, type="AREA")
    light_data.shape = "SQUARE"
    light_data.size = size
    light_data.energy = energy
    light_data.color = (1.0, 1.0, 1.0)
    light_data.use_shadow = True
    if hasattr(light_data, "specular_factor"):
        light_data.specular_factor = specular
    obj = bpy.data.objects.new(name, light_data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    aim_at(obj, look_at)
    return obj


def add_sun_light(name: str, location: Vector, energy: float, look_at: Vector) -> bpy.types.Object:
    light_data = bpy.data.lights.new(name, type="SUN")
    light_data.energy = energy
    light_data.angle = math.radians(35.0)
    light_data.color = (1.0, 1.0, 1.0)
    light_data.use_shadow = True
    if hasattr(light_data, "specular_factor"):
        light_data.specular_factor = 0.35
    obj = bpy.data.objects.new(name, light_data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    aim_at(obj, look_at)
    return obj


def size_scale(scale: float, multiplier: float) -> float:
    return scale * 1.3 * multiplier


def setup_studio_lights(radius: float, config: dict) -> list[dict]:
    brightness = float(config.get("light_brightness", 1.0))
    # Keep lights close enough that a small pack still gets a real key/fill.
    scale = max(radius * 4.0, 0.5)
    target = Vector((0.0, 0.0, 0.0))
    factor = (scale / 0.6) ** 2
    specs = [
        ("FrontLight", Vector((scale * 0.35, -scale * 2.6, scale * 0.55)), 28.0 * brightness * factor, size_scale(scale, 1.0), 0.18),
        ("KeyLight", Vector((scale * 1.7, -scale * 1.9, scale * 2.1)), 24.0 * brightness * factor, size_scale(scale, 1.0), 0.22),
        ("FillLight", Vector((-scale * 2.2, -scale * 1.1, scale * 1.5)), 16.0 * brightness * factor, size_scale(scale, 1.2), 0.12),
        ("RimLight", Vector((scale * 0.4, scale * 2.4, scale * 1.8)), 10.0 * brightness * factor, size_scale(scale, 0.7), 0.2),
        ("TopLight", Vector((0.0, -scale * 0.2, scale * 3.4)), 6.0 * brightness * factor, size_scale(scale, 1.0), 0.08),
    ]
    placed = []
    for name, location, energy, size, specular in specs:
        light = add_area_light(name, location, energy, size, target, specular)
        placed.append({"object": light, "rest_location": location.copy()})
    sun_strength = float(config.get("sun_strength", 0.0)) * brightness
    if sun_strength > 0.05:
        location = Vector((scale * 1.3, -scale * 2.0, scale * 2.2))
        light = add_sun_light("KeySun", location, sun_strength, target)
        placed.append({"object": light, "rest_location": location.copy()})
    return placed


def configure_engine(scene: bpy.types.Scene, config: dict) -> None:
    engine = str(config.get("engine", "EEVEE")).upper()
    if engine == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = int(config.get("cycles_samples", 64))
        scene.cycles.use_denoising = True
        if config.get("use_gpu", True):
            scene.cycles.device = "GPU"
            prefs = bpy.context.preferences.addons.get("cycles")
            if prefs:
                cprefs = prefs.preferences
                try:
                    cprefs.compute_device_type = "OPTIX"
                    cprefs.get_devices()
                except Exception:
                    try:
                        cprefs.compute_device_type = "CUDA"
                        cprefs.get_devices()
                    except Exception:
                        try:
                            cprefs.compute_device_type = "HIP"
                            cprefs.get_devices()
                        except Exception:
                            scene.cycles.device = "CPU"
                for device in getattr(cprefs, "devices", []):
                    device.use = True
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        eevee = scene.eevee
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = int(config.get("eevee_samples", 64))
        if hasattr(eevee, "use_shadows"):
            eevee.use_shadows = True
        if hasattr(eevee, "use_raytracing"):
            eevee.use_raytracing = False


def setup_camera(scene: bpy.types.Scene, lens_mm: float) -> tuple[bpy.types.Object, bpy.types.Object]:
    target = bpy.data.objects.new("LookAt", None)
    bpy.context.scene.collection.objects.link(target)
    target.location = (0.0, 0.0, 0.0)

    cam_data = bpy.data.cameras.new("StudioCamera")
    cam_data.lens = lens_mm
    cam_data.sensor_width = 36.0
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.clip_start = 0.01
    cam_data.clip_end = 1000.0
    camera = bpy.data.objects.new("StudioCamera", cam_data)
    bpy.context.scene.collection.objects.link(camera)
    scene.camera = camera

    track = camera.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    return camera, target


def camera_distance(camera: bpy.types.Object, radius: float, fill: float) -> float:
    fill = max(0.15, min(fill, 0.95))
    angle = float(camera.data.angle_x)
    return (radius / math.tan(angle * 0.5)) / fill


def spherical_location(distance: float, azimuth_deg: float, elev_deg: float) -> Vector:
    # TRACK_TO gimbal-locks looking straight down; nudge off the exact pole.
    if abs(elev_deg - 90.0) < 0.35:
        elev_deg = 90.35 if elev_deg >= 90.0 else 89.65
    az = math.radians(azimuth_deg)
    el = math.radians(elev_deg)
    x = distance * math.cos(el) * math.sin(az)
    y = -distance * math.cos(el) * math.cos(az)
    z = distance * math.sin(el)
    return Vector((x, y, z))


def clear_animation(obj: bpy.types.Object) -> None:
    obj.animation_data_clear()


def key_camera_path(camera: bpy.types.Object, locations: list[Vector], frames: int) -> None:
    clear_animation(camera)
    if frames <= 1:
        camera.location = locations[0]
        return
    for index, location in enumerate(locations):
        frame = index + 1
        camera.location = location
        camera.keyframe_insert(data_path="location", frame=frame)
    if camera.animation_data and camera.animation_data.action:
        for fcurve in camera.animation_data.action.fcurves:
            for key in fcurve.keyframe_points:
                key.interpolation = "LINEAR"


def follow_rotation(azimuth_deg: float, elev_deg: float) -> Matrix:
    """Rotate the rest studio (camera on -Y) onto the current camera heading."""
    rx = Matrix.Rotation(math.radians(-elev_deg), 4, "X")
    rz = Matrix.Rotation(math.radians(azimuth_deg), 4, "Z")
    return rz @ rx


def key_follow_lights(lights: list[dict], frames_data: list[dict], follow: bool) -> None:
    origin = Vector((0.0, 0.0, 0.0))
    for item in lights:
        clear_animation(item["object"])
    for index, frame_data in enumerate(frames_data):
        frame = index + 1
        if follow:
            rotation = follow_rotation(frame_data["azimuth_deg"], frame_data["elev_deg"])
        else:
            rotation = Matrix.Identity(4)
        for item in lights:
            light = item["object"]
            light.location = rotation @ item["rest_location"]
            aim_at(light, origin)
            light.keyframe_insert(data_path="location", frame=frame)
            light.keyframe_insert(data_path="rotation_euler", frame=frame)
    for item in lights:
        action = item["object"].animation_data.action if item["object"].animation_data else None
        if action:
            for fcurve in action.fcurves:
                for key in fcurve.keyframe_points:
                    key.interpolation = "LINEAR"


def shot_path(shot: dict, camera: bpy.types.Object, radius: float, default_fill: float) -> list[dict]:
    shot_type = shot["type"]
    frames = max(1, int(shot["_frames"]))
    path = []
    if shot_type == "orbit":
        fill = float(shot.get("fill", default_fill))
        distance = camera_distance(camera, radius, fill)
        start = float(shot["azimuth_start_deg"])
        end = float(shot["azimuth_end_deg"])
        elev = float(shot["elev_deg"])
        for i in range(frames):
            t = i / max(frames - 1, 1)
            azimuth = start + (end - start) * t
            path.append(
                {
                    "location": spherical_location(distance, azimuth, elev),
                    "azimuth_deg": azimuth,
                    "elev_deg": elev,
                }
            )
        return path

    if shot_type == "helix":
        fill = float(shot.get("fill", default_fill))
        distance = camera_distance(camera, radius, fill)
        az0 = float(shot["azimuth_start_deg"])
        az1 = float(shot["azimuth_end_deg"])
        el0 = float(shot["elev_start_deg"])
        el1 = float(shot["elev_end_deg"])
        for i in range(frames):
            t = i / max(frames - 1, 1)
            azimuth = az0 + (az1 - az0) * t
            elev = el0 + (el1 - el0) * t
            path.append(
                {
                    "location": spherical_location(distance, azimuth, elev),
                    "azimuth_deg": azimuth,
                    "elev_deg": elev,
                }
            )
        return path

    if shot_type == "vertical":
        fill = float(shot.get("fill", default_fill))
        distance = camera_distance(camera, radius, fill)
        azimuth = float(shot["azimuth_deg"])
        el0 = float(shot["elev_start_deg"])
        el1 = float(shot["elev_end_deg"])
        for i in range(frames):
            t = i / max(frames - 1, 1)
            elev = el0 + (el1 - el0) * t
            path.append(
                {
                    "location": spherical_location(distance, azimuth, elev),
                    "azimuth_deg": azimuth,
                    "elev_deg": elev,
                }
            )
        return path

    if shot_type == "dolly":
        az = float(shot["azimuth_deg"])
        elev = float(shot["elev_deg"])
        fill0 = float(shot["fill_start"])
        fill1 = float(shot["fill_end"])
        for i in range(frames):
            t = i / max(frames - 1, 1)
            fill = fill0 + (fill1 - fill0) * t
            distance = camera_distance(camera, radius, fill)
            path.append(
                {
                    "location": spherical_location(distance, az, elev),
                    "azimuth_deg": az,
                    "elev_deg": elev,
                }
            )
        return path

    raise SystemExit(f"Unknown shot type: {shot_type}")


def configure_output(scene: bpy.types.Scene, config: dict) -> None:
    width, height = config.get("resolution", [1920, 1080])
    scene.render.resolution_x = int(width)
    scene.render.resolution_y = int(height)
    scene.render.resolution_percentage = 100
    scene.render.fps = int(config.get("fps", 30))
    scene.render.fps_base = 1.0
    scene.render.use_file_extension = True
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"


def set_ffmpeg(scene: bpy.types.Scene) -> None:
    scene.render.image_settings.file_format = "FFMPEG"
    ffmpeg = scene.render.ffmpeg
    ffmpeg.format = "MPEG4"
    ffmpeg.codec = "H264"
    ffmpeg.audio_codec = "NONE"
    ffmpeg.constant_rate_factor = "HIGH"
    ffmpeg.ffmpeg_preset = "GOOD"
    ffmpeg.gopsize = 12


def set_png(scene: bpy.types.Scene) -> None:
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.compression = 15


def enabled_shots(config: dict, only: str) -> list[dict]:
    wanted = {item.strip() for item in only.split(",") if item.strip()} if only else set()
    shots = []
    for shot in config.get("shots", []):
        if wanted:
            if shot.get("id") in wanted:
                shots.append(shot)
        elif shot.get("enabled", True):
            shots.append(shot)
    if not shots:
        raise SystemExit("No shots selected. Check config.json or --shots.")
    fps = int(config.get("fps", 30))
    for shot in shots:
        seconds = float(shot.get("seconds", 4))
        shot["_frames"] = max(2, int(round(seconds * fps)))
    return shots


def write_sidecar(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def render_shot(
    scene: bpy.types.Scene,
    camera: bpy.types.Object,
    lights: list[dict],
    shot: dict,
    frames_data: list[dict],
    output_dir: Path,
    preview: bool,
    write_png: bool,
    write_video: bool,
    every: int,
    lights_follow_camera: bool,
) -> dict:
    shot_id = shot["id"]
    frames = len(frames_data)
    locations = [item["location"] for item in frames_data]
    key_camera_path(camera, locations, frames)
    key_follow_lights(lights, frames_data, lights_follow_camera)
    scene.frame_start = 1
    scene.frame_end = frames
    scene.frame_current = 1
    bpy.context.view_layer.update()

    result = {
        "id": shot_id,
        "type": shot["type"],
        "frames": frames,
        "description": shot.get("description", ""),
        "lights_follow_camera": lights_follow_camera,
    }

    if preview:
        preview_dir = output_dir / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        set_png(scene)
        scene.frame_set(1)
        scene.render.filepath = str(preview_dir / f"{shot_id}.png")
        bpy.ops.render.render(write_still=True)
        result["preview"] = str(preview_dir / f"{shot_id}.png")
        print(f"[preview] {shot_id} -> {result['preview']}")
        return result

    if write_video:
        set_ffmpeg(scene)
        mp4_path = output_dir / f"{shot_id}.mp4"
        scene.render.filepath = str(mp4_path)
        print(f"[render] {shot_id}  {frames} frames  -> {mp4_path}")
        bpy.ops.render.render(animation=True)
        result["mp4"] = str(mp4_path)

    if write_png:
        png_dir = output_dir / shot_id
        png_dir.mkdir(parents=True, exist_ok=True)
        set_png(scene)
        selected = png_frame_numbers(frames, every)
        print(f"[png] {shot_id}  {len(selected)}/{frames} stills (every {every}) -> {png_dir}")
        if every <= 1:
            scene.render.filepath = str(png_dir / "frame_")
            bpy.ops.render.render(animation=True)
        else:
            for frame in selected:
                scene.frame_set(frame)
                scene.render.filepath = str(png_dir / f"frame_{frame:04d}")
                bpy.ops.render.render(write_still=True)
        result["png_sequence"] = str(png_dir)
        result["png_every"] = every
        result["png_frames"] = selected

    return result


def list_model_files(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(
        path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED
    )


def resolve_input_models(input_arg: str) -> list[Path]:
    if input_arg:
        path = Path(input_arg).expanduser().resolve()
        if path.is_file():
            if path.suffix.lower() not in SUPPORTED:
                raise SystemExit(f"Unsupported file type: {path.suffix}")
            return [path]
        if path.is_dir():
            files = list_model_files(path)
            if not files:
                raise SystemExit(f"No .glb/.gltf/.fbx/.obj files in {path}")
            return files
        raise SystemExit(f"Input not found: {path}")
    files = list_model_files(ROOT / "input")
    if not files:
        raise SystemExit(
            "No model found. Put a .glb / .gltf / .fbx / .obj in the input folder, "
            "pass --input, or use --demo."
        )
    return files


def unique_stems(paths: list[Path]) -> list[str]:
    used: dict[str, int] = {}
    stems = []
    for path in paths:
        base = path.stem or "model"
        key = base.lower()
        if key in used:
            used[key] += 1
            stems.append(f"{base}_{used[key]}")
        else:
            used[key] = 1
            stems.append(base)
    return stems


def render_model(
    input_path: Path | None,
    model_name: str,
    output_dir: Path,
    config: dict,
    config_path: Path,
    args: argparse.Namespace,
    write_png: bool,
    write_video: bool,
    every: int,
    lights_follow_camera: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== {model_name} ===")
    scene = reset_scene()
    objects = add_demo_subject() if args.demo else import_model(input_path)
    root = parent_to_root(objects)
    bounds = center_product(root, objects)
    floor_material_roughness()

    setup_white_world(scene, config)
    lights = setup_studio_lights(bounds["radius"], config)
    configure_engine(scene, config)
    configure_output(scene, config)
    camera, _target = setup_camera(scene, float(config.get("lens_mm", 50)))

    shots = enabled_shots(config, args.shots)
    default_fill = float(config.get("fill", 0.68))
    results = []
    for shot in shots:
        frames_data = shot_path(shot, camera, bounds["radius"], default_fill)
        results.append(
            render_shot(
                scene,
                camera,
                lights,
                shot,
                frames_data,
                output_dir,
                preview=args.preview,
                write_png=write_png,
                write_video=write_video,
                every=every,
                lights_follow_camera=lights_follow_camera,
            )
        )

    if args.save_blend:
        blend_path = output_dir / "studio.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        print(f"[blend] {blend_path}")

    sidecar = {
        "input": None if args.demo else str(input_path),
        "demo": bool(args.demo),
        "model": model_name,
        "output": str(output_dir),
        "config": str(config_path),
        "resolution": config.get("resolution"),
        "fps": config.get("fps"),
        "engine": config.get("engine"),
        "lights_follow_camera": lights_follow_camera,
        "png_every": every if write_png else None,
        "bounds": bounds,
        "clips": results,
    }
    sidecar_name = "preview.json" if args.preview else "dataset.json"
    write_sidecar(output_dir / sidecar_name, sidecar)
    print(f"Done: {model_name}")
    for item in results:
        print(f"  - {item['id']}: {item.get('mp4') or item.get('png_sequence') or item.get('preview')}")


def main() -> None:
    args = parse_args(blender_argv())
    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        raise SystemExit(f"Config not found: {config_path}")
    config = load_config(config_path)
    if args.list_shots:
        print_shot_list(config)
        return

    lights_follow_camera = True
    if args.lights_follow_camera is not None:
        lights_follow_camera = bool(args.lights_follow_camera)
    write_png = bool(args.png)
    write_video = bool(args.mp4)
    every = max(1, int(args.png_interval))
    if not args.preview and not write_png and not write_video:
        raise SystemExit(
            "Need an output format. Re-run with --mp4, --png, or both."
        )

    output_root = Path(args.output).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if args.demo:
        jobs = [(None, "demo")]
    else:
        models = resolve_input_models(args.input)
        jobs = list(zip(models, unique_stems(models)))

    print(f"Models: {len(jobs)}")
    for _path, name in jobs:
        label = "demo" if _path is None else _path.name
        print(f"  - {label}  ->  {output_root / name}")

    for input_path, model_name in jobs:
        render_model(
            input_path,
            model_name,
            output_root / model_name,
            config,
            config_path,
            args,
            write_png,
            write_video,
            every,
            lights_follow_camera,
        )

    print("\nAll models finished.")


if __name__ == "__main__":
    main()

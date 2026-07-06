#!/usr/bin/env python3
"""
Convert an image to a splash logo for MeshCore firmware.

Usage:
    python3 bin/generate_splash.py <image.png> [--invert] [--build ENV] [--commit]
    python3 bin/generate_splash.py <image.png> --color [--build ENV] [--commit]

Requires: ImageMagick (magick command).

Without --color: produces a 128x64 monochrome bitmap (MSB-first packed, 1024 bytes).
With --color: produces a 240x135 RGB565 color image (byte-swapped, ~64 KB).
"""

import subprocess, sys, os, re, tempfile, argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
ICONS_H = os.path.join(PROJECT_DIR, "examples", "companion_radio", "ui-new", "icons.h")
ARRAY_NAME = "custom_splash_logo"
ARRAY_NAME_COLOR = "custom_splash_logo_rgb565"
WIDTH, HEIGHT = 128, 64
NATIVE_WIDTH, NATIVE_HEIGHT = 240, 135


def convert_image(image_path, invert=False):
    tmp = os.path.join(tempfile.gettempdir(), "splash.pbm")

    cmd = [
        "magick", image_path,
        "-resize", f"{WIDTH}x{HEIGHT}",
        "-gravity", "center",
        "-background", "white",
        "-extent", f"{WIDTH}x{HEIGHT}",
        "-threshold", "50%",
    ]
    if invert:
        cmd.append("-negate")
    cmd.append(f"pbm:{tmp}")

    subprocess.run(cmd, check=True)

    with open(tmp, "rb") as f:
        header = f.readline()  # P4\n
        line = f.readline()
        while line.startswith(b"#"):
            line = f.readline()
        data = f.read()

    os.unlink(tmp)

    expected = WIDTH * HEIGHT // 8
    if len(data) != expected:
        print(f"Error: expected {expected} bytes, got {len(data)}", file=sys.stderr)
        sys.exit(1)

    return data


def convert_image_color(image_path):
    tmp = os.path.join(tempfile.gettempdir(), "splash_rgb.raw")

    cmd = [
        "magick", image_path,
        "-auto-orient",
        "-resize", f"{NATIVE_WIDTH}x{NATIVE_HEIGHT}^",
        "-gravity", "center",
        "-extent", f"{NATIVE_WIDTH}x{NATIVE_HEIGHT}",
        "-depth", "8",
        f"rgb:{tmp}",
    ]
    subprocess.run(cmd, check=True)

    with open(tmp, "rb") as f:
        raw = f.read()
    os.unlink(tmp)

    expected = NATIVE_WIDTH * NATIVE_HEIGHT * 3
    if len(raw) != expected:
        print(f"Error: expected {expected} bytes, got {len(raw)}", file=sys.stderr)
        sys.exit(1)

    import struct
    pixels = []
    for i in range(0, len(raw), 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        swapped = ((rgb565 >> 8) & 0xFF) | ((rgb565 & 0xFF) << 8)
        pixels.append(swapped)

    return struct.pack(f"<{len(pixels)}H", *pixels)


def format_c_array_color(data):
    import struct
    count = len(data) // 2
    pixels = struct.unpack(f"<{count}H", data)
    lines = [f"static const uint16_t {ARRAY_NAME_COLOR} [] PROGMEM = {{"]
    for i in range(0, len(pixels), 10):
        chunk = pixels[i : i + 10]
        hex_vals = ", ".join(f"0x{v:04x}" for v in chunk)
        lines.append(f"  {hex_vals},")
    lines.append("};")
    return "\n".join(lines)


def format_c_array(data):
    lines = [f"static const uint8_t {ARRAY_NAME} [] = {{"]
    for i in range(0, len(data), 12):
        chunk = data[i : i + 12]
        hex_bytes = ", ".join(f"0x{b:02x}" for b in chunk)
        lines.append(f"  {hex_bytes},")
    lines.append("};")
    return "\n".join(lines)


def update_icons_h(c_array, array_name=None, dtype="uint8_t"):
    with open(ICONS_H, "r") as f:
        content = f.read()

    name = array_name or ARRAY_NAME
    pattern = rf"static const {dtype} {re.escape(name)}\s*\[\]\s*(?:PROGMEM\s*)?=\s*\{{[^}}]+\}};"
    if re.search(pattern, content):
        new_content = re.sub(pattern, c_array, content)
    else:
        idx = content.find("\n", content.rfind("#include")) + 1
        if idx <= 0:
            idx = len(content)
        new_content = content[:idx] + "\n" + c_array + "\n" + content[idx:]

    with open(ICONS_H, "w") as f:
        f.write(new_content)

    print(f"Updated {ICONS_H}")


def build(env_name):
    print(f"\nBuilding {env_name}...")
    subprocess.run(
        ["pio", "run", "-e", env_name],
        cwd=PROJECT_DIR, check=True,
        env={**os.environ, "FIRMWARE_VERSION": os.environ.get("FIRMWARE_VERSION", "v1.16.0")},
    )

    print(f"Generating UF2...")
    subprocess.run(
        ["pio", "run", "-e", env_name, "-t", "create_uf2"],
        cwd=PROJECT_DIR, check=True,
        env={**os.environ, "FIRMWARE_VERSION": os.environ.get("FIRMWARE_VERSION", "v1.16.0")},
    )

    uf2_src = os.path.join(PROJECT_DIR, ".pio", "build", env_name, "firmware.uf2")
    uf2_dst = os.path.join(SCRIPT_DIR, f"{env_name}.uf2")
    if os.path.exists(uf2_src):
        import shutil
        shutil.copy2(uf2_src, uf2_dst)
        print(f"UF2 ready: {uf2_dst}")
    else:
        print(f"Warning: {uf2_src} not found", file=sys.stderr)


def commit_and_push(env_name):
    uf2_file = os.path.join("bin", f"{env_name}.uf2")
    icons_rel = os.path.relpath(ICONS_H, PROJECT_DIR)

    subprocess.run(["git", "add", icons_rel, uf2_file], cwd=PROJECT_DIR, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Update custom splash logo and firmware"],
        cwd=PROJECT_DIR, check=True,
    )
    subprocess.run(["git", "push"], cwd=PROJECT_DIR, check=True)
    print("Committed and pushed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", help="Input image (PNG, JPG, etc.)")
    parser.add_argument("--invert", action="store_true", help="Invert colors (bright logo on dark background)")
    parser.add_argument("--color", action="store_true", help="Generate 240x135 RGB565 color image instead of 128x64 mono")
    parser.add_argument("--build", metavar="ENV", help="PlatformIO env to build (e.g. Heltec_t114_companion_radio_ble)")
    parser.add_argument("--commit", action="store_true", help="git add, commit, and push after build")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"File not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    if args.color:
        data = convert_image_color(args.image)
        c_array = format_c_array_color(data)
        print(f"\nGenerated {ARRAY_NAME_COLOR} ({len(data)} bytes, {NATIVE_WIDTH}x{NATIVE_HEIGHT} RGB565)")
        update_icons_h(c_array, array_name=ARRAY_NAME_COLOR, dtype="uint16_t")
    else:
        data = convert_image(args.image, args.invert)
        c_array = format_c_array(data)
        print(f"\nGenerated {ARRAY_NAME} ({len(data)} bytes, {WIDTH}x{HEIGHT})")
        update_icons_h(c_array)

    if args.build:
        build(args.build)
        if args.commit:
            commit_and_push(args.build)
    elif args.commit:
        print("--commit requires --build", file=sys.stderr)
        sys.exit(1)
    else:
        print("\nTo build and flash:")
        print(f"  python3 bin/generate_splash.py {args.image} --build Heltec_t114_companion_radio_ble")
        print("\nTo also commit and push:")
        print(f"  python3 bin/generate_splash.py {args.image} --build Heltec_t114_companion_radio_ble --commit")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Convert an image to a 128x64 splash logo for MeshCore firmware.

Usage:
    python3 bin/generate_splash.py <image.png> [--invert] [--build ENV] [--commit]

Requires: ImageMagick (magick command).

The bitmap is written in MSB-first packed format, matching the Adafruit GFX
drawBitmap convention used by MeshCore display drivers (SSD1306, ST7789).
Standard XBM is LSB-first and will render garbled -- this script avoids that.
"""

import subprocess, sys, os, re, tempfile, argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
ICONS_H = os.path.join(PROJECT_DIR, "examples", "companion_radio", "ui-new", "icons.h")
ARRAY_NAME = "custom_splash_logo"
WIDTH, HEIGHT = 128, 64


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


def format_c_array(data):
    lines = [f"static const uint8_t {ARRAY_NAME} [] = {{"]
    for i in range(0, len(data), 12):
        chunk = data[i : i + 12]
        hex_bytes = ", ".join(f"0x{b:02x}" for b in chunk)
        lines.append(f"  {hex_bytes},")
    lines.append("};")
    return "\n".join(lines)


def update_icons_h(c_array):
    with open(ICONS_H, "r") as f:
        content = f.read()

    pattern = r"static const uint8_t custom_splash_logo\s*\[\]\s*=\s*\{[^}]+\};"
    if re.search(pattern, content):
        new_content = re.sub(pattern, c_array, content)
    else:
        idx = content.find("\n", content.rfind("#include")) + 1
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
    parser.add_argument("--build", metavar="ENV", help="PlatformIO env to build (e.g. Heltec_t114_companion_radio_ble)")
    parser.add_argument("--commit", action="store_true", help="git add, commit, and push after build")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"File not found: {args.image}", file=sys.stderr)
        sys.exit(1)

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

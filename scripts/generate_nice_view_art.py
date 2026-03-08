#!/usr/bin/env python3
"""
Generate nice_view_custom widgets/art.c and widgets/art.h from image files.

Requires Pillow:
    python -m pip install pillow
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, NoReturn, Sequence

try:
    from PIL import Image, ImageOps, ImageSequence
except ImportError:
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]
    ImageSequence = None  # type: ignore[assignment]


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
DEFAULT_WIDTH = 140
DEFAULT_HEIGHT = 68
DEFAULT_THRESHOLD = 128
DEFAULT_FRAME_DURATION_MS = 100
DEFAULT_RESIZE_MODE = "contain"
DEFAULT_ROTATE = "cw"


def lanczos_resample() -> int:
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS  # type: ignore[union-attr]
    return Image.LANCZOS  # type: ignore[union-attr]


@dataclass
class Frame:
    symbol: str
    source_label: str
    width: int
    height: int
    pixel_bytes: bytes

    @property
    def data_size(self) -> int:
        # 8-byte palette + packed pixels.
        return 8 + len(self.pixel_bytes)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate nice_view_custom/widgets/art.c and art.h from image frames."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Image files and/or directories of images (sorted by name). Animated files add all frames.",
    )
    parser.add_argument(
        "--output-c",
        default="boards/shields/nice_view_custom/widgets/art.c",
        help="Path to generated art.c (default: %(default)s).",
    )
    parser.add_argument(
        "--output-h",
        default="boards/shields/nice_view_custom/widgets/art.h",
        help="Path to generated art.h (default: %(default)s).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_WIDTH,
        help=f"Output frame width in pixels (default: {DEFAULT_WIDTH}).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_HEIGHT,
        help=f"Output frame height in pixels (default: {DEFAULT_HEIGHT}).",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help=f"Grayscale threshold 0-255 for black/white conversion (default: {DEFAULT_THRESHOLD}).",
    )
    parser.add_argument(
        "--frame-duration-ms",
        type=int,
        default=DEFAULT_FRAME_DURATION_MS,
        help=f"Per-frame duration in ms (default: {DEFAULT_FRAME_DURATION_MS}).",
    )
    parser.add_argument(
        "--resize-mode",
        choices=("cover", "contain", "stretch"),
        default=DEFAULT_RESIZE_MODE,
        help="Resize behavior before thresholding (default: %(default)s).",
    )
    parser.add_argument(
        "--rotate",
        choices=("none", "cw", "ccw", "180"),
        default=DEFAULT_ROTATE,
        help="Rotate each source frame before resize (default: %(default)s).",
    )
    return parser.parse_args()


def fail(message: str) -> "NoReturn":
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def collect_input_files(raw_inputs: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    for raw in raw_inputs:
        path = Path(raw)
        if not path.exists():
            fail(f"input path does not exist: {path}")
        if path.is_dir():
            dir_files = [
                child
                for child in sorted(path.iterdir())
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS
            ]
            if not dir_files:
                fail(f"no supported images found in directory: {path}")
            files.extend(dir_files)
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            fail(
                f"unsupported extension for {path} (supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))})"
            )
        files.append(path)
    return files


def rotate_image(image: Image.Image, rotate: str) -> Image.Image:
    if rotate == "none":
        return image
    if rotate == "cw":
        return image.transpose(Image.Transpose.ROTATE_270)
    if rotate == "ccw":
        return image.transpose(Image.Transpose.ROTATE_90)
    return image.transpose(Image.Transpose.ROTATE_180)


def preprocess_frame(
    frame_rgba: Image.Image,
    width: int,
    height: int,
    resize_mode: str,
    rotate: str,
    threshold: int,
) -> bytes:
    lanczos = lanczos_resample()
    frame_rgba = rotate_image(frame_rgba, rotate)
    if resize_mode == "stretch":
        sized = frame_rgba.resize((width, height), lanczos)
    elif resize_mode == "contain":
        contained = ImageOps.contain(frame_rgba, (width, height), method=lanczos)
        sized = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        left = (width - contained.width) // 2
        top = (height - contained.height) // 2
        sized.paste(contained, (left, top), contained)
    else:
        sized = ImageOps.fit(
            frame_rgba,
            (width, height),
            method=lanczos,
            centering=(0.5, 0.5),
        )

    # Blend alpha onto white so transparent pixels become white.
    flattened = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    flattened.alpha_composite(sized)
    gray = flattened.convert("L")

    bytes_per_row = (width + 7) // 8
    packed = bytearray(bytes_per_row * height)

    offset = 0
    for y in range(height):
        for byte_idx in range(bytes_per_row):
            value = 0
            for bit in range(8):
                x = byte_idx * 8 + bit
                if x >= width:
                    continue
                # Bit 1 -> palette index 1 (white); bit 0 -> palette index 0 (black)
                if gray.getpixel((x, y)) >= threshold:
                    value |= 1 << (7 - bit)
            packed[offset] = value
            offset += 1

    return bytes(packed)


def load_frames(
    files: Sequence[Path], width: int, height: int, resize_mode: str, rotate: str, threshold: int
) -> List[Frame]:
    frames: List[Frame] = []
    frame_index = 0

    for file_path in files:
        with Image.open(file_path) as img:
            for local_index, frame in enumerate(ImageSequence.Iterator(img)):
                rgba = ImageOps.exif_transpose(frame.convert("RGBA"))
                packed = preprocess_frame(rgba, width, height, resize_mode, rotate, threshold)
                symbol = f"custom_frame_{frame_index:03d}"
                if getattr(img, "is_animated", False):
                    label = f"{file_path.name}#{local_index}"
                else:
                    label = file_path.name
                frames.append(
                    Frame(
                        symbol=symbol,
                        source_label=label,
                        width=width,
                        height=height,
                        pixel_bytes=packed,
                    )
                )
                frame_index += 1

    if not frames:
        fail("no frames found after reading input images")
    if len(frames) > 255:
        fail(
            f"{len(frames)} frames generated, but LVGL animimg supports max 255 frames in this widget"
        )
    return frames


def format_hex_rows(data: bytes, row_width: int) -> str:
    lines: List[str] = []
    for offset in range(0, len(data), row_width):
        row = data[offset : offset + row_width]
        lines.append("  " + ", ".join(f"0x{value:02x}" for value in row) + ",")
    return "\n".join(lines)


def render_header(frame_count: int, frame_duration_ms: int) -> str:
    return f"""/*
 *
 * Auto-generated by scripts/generate_nice_view_art.py
 * SPDX-License-Identifier: MIT
 *
 */

#pragma once

#include <lvgl.h>

#define CUSTOM_ART_FRAME_COUNT {frame_count}
#define CUSTOM_ART_FRAME_DURATION_MS {frame_duration_ms}
#define CUSTOM_ART_ANIM_DURATION_MS (CUSTOM_ART_FRAME_COUNT * CUSTOM_ART_FRAME_DURATION_MS)

extern const lv_img_dsc_t *const custom_art_frames[CUSTOM_ART_FRAME_COUNT];
"""


def render_source(frames: Sequence[Frame]) -> str:
    blocks: List[str] = []
    bytes_per_row = (frames[0].width + 7) // 8

    for frame in frames:
        macro = frame.symbol.upper()
        pixels = format_hex_rows(frame.pixel_bytes, bytes_per_row)
        blocks.append(
            f"""/* Source: {frame.source_label} */
#ifndef LV_ATTRIBUTE_IMG_{macro}
#define LV_ATTRIBUTE_IMG_{macro}
#endif

const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST LV_ATTRIBUTE_IMG_{macro} uint8_t {frame.symbol}_map[] = {{
#if CONFIG_NICE_VIEW_WIDGET_INVERTED
    0xff, 0xff, 0xff, 0xff, /*Color of index 0*/
    0x00, 0x00, 0x00, 0xff, /*Color of index 1*/
#else
    0x00, 0x00, 0x00, 0xff, /*Color of index 0*/
    0xff, 0xff, 0xff, 0xff, /*Color of index 1*/
#endif
{pixels}
}};

const lv_img_dsc_t {frame.symbol} = {{
    .header.cf = LV_IMG_CF_INDEXED_1BIT,
    .header.always_zero = 0,
    .header.reserved = 0,
    .header.w = {frame.width},
    .header.h = {frame.height},
    .data_size = {frame.data_size},
    .data = {frame.symbol}_map,
}};
"""
        )

    frame_list = ",\n".join(f"    &{frame.symbol}" for frame in frames)

    return f"""/*
 *
 * Auto-generated by scripts/generate_nice_view_art.py
 * SPDX-License-Identifier: MIT
 *
 */

#include <lvgl.h>

#include "art.h"

#ifndef LV_ATTRIBUTE_MEM_ALIGN
#define LV_ATTRIBUTE_MEM_ALIGN
#endif

{"".join(blocks)}
const lv_img_dsc_t *const custom_art_frames[CUSTOM_ART_FRAME_COUNT] = {{
{frame_list}
}};
"""


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    args = parse_args()
    if Image is None or ImageOps is None or ImageSequence is None:
        fail("Pillow is required. Install with: python -m pip install pillow")
    if args.width <= 0 or args.height <= 0:
        fail("width and height must be positive integers")
    if not 0 <= args.threshold <= 255:
        fail("threshold must be in range 0-255")
    if args.frame_duration_ms <= 0:
        fail("frame-duration-ms must be > 0")

    input_files = collect_input_files(args.inputs)
    frames = load_frames(
        files=input_files,
        width=args.width,
        height=args.height,
        resize_mode=args.resize_mode,
        rotate=args.rotate,
        threshold=args.threshold,
    )

    output_h = Path(args.output_h)
    output_c = Path(args.output_c)

    write_file(output_h, render_header(len(frames), args.frame_duration_ms))
    write_file(output_c, render_source(frames))

    print(
        f"Generated {len(frames)} frames at {args.width}x{args.height}: "
        f"{output_h} and {output_c}"
    )


if __name__ == "__main__":
    main()

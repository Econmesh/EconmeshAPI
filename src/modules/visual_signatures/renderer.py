"""PNG rendering, sanitization, metadata embedding, and integrity hashing."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont, ImageOps
from PIL.PngImagePlugin import PngInfo

from src.modules.visual_signatures.fonts import get_font
from src.modules.visual_signatures.model import (
    GENERATION_VERSION,
    VisualSignatureKind,
    VisualSignatureSource,
)

SIGNATURE_SIZE = (640, 160)
INITIALS_SIZE = (240, 160)
_PADDING = 16
_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)
_THRESHOLD = 200


@dataclass(frozen=True, slots=True)
class RenderedImage:
    data: bytes
    sha256: str
    width: int
    height: int
    content_type: str = "image/png"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canvas_size_for(kind: VisualSignatureKind | str) -> tuple[int, int]:
    if VisualSignatureKind(kind) == VisualSignatureKind.INITIALS:
        return INITIALS_SIZE
    return SIGNATURE_SIZE


def _enum_str(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def render_automatic(
    text: str,
    *,
    font_id: str,
    kind: VisualSignatureKind,
    user_id: UUID,
    signature_id: UUID,
    created_at: datetime,
) -> RenderedImage:
    kind = VisualSignatureKind(kind)
    font_spec = get_font(font_id)
    width, height = canvas_size_for(kind)
    image = Image.new("RGB", (width, height), _WHITE)
    draw = ImageDraw.Draw(image)
    max_width = width - (_PADDING * 2)
    max_height = height - (_PADDING * 2)
    font, bbox = _fit_font(text, font_spec.path, max_width, max_height)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (width - text_w) // 2 - bbox[0]
    y = (height - text_h) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=_BLACK)
    return _encode(
        image,
        user_id=user_id,
        signature_id=signature_id,
        kind=kind,
        source=VisualSignatureSource.AUTOMATIC,
        font_id=font_id,
        source_text=text,
        created_at=created_at,
    )


def process_manual_png(
    raw: bytes,
    *,
    kind: VisualSignatureKind,
    user_id: UUID,
    signature_id: UUID,
    created_at: datetime,
) -> RenderedImage:
    kind = VisualSignatureKind(kind)
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid_png") from exc

    rgb = ImageOps.exif_transpose(image.convert("RGBA"))
    background = Image.new("RGBA", rgb.size, (*_WHITE, 255))
    composited = Image.alpha_composite(background, rgb).convert("L")
    binary = composited.point(lambda px: 0 if px < _THRESHOLD else 255, mode="L")
    sanitized = binary.convert("RGB")
    target = canvas_size_for(kind)
    sanitized.thumbnail(target, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", target, _WHITE)
    offset = (
        (target[0] - sanitized.size[0]) // 2,
        (target[1] - sanitized.size[1]) // 2,
    )
    canvas.paste(sanitized, offset)
    return _encode(
        canvas,
        user_id=user_id,
        signature_id=signature_id,
        kind=kind,
        source=VisualSignatureSource.MANUAL,
        font_id=None,
        source_text="",
        created_at=created_at,
    )


def _fit_font(
    text: str,
    font_path: object,
    max_width: int,
    max_height: int,
    *,
    min_size: int = 18,
    max_size: int = 96,
) -> tuple[ImageFont.FreeTypeFont, tuple[int, int, int, int]]:
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8), _WHITE))
    best: tuple[ImageFont.FreeTypeFont, tuple[int, int, int, int]] | None = None
    lo, hi = min_size, max_size
    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(str(font_path), mid)
        bbox = probe.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= max_width and height <= max_height:
            best = (font, bbox)
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        font = ImageFont.truetype(str(font_path), min_size)
        bbox = probe.textbbox((0, 0), text, font=font)
        return font, bbox
    return best


def _encode(
    image: Image.Image,
    *,
    user_id: UUID,
    signature_id: UUID,
    kind: VisualSignatureKind,
    source: VisualSignatureSource,
    font_id: str | None,
    source_text: str,
    created_at: datetime,
) -> RenderedImage:
    info = PngInfo()
    info.add_text("EconmeshUserId", str(user_id))
    info.add_text("EconmeshSignatureId", str(signature_id))
    info.add_text("EconmeshKind", _enum_str(kind))
    info.add_text("EconmeshSource", _enum_str(source))
    info.add_text("EconmeshCreatedAt", created_at.isoformat())
    info.add_text("EconmeshGenerationVersion", GENERATION_VERSION)
    if font_id:
        info.add_text("EconmeshFontId", font_id)
    if source_text:
        info.add_text("EconmeshSourceText", source_text)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", pnginfo=info, optimize=True)
    data = buffer.getvalue()
    return RenderedImage(
        data=data,
        sha256=sha256_bytes(data),
        width=image.width,
        height=image.height,
    )


__all__ = [
    "INITIALS_SIZE",
    "SIGNATURE_SIZE",
    "RenderedImage",
    "canvas_size_for",
    "process_manual_png",
    "render_automatic",
    "sha256_bytes",
]

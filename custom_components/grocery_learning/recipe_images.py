"""Bounded local recipe images; no Home Assistant dependencies."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import ipaddress
import re
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from PIL import Image, ImageOps

MAX_INPUT = 8 * 1024 * 1024
MAX_OUTPUT = 256 * 1024
IMAGE_ID = re.compile(r"^[a-f0-9]{64}$")


def normalize_image(raw: bytes) -> bytes:
    """Decode raster input, strip metadata, orient and bound the stored image."""
    if not raw or len(raw) > MAX_INPUT:
        raise ValueError("Image must be smaller than 8 MB")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Use a JPEG, PNG or WebP image")
            if source.width * source.height > 25_000_000:
                raise ValueError("Image dimensions are too large")
            source.load()
            if source.format == "WEBP" and source.mode == "RGB" and max(source.size) <= 1200 and len(raw) <= MAX_OUTPUT and getattr(source, "n_frames", 1) == 1 and not any(k in source.info for k in ("exif", "icc_profile", "xmp")):
                return raw
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1200, 1200))
            for quality in (80, 65, 45):
                output = io.BytesIO()
                image.save(output, format="WEBP", quality=quality)
                if output.tell() <= MAX_OUTPUT:
                    return output.getvalue()
    except (OSError, Image.DecompressionBombError) as err:
        raise ValueError("Invalid image") from err
    raise ValueError("Image cannot be compressed sufficiently")


def encode_image(raw: bytes) -> str:
    return "data:image/webp;base64," + base64.b64encode(raw).decode("ascii")


def decode_image(value: str) -> bytes:
    if not isinstance(value, str) or len(value) > MAX_INPUT * 4 // 3 + 100:
        raise ValueError("Image is too large")
    header, sep, data = value.partition(",")
    if not sep or header not in {"data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64"}:
        raise ValueError("Use a JPEG, PNG or WebP image")
    try:
        return normalize_image(base64.b64decode(data, validate=True))
    except (ValueError, TypeError) as err:
        raise ValueError("Invalid image data") from err


def image_path(directory: Path, image_id: str) -> Path:
    if not IMAGE_ID.fullmatch(image_id):
        raise ValueError("Invalid image identifier")
    return directory / (image_id + ".webp")


def save_image(directory: Path, data: str) -> str:
    raw = decode_image(data)
    image_id = hashlib.sha256(raw).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    target = image_path(directory, image_id)
    if not target.exists():
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(raw)
        temporary.replace(target)
    return image_id


def read_image(directory: Path, image_id: str) -> str:
    return encode_image(image_path(directory, image_id).read_bytes())


def cleanup_images(directory: Path, retained: set[str]) -> None:
    for path in directory.glob("*.webp"):
        if IMAGE_ID.fullmatch(path.stem) and path.stem not in retained:
            path.unlink(missing_ok=True)


class PublicResolver(aiohttp.resolver.DefaultResolver):
    async def resolve(self, host, port=0, family=0):
        results = await super().resolve(host, port, family)
        if any(not ipaddress.ip_address(r["host"]).is_global for r in results):
            raise ValueError("Image host must be public")
        return results


def public_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        if parsed.port not in {None, 80, 443}:
            return False
        try:
            return ipaddress.ip_address(parsed.hostname).is_global
        except ValueError:
            return parsed.hostname.lower() != "localhost"
    except ValueError:
        return False


async def download_image(url: str) -> bytes:
    """Validate DNS and each redirect, cap streamed bytes and total duration."""
    from urllib.parse import urljoin
    async with asyncio.timeout(20):
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=PublicResolver())) as session:
            for _ in range(5):
                if not public_url(url):
                    raise ValueError("Image address must be public")
                async with session.get(url, allow_redirects=False) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        url = urljoin(url, response.headers.get("Location", ""))
                        continue
                    response.raise_for_status()
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        raw.extend(chunk)
                        if len(raw) > MAX_INPUT:
                            raise ValueError("Image is too large")
                    return bytes(raw)
    raise ValueError("Too many image redirects")

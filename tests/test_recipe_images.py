import asyncio
import base64
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

spec = importlib.util.spec_from_file_location("recipe_images", Path(__file__).resolve().parents[1] / "custom_components/grocery_learning/recipe_images.py")
images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(images)


def photo():
    output = io.BytesIO()
    Image.new("RGB", (1800, 900), "green").save(output, format="PNG")
    return output.getvalue()


class RecipeImagesTests(unittest.TestCase):
    def test_normalize_strips_metadata_bounds_dimensions(self):
        raw = images.normalize_image(photo())
        with Image.open(io.BytesIO(raw)) as result:
            self.assertEqual(result.format, "WEBP")
            self.assertEqual(result.size, (1200, 600))
            self.assertFalse(result.getexif())
        self.assertLessEqual(len(raw), images.MAX_OUTPUT)

    def test_invalid_and_oversized_images(self):
        for value in (b"<svg></svg>", b"not a photo", b"x" * (images.MAX_INPUT + 1)):
            with self.assertRaises(ValueError):
                images.normalize_image(value)
        with self.assertRaises(ValueError):
            images.decode_image("data:image/webp;base64,!!!!")

    def test_local_save_backup_restore_and_cleanup(self):
        value = "data:image/png;base64," + base64.b64encode(photo()).decode()
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first, second = Path(first), Path(second)
            identifier = images.save_image(first, value)
            self.assertEqual(identifier, images.save_image(first, value))
            backup = images.read_image(first, identifier)
            restored = images.save_image(second, backup)
            self.assertTrue(images.image_path(second, restored).exists())
            self.assertEqual(identifier, restored)
            images.cleanup_images(first, {identifier})
            self.assertTrue(images.image_path(first, identifier).exists())
            images.cleanup_images(first, set())
            self.assertFalse(images.image_path(first, identifier).exists())

    def test_path_traversal_rejected(self):
        for value in ("../secret", "/etc/passwd", "abcd", "a" * 65):
            with self.assertRaises(ValueError):
                images.image_path(Path("/tmp"), value)

    def test_private_addresses_rejected(self):
        for value in ("http://127.0.0.1/x", "http://[::1]/x", "http://169.254.169.254/x", "file:///x", "http://localhost/x", "http://example.com:8123/x", "https://user:pass@example.com/x"):
            self.assertFalse(images.public_url(value), value)
        self.assertTrue(images.public_url("https://example.com/photo.jpg"))

    def test_dns_private_result_rejected(self):
        async def check():
            resolver = images.PublicResolver()
            try:
                with patch.object(images.aiohttp.resolver.DefaultResolver, "resolve", new=AsyncMock(return_value=[{"host": "10.0.0.1"}])):
                    with self.assertRaises(ValueError):
                        await resolver.resolve("example.com")
            finally:
                await resolver.close()
        asyncio.run(check())

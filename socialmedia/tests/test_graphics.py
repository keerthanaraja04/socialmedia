"""Unit tests for graphics design and Pixabay integration."""

from pathlib import Path
from unittest.mock import MagicMock, patch
from PIL import Image

from src.graphics.designer import GraphicsDesigner, hex_to_rgb


def test_hex_to_rgb() -> None:
    assert hex_to_rgb("#0F172A") == (15, 23, 42)
    assert hex_to_rgb("#FFF") == (255, 255, 255)


def test_thumbnail_generation(tmp_path: Path) -> None:
    designer = GraphicsDesigner()
    out_file = tmp_path / "thumb_test.png"

    designer.generate_thumbnail(
        title="Stop Writing Boilerplate Code",
        subtitle="The Future of AI Software Engineering",
        output_path=out_file,
        width=720,
        height=1280,
    )

    assert out_file.exists()
    assert out_file.stat().st_size > 0

    with Image.open(out_file) as img:
        assert img.size == (720, 1280)
        assert img.format == "PNG"


@patch("src.graphics.designer.requests.get")
def test_pixabay_search_mock(mock_get: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "hits": [
            {
                "id": 999,
                "pageURL": "https://pixabay.com/photo/999",
                "previewURL": "https://cdn.pixabay.com/preview.jpg",
                "largeImageURL": "https://cdn.pixabay.com/large.jpg",
                "tags": "technology, code",
            }
        ]
    }
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    designer = GraphicsDesigner()
    # Mock settings with temporary key
    designer.settings.pixabay_api_key = "test_pixabay_key"

    assets = designer.search_pixabay_assets("coding", limit=1)
    assert len(assets) == 1
    assert assets[0].id == 999
    assert "large.jpg" in assets[0].large_image_url

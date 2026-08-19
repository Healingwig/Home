from pathlib import Path

import pytest

from app.pipeline import download, media
from app.pipeline.extract import ExtractionInput, build_parts


def test_normalize_url_extrae_el_enlace_del_texto_compartido():
    compartido = "Mira esta receta https://www.instagram.com/reel/ABC123/?igshid=xyz vía @cuenta"
    assert download.normalize_url(compartido) == "https://www.instagram.com/reel/ABC123/"


def test_normalize_url_conserva_parametros_utiles():
    url = "https://www.instagram.com/p/ABC/?foo=1&utm_source=ig"
    assert download.normalize_url(url) == "https://www.instagram.com/p/ABC/?foo=1"


def test_normalize_url_limpia_puntuacion_final():
    assert download.normalize_url("(https://instagram.com/reel/A/)") == "https://instagram.com/reel/A/"


def test_is_supported_url():
    assert download.is_supported_url("https://instagram.com/reel/A/")
    assert not download.is_supported_url("instagram.com/reel/A/")


def test_frame_timestamps_reparte_dentro_del_video():
    stamps = media.frame_timestamps(duration=60, count=5)
    assert len(stamps) == 5
    assert stamps == sorted(stamps)
    assert stamps[0] >= 0 and stamps[-1] < 60


def test_frame_timestamps_soporta_videos_muy_cortos():
    assert media.frame_timestamps(duration=1.5, count=3) == pytest.approx([0.2, 0.75, 1.3], abs=0.05)
    assert media.frame_timestamps(duration=0, count=4) == [0.0]


def test_build_parts_intercala_etiquetas_e_imagenes(tmp_path: Path):
    frame = tmp_path / "f.jpg"
    frame.write_bytes(b"\xff\xd8\xff\xdb-falso-jpeg")
    parts = build_parts(
        ExtractionInput(caption="1 huevo", transcript="batimos el huevo", frames=[(1.5, frame)])
    )
    assert [kind for kind, _ in parts] == ["text", "text", "text", "image", "text"]
    assert "1 huevo" in parts[0][1]
    assert "batimos el huevo" in parts[0][1]
    assert parts[2][1].startswith("Fotograma 1 de 1, en 1.5s")
    assert parts[3][1] == frame


def test_build_parts_sin_material_util_no_llama_al_modelo():
    from app.pipeline.extract import ExtractionError, extract_recipe

    with pytest.raises(ExtractionError):
        extract_recipe(ExtractionInput())

"""Decisión de qué material se le manda al modelo."""

from pathlib import Path

import pytest

from app.pipeline import runner
from app.pipeline.extract import ExtractionInput


class ProveedorConVideo:
    name = "con-video"
    accepts_video = True


class ProveedorSoloImagenes:
    name = "solo-imagenes"
    accepts_video = False


@pytest.fixture
def video(tmp_path):
    ruta = tmp_path / "source.mp4"
    ruta.write_bytes(b"video" * 100)
    return ruta


@pytest.fixture
def sin_efectos(monkeypatch, tmp_path):
    """Neutraliza ffmpeg, Whisper y el almacén: solo miramos qué se decide."""
    monkeypatch.setattr(runner.media, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(runner.media, "duration_seconds", lambda _: 30.0)
    monkeypatch.setattr(runner.media, "extract_audio", lambda *a, **k: None)
    monkeypatch.setattr(
        runner.media, "extract_frames_at",
        lambda video, out, stamps, dim: [(stamps[0], tmp_path / "p.jpg")],
    )
    monkeypatch.setattr(runner.storage, "save_thumbnail", lambda *a, **k: None)
    monkeypatch.setattr(runner.storage, "update_recipe", lambda *a, **k: None)


def test_con_gemini_se_manda_el_video_entero(monkeypatch, tmp_path, video, sin_efectos):
    comprimido = tmp_path / "subida.mp4"
    comprimido.write_bytes(b"x" * 1000)
    monkeypatch.setattr(runner.media, "compress_for_upload", lambda *a, **k: comprimido)

    payload = ExtractionInput()
    runner._attach_video_material("id", video, tmp_path, ProveedorConVideo(), payload)

    assert payload.video == comprimido
    assert payload.frames == []          # no hace falta extraer fotogramas
    assert payload.transcript == ""      # ni transcribir: Gemini oye el audio


def test_si_el_video_no_cabe_se_cae_a_fotogramas(monkeypatch, tmp_path, video, sin_efectos):
    monkeypatch.setattr(runner.media, "compress_for_upload", lambda *a, **k: None)
    monkeypatch.setattr(
        runner.media, "extract_frames", lambda *a, **k: [(1.0, tmp_path / "f.jpg")]
    )

    payload = ExtractionInput()
    runner._attach_video_material("id", video, tmp_path, ProveedorConVideo(), payload)

    assert payload.video is None
    assert len(payload.frames) == 1


def test_los_modelos_sin_video_reciben_fotogramas_y_transcripcion(
    monkeypatch, tmp_path, video, sin_efectos
):
    monkeypatch.setattr(runner.media, "extract_frames", lambda *a, **k: [(1.0, tmp_path / "f.jpg")])
    monkeypatch.setattr(runner.media, "extract_audio", lambda *a, **k: tmp_path / "a.wav")
    monkeypatch.setattr(runner.transcribe, "transcribe", lambda _: "batimos los huevos")

    payload = ExtractionInput()
    runner._attach_video_material("id", video, tmp_path, ProveedorSoloImagenes(), payload)

    assert payload.video is None
    assert payload.frames == [(1.0, tmp_path / "f.jpg")]
    assert payload.transcript == "batimos los huevos"


def test_sin_ffmpeg_y_sin_video_solo_queda_el_texto_del_post(monkeypatch, tmp_path, video):
    monkeypatch.setattr(runner.media, "ffmpeg_available", lambda: False)

    payload = ExtractionInput(caption="2 huevos")
    runner._attach_video_material("id", video, tmp_path, ProveedorSoloImagenes(), payload)

    assert payload.video is None and payload.frames == [] and payload.transcript == ""


def test_sin_ffmpeg_gemini_recibe_el_video_tal_cual(monkeypatch, tmp_path, video):
    monkeypatch.setattr(runner.media, "ffmpeg_available", lambda: False)
    monkeypatch.setattr(runner.storage, "save_thumbnail", lambda *a, **k: None)

    payload = ExtractionInput()
    runner._attach_video_material("id", video, tmp_path, ProveedorConVideo(), payload)

    assert payload.video == video


def test_un_fallo_al_guardar_la_miniatura_no_tumba_el_procesado(monkeypatch, tmp_path, video):
    monkeypatch.setattr(runner.media, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(runner.media, "compress_for_upload", lambda *a, **k: video)
    monkeypatch.setattr(runner.media, "duration_seconds", lambda _: 30.0)
    monkeypatch.setattr(
        runner.media, "extract_frames_at",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ffmpeg petó")),
    )

    payload = ExtractionInput()
    runner._attach_video_material("id", video, tmp_path, ProveedorConVideo(), payload)
    assert payload.video == video

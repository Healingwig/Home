import base64
import json

import httpx
import pytest

from app.models import RECIPE_JSON_SCHEMA
from app.pipeline.providers import ProviderError, get_provider
from app.pipeline.providers.gemini_provider import GeminiProvider
from app.pipeline.providers.ollama_provider import OllamaProvider
from app.schema_utils import gemini_schema, relaxed_schema


@pytest.fixture
def frame(tmp_path):
    path = tmp_path / "frame.jpg"
    path.write_bytes(b"\xff\xd8\xff\xdb-falso-jpeg")
    return path


def _fake_post(capture, response):
    def post(url, **kwargs):
        capture["url"] = url
        capture.update(kwargs)
        return response
    return post


def _response(status, payload):
    request = httpx.Request("POST", "https://ejemplo.test")
    if isinstance(payload, str):
        return httpx.Response(status, text=payload, request=request)
    return httpx.Response(status, json=payload, request=request)


# --- Adaptaciones del esquema ----------------------------------------------

def test_esquema_relajado_quita_las_uniones_con_null():
    relajado = relaxed_schema(RECIPE_JSON_SCHEMA)
    assert relajado["properties"]["servings"]["type"] == "integer"
    # Lo que podía ser null deja de ser obligatorio: Pydantic pone el defecto.
    assert "servings" not in relajado["required"]
    assert "title" in relajado["required"]
    paso = relajado["properties"]["steps"]["items"]
    assert paso["properties"]["timer_seconds"]["type"] == "integer"
    assert "timer_seconds" not in paso["required"]


def test_esquema_de_gemini_usa_nullable_y_tipos_en_mayusculas():
    convertido = gemini_schema(RECIPE_JSON_SCHEMA)
    assert convertido["type"] == "OBJECT"
    assert convertido["properties"]["servings"] == {
        "type": "INTEGER",
        "nullable": True,
        "description": "Raciones que salen con estas cantidades",
    }
    assert convertido["properties"]["tags"]["items"]["type"] == "STRING"
    assert convertido["properties"]["difficulty"]["enum"] == ["fácil", "media", "difícil"]
    # `additionalProperties` no forma parte del subconjunto que admite Gemini.
    assert "additionalProperties" not in json.dumps(convertido)


# --- Ollama ------------------------------------------------------------------

def test_ollama_manda_las_imagenes_aparte_del_texto(monkeypatch, frame):
    capture = {}
    monkeypatch.setattr(
        "app.pipeline.providers.ollama_provider.httpx.post",
        _fake_post(capture, _response(200, {"message": {"content": '{"title":"x"}'}})),
    )

    provider = OllamaProvider(host="http://ollama.test", model="qwen2.5vl:7b")
    result = provider.generate("sistema", [("text", "hola"), ("image", frame), ("text", "adiós")])

    assert result == '{"title":"x"}'
    body = capture["json"]
    assert capture["url"] == "http://ollama.test/api/chat"
    assert body["model"] == "qwen2.5vl:7b"
    assert body["messages"][0] == {"role": "system", "content": "sistema"}
    assert body["messages"][1]["content"] == "hola\nadiós"
    assert body["messages"][1]["images"] == [base64.standard_b64encode(frame.read_bytes()).decode()]
    assert body["format"]["properties"]["title"]["type"] == "string"


def test_ollama_sin_el_modelo_descargado_lo_dice_claro(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.providers.ollama_provider.httpx.post",
        _fake_post({}, _response(404, "model not found")),
    )
    with pytest.raises(ProviderError, match="ollama pull"):
        OllamaProvider().generate("s", [("text", "t")])


def test_ollama_apagado_da_un_mensaje_util(monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.pipeline.providers.ollama_provider.httpx.post", boom)
    with pytest.raises(ProviderError, match="¿Está arrancado?"):
        OllamaProvider().generate("s", [("text", "t")])


def test_ollama_reintenta_en_json_libre_si_rechaza_el_esquema(monkeypatch):
    llamadas = []

    def post(url, **kwargs):
        llamadas.append(kwargs["json"]["format"])
        if len(llamadas) == 1:
            return _response(400, "invalid format schema")
        return _response(200, {"message": {"content": '{"title":"x"}'}})

    monkeypatch.setattr("app.pipeline.providers.ollama_provider.httpx.post", post)
    assert OllamaProvider().generate("s", [("text", "t")]) == '{"title":"x"}'
    assert isinstance(llamadas[0], dict) and llamadas[1] == "json"


# --- Gemini ------------------------------------------------------------------

def test_gemini_intercala_texto_e_imagenes(monkeypatch, frame):
    capture = {}
    payload = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"title":"x"}'}]}}]}
    monkeypatch.setattr(
        "app.pipeline.providers.gemini_provider.httpx.post", _fake_post(capture, _response(200, payload))
    )

    provider = GeminiProvider(api_key="clave", model="gemini-2.5-flash")
    assert provider.generate("sistema", [("text", "hola"), ("image", frame)]) == '{"title":"x"}'

    body = capture["json"]
    assert capture["params"] == {"key": "clave"}
    assert body["systemInstruction"]["parts"][0]["text"] == "sistema"
    partes = body["contents"][0]["parts"]
    assert partes[0] == {"text": "hola"}
    assert partes[1]["inline_data"]["mime_type"] == "image/jpeg"
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_sin_clave_avisa_de_donde_sacarla():
    with pytest.raises(ProviderError, match="aistudio.google.com"):
        GeminiProvider(api_key="")


def test_gemini_al_agotar_la_cuota_sugiere_ollama(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.providers.gemini_provider.httpx.post",
        _fake_post({}, _response(429, "quota exceeded")),
    )
    with pytest.raises(ProviderError, match="ollama"):
        GeminiProvider(api_key="k").generate("s", [("text", "t")])


def test_gemini_respuesta_cortada_por_longitud(monkeypatch):
    payload = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]}
    monkeypatch.setattr(
        "app.pipeline.providers.gemini_provider.httpx.post", _fake_post({}, _response(200, payload))
    )
    with pytest.raises(ProviderError, match="menos fotogramas"):
        GeminiProvider(api_key="k").generate("s", [("text", "t")])


def test_gemini_peticion_bloqueada(monkeypatch):
    payload = {"promptFeedback": {"blockReason": "SAFETY"}}
    monkeypatch.setattr(
        "app.pipeline.providers.gemini_provider.httpx.post", _fake_post({}, _response(200, payload))
    )
    with pytest.raises(ProviderError, match="bloqueó"):
        GeminiProvider(api_key="k").generate("s", [("text", "t")])


# --- Selección del backend ---------------------------------------------------

def test_backend_desconocido_lista_las_opciones():
    with pytest.raises(ProviderError, match="anthropic, gemini, ollama"):
        get_provider("chatgpt")


def test_se_puede_pedir_cada_backend_por_nombre():
    assert get_provider("ollama").name == "ollama"
    assert get_provider("gemini").name == "gemini"


def test_sin_el_paquete_anthropic_se_explica_como_instalarlo(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def sin_anthropic(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sin_anthropic)
    monkeypatch.delitem(__import__("sys").modules, "anthropic", raising=False)

    with pytest.raises(ProviderError, match="pip install anthropic"):
        get_provider("anthropic")


def test_gemini_manda_el_video_con_su_tipo_mime(monkeypatch, tmp_path):
    capture = {}
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    payload = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]}
    monkeypatch.setattr(
        "app.pipeline.providers.gemini_provider.httpx.post", _fake_post(capture, _response(200, payload))
    )

    GeminiProvider(api_key="k").generate("s", [("text", "contexto"), ("video", video)])

    partes = capture["json"]["contents"][0]["parts"]
    assert partes[1]["inline_data"]["mime_type"] == "video/mp4"


def test_solo_gemini_acepta_el_video_entero():
    assert get_provider("gemini").accepts_video is True
    assert get_provider("ollama").accepts_video is False

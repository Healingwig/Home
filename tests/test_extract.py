import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.pipeline.extract import ExtractionError, ExtractionInput, extract_recipe

RECETA_JSON = {
    "title": "Tortilla de patatas",
    "summary": "La de toda la vida, jugosa por dentro.",
    "servings": 4,
    "prep_minutes": 15,
    "cook_minutes": 25,
    "difficulty": "media",
    "cuisine": "española",
    "tags": ["clásico"],
    "equipment": ["sartén antiadherente"],
    "ingredients": [
        {"name": "patatas", "quantity": 700, "unit": "g", "note": "en láminas finas",
         "category": "frutas y verduras", "optional": False, "pantry": False},
        {"name": "huevos", "quantity": 6, "unit": "unidades", "note": None,
         "category": "lácteos y huevos", "optional": False, "pantry": False},
        {"name": "sal", "quantity": None, "unit": "al gusto", "note": None,
         "category": "especias y condimentos", "optional": False, "pantry": True},
    ],
    "steps": [
        {"number": 1, "title": "Pochar las patatas", "instruction": "Fríe las patatas a fuego suave.",
         "minutes": 20, "timer_seconds": 1200, "tip": "Que no cojan color.", "ingredients": ["700 g de patatas"]},
        {"number": 2, "title": "Cuajar", "instruction": "Mezcla con el huevo batido y cuaja por ambos lados.",
         "minutes": 5, "timer_seconds": None, "tip": None, "ingredients": ["6 huevos"]},
    ],
    "tips": ["Deja reposar la mezcla 10 minutos."],
    "storage": "Aguanta 2 días en la nevera.",
    "confidence": 0.86,
    "warnings": ["Las raciones están estimadas por la cantidad de huevo."],
}


def _response(payload, stop_reason="end_turn", stop_details=None):
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        stop_details=stop_details,
    )


class FakeClient:
    """Sustituto de anthropic.Anthropic que registra la petición recibida."""

    def __init__(self, response, beta_error: Exception | None = None):
        self.response = response
        self.beta_error = beta_error
        self.calls: list[tuple[str, dict]] = []
        outer = self

        class _BetaMessages:
            def create(self, **kwargs):
                outer.calls.append(("beta", kwargs))
                if outer.beta_error:
                    raise outer.beta_error
                return outer.response

        class _Messages:
            def create(self, **kwargs):
                outer.calls.append(("standard", kwargs))
                return outer.response

        self.beta = SimpleNamespace(messages=_BetaMessages())
        self.messages = _Messages()


def _bad_request() -> anthropic.BadRequestError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.BadRequestError(
        "beta no disponible", response=httpx.Response(400, request=request), body=None
    )


def _entrada():
    return ExtractionInput(caption="700 g de patatas, 6 huevos", source_url="https://instagram.com/reel/A/")


def test_extrae_y_valida_la_receta():
    client = FakeClient(_response(RECETA_JSON))
    recipe = extract_recipe(_entrada(), client=client)

    assert recipe.title == "Tortilla de patatas"
    assert recipe.ingredients[0].quantity == 700
    assert recipe.ingredients[2].pantry is True
    assert recipe.steps[0].timer_seconds == 1200
    assert recipe.total_minutes == 40


def test_la_peticion_lleva_el_esquema_y_el_pensamiento_adaptativo():
    client = FakeClient(_response(RECETA_JSON))
    extract_recipe(_entrada(), client=client)

    kind, kwargs = client.calls[0]
    assert kind == "beta"
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["fallbacks"] == "default"
    assert "700 g de patatas" in kwargs["messages"][0]["content"][0]["text"]


def test_si_el_beta_no_esta_disponible_reintenta_sin_el():
    client = FakeClient(_response(RECETA_JSON), beta_error=_bad_request())
    recipe = extract_recipe(_entrada(), client=client)

    assert recipe.title == "Tortilla de patatas"
    assert [kind for kind, _ in client.calls] == ["beta", "standard"]
    assert "fallbacks" not in client.calls[1][1]


def test_un_rechazo_del_modelo_se_reporta_como_error_claro():
    client = FakeClient(
        _response(RECETA_JSON, stop_reason="refusal", stop_details=SimpleNamespace(explanation="motivo"))
    )
    with pytest.raises(ExtractionError, match="rechazó"):
        extract_recipe(_entrada(), client=client)


def test_json_invalido_da_un_error_legible():
    client = FakeClient(_response("esto no es json"))
    with pytest.raises(ExtractionError, match="JSON"):
        extract_recipe(_entrada(), client=client)


def test_json_que_no_cumple_el_esquema_da_un_error_legible():
    client = FakeClient(_response({"title": "Sin pasos", "steps": [{"number": "uno"}]}))
    with pytest.raises(ExtractionError, match="esquema"):
        extract_recipe(_entrada(), client=client)

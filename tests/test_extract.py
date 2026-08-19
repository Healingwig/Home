import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.pipeline.extract import ExtractionError, ExtractionInput, extract_recipe, parse_recipe
from app.pipeline.providers import ProviderError

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


class FakeProvider:
    """Backend de mentira: devuelve lo que le digas y guarda lo que recibió."""

    name = "falso"

    def __init__(self, raw=None, error: Exception | None = None):
        self.raw = raw if isinstance(raw, str) or raw is None else json.dumps(raw, ensure_ascii=False)
        self.error = error
        self.system = None
        self.parts = None

    def generate(self, system, parts):
        self.system, self.parts = system, parts
        if self.error:
            raise self.error
        return self.raw


def _entrada():
    return ExtractionInput(caption="700 g de patatas, 6 huevos", source_url="https://instagram.com/reel/A/")


def test_extrae_y_valida_la_receta():
    recipe = extract_recipe(_entrada(), provider=FakeProvider(RECETA_JSON))

    assert recipe.title == "Tortilla de patatas"
    assert recipe.ingredients[0].quantity == 700
    assert recipe.ingredients[2].pantry is True
    assert recipe.steps[0].timer_seconds == 1200
    assert recipe.total_minutes == 40


def test_el_material_del_video_llega_al_modelo():
    provider = FakeProvider(RECETA_JSON)
    extract_recipe(_entrada(), provider=provider)

    assert "700 g de patatas" in provider.parts[0][1]
    assert "chef" in provider.system


def test_un_fallo_del_backend_se_reporta_como_error_de_extraccion():
    provider = FakeProvider(error=ProviderError("Ollama no responde"))
    with pytest.raises(ExtractionError, match="Ollama no responde"):
        extract_recipe(_entrada(), provider=provider)


def test_json_invalido_da_un_error_legible():
    with pytest.raises(ExtractionError, match="JSON"):
        extract_recipe(_entrada(), provider=FakeProvider("esto no es json"))


def test_json_que_no_cumple_el_esquema_da_un_error_legible():
    provider = FakeProvider({"title": "Sin pasos", "steps": [{"number": "uno"}]})
    with pytest.raises(ExtractionError, match="esquema"):
        extract_recipe(_entrada(), provider=provider)


def test_sin_material_util_no_se_llama_al_modelo():
    provider = FakeProvider(RECETA_JSON)
    with pytest.raises(ExtractionError):
        extract_recipe(ExtractionInput(), provider=provider)
    assert provider.parts is None


# --- Tolerancia con lo que devuelven los modelos locales --------------------

def test_acepta_json_envuelto_en_bloque_de_codigo():
    envuelto = f"```json\n{json.dumps(RECETA_JSON)}\n```"
    assert parse_recipe(envuelto).title == "Tortilla de patatas"


def test_acepta_json_con_texto_alrededor():
    con_texto = f"Aquí tienes la receta:\n{json.dumps(RECETA_JSON)}\n¡Que aproveche!"
    assert parse_recipe(con_texto).title == "Tortilla de patatas"


def test_receta_incompleta_se_completa_con_los_valores_por_defecto():
    minima = parse_recipe(json.dumps({"title": "Algo", "ingredients": [{"name": "pan"}]}))
    assert minima.servings is None
    assert minima.difficulty == "media"
    assert minima.steps == []
    assert minima.ingredients[0].category == "otros"


def test_una_lista_json_no_es_una_receta():
    with pytest.raises(ExtractionError, match="objeto de receta"):
        parse_recipe("[1, 2, 3]")

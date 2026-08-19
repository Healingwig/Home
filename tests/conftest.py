"""La configuración se lee al importar `app.config`, así que el entorno de
pruebas debe quedar fijado antes de cualquier import de la aplicación."""

import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="recetas-test-"))
os.environ.setdefault("API_KEY", "clave-de-prueba")
os.environ.setdefault("APP_PASSWORD", "hola")
os.environ.setdefault("TRANSCRIBER", "none")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, main  # noqa: E402
from app.models import Ingredient, Recipe, Step  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    # Nada de trabajo en segundo plano real durante las pruebas.
    monkeypatch.setattr(main._workers, "submit", lambda *args, **kwargs: None)
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def auth():
    return {"X-API-Key": "clave-de-prueba"}


@pytest.fixture
def sample_recipe() -> Recipe:
    return Recipe(
        title="Pasta al limón",
        summary="Pasta cremosa con limón y parmesano.",
        servings=2,
        prep_minutes=10,
        cook_minutes=15,
        difficulty="fácil",
        ingredients=[
            Ingredient(name="espaguetis", quantity=200, unit="g", category="despensa"),
            Ingredient(name="nata para cocinar", quantity=150, unit="ml", category="lácteos y huevos"),
            Ingredient(name="limón", quantity=1, unit="unidad", category="frutas y verduras", note="la ralladura y el zumo"),
            Ingredient(name="sal", quantity=None, unit="al gusto", category="especias y condimentos", pantry=True),
            Ingredient(name="albahaca fresca", quantity=4, unit="hojas", category="frutas y verduras", optional=True),
        ],
        steps=[
            Step(number=1, title="Cocer la pasta", instruction="Cuece los espaguetis en agua con sal.", timer_seconds=540),
            Step(number=2, title="Salsa", instruction="Calienta la nata con la ralladura de limón."),
        ],
    )


@pytest.fixture
def stored_recipe(sample_recipe):
    db.init_db()
    recipe_id = db.create_recipe("https://www.instagram.com/reel/ABC123/")
    db.update_recipe(
        recipe_id,
        status="ready",
        title=sample_recipe.title,
        data=sample_recipe.model_dump(mode="json"),
    )
    return recipe_id

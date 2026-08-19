"""Modelo de datos de una receta y el esquema JSON que le pedimos a Claude."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.config import GROCERY_CATEGORIES

DIFFICULTIES = ["fácil", "media", "difícil"]


class Ingredient(BaseModel):
    name: str
    quantity: float | None = None
    unit: str | None = None
    note: str | None = None
    category: str = "otros"
    optional: bool = False
    pantry: bool = False

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        value = (value or "").strip().lower()
        return value if value in GROCERY_CATEGORIES else "otros"

    def scaled(self, factor: float) -> "Ingredient":
        if factor == 1 or self.quantity is None:
            return self
        return self.model_copy(update={"quantity": self.quantity * factor})

    def display_amount(self) -> str:
        """'250 g', '1/2 cucharadita', '2 unidades', 'al gusto'…"""
        if self.quantity is None:
            return self.unit.strip() if self.unit else ""
        amount = format_quantity(self.quantity)
        if not self.unit:
            return amount
        return f"{amount} {pluralize_unit(self.unit.strip(), self.quantity)}"

    def shopping_line(self) -> str:
        amount = self.display_amount()
        line = f"{self.name} — {amount}" if amount else self.name
        if self.note:
            line += f" ({self.note})"
        if self.optional:
            line += " [opcional]"
        return line


class Step(BaseModel):
    number: int
    title: str
    instruction: str
    minutes: float | None = None
    timer_seconds: int | None = None
    tip: str | None = None
    ingredients: list[str] = Field(default_factory=list)


class Recipe(BaseModel):
    title: str
    summary: str = ""
    servings: int | None = None
    prep_minutes: int | None = None
    cook_minutes: int | None = None
    difficulty: str = "media"
    cuisine: str | None = None
    tags: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    storage: str | None = None
    confidence: float = 0.5
    warnings: list[str] = Field(default_factory=list)

    @property
    def total_minutes(self) -> int | None:
        parts = [p for p in (self.prep_minutes, self.cook_minutes) if p]
        return sum(parts) if parts else None

    def scaled(self, servings: int | None) -> "Recipe":
        """Reescala las cantidades a otro número de raciones."""
        if not servings or not self.servings or servings == self.servings:
            return self
        factor = servings / self.servings
        return self.model_copy(
            update={
                "servings": servings,
                "ingredients": [i.scaled(factor) for i in self.ingredients],
            }
        )

    def shopping_items(self, include_pantry: bool = True, include_optional: bool = True) -> list[Ingredient]:
        items = [
            i
            for i in self.ingredients
            if (include_pantry or not i.pantry) and (include_optional or not i.optional)
        ]
        order = {name: index for index, name in enumerate(GROCERY_CATEGORIES)}
        return sorted(items, key=lambda i: (order.get(i.category, len(order)), i.name.lower()))


def format_quantity(value: float) -> str:
    """1.0 -> '1', 0.5 -> '1/2', 1.25 -> '1 1/4', 2.35 -> '2,35'."""
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return ""
    rounded = round(value, 2)
    if abs(rounded - round(rounded)) < 0.01:
        return str(int(round(rounded)))

    whole = int(rounded)
    frac = round(rounded - whole, 2)
    fractions = ((0.25, "1/4"), (1 / 3, "1/3"), (0.5, "1/2"), (2 / 3, "2/3"), (0.75, "3/4"))
    for target, label in fractions:
        if abs(frac - target) < 0.015:
            return f"{whole} {label}" if whole else label

    return f"{rounded:g}".replace(".", ",")


# Unidades que son palabras y sí se pluralizan. Las abreviaturas (g, ml, kg,
# cda) no llevan plural, así que se quedan fuera a propósito.
PLURAL_UNITS = {
    "unidad": "unidades",
    "diente": "dientes",
    "hoja": "hojas",
    "rama": "ramas",
    "loncha": "lonchas",
    "rodaja": "rodajas",
    "rebanada": "rebanadas",
    "cucharada": "cucharadas",
    "cucharadita": "cucharaditas",
    "taza": "tazas",
    "vaso": "vasos",
    "pizca": "pizcas",
    "puñado": "puñados",
    "lata": "latas",
    "sobre": "sobres",
    "paquete": "paquetes",
    "gota": "gotas",
    "tira": "tiras",
    "filete": "filetes",
    "trozo": "trozos",
}


def pluralize_unit(unit: str, quantity: float) -> str:
    """'2 unidad' queda mal en la lista de la compra; '2 unidades', no."""
    if quantity <= 1:
        return unit
    return PLURAL_UNITS.get(unit.lower(), unit)


def _nullable(kind: str) -> dict[str, Any]:
    return {"type": [kind, "null"]}


# Esquema para `output_config.format` (structured outputs). Requisitos de la
# API: todas las propiedades en `required` y `additionalProperties: false`.
RECIPE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Nombre corto y apetecible del plato"},
        "summary": {"type": "string", "description": "Una o dos frases describiendo el plato"},
        "servings": _nullable("integer") | {"description": "Raciones que salen con estas cantidades"},
        "prep_minutes": _nullable("integer"),
        "cook_minutes": _nullable("integer"),
        "difficulty": {"type": "string", "enum": DIFFICULTIES},
        "cuisine": _nullable("string"),
        "tags": {"type": "array", "items": {"type": "string"}},
        "equipment": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Utensilios necesarios (sartén, batidora, horno…)",
        },
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre del ingrediente, sin cantidad"},
                    "quantity": _nullable("number") | {"description": "Cantidad numérica; null si es 'al gusto'"},
                    "unit": _nullable("string") | {"description": "g, ml, cucharada, unidad…"},
                    "note": _nullable("string") | {"description": "Preparación previa: picado, a temperatura ambiente…"},
                    "category": {"type": "string", "enum": GROCERY_CATEGORIES},
                    "optional": {"type": "boolean"},
                    "pantry": {
                        "type": "boolean",
                        "description": "true si es un básico que casi siempre se tiene en casa (sal, aceite, pimienta, agua)",
                    },
                },
                "required": ["name", "quantity", "unit", "note", "category", "optional", "pantry"],
                "additionalProperties": False,
            },
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "title": {"type": "string", "description": "Título corto del paso, 2-5 palabras"},
                    "instruction": {"type": "string", "description": "Instrucción completa y autocontenida"},
                    "minutes": _nullable("number"),
                    "timer_seconds": _nullable("integer") | {
                        "description": "Segundos para un temporizador, solo si el paso tiene un tiempo concreto de espera"
                    },
                    "tip": _nullable("string"),
                    "ingredients": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ingredientes que se usan en este paso, con su cantidad",
                    },
                },
                "required": ["number", "title", "instruction", "minutes", "timer_seconds", "tip", "ingredients"],
                "additionalProperties": False,
            },
        },
        "tips": {"type": "array", "items": {"type": "string"}},
        "storage": _nullable("string") | {"description": "Cómo conservar las sobras"},
        "confidence": {
            "type": "number",
            "description": "0-1: cómo de seguro estás de que la receta refleja el vídeo",
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Cosas que has tenido que deducir o que no quedaban claras en el vídeo",
        },
    },
    "required": [
        "title",
        "summary",
        "servings",
        "prep_minutes",
        "cook_minutes",
        "difficulty",
        "cuisine",
        "tags",
        "equipment",
        "ingredients",
        "steps",
        "tips",
        "storage",
        "confidence",
        "warnings",
    ],
    "additionalProperties": False,
}

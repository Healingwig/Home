"""Construcción de la lista de la compra a partir de una receta."""

from __future__ import annotations

from app.config import GROCERY_CATEGORIES
from app.models import Recipe


def shopping_payload(
    recipe: Recipe,
    servings: int | None = None,
    include_pantry: bool = False,
    include_optional: bool = True,
    prefix_title: bool = False,
) -> dict:
    """Estructura pensada para que el Atajo de iOS la consuma sin lógica extra.

    - `lines`: una línea por producto, listo para 'Dividir texto por líneas'.
    - `items`: los mismos datos desglosados por si quieres agrupar por sección.
    """
    scaled = recipe.scaled(servings)
    selected = scaled.shopping_items(include_pantry=include_pantry, include_optional=include_optional)

    lines: list[str] = []
    items: list[dict] = []
    for ingredient in selected:
        line = ingredient.shopping_line()
        if prefix_title:
            line = f"{line} · {scaled.title}"
        lines.append(line)
        items.append(
            {
                "name": ingredient.name,
                "amount": ingredient.display_amount(),
                "quantity": ingredient.quantity,
                "unit": ingredient.unit,
                "note": ingredient.note,
                "category": ingredient.category,
                "optional": ingredient.optional,
                "pantry": ingredient.pantry,
                "line": line,
            }
        )

    by_category: dict[str, list[str]] = {}
    for item in items:
        by_category.setdefault(item["category"], []).append(item["line"])

    return {
        "title": scaled.title,
        "servings": scaled.servings,
        "count": len(items),
        "lines": lines,
        "text": "\n".join(lines),
        "items": items,
        "by_category": {
            category: by_category[category] for category in GROCERY_CATEGORIES if category in by_category
        },
    }

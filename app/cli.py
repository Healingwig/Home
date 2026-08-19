"""Procesa una URL desde la terminal, sin levantar el servidor.

    python -m app.cli https://www.instagram.com/reel/XXXX/
"""

from __future__ import annotations

import argparse
import json
import sys

from app import storage
from app.config import settings
from app.models import Recipe
from app.pipeline import download, process_recipe
from app.shopping import shopping_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convierte un vídeo de Instagram en una receta.")
    parser.add_argument("url", nargs="?", help="Enlace del reel o post")
    parser.add_argument(
        "--ejemplo", action="store_true",
        help="Guarda una receta de ejemplo para ver la web sin configurar nada",
    )
    parser.add_argument("--json", action="store_true", help="Volcar la receta en JSON")
    parser.add_argument("--raciones", type=int, default=None, help="Reescalar a N raciones")
    args = parser.parse_args(argv)

    settings.ensure_dirs()
    storage.init()

    if args.ejemplo:
        return _guardar_ejemplo()
    if not args.url:
        parser.error("hace falta una URL, o --ejemplo para guardar una receta de muestra")

    url = download.normalize_url(args.url)
    recipe_id = storage.create_recipe(url)
    print(f"Procesando {url} …", file=sys.stderr)
    process_recipe(recipe_id, url)

    row = storage.get_recipe(recipe_id) or {}
    if row.get("status") != "ready":
        print(f"Error: {row.get('error', 'desconocido')}", file=sys.stderr)
        return 1

    recipe = Recipe.model_validate(row["data"]).scaled(args.raciones)
    if args.json:
        print(json.dumps(recipe.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    print(f"\n{recipe.title}")
    if recipe.summary:
        print(recipe.summary)
    print(f"\nRaciones: {recipe.servings or '?'} · Tiempo: {recipe.total_minutes or '?'} min · {recipe.difficulty}")

    print("\nINGREDIENTES")
    for ingredient in recipe.ingredients:
        print(f"  · {ingredient.shopping_line()}")

    print("\nPASOS")
    for step in recipe.steps:
        print(f"  {step.number}. {step.title}\n     {step.instruction}")
        if step.tip:
            print(f"     💡 {step.tip}")

    print("\nLISTA DE LA COMPRA")
    print(shopping_payload(recipe, servings=args.raciones)["text"])

    if recipe.warnings:
        print("\nAVISOS")
        for warning in recipe.warnings:
            print(f"  ⚠ {warning}")

    print(f"\nID de la receta: {recipe_id}", file=sys.stderr)
    return 0


def _guardar_ejemplo() -> int:
    from app.demo import DEMO_RECIPE

    recipe_id = storage.create_recipe("ejemplo://receta-de-muestra")
    storage.update_recipe(
        recipe_id, status="ready", title=DEMO_RECIPE["title"], data=DEMO_RECIPE
    )
    print(f"Receta de ejemplo guardada: {DEMO_RECIPE['title']}")
    print(f"Ábrela en /receta/{recipe_id} y prueba el modo cocina.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

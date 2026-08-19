"""Adaptaciones del esquema JSON de la receta a lo que acepta cada modelo.

El esquema canónico (`RECIPE_JSON_SCHEMA`) usa uniones del tipo
`["integer", "null"]`, que la API de Claude admite pero otros backends no.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_GEMINI_TYPES = {
    "object": "OBJECT",
    "array": "ARRAY",
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
}


def _split_nullable(node: dict[str, Any]) -> tuple[str | None, bool]:
    """Devuelve (tipo_base, admite_null) para un nodo del esquema."""
    kind = node.get("type")
    if isinstance(kind, list):
        types = [t for t in kind if t != "null"]
        return (types[0] if types else None), "null" in kind
    return kind, False


def relaxed_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Versión sin uniones, para modelos locales que solo entienden un tipo.

    Los campos que podían ser nulos dejan de ser obligatorios: si el modelo no
    sabe el valor, lo omite y Pydantic aplica el valor por defecto.
    """
    node = deepcopy(schema)
    base, nullable = _split_nullable(node)
    if base:
        node["type"] = base

    if node.get("type") == "object":
        properties = node.get("properties", {})
        optional = {
            name for name, child in properties.items() if _split_nullable(child)[1]
        }
        node["properties"] = {name: relaxed_schema(child) for name, child in properties.items()}
        if "required" in node:
            node["required"] = [name for name in node["required"] if name not in optional]
    elif node.get("type") == "array" and "items" in node:
        node["items"] = relaxed_schema(node["items"])

    return node


def gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Subconjunto de OpenAPI que acepta `responseSchema` de Gemini.

    Los tipos van en mayúsculas, los nulos se expresan con `nullable` y
    `additionalProperties` no está soportado.
    """
    node: dict[str, Any] = {}
    base, nullable = _split_nullable(schema)
    if base:
        node["type"] = _GEMINI_TYPES.get(base, base.upper())
    if nullable:
        node["nullable"] = True
    for key in ("description", "enum"):
        if key in schema:
            node[key] = schema[key]

    if base == "object":
        properties = schema.get("properties", {})
        node["properties"] = {name: gemini_schema(child) for name, child in properties.items()}
        # `propertyOrdering` fija el orden de generación, lo que mejora la
        # coherencia del JSON en respuestas largas.
        node["propertyOrdering"] = list(properties)
        if schema.get("required"):
            node["required"] = list(schema["required"])
    elif base == "array" and "items" in schema:
        node["items"] = gemini_schema(schema["items"])

    return node

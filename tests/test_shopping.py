from app.shopping import shopping_payload


def test_lista_excluye_basicos_de_despensa_por_defecto(sample_recipe):
    payload = shopping_payload(sample_recipe)
    assert not any("sal" == item["name"] for item in payload["items"])
    assert payload["count"] == 4


def test_lista_ordena_por_seccion_del_super(sample_recipe):
    payload = shopping_payload(sample_recipe)
    assert list(payload["by_category"]) == ["frutas y verduras", "lácteos y huevos", "despensa"]


def test_lineas_legibles_para_recordatorios(sample_recipe):
    lines = shopping_payload(sample_recipe)["lines"]
    assert "espaguetis — 200 g" in lines
    assert "limón — 1 unidad (la ralladura y el zumo)" in lines
    assert "albahaca fresca — 4 hojas [opcional]" in lines
    assert "\n".join(lines) == shopping_payload(sample_recipe)["text"]


def test_escalado_y_prefijo_de_titulo(sample_recipe):
    payload = shopping_payload(sample_recipe, servings=4, prefix_title=True)
    assert payload["servings"] == 4
    assert "espaguetis — 400 g · Pasta al limón" in payload["lines"]


def test_se_pueden_excluir_los_opcionales(sample_recipe):
    payload = shopping_payload(sample_recipe, include_optional=False)
    assert not any(item["optional"] for item in payload["items"])

import threading

from app import storage


def test_ciclo_de_vida_de_una_receta(sample_recipe):
    recipe_id = storage.create_recipe("https://instagram.com/reel/A/")
    assert storage.get_recipe(recipe_id)["status"] == "pending"

    storage.update_recipe(recipe_id, status="ready", title=sample_recipe.title,
                          data=sample_recipe.model_dump(mode="json"))
    guardada = storage.get_recipe(recipe_id)
    assert guardada["status"] == "ready"
    assert guardada["data"]["title"] == "Pasta al limón"
    assert guardada["updated_at"] >= guardada["created_at"]

    assert storage.delete_recipe(recipe_id) is True
    assert storage.get_recipe(recipe_id) is None
    assert storage.list_recipes() == []


def test_actualizar_una_receta_inexistente_no_revienta():
    assert storage.update_recipe("nohay", status="ready") is None


def test_el_listado_va_de_la_mas_nueva_a_la_mas_vieja():
    ids = [storage.create_recipe(f"https://instagram.com/reel/{n}/") for n in range(3)]
    assert [row["id"] for row in storage.list_recipes()] == list(reversed(ids))


def test_el_listado_no_necesita_abrir_cada_receta(sample_recipe):
    recipe_id = storage.create_recipe("https://instagram.com/reel/A/")
    storage.update_recipe(recipe_id, status="ready", data=sample_recipe.model_dump(mode="json"))

    fila = storage.list_recipes()[0]
    assert fila["title"] == "Pasta al limón"
    assert fila["total_minutes"] == 25
    assert "data" not in fila


def test_se_puede_buscar_por_ingrediente(sample_recipe):
    recipe_id = storage.create_recipe("https://instagram.com/reel/A/")
    storage.update_recipe(recipe_id, status="ready", data=sample_recipe.model_dump(mode="json"))

    assert len(storage.list_recipes(query="espaguetis")) == 1
    assert len(storage.list_recipes(query="LIMÓN")) == 1
    assert storage.list_recipes(query="paella") == []


def test_find_by_url_ignora_las_que_fallaron():
    url = "https://instagram.com/reel/REPE/"
    fallida = storage.create_recipe(url)
    storage.update_recipe(fallida, status="error", error="algo")
    assert storage.find_by_url(url) is None

    nueva = storage.create_recipe(url)
    assert storage.find_by_url(url)["id"] == nueva


def test_miniaturas(tmp_path):
    origen = tmp_path / "portada.jpg"
    origen.write_bytes(b"\xff\xd8jpeg")
    recipe_id = storage.create_recipe("https://instagram.com/reel/A/")

    storage.save_thumbnail(recipe_id, origen)
    assert storage.read_thumbnail(recipe_id) == b"\xff\xd8jpeg"
    assert storage.get_recipe(recipe_id)["thumbnail"] == f"{recipe_id}.jpg"

    storage.delete_recipe(recipe_id)
    assert storage.read_thumbnail(recipe_id) is None


def test_detecta_las_recetas_que_se_quedaron_a_medias():
    reciente = storage.create_recipe("https://instagram.com/reel/NUEVA/")
    antigua = storage.create_recipe("https://instagram.com/reel/VIEJA/")
    storage.update_recipe(antigua, status="processing")
    # La envejecemos a mano en el índice y en la propia receta.
    record = storage.get_recipe(antigua)
    record["updated_at"] -= 3600
    storage.get_store().put_json(storage._recipe_name(antigua), record)
    storage.get_store().update_json(
        storage.INDEX_NAME,
        lambda index: {**index, antigua: {**index[antigua], "updated_at": record["updated_at"]}},
    )

    paradas = [row["id"] for row in storage.iter_stale_processing(older_than_seconds=1800)]
    assert paradas == [antigua]
    assert reciente not in paradas


def test_el_indice_no_se_pisa_con_escrituras_simultaneas():
    ids = [storage.create_recipe(f"https://instagram.com/reel/{n}/") for n in range(8)]

    hilos = [
        threading.Thread(target=storage.update_recipe, args=(rid,), kwargs={"status": "ready"})
        for rid in ids
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    guardadas = storage.list_recipes()
    assert len(guardadas) == 8
    assert {row["status"] for row in guardadas} == {"ready"}


def test_el_almacen_local_no_deja_escapar_de_su_directorio(tmp_path):
    import pytest

    almacen = storage.LocalObjectStore(tmp_path / "raiz")
    with pytest.raises(ValueError):
        almacen.put_bytes("../fuera.json", b"x", "application/json")

def test_healthz_no_requiere_clave(client):
    assert client.get("/healthz").json()["ok"] is True


def test_api_sin_clave_devuelve_401(client):
    assert client.get("/api/recipes").status_code == 401


def test_clave_incorrecta_devuelve_401(client):
    assert client.get("/api/recipes", headers={"X-API-Key": "no"}).status_code == 401


def test_crear_receta_encola_y_devuelve_202(client, auth):
    response = client.post(
        "/api/recipes",
        json={"url": "Mira esto https://www.instagram.com/reel/NUEVO1/?igshid=z"},
        headers=auth,
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["source_url"] == "https://www.instagram.com/reel/NUEVO1/"
    assert body["web_url"].endswith(f"/receta/{body['id']}")


def test_crear_dos_veces_la_misma_url_reutiliza(client, auth):
    payload = {"url": "https://www.instagram.com/reel/REPETIDO/"}
    first = client.post("/api/recipes", json=payload, headers=auth).json()
    second = client.post("/api/recipes", json=payload, headers=auth)
    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    assert second.json()["reused"] is True


def test_url_invalida_devuelve_400(client, auth):
    response = client.post("/api/recipes", json={"url": "no es una url"}, headers=auth)
    assert response.status_code == 400


def test_lista_de_la_compra_en_json(client, auth, stored_recipe):
    response = client.get(f"/api/recipes/{stored_recipe}/shopping-list", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Pasta al limón"
    assert "espaguetis — 200 g" in body["lines"]


def test_lista_de_la_compra_en_texto_plano_y_escalada(client, auth, stored_recipe):
    response = client.get(
        f"/api/recipes/{stored_recipe}/shopping-list",
        params={"format": "text", "servings": 4},
        headers=auth,
    )
    assert response.headers["content-type"].startswith("text/plain")
    assert "espaguetis — 400 g" in response.text


def test_lista_de_una_receta_no_lista_devuelve_409(client, auth):
    created = client.post(
        "/api/recipes", json={"url": "https://www.instagram.com/reel/ENCOLA/"}, headers=auth
    ).json()
    response = client.get(f"/api/recipes/{created['id']}/shopping-list", headers=auth)
    assert response.status_code == 409


def test_receta_inexistente_devuelve_404(client, auth):
    assert client.get("/api/recipes/nohay", headers=auth).status_code == 404


def test_clave_por_query_string_funciona_para_el_atajo(client, stored_recipe):
    response = client.get(f"/api/recipes/{stored_recipe}", params={"key": "clave-de-prueba"})
    assert response.status_code == 200


def test_borrar_receta(client, auth, stored_recipe):
    assert client.delete(f"/api/recipes/{stored_recipe}", headers=auth).status_code == 200
    assert client.get(f"/api/recipes/{stored_recipe}", headers=auth).status_code == 404


# --- Espera en una sola petición (lo que usa el Atajo) ----------------------

def test_wait_devuelve_la_receta_terminada_en_la_misma_peticion(client, auth, monkeypatch, sample_recipe):
    from app import main, storage

    def procesar_al_instante(_funcion, recipe_id, _url):
        storage.update_recipe(recipe_id, status="ready", title=sample_recipe.title,
                              data=sample_recipe.model_dump(mode="json"))

    monkeypatch.setattr(main._workers, "submit", procesar_al_instante)

    response = client.post(
        "/api/recipes",
        json={"url": "https://www.instagram.com/reel/ESPERA/", "wait": 30},
        headers=auth,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["recipe"]["title"] == "Pasta al limón"


def test_wait_va_mandando_espacios_para_que_ios_no_corte(client, auth, monkeypatch):
    import json

    from app import main

    monkeypatch.setattr(main, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(main._workers, "submit", lambda *a, **k: None)

    response = client.post(
        "/api/recipes",
        json={"url": "https://www.instagram.com/reel/LENTA/", "wait": 1},
        headers=auth,
    )
    # El cuerpo lleva relleno delante, pero sigue siendo JSON válido.
    assert response.text.startswith(" ")
    assert json.loads(response.text)["status"] in {"pending", "processing"}
    assert response.headers["content-type"].startswith("application/json")


def test_wait_no_puede_pedir_mas_de_cuatro_minutos(client, auth):
    response = client.post(
        "/api/recipes",
        json={"url": "https://www.instagram.com/reel/A/", "wait": 9999},
        headers=auth,
    )
    assert response.status_code == 422

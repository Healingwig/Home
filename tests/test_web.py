def test_la_portada_redirige_al_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_login_correcto_deja_ver_el_recetario(client):
    response = client.post("/login", data={"password": "hola", "next": "/"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Recetario" in response.text or "Recetas" in response.text


def test_login_incorrecto_devuelve_401(client):
    response = client.post("/login", data={"password": "mal", "next": "/"})
    assert response.status_code == 401


def test_ficha_de_receta_muestra_ingredientes_y_pasos(client, stored_recipe):
    client.post("/login", data={"password": "hola", "next": "/"})
    response = client.get(f"/receta/{stored_recipe}")
    assert response.status_code == 200
    assert "Pasta al limón" in response.text
    assert "espaguetis" in response.text
    assert "Cocer la pasta" in response.text
    assert "Modo cocina" in response.text


def test_la_ficha_escala_las_raciones(client, stored_recipe):
    client.post("/login", data={"password": "hola", "next": "/"})
    response = client.get(f"/receta/{stored_recipe}", params={"servings": 4})
    assert "400 g" in response.text


def test_receta_en_proceso_muestra_el_estado(client, auth):
    created = client.post(
        "/api/recipes", json={"url": "https://www.instagram.com/reel/ENPROCESO/"}, headers=auth
    ).json()
    client.post("/login", data={"password": "hola", "next": "/"})
    response = client.get(f"/receta/{created['id']}")
    assert "Preparando la receta" in response.text

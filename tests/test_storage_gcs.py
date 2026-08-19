"""El almacén de Cloud Storage, con un bucket de mentira.

Lo que importa aquí es la escritura condicionada del índice: dos recetas
procesándose a la vez escriben el mismo objeto y ninguna puede perderse.
"""

import json

import pytest
from google.api_core.exceptions import PreconditionFailed
from google.cloud.exceptions import NotFound

from app import storage
from app.storage import GcsObjectStore


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name

    @property
    def generation(self):
        return self.bucket.generations.get(self.name)

    def download_as_bytes(self):
        if self.name not in self.bucket.objects:
            raise NotFound(self.name)
        return self.bucket.objects[self.name]

    def upload_from_string(self, data, content_type=None, if_generation_match=None):
        self.bucket.uploads.append(self.name)
        if if_generation_match is not None:
            actual = self.bucket.generations.get(self.name, 0)
            if actual != if_generation_match:
                raise PreconditionFailed("la generación no coincide")
        if self.bucket.colisiones_pendientes:
            # Simula que otro proceso escribió justo antes que nosotros.
            self.bucket.colisiones_pendientes -= 1
            self.bucket.generations[self.name] = self.bucket.generations.get(self.name, 0) + 1
            raise PreconditionFailed("otro proceso se adelantó")
        self.bucket.objects[self.name] = data.encode() if isinstance(data, str) else data
        self.bucket.generations[self.name] = self.bucket.generations.get(self.name, 0) + 1

    def delete(self):
        if self.name not in self.bucket.objects:
            raise NotFound(self.name)
        del self.bucket.objects[self.name]


class FakeBucket:
    def __init__(self):
        self.objects, self.generations, self.uploads = {}, {}, []
        self.colisiones_pendientes = 0

    def blob(self, name):
        return FakeBlob(self, name)


@pytest.fixture
def bucket():
    return FakeBucket()


@pytest.fixture
def store(bucket, monkeypatch):
    # Sin esperas reales entre reintentos: aquí solo interesa la lógica.
    monkeypatch.setattr(storage, "INDEX_BACKOFF_SECONDS", 0)
    return GcsObjectStore("mi-cubo", prefix="recetario", bucket=bucket)


def test_el_prefijo_se_aplica_a_los_nombres(store, bucket):
    store.put_bytes("recetas/a.json", b"{}", "application/json")
    assert "recetario/recetas/a.json" in bucket.objects


def test_leer_escribir_y_borrar(store):
    assert store.get_bytes("x.json") is None
    store.put_json("x.json", {"hola": "mundo"})
    assert store.get_json("x.json") == {"hola": "mundo"}
    assert store.delete("x.json") is True
    assert store.delete("x.json") is False


def test_update_json_crea_el_objeto_si_no_existe(store):
    resultado = store.update_json("index.json", lambda actual: {**actual, "a": 1})
    assert resultado == {"a": 1}
    assert store.get_json("index.json") == {"a": 1}


def test_update_json_acumula_sobre_lo_que_ya_habia(store):
    store.update_json("index.json", lambda actual: {**actual, "a": 1})
    store.update_json("index.json", lambda actual: {**actual, "b": 2})
    assert store.get_json("index.json") == {"a": 1, "b": 2}


def test_update_json_reintenta_cuando_otro_proceso_se_adelanta(store, bucket):
    store.update_json("index.json", lambda actual: {**actual, "a": 1})
    bucket.colisiones_pendientes = 2

    store.update_json("index.json", lambda actual: {**actual, "b": 2})

    # Reintentó hasta que le tocó, y no perdió lo que ya estaba escrito.
    assert store.get_json("index.json") == {"a": 1, "b": 2}
    assert len([n for n in bucket.uploads if n.endswith("index.json")]) == 4


def test_update_json_se_rinde_si_no_para_de_chocar(store, bucket):
    bucket.colisiones_pendientes = 99
    with pytest.raises(RuntimeError, match="varios reintentos"):
        store.update_json("index.json", lambda actual: actual)


def test_un_indice_corrupto_no_bloquea_la_escritura(store, bucket):
    bucket.objects["recetario/index.json"] = b"esto no es json"
    bucket.generations["recetario/index.json"] = 7

    resultado = store.update_json("index.json", lambda actual: {**actual, "a": 1})
    assert resultado == {"a": 1}


def test_get_json_de_un_objeto_ilegible_devuelve_none(store, bucket):
    bucket.objects["recetario/roto.json"] = b"{{{"
    assert store.get_json("roto.json") is None

from app.models import Ingredient, format_quantity


def test_format_quantity_prefiere_fracciones_de_cocina():
    assert format_quantity(1.0) == "1"
    assert format_quantity(0.5) == "1/2"
    assert format_quantity(1.25) == "1 1/4"
    assert format_quantity(0.333) == "1/3"
    assert format_quantity(2.35) == "2,35"


def test_display_amount_sin_cantidad_usa_la_unidad():
    assert Ingredient(name="sal", unit="al gusto").display_amount() == "al gusto"
    assert Ingredient(name="huevo", quantity=2, unit="unidades").display_amount() == "2 unidades"


def test_categoria_desconocida_cae_en_otros():
    assert Ingredient(name="x", category="charcutería alemana").category == "otros"


def test_escalar_receta_multiplica_las_cantidades(sample_recipe):
    doble = sample_recipe.scaled(4)
    assert doble.servings == 4
    assert doble.ingredients[0].quantity == 400
    assert doble.ingredients[3].quantity is None  # "al gusto" no se escala
    # El original no se toca.
    assert sample_recipe.ingredients[0].quantity == 200


def test_escalar_sin_raciones_conocidas_no_hace_nada(sample_recipe):
    sin_raciones = sample_recipe.model_copy(update={"servings": None})
    assert sin_raciones.scaled(8) is sin_raciones

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


def test_las_unidades_en_palabra_se_pluralizan_al_escalar():
    from app.models import Ingredient

    cebolla = Ingredient(name="cebolla", quantity=1, unit="unidad")
    assert cebolla.display_amount() == "1 unidad"
    assert cebolla.scaled(2).display_amount() == "2 unidades"
    assert Ingredient(name="ajo", quantity=3, unit="diente").display_amount() == "3 dientes"


def test_las_abreviaturas_no_llevan_plural():
    from app.models import Ingredient

    assert Ingredient(name="harina", quantity=500, unit="g").display_amount() == "500 g"
    assert Ingredient(name="leche", quantity=250, unit="ml").display_amount() == "250 ml"


def test_media_unidad_sigue_en_singular():
    from app.models import Ingredient

    assert Ingredient(name="limón", quantity=0.5, unit="unidad").display_amount() == "1/2 unidad"


def test_una_unidad_desconocida_se_deja_como_viene():
    from app.models import Ingredient

    assert Ingredient(name="x", quantity=4, unit="chorretón").display_amount() == "4 chorretón"

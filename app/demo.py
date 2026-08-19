"""Receta de ejemplo, para ver la web y el modo cocina sin tocar Instagram."""

DEMO_RECIPE = {
    "title": "Tortilla de patatas jugosa",
    "summary": "La de siempre, con la patata pochada despacio y el huevo poco cuajado.",
    "servings": 4,
    "prep_minutes": 20,
    "cook_minutes": 30,
    "difficulty": "media",
    "cuisine": "española",
    "tags": ["clásico", "sin gluten", "cena rápida"],
    "equipment": ["sartén antiadherente de 24 cm", "plato llano más grande que la sartén"],
    "ingredients": [
        {"name": "patatas", "quantity": 700, "unit": "g", "note": "en láminas de medio centímetro",
         "category": "frutas y verduras", "optional": False, "pantry": False},
        {"name": "huevos", "quantity": 6, "unit": "unidades", "note": None,
         "category": "lácteos y huevos", "optional": False, "pantry": False},
        {"name": "cebolla", "quantity": 1, "unit": "unidad", "note": "en juliana fina",
         "category": "frutas y verduras", "optional": True, "pantry": False},
        {"name": "aceite de oliva virgen extra", "quantity": 400, "unit": "ml",
         "note": "para pochar; se reutiliza después", "category": "despensa",
         "optional": False, "pantry": True},
        {"name": "sal", "quantity": None, "unit": "al gusto", "note": None,
         "category": "especias y condimentos", "optional": False, "pantry": True},
    ],
    "steps": [
        {"number": 1, "title": "Preparar la patata",
         "instruction": "Pela las patatas y córtalas en láminas de medio centímetro. Sécalas bien "
                        "con un paño: el agua hace que salpiquen y que se frían en vez de pocharse.",
         "minutes": 10, "timer_seconds": None,
         "tip": "Que las láminas sean parecidas: si no, unas se deshacen y otras quedan duras.",
         "ingredients": ["700 g de patatas"]},
        {"number": 2, "title": "Pochar a fuego suave",
         "instruction": "Calienta el aceite a fuego medio-bajo y echa las patatas con la cebolla y "
                        "una pizca de sal. No deben freírse ni dorarse: tienen que quedar blandas y "
                        "pálidas. Remueve de vez en cuando.",
         "minutes": 20, "timer_seconds": 1200,
         "tip": "Si burbujea con fuerza, baja el fuego.",
         "ingredients": ["400 ml de aceite", "1 cebolla"]},
        {"number": 3, "title": "Escurrir y mezclar",
         "instruction": "Escurre bien las patatas en un colador y mézclalas con los huevos batidos "
                        "y sal. Deja reposar 10 minutos: la patata suelta almidón y la tortilla "
                        "queda mucho más cremosa.",
         "minutes": 10, "timer_seconds": 600, "tip": None,
         "ingredients": ["6 huevos"]},
        {"number": 4, "title": "Cuajar por el primer lado",
         "instruction": "En una sartén con una cucharada del aceite, a fuego medio-alto, vuelca la "
                        "mezcla. Baja a fuego medio y cuaja 3-4 minutos, separando los bordes con "
                        "una espátula.",
         "minutes": 4, "timer_seconds": 240,
         "tip": "El centro debe seguir moviéndose cuando agitas la sartén.",
         "ingredients": []},
        {"number": 5, "title": "Dar la vuelta",
         "instruction": "Tapa con un plato más grande que la sartén, dale la vuelta de golpe y "
                        "desliza la tortilla de nuevo a la sartén. Cuaja 2-3 minutos más.",
         "minutes": 3, "timer_seconds": 180,
         "tip": "Hazlo sobre el fregadero: si se escapa aceite, cae ahí.",
         "ingredients": []},
        {"number": 6, "title": "Reposar",
         "instruction": "Pásala a un plato y déjala reposar 5 minutos antes de cortar. Se asienta y "
                        "no se desmonta.",
         "minutes": 5, "timer_seconds": 300, "tip": None, "ingredients": []},
    ],
    "tips": [
        "El aceite de pochar, colado, sirve para freír patatas otra vez o para un sofrito.",
        "Con 6 huevos para 700 g de patata queda jugosa; con 5 queda más compacta.",
    ],
    "storage": "2 días en la nevera, tapada. Mejor a temperatura ambiente que fría de nevera.",
    "confidence": 1.0,
    "warnings": [
        "Esta es una receta de ejemplo escrita a mano, no sale de ningún vídeo: sirve para ver "
        "cómo se ve la aplicación antes de configurar nada.",
    ],
}

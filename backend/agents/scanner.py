"""Scanner Agent — identifica productos por barcode usando OpenFoodFacts."""
import requests


OPENFOODFACTS_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"


def lookup_barcode(barcode: str) -> dict | None:
    """Busca un producto por barcode en OpenFoodFacts. Devuelve None si no existe."""
    try:
        resp = requests.get(
            OPENFOODFACTS_URL.format(barcode=barcode),
            timeout=5,
            headers={"User-Agent": "MermaOps/1.0"},
        )
        data = resp.json()
        if data.get("status") != 1:
            return None
        product = data.get("product", {})
        return {
            "barcode": barcode,
            "name": product.get("product_name_es") or product.get("product_name", ""),
            "brand": product.get("brands", ""),
            "category": (product.get("categories_tags") or [""])[0].replace("en:", ""),
            "image_url": product.get("image_url", ""),
        }
    except Exception:
        return None

"""Fusiona movimientos recién importados con los que ya están guardados,
descartando los que ya existen (misma huella). Esto es lo que permite
volver a subir un CSV/PDF con meses superpuestos sin duplicar nada —
ver guion §6, "Deduplicación por huella"."""


def fusionar(existentes: list[dict], nuevos: list[dict]) -> tuple[list[dict], int]:
    """Devuelve (lista_fusionada, cantidad_agregada). Ordena por fecha."""
    huellas_existentes = {m.get("huella") for m in existentes if m.get("huella")}
    agregados = [m for m in nuevos if m.get("huella") not in huellas_existentes]
    fusionados = existentes + agregados
    fusionados.sort(key=lambda m: (m["fecha"], m["id"]))
    return fusionados, len(agregados)

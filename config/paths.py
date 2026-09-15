"""Rutas locales del proyecto (no versionar datos).

La carpeta de planos DXF se define por la variable de entorno PLANOS_DIR;
si no existe, se busca la ruta por defecto local.
"""
import os
from pathlib import Path

PROYECTO = Path(__file__).resolve().parents[1]
OUT = PROYECTO / "out"


def planos_dir() -> Path:
    env = os.environ.get("PLANOS_DIR")
    if env:
        p = Path(env)
        if p.exists():
            return p
    cand = PROYECTO.parent / "Proyecto_1_desde_0" / "Planos_1_dxf"
    if cand.exists():
        return cand
    raise FileNotFoundError(
        "No se encontraron los planos DXF. Defina la variable PLANOS_DIR."
    )


def etapa_dir(etapa: int) -> Path:
    if etapa not in (1, 2):
        raise ValueError("etapa debe ser 1 o 2")
    pref = "2017_67" if etapa == 1 else "2024_22"
    return planos_dir()


def prefijo(etapa: int) -> str:
    return "2017_67" if etapa == 1 else "2024_22"
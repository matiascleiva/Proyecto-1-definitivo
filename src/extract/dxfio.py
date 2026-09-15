"""Lectura de planos DXF y utilidades de entidades (ezdxf)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import ezdxf
from ezdxf.entities import DXFEntity
from ezdxf.math import Vec3

# Capas estructurales (plantas)
CAPAS = {
    "ejes_lineas": "RLE-EJES",
    "ejes_etiquetas": "RLE-EJE",
    "pilar": "RLE-PILAR",
    "viga": "RLE-VIGA",
    "losa": "RLE-LOSA",
    "muro": "RLE-MURO",
    "fundacion": "RLE-FUNDACION",
    "niveles": "RLE-NIVELES",
    "cota": "RLA-COTAS",
    "cota1": "RLA-COTAS1",
}


def cargar(path: Path):
    """Carga un DXF tolerante a codificación y saltos de línea."""
    for errs in (("strict",), ("replace",)):
        try:
            return ezdxf.readfile(path, encoding="cp1252", errors=errs[0])
        except (UnicodeDecodeError, ezdxf.DXFStructureError):
            continue
    return ezdxf.readfile(path)


def entidades(doc, layer: str) -> list:
    """Entidades de una capa en el modelspace."""
    if not doc:
        return []
    return list(doc.modelspace().query(f'*[layer=="{layer}"]'))


def extied(puntos: Sequence[Vec3]):
    """Bounding box (x0,y0,x1,y1) de puntos, o None si vacío."""
    xs, ys = [], []
    for p in puntos:
        xs.append(p[0])
        ys.append(p[1])
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def puntos_entidad(e: DXFEntity) -> Iterator[Vec3]:
    """Devuelve puntos representativos de una entidad."""
    t = e.dxftype()
    if t == "LINE":
        yield e.dxf.start
        yield e.dxf.end
    elif t == "LWPOLYLINE":
        for p in e.get_points():
            yield Vec3(p[0], p[1], p[2] if len(p) > 2 else 0)
    elif t == "CIRCLE":
        c = e.dxf.center
        yield Vec3(c[0] - e.dxf.radius, c[1] - e.dxf.radius, 0)
        yield Vec3(c[0] + e.dxf.radius, c[1] + e.dxf.radius, 0)
    elif t == "ARC":
        c = e.dxf.center
        yield Vec3(c[0] - e.dxf.radius, c[1] - e.dxf.radius, 0)
        yield Vec3(c[0] + e.dxf.radius, c[1] + e.dxf.radius, 0)


def bbox_entidades(elems: Iterable[DXFEntity]):
    pts = []
    for e in elems:
        pts.extend(puntos_entidad(e))
    return extied(pts)


def texto_entidad(e: DXFEntity) -> str:
    if e.dxftype() == "TEXT":
        return str(e.dxf.text)
    if e.dxftype() == "MTEXT":
        return str(e.plain_text())
    return ""


def agrupar(elems: Iterable[float], tol: float) -> list[float]:
    """Valores ordenados agrupados a una tolerancia (ej. coordenadas de ejes)."""
    vals = sorted(elems)
    grupos = []
    for v in vals:
        if grupos and abs(v - grupos[-1]) <= tol:
            grupos[-1] = (grupos[-1] + v) / 2.0
        else:
            grupos.append(v)
    return grupos
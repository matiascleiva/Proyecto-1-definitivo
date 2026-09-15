# -*- coding: utf-8 -*-
"""Paso 2 — Columnas S1 (de Z=0 a nivel 1° Subterráneo).

Fuentes:
  • Niveles (Serie 300 + planos 100-103): Z(1°S) = 3.96 m sobre Z=0
    (Z0 = N.R. -7.97; losa S1 = N.R. -4.01 → Δ = 3.96 m; pisos 3.96 m c/u).
  • Secciones: rótulos de elevación 'P.70x70' (0.70 × 0.70 m).

Genera:
  data/etapa1/secciones.json
  data/etapa1/nodos.json
  data/etapa1/elementos_verticales_Z1.json
  out/etapa1/02_columnas_z1.py     (OpenSeesPy: nodos 1°S + elasticBeamColumn)
  out/etapa1/resumen_columnas_z1.txt

Ejecuta el módulo y reporta trazabilidad.

Uso:
    python scripts/paso2_verticales.py
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.paths import OUT  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA1 = ROOT / "data" / "etapa1"
OUT1 = OUT / "etapa1"

Z_S1 = 3.96          # altura superior fundaciones → losa 1°S, en metros
E9 = 27_805_600.0    # kPa (módulo de elasticidad del hormigón, referencia)
G9 = 11_585_700.0    # kPa
GAMMA = 24.0         # kN/m³
# Conexión de cada columna basal con su nivel superior (esclavo).
NODE_SHIFT = 100


MATERIAL = {
    "name": "Hormigón (genérico)",
    "fck_mpa": 35,
    "E_kpa": E9,
    "G_kpa": G9,
    "gamma_kNm3": GAMMA,
}


def area_rect(b, h):
    return b * h


def inertia(b, h):
    return b * h ** 3 / 12


def torsion_j_square(a):
    return 0.1406 * a ** 4


def main() -> int:
    with open(DATA1 / "fundaciones.json", encoding="utf-8") as f:
        fund = json.load(f)

    # ---- secciones.json -------------------------------------------------
    b = h = 0.70  # m (P.70x70)
    sec = {
        "P70_70": {
            "tag": "P70_70",
            "nombre": "P. 70x70",
            "fuente": "Elevaciones Serie 300 (P.70x70) + planos de armaduras",
            "tipo": "rectangular",
            "b_m": b,
            "h_m": h,
            "A_m2": round(area_rect(b, h), 6),
            "Iy_m4": round(inertia(b, h), 8),
            "Iz_m4": round(inertia(b, h), 8),
            "J_m4": round(torsion_j_square(b), 8),
            "E_kpa": E9,
            "G_kpa": G9,
        }
    }
    secciones = {"material": MATERIAL, "secciones": sec,
                 "nota": "Secciones brutas; armadura se omite (solo rigideces).",
                 "niveles": {
                     "Z0_nivel_superior_fundaciones": 0.0,
                     "Z1S_losa_superior": Z_S1,
                     "Z1_piso": 7.92,
                     "h_piso": 3.96,
                     "fuente": "2017_67-100/101/102/103 + Serie 300",
                 }}

    # ---- nodos.json ------------------------------------------------------
    nodos = []
    for i, c in enumerate(fund["columnas_basales"], start=1):
        base = {
            "tag": i, "nombre": c["tag"], "x_m": c["x_m"], "y_m": c["y_m"],
            "z_m": 0.0, "nivel": "S0_fundaciones",
        }
        esclavo = {
            "tag": i + NODE_SHIFT, "nombre": c["tag"],
            "x_m": c["x_m"], "y_m": c["y_m"], "z_m": Z_S1,
            "nivel": "Z1S",
        }
        nodos.append(base)
        nodos.append(esclavo)

    ELEV_BLOQUE = {"1": "EJE1-1'", "2": "EJE2", "3": "EJE3-3'"}

    # ---- elementos_verticales_Z1.json -----------------------------------
    elems = []
    for i, c in enumerate(fund["columnas_basales"], start=1):
        elems.append({
            "elementTag": i,
            "type": "columna",
            "iNode": i,
            "jNode": i + NODE_SHIFT,
            "sectionTag": "P70_70",
            "geomTransfTag": 1,
            "geomTransf": "Linear",           # PDelta se activará con sismo
            "nombre": c["tag"],
            "elevacionFuente": f"Serie 300 · {ELEV_BLOQUE[c['eje_x']]}",
            "nivel": "S0_fundaciones",
        })

    for name, obj in (("secciones.json", secciones),
                      ("nodos.json", nodos),
                      ("elementos_verticales_Z1.json", elems)):
        with open(DATA1 / name, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    # ---- modulo OpenSeesPy ----------------------------------------------
    ejes = {c["tag"]: (c["eje_x"], c["eje_y"]) for c in fund["columnas_basales"]}
    tabla_sec = secciones["secciones"]["P70_70"]

    ins = []
    sec0 = tabla_sec
    for e in elems:
        x0 = next(n["x_m"] for n in nodos if n["tag"] == e["iNode"])
        y0 = next(n["y_m"] for n in nodos if n["tag"] == e["iNode"])
        ins.append(
            f"    ops.element(\"elasticBeamColumn\", {e['elementTag']}, "
            f"{e['iNode']}, {e['jNode']}, "
            f"{sec0['A_m2']}, {E9}, {G9}, {sec0['J_m4']}, "
            f"{sec0['Iy_m4']}, {sec0['Iz_m4']}, {e['geomTransfTag']})\n"
            f"    #   {e['nombre']} ({e['elevacionFuente']}) "
            f"@ X={x0} m, Y={y0} m, Z=0..{Z_S1}"
        )
    cuerpo = "\n".join(ins)

    src = (
        "# -*- coding: utf-8 -*-\n"
        '"""Columnas S1 — Z desde 0.0 (sup. fundaciones) hasta 3.96 m (losa 1°S).\n'
        "Generado por scripts/paso2_verticales.py.\n"
        'Secciones por elasticBeamColumn (material elástico E/G de secciones.json).\n'
        '"""\n'
        "import openseespy.opensees as ops\n"
        "\n"
        "from config.paths import PROYECTO  # noqa\n"
    )
    # src usa PROYECTO solo para robustez; evitamos import innecesario:
    src = src.replace("from config.paths import PROYECTO  # noqa\n", "")

    ind = "    "
    b_seg = (
        f"{ind}# Seccion P70_70 (0.70x0.70 m): A={sec0['A_m2']} m², "
        f"Iy=Iz={sec0['Iy_m4']} m⁴, J={sec0['J_m4']} m⁴ "
        "(propiedades inline en elasticBeamColumn)\n"
    )

    src += (
        "\n"
        "def crear(z_s1):\n"
        '    ops.wipe()\n'
        '    ops.model("basic", "-ndm", 3, "-ndf", 6)\n'
        + b_seg
        + "    _nodes = [\n"
    )
    for n in nodos:
        src += (f"        ({n['tag']}, \"{n['nombre']}\", "
                f"{n['x_m']:.4f}, {n['y_m']:.4f}, {n['z_m']:.4f}),\n")
    src += (
        "    ]\n"
        "    tag_map = {}\n"
        "    for tag, nombre, x, y, z in _nodes:\n"
        "        ops.node(tag, x, y, z)\n"
        "        tag_map[tag] = nombre\n"
        "    for tag, *_ in _nodes:\n"
        "        if tag <= 17:\n"
        '            ops.fix(tag, 1, 1, 1, 1, 1, 1)\n'
        '    ops.geomTransf("Linear", 1, 1.0, 0.0, 0.0)\n'
        "\n"
        + cuerpo + "\n"
        "    return tag_map\n"
        "\n"
        "\n"
        "def info():\n"
        "    return {\"nodos\": 34, \"columnas\": 17, \"z_s1_m\": 3.96, "
        "\"seccion\": \"P70_70\"}\n"
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    tag_map = crear(3.96)\n"
        '    print(f"Columnas S1 listas: 17 elementos elasticBeamColumn, '
        "34 nodos, Z 0 -> 3.96 m\")\n"
    )
    OUT1.mkdir(parents=True, exist_ok=True)
    (OUT1 / "02_columnas_z1.py").write_text(src, encoding="utf-8")

    # ---- reporte ---------------------------------------------------------
    ej2f = next((e for e in elems if e["nombre"] == "2-F"), None)
    reporte = (
        "PASO 2 — COLUMNAS S1 (fundaciones -> losa 1° Subterráneo)\n"
        f"nivel 1°S: Z = {Z_S1} m sobre Z=0 (sup. fundaciones N.R. -7.97)\n"
        "secciones:  P70_70 = 0.70x0.70 m (A, Iy, Iz, J en secciones.json)\n"
        f"nodos esclavos generados: {len(elems)}\n"
        f"columnas instanciadas:     {len(elems)}\n"
        "--- trazabilidad (ejemplo) ---\n"
        f"Columna Eje 2-F -> Elevación Eje 2 -> P.70x70 -> sectionTag P70_70 "
        f"-> geomTransf 1 (Linear) -> elementTag {ej2f['elementTag']} "
        f"(node {ej2f['iNode']} -> node {ej2f['jNode']})\n"
    )
    (OUT1 / "resumen_columnas_z1.txt").write_text(reporte, encoding="utf-8")
    print(reporte)
    print("archivos:")
    for n in ("secciones.json", "nodos.json", "elementos_verticales_Z1.json"):
        print("  ", DATA1 / n)
    print("  ", OUT1 / "02_columnas_z1.py")

    try:
        subprocess.run([sys.executable, str(OUT1 / "02_columnas_z1.py")], check=True)
    except Exception as err:
        print("  [aviso] fallo al correr el módulo:", err)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
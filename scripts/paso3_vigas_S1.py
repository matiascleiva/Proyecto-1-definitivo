"""Paso 3 — Vigas del nivel 1S (Z = 3.96 m).

Lee nodos.json + vigas_1S.json + secciones.json e instancia:
  - Nodos basales (Z=0, fijos) y esclavos (Z=3.96)
  - Columnas S1 (elasticBeamColumn, Z=0 -> Z=3.96)
  - Vigas principales 1S (elasticBeamColumn, Z=3.96)

Salida: out/etapa1/03_vigas_1S.py
"""
import json
from pathlib import Path

import openseespy.opensees as ops

DATA = Path(__file__).resolve().parents[1] / "data" / "etapa1"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def main():
    nodos = load("nodos.json")
    col_data = load("elementos_verticales_Z1.json")
    vigas = load("vigas_1S.json")
    secciones = load("secciones.json")
    mat = secciones["material"]

    ops.wipe()
    ops.model("basic", "-ndm", 3)

    # --- nodos ---
    for n in nodos:
        ops.node(n["tag"], n["x_m"], n["y_m"], n["z_m"])

    # --- fix basales (Z=0) ---
    basal_tags = {n["tag"] for n in nodos if n["z_m"] == 0.0}
    for tag in sorted(basal_tags):
        ops.fix(tag, 1, 1, 1, 1, 1, 1)

    # --- material ---
    ops.uniaxialMaterial("Elastic", 100, 1.0)

    # --- geomTransf ---
    # Tag 1: columnas verticales (vecX = (1,0,0))
    ops.geomTransf("Linear", 1, 1.0, 0.0, 0.0)
    # Tag 2: vigas long沿着Y (vecX = (1,0,0) -> eje local Z vertical)
    ops.geomTransf("Linear", 2, 1.0, 0.0, 0.0)
    # Tag 3: vigas trans沿着X (vecX = (0,1,0) -> eje local Z vertical)
    ops.geomTransf("Linear", 3, 0.0, 1.0, 0.0)

    # --- columnas ---
    sec_col = secciones["secciones"]["P70_70"]
    for c in col_data:
        A = sec_col["A_m2"]
        E = mat["E_kpa"]
        G = mat["G_kpa"]
        J = sec_col["J_m4"]
        Iy = sec_col["Iy_m4"]
        Iz = sec_col["Iz_m4"]
        ops.element("elasticBeamColumn", c["elementTag"],
                     c["iNode"], c["jNode"],
                     A, E, G, J, Iy, Iz, 1)

    # --- vigas 1S ---
    sec_v = secciones["secciones"]["V60x80"]
    tags_nodos = {n["tag"] for n in nodos}
    ok_vigas = []
    fail_vigas = []
    for v in vigas["vigas"]:
        iN, jN = v["iNode"], v["jNode"]
        if iN not in tags_nodos or jN not in tags_nodos:
            fail_vigas.append(v)
            continue
        gt = 2 if v["directriz"] == "Y" else 3  # Y沿=geom2, X沿=geom3
        A = sec_v["A_m2"]
        E = mat["E_kpa"]
        G = mat["G_kpa"]
        J = sec_v["J_m4"]
        Iy = sec_v["Iy_m4"]
        Iz = sec_v["Iz_m4"]
        ops.element("elasticBeamColumn", v["elementTag"],
                     iN, jN, A, E, G, J, Iy, Iz, gt)
        ok_vigas.append(v)

    # --- reporte ---
    n_nodos = ops.getNodeTags()
    n_elems = ops.getEleTags()
    n_cols = len(col_data)
    n_vigas = len(ok_vigas)

    print(f"Nodos totales:  {len(n_nodos)} (basales {len(basal_tags)} + esclavos {len(n_nodos)-len(basal_tags)})")
    print(f"Elementos total: {len(n_elems)} (columnas {n_cols} + vigas {n_vigas})")
    print(f"Vigas 1S OK:     {n_vigas}")
    if fail_vigas:
        print(f"Vigas FALLIDAS:  {len(fail_vigas)}")
        for v in fail_vigas:
            print(f"  tag={v['elementTag']} iNode={v['iNode']} jNode={v['jNode']} - nodo no encontrado")

    print("\n--- trazabilidad vigas (primeras 5) ---")
    for v in ok_vigas[:5]:
        ni = next(n for n in nodos if n["tag"] == v["iNode"])
        nj = next(n for n in nodos if n["tag"] == v["jNode"])
        L = ((nj["x_m"]-ni["x_m"])**2 + (nj["y_m"]-ni["y_m"])**2)**0.5
        print(f"  el={v['elementTag']:3d}  {ni['nombre']:4s}->{nj['nombre']:4s}  "
              f"L={L:.2f}m  eje={v['eje']}-{v['tramo']}  sec={v['seccion']}")

    print(f"\nResumen: {len(n_nodos)} nodos + {n_cols} columnas + {n_vigas} vigas = {len(n_nodos)+n_cols+n_vigas} items")
    print("Nivel 1S modelado correctamente.")


if __name__ == "__main__":
    main()

"""Paso 4 - Análisis del modelo 1S en la terminal.

Reconstruye el pórtico (columnas P70_70 + vigas V60x80) desde los JSON,
asigna masas lumped a nivel de losa (Z=3.96) y ejecuta:
  1) Análisis modal  -> períodos y frecuencias de los primeros modos
  2) Análisis estático de gravedad -> desplazamientos y reacciones base

Uso:
    python scripts/paso4_analisis.py
"""
import json
import math
from pathlib import Path

import openseespy.opensees as ops

DATA = Path(__file__).resolve().parents[1] / "data" / "etapa1"

# pesos por unidad de área (losas)
Q_LOSA_KPA = 7.5   # kN/m^2 (losa 15cm + acabados, primera estimacion)
G = 9.81            # m/s^2


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def construir_modelo():
    """Construye el modelo completo (nodos, fix, geomTransf, elementos, masas)."""
    nodos = load("nodos.json")
    cols = load("elementos_verticales_Z1.json")
    vgs = load("vigas_1S.json")
    secs = load("secciones.json")
    mat = secs["material"]

    ops.wipe()
    ops.model("basic", "-ndm", 3)

    for n in nodos:
        ops.node(n["tag"], n["x_m"], n["y_m"], n["z_m"])
        if n["z_m"] == 0.0:
            ops.fix(n["tag"], 1, 1, 1, 1, 1, 1)

    # geomTransf
    ops.geomTransf("Linear", 1, 1.0, 0.0, 0.0)   # columnas
    ops.geomTransf("Linear", 2, 1.0, 0.0, 0.0)   # vigas a lo largo de Y
    ops.geomTransf("Linear", 3, 0.0, 1.0, 0.0)   # vigas a lo largo de X

    E = mat["E_kpa"]; Go = mat["G_kpa"]
    pc = secs["secciones"]["P70_70"]
    pv = secs["secciones"]["V60x80"]

    for c in cols:
        ops.element("elasticBeamColumn", c["elementTag"], c["iNode"], c["jNode"],
                    pc["A_m2"], E, Go, pc["J_m4"], pc["Iy_m4"], pc["Iz_m4"], 1)
    for v in vgs["vigas"]:
        gt = 2 if v["directriz"] == "Y" else 3
        ops.element("elasticBeamColumn", v["elementTag"], v["iNode"], v["jNode"],
                    pv["A_m2"], E, Go, pv["J_m4"], pv["Iy_m4"], pv["Iz_m4"], gt)

    # área de losa y masa lumped por nodo esclavo
    esclavos = [n for n in nodos if n["z_m"] > 0]
    area = (max(n["x_m"] for n in nodos) * max(n["y_m"] for n in nodos))
    w_total = area * Q_LOSA_KPA          # kN
    m_total = w_total / G                # Mg (t)
    m_nodo = m_total / len(esclavos)

    for n in esclavos:
        ops.mass(n["tag"], m_nodo, m_nodo, m_nodo, 0, 0, 0)

    return nodos, cols, w_total, m_nodo, esclavos


def analisis_modal(n_modos=8):
    ops.wipeAnalysis()
    try:
        vals = list(ops.eigen(n_modos))
    except Exception as e:
        print(f"eigen fallo: {e}")
        return
    # eigen val que devuelve: lista de autovalores (omega^2) de menor a mayor
    print("\n" + "=" * 70)
    print(f"ANALISIS MODAL  ({n_modos} modos)  -  masa por piso {m_nodo:.1f} Mg")
    print("=" * 70)
    print(f"{'Modo':>5s} {'Periodo T (s)':>14s} {'Frec. f (Hz)':>14s} "
          f"{'Omega (rad/s)':>14s} {'Tf/1':>8s}")
    for i, omega2 in enumerate(vals, 1):
        if omega2 <= 0:
            continue
        w = math.sqrt(omega2)
        T = 2 * math.pi / w
        f = w / (2 * math.pi)
        tt = T / vals[0] ** 0.5 if vals[0] > 0 else 0
        if i == 1:
            print(f"{i:5d} {T:14.4f} {f:14.4f} {w:14.4f} {'--':>8s}")
        else:
            try:
                t1 = 2 * math.pi / math.sqrt(vals[0])
                print(f"{i:5d} {T:14.4f} {f:14.4f} {w:14.4f} {T/t1:8.3f}")
            except Exception:
                print(f"{i:5d} {T:14.4f} {f:14.4f} {w:14.4f} {'--':>8s}")


def analisis_gravedad(nodos, cols, w_total):
    """Analisis estatico de gravedad (reacta en base via recorder)."""
    ops.wipeAnalysis()

    basal_tags = [n["tag"] for n in nodos if n["z_m"] == 0.0]
    reacf = Path(__file__).resolve().parent / "_reac_base.txt"
    if reacf.exists():
        reacf.unlink()

    ops.recorder("Node", "-file", str(reacf), "-node", *basal_tags,
                 "-dof", 3, "reaction")

    esclavos = [n for n in nodos if n["z_m"] > 0]
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    w_nodo = w_total / len(esclavos)     # kN por nodo
    for n in esclavos:
        ops.load(n["tag"], 0.0, 0.0, -w_nodo, 0, 0, 0)

    ops.constraints("Plain")
    ops.numberer("RCM")
    ops.system("BandGeneral")
    ops.test("NormDispIncr", 1.0e-8, 50)
    ops.algorithm("Linear")
    ops.integrator("LoadControl", 1.0)
    ops.analysis("Static")
    ok = ops.analyze(1)
    ops.record()

    print("\n" + "=" * 70)
    print(f"ANALISIS ESTATICO DE GRAVEDAD  (carga en losados {Q_LOSA_KPA:.1f} kPa)")
    print("=" * 70)
    if ok != 0:
        print(f"ANALISIS NO CONVERGIO (ok={ok})")
        return

    # desplazamientos verticales en nivel 1S
    dzs = [ops.nodeDisp(n["tag"], 3) for n in esclavos]
    dmax = max(dzs, key=abs)
    dmin = min(dzs, key=abs)
    dxs = [ops.nodeDisp(n["tag"], 1) for n in esclavos]
    dys = [ops.nodeDisp(n["tag"], 2) for n in esclavos]
    print(f"convergencia: ok={ok}")
    print(f"desp. vertical maximo : {dmax:+.4f} m en nodo {esclavos[dzs.index(dmax)]['tag']}")
    print(f"desp. vertical minimo : {dmin:+.4f} m")
    print(f"desp. horizontal medio X: {sum(dxs)/len(dxs)*1000:+.3f} mm")
    print(f"desp. horizontal medio Y: {sum(dys)/len(dys)*1000:+.3f} mm")

    # reacciones en base desde recorder
    rz = sum(float(x) for x in reacf.read_text().split())
    print(f"reaccion base  Rz (suma columnas) = {rz:+.1f} kN")
    print(f"carga aplicada       W = {w_total:+.1f} kN"
          f"   [balance: {abs(rz-w_total)/max(abs(w_total),1)*100:5.2f}%]")


if __name__ == "__main__":
    nodos, cols, w_total, m_nodo, esclavos = construir_modelo()
    print(f"Modelo: {len(nodos):3d} nodos | {len(cols):2d} columnas | "
          f"{(sum(1 for _ in load('vigas_1S.json')['vigas'])):2d} vigas")
    print(f"Area losa: {max(n['x_m'] for n in nodos) * max(n['y_m'] for n in nodos):.1f} m^2"
          f" | W_total = {w_total:.0f} kN | m_nodo = {m_nodo:.1f} Mg")
    analisis_gravedad(nodos, cols, w_total)
    analisis_modal(8)
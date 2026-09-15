"""Panel de resultados — imprime un resumen analítico por etapa.

Lee los JSON generados por step3_modelo (gravedad) y step4_sismo
(sismo estático NCh433/DS61) y los presenta en consola.

Uso:
    python scripts/ver_resultados.py [etapa ...]

Los resultados crudos están en out/etapaN/:
    modelo_columnas.json    axial (P) por columna y nivel (solo gravedad)
    sismo.json              períodos, corte basal, F_k y fuerzas por caso
    sismo_envolvente.json   máximos por elemento/nivel (4 casos: X±, Y±)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.paths import OUT  # noqa: E402


def tab(lista, anchos):
    return "  " + "  ".join(f"{str(v):>{a}}" for v, a in zip(lista, anchos))


def resumen(etapa):
    o = OUT / f"etapa{etapa}"
    print("=" * 78)
    print(f"  RESULTADOS — ETAPA {etapa}")
    print("=" * 78)

    geo = json.loads((o / "modelo_geometria.json").read_text(encoding="utf-8"))
    cfg = geo["config"]
    print(tab(["Parámetro", "Valor", "", "", ""], [0, 50, 0, 0, 0]).rstrip())
    for kcnf, lab in (("n_columnas", "Columnas/nivel"), ("n_vigas", "Vigas/nivel"),
                      ("n_muros", "Muros/nivel"), ("n_niveles", "Niveles"),
                      ("area_piso_m2", "Área de piso [m²]"),
                      ("qG_kN_m2", "Carga qG [kN/m²]")):
        print(f"  {lab:<28} {cfg.get(kcnf):>10.2f}")

    # --- gravedad: axial por columna ---
    print("\n-- GRAVEDAD (solo PP + S/C por área de influencia) --")
    col = json.loads((o / "modelo_columnas.json").read_text(encoding="utf-8"))
    ks = sorted(col, key=int)
    base = [(t, col[ks[0]][t]) for t in sorted(col[ks[0]], key=lambda t: -col[ks[0]][t])]
    print("  Axial P [kN] en columna (base = nivel 1):")
    print(tab(["Columna", "n1", "n2", "n3", "n4", "n5"], [10, 10, 10, 10, 10, 10]))
    for tag, _ in base:
        print(tab([tag] + [f"{col[kk][tag]:,.0f}" for kk in ks], [10, 10, 10, 10, 10, 10]))
    print(f"  Σ axial total (nivel 5) = "
          f"{sum(col[ks[-1]].values()):,.1f} kN")

    # --- tributarias: verificación losa→columnas ---
    tr = json.loads((o / "tributarias_101.json").read_text(encoding="utf-8"))
    at_sum = sum(c["area_influencia_m2"] for c in tr["columnas"])
    print("\n-- LOSA POR ÁREAS TRIBUTARIAS (por piso) --")
    print(f"  Σ áreas de influencia = {at_sum:,.1f} m²  vs  losa neta = "
          f"{tr['area_losa_neta_m2']:,.1f} m² "
          f"({at_sum / tr['area_losa_neta_m2'] - 1:+.1%})")
    cols_tr = sorted(tr["columnas"], key=lambda x: -x["area_influencia_m2"])
    print("  Columnas de mayor área de influencia:")
    for cc in cols_tr[:5]:
        print(f"    {cc['tag']:<7} A={cc['area_influencia_m2']:>6.1f} m² | "
              f"q={cc['q_axial_por_piso_kN']:>7.1f} kN")
    qg = tr.get("cargas", {}).get("qG_kN_m2")
    if qg:
        P_check = at_sum * qg
        suma = sum(x["q_axial_por_piso_kN"] for x in cols_tr)
        print(f"  qG={qg:.2f} kN/m² · ΣA={sus:,.0f} m² → carga por piso "
              f"esperada {P_check:,.0f} kN (tributaria: {suma:,.0f} kN)")

    # --- sismo ---
    si = json.loads((o / "sismo.json").read_text(encoding="utf-8"))
    print("\n-- SISMO (NCh433 mod.2009 + DS61, A0=0.30g, Suelo II, R=11) --")
    for dx in ("X", "Y"):
        print(f"  {dx}: T bruto={si['T' + dx]:.3f} s → T*={si['T' + dx + 's']:.3f} s | "
              f"C={si['C' + dx]:.4f} | V={si['V' + dx]:,.0f} kN "
              f"({si['V' + dx] / si['W']:.2%} W)")
    print("  Fuerzas F_k por nivel: X:", ", ".join(f"{f:,.0f}" for f in si["Fx"]))
    print("                         Y:", ", ".join(f"{f:,.0f}" for f in si["Fy"]))
    if "todo" in si:
        dr = max(max(abs(d) for d in c.get("drift", [0])) for c in si["todo"].values())
        rd = max(max(abs(d) for d in c.get("disp", [0])) for c in si["todo"].values())
        print(f"  Desplazamiento de techo máx: {rd * 1000:,.1f} mm")
        print(f"  Drift de entrepiso máx:      {dr * 1000:,.2f} ‰")

    # --- envolvente sismo ---
    env = json.loads((o / "sismo_envolvente.json").read_text(encoding="utf-8"))
    if isinstance(env, list):
        fused: dict = {}
        for dic in env:
            for tag, niv in dic.items():
                if tag in fused:
                    fused[tag] = {nv: {c: max(fused[tag].get(nv, {}).get(c, 0), niv[nv][c])
                                       for c in niv[nv]}
                                  for nv in niv}
                else:
                    fused[tag] = {nv: dict(niv[nv]) for nv in niv}
        env = fused
        with open(o / "sismo_envolvente.json", "w", encoding="utf-8") as f:
            json.dump(env, f, ensure_ascii=False, indent=2)
    print("\n-- ENVOLVENTE SÍSMICA (máx |P|,|Vy|,|Vz|,|My|,|Mz| entre X± Y±) --")
    cols = [t for t in env if not t.startswith("MUR")]
    murs = [t for t in env if t.startswith("MUR")]
    pc = max((env[t][nv]["P"] for t in cols for nv in env[t]), default=0)
    pc_t = max((t for t in cols), key=lambda t: max(env[t][nv]["P"] for nv in env[t]))
    mm = max((env[t][nv]["My"] for t in murs for nv in env[t]), default=0)
    mm_t = max((t for t in murs),
               key=lambda t: max(env[t][nv]["My"] for nv in env[t]))
    mv = max((env[t][nv]["Mz"] for t in cols for nv in env[t]), default=0)
    mv_t = max((t for t in cols),
               key=lambda t: max(env[t][nv]["Mz"] for nv in env[t]))
    print(f"  Columna con mayor axial     : {pc_t}  P={pc:,.0f} kN")
    print(f"  Columna con mayor Mz        : {mv_t}  Mz={mv:,.0f} kN·m")
    print(f"  Muro con mayor My (base)    : {mm_t}  My={mm:,.0f} kN·m")
    print(f"  Elementos envolvente: {len(env)}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    etapas = [int(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else [1, 2]
    for e in etapas:
        try:
            resumen(e)
        except FileNotFoundError as ex:
            print(f"Etapa {e}: falta archivo de resultados — "
                  f"corre primero step3/step4 ({ex.filename})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
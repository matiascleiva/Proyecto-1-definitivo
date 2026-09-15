"""Paso 1 — Reconocimiento de la grilla de ejes de una planta (Etapa dada).

Detecta los ejes a partir de los círculos de rótulo (capa RLE-EJE) y las
etiquetas de texto asociadas, y genera:

    out/etapa<k>/grid_ejes.json      # ejes X e Y con etiquetas (cm y m)
    out/etapa<k>/reconocimiento.png  # verificación visual

Uso:
    python scripts/step1_ejes.py [etapa] [lámina]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.paths import OUT, prefijo  # noqa: E402
from src.extract import dxfio  # noqa: E402


def circulos(doc):
    """Círculos de rótulo de ejes (capa RLE-EJE)."""
    return [e for e in dxfio.entidades(doc, "RLE-EJE") if e.dxftype() == "CIRCLE"]


def etiquetas(doc, c, x0, x1, y0, y1, hoja, eje_val, lado="abajo"):
    """Etiqueta del rótulo (capa RLE-EJE) cercana a un círculo de eje,
    prefiriendo textos fuera del plano (al borde de la lámina)."""
    mejor, dmin = "", 1e18

    def fuera(t):
        # texto del rótulo colocado fuera del plano (sector de estrellas)
        return t[0] < x0 or t[0] > x1 or t[1] < y0 or t[1] > y1

    for e in dxfio.entidades(doc, "RLE-EJE"):
        if e.dxftype() not in ("TEXT", "MTEXT"):
            continue
        txt = dxfio.texto_entidad(e).strip()
        if not txt or len(txt) > 3:
            continue
        ins = e.dxf.insert
        if hoja == "X":   # eje vertical: alineado en X con el círculo
            d = abs(ins[0] - eje_val)
            alineado = d < 60 and (ins[1] < y0 + 120 or ins[1] > y1 - 120)
        else:             # eje horizontal: alineado en Y con el círculo
            d = abs(ins[1] - eje_val)
            alineado = d < 60 and (ins[0] < x0 + 120 or ins[0] > x1 - 120)
        if not alineado:
            continue
        p = d + (0.0 if fuera((ins[0], ins[1])) else 200.0)
        if p < dmin:
            mejor, dmin = txt, p
    return mejor


def main():
    etapa = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    lamina = sys.argv[2] if len(sys.argv) > 2 else "-100"

    doc = dxfio.cargar(dxfio_path(etapa, lamina))
    cirs = circulos(doc)
    cs = [(e.dxf.center[0], e.dxf.center[1]) for e in cirs]
    if not cs:
        print("No se encontraron círculos de ejes en", lamina)
        return 1

    xs, ys = [p[0] for p in cs], [p[1] for p in cs]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    spanx, spany = (x1 - x0), (y1 - y0)

    tol = 5.0
    # Filas inferior (abajo) y superior (arriba): contienen los círculos de los
    # EJES VERTICALES (su coordenada X es la posición del eje).
    abajo = [y for x, y in cs if y - y0 < 0.35 * spany]
    arriba = [y for x, y in cs if y1 - y < 0.35 * spany]
    x_baj = [x for x, y in cs if y - y0 < 0.35 * spany]
    x_arriba = [x for x, y in cs if y1 - y < 0.35 * spany]
    ejes_x = dxfio.agrupar(x_baj + x_arriba, 15.0)   # ejes verticales (letras)

    # Columnas izquierda y derecha: contienen los círculos de los
    # EJES HORIZONTALES (su coordenada Y es la posición del eje).
    y_izq = [y for x, y in cs if x - x0 < 0.35 * spanx]
    y_der = [y for x, y in cs if x1 - x < 0.35 * spanx]
    ejes_y = dxfio.agrupar(y_izq + y_der, 15.0)      # ejes horizontales (números)

    # Etiquetas de los ejes
    gx, gy = [], []
    for vx in ejes_x:
        c = (vx, (y0 + y1) / 2.0)
        gx.append({"etiqueta": etiquetas(doc, c, x0, x1, y0, y1, "X", vx),
                   "x_cm": round(vx, 2)})
    for vy in ejes_y:
        c = ((x0 + x1) / 2.0, vy)
        gy.append({"etiqueta": etiquetas(doc, c, x0, x1, y0, y1, "Y", vy),
                   "y_cm": round(vy, 2)})
    gx = [e for e in gx if e["etiqueta"]]
    gy = [e for e in gy if e["etiqueta"]]

    # Resumen de capas
    resumen = {
        layer: len(dxfio.entidades(doc, CAPA)) for layer, CAPA in dxfio.CAPAS.items()
    }

    out_dir = OUT / f"etapa{etapa}"
    out_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "etapa": etapa,
        "lamina": lamina,
        "extent_cm": {"x0": round(x0, 1), "y0": round(y0, 1),
                      "x1": round(x1, 1), "y1": round(y1, 1)},
        "ejes_x": gx,
        "ejes_y": gy,
        "n_ejes_x": len(gx),
        "n_ejes_y": len(gy),
        "resumen_capas": resumen,
    }
    with open(out_dir / "grid_ejes.json", "w", encoding="utf-8") as f:
        import json
        json.dump(data, f, ensure_ascii=False, indent=2)

    try:
        render(doc, out_dir / f"reconocimiento_{lamina.strip('-')}.png", gx, gy, data["extent_cm"], etapa, lamina)
    except Exception as err:
        print("  [aviso] no se generó la imagen:", err)

    print(f"Etapa {etapa} · {lamina}")
    print(f"  ejes X ({len(gx)}): " + ", ".join(f'{e["etiqueta"]}={e["x_cm"]/100:.2f}m' for e in gx))
    print(f"  ejes Y ({len(gy)}): " + ", ".join(f'{e["etiqueta"]}={e["y_cm"]/100:.2f}m' for e in gy))
    print(f"  extensión: {spanx/100:.1f} m x {spany/100:.1f} m  ->  {out_dir / 'grid_ejes.json'}")


def dxfio_path(etapa, lamina):
    return dxfio_root() / f"{prefijo(etapa)}{lamina}.dxf"


def dxfio_root():
    from config.paths import planos_dir
    return planos_dir()


def render(doc, out_png, gx, gy, extent, etapa, lamina):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle

    x0, y0, x1, y1 = extent["x0"], extent["y0"], extent["x1"], extent["y1"]
    fig, ax = plt.subplots(figsize=(15, 12))

    def dib_layers(capa, color, lw=0.8, alpha=0.8):
        for e in dxfio.entidades(doc, capa):
            if e.dxftype() == "LINE":
                s, t = e.dxf.start, e.dxf.end
                ax.plot([s[0], t[0]], [s[1], t[1]], color=color, lw=lw, alpha=alpha)
            elif e.dxftype() == "CIRCLE":
                c = e.dxf.center
                ax.add_patch(Circle((c[0], c[1]), e.dxf.radius, fill=False,
                                    edgecolor=color, lw=lw, alpha=alpha))

    dib_layers("RLE-EJES", "gray", lw=0.5, alpha=0.5)     # líneas de eje
    dib_layers("RLE-VIGA", "tab:blue", lw=1.0)            # vigas
    dib_layers("RLE-PILAR", "tab:red", lw=1.5)            # columnas
    dib_layers("RLE-MURO", "tab:green", lw=1.2)           # muros
    dib_layers("RLE-FUNDACION", "tab:orange", lw=1.0)     # fundaciones

    # grilla detectada
    for e in gx:
        ax.axvline(e["x_cm"], color="purple", lw=1.2, ls="--")
        ax.text(e["x_cm"], y1 - 40, e["etiqueta"], fontsize=8, ha="center", color="purple")
    for e in gy:
        ax.axhline(e["y_cm"], color="purple", lw=1.2, ls="--")
        ax.text(x1 - 40, e["y_cm"], e["etiqueta"], fontsize=8, va="center", color="purple")

    ax.set_xlim(x0 - 300, x1 + 300)
    ax.set_ylim(y0 - 300, y1 + 300)
    ax.set_aspect("equal")
    ax.set_title(f"Etapa {etapa} · {lamina} · PLANTA FUNDACIONES — verificación")
    ax.grid(True, lw=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    print(f"  imagen de verificación -> {out_png}")


if __name__ == "__main__":
    raise SystemExit(main())
# Proyecto 1 — Análisis Estructural con OpenSees + Unity

Modelo estructural 3D (6 GDL/nodo) de un edificio de hormigón armado en dos etapas
(construidas como un solo edificio con junta estructural), idealizado a partir de
planos DXF reales.

- **Análisis**: OpenSees/OpenSeesPy (modelo lineal elástico 3D + secciones de fibras
  para capacidad P-M y M-φ).
- **Visualización / pre-postproceso**: Unity (geometría, IDs, ejes, apoyos,
  diafragmas, cargas, áreas tributarias, deformadas, diagramas, demanda-capacidad).
- **Planos fuente**: 
  - Etapa 1: `2017_67-*.dxf`
  - Etapa 2: `2024_22-*.dxf`

## Flujo

| Fase | Descripción | Salida |
|---|---|---|
| 1 | Extracción DXF → modelo geométrico normalizado (m) | `out/etapa*/...json` |
| 2 | Construcción del modelo OpenSeesPy (G, Q, EX, EY) | scripts `src/model/` |
| 3 | Verificación (equilibrio, superposición, deformadas) | `out/resultados*.json` |
| 4 | Capacidad no lineal (fibras, P-M, M-φ) | `out/capacidad/` |
| 5 | Export a Unity + viewer | `unity/` |

## Estructura

```
config/            # rutas locales (planos, salidas)
src/extract/       # lectura DXF y normalización
scripts/           # pasos ejecutables (step1_ejes.py, ...)
out/               # resultados generados (gitignored)
unity/             # proyecto Unity
```

## Convenciones principales

- Unidades de planos: dibujo en **cm** → modelo en **m** (factor 1/100).
- Material estructural: hormigón **G35 (H-35)**, refuerzo según planos.
- Elementos: viga-columna lineales (`elasticBeamColumn` / fibras), muros como
  elementos lineales equivalentes, losas **NO** como FEM (solo carga vía áreas
  tributarias).
- Casos base independientes: **G** (peso propio + terminaciones), **Q** (viva),
  **EX**, **EY** (lateral pseudoestático).

## Cómo correr

```bash
pip install -r requirements.txt
python scripts/step1_ejes.py          # Paso 1: grilla de ejes Etapa 1
```

Los DXFs no se versionan (≈ 1.7 GB). La ruta se define en `config/paths.py`
(variable de entorno `PLANOS_DIR`).
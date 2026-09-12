#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Dashboard interactivo — CMF / Ley 21.757
Lee una corrida V3.x generada por cmf_directorios_21757_v3_2.py.

Uso:
    py -m streamlit run dashboard_directorios_21757.py
o:
    py -m streamlit run dashboard_directorios_21757.py -- --run-dir .\corrida_20260911_v3_2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


REQUIRED = (
    "03_directores_con_sexo.csv",
    "05_resumen_final_v3.csv",
)

OPTIONAL = (
    "00_universo_ley_21757.csv",
    "09_discordancias_registro_vs_reporte.csv",
    "10_discordancias_prioritarias.csv",
    "12_entidades_sin_composicion_nominal.csv",
    "AUDITORIA_checks.csv",
)


def clean(x) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip()


def normalize_rut(x) -> str:
    s = clean(x)
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return "".join(ch for ch in s if ch.isdigit() or ch.upper() == "K").upper()


def rut_display(body: str) -> str:
    """Pretty-print the company RUT body if DV is not available."""
    s = normalize_rut(body)
    if not s:
        return ""
    # Dataset uses company RUT body without DV.
    if len(s) <= 3:
        return s
    groups = []
    while len(s) > 3:
        groups.append(s[-3:])
        s = s[:-3]
    groups.append(s)
    return ".".join(reversed(groups))


def parse_date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, dayfirst=True, errors="coerce")


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def discover_run_dir() -> Path | None:
    here = Path.cwd()
    candidates = []
    for p in here.glob("corrida_*"):
        if p.is_dir() and all((p / f).exists() for f in REQUIRED):
            try:
                mtime = max((p / f).stat().st_mtime for f in REQUIRED)
            except OSError:
                mtime = 0
            candidates.append((mtime, p))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def cli_default_run_dir() -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--run-dir")
    try:
        args, _ = parser.parse_known_args(sys.argv[1:])
        if args.run_dir:
            return args.run_dir
    except Exception:
        pass
    found = discover_run_dir()
    return str(found) if found else ""


@st.cache_data(show_spinner=False)
def load_data(run_dir_str: str):
    root = Path(run_dir_str).expanduser().resolve()
    missing = [f for f in REQUIRED if not (root / f).exists()]
    if missing:
        raise FileNotFoundError("Faltan archivos requeridos: " + ", ".join(missing))

    directors = read_csv(root / "03_directores_con_sexo.csv")
    summary = read_csv(root / "05_resumen_final_v3.csv")

    optional = {}
    for f in OPTIONAL:
        p = root / f
        optional[f] = read_csv(p) if p.exists() else pd.DataFrame()

    # Normalize join keys.
    for df in [directors, summary, *optional.values()]:
        if not df.empty and "rut_empresa" in df.columns:
            df["rut_empresa"] = df["rut_empresa"].map(normalize_rut)

    # Numeric summary columns.
    numeric_cols = [
        "n_titulares", "n_hombres", "n_mujeres", "n_revisar",
        "pct_hombres", "pct_mujeres",
        "pct_cmf_actual_num", "pct_cmf_anterior",
        "pct_reconstruido_registro_nominal",
        "delta_registro_vs_reporte_pp", "delta_abs_registro_vs_reporte_pp",
        "umbral_aplicable",
    ]
    for c in numeric_cols:
        if c in summary.columns:
            summary[c] = pd.to_numeric(summary[c], errors="coerce")

    bool_cols = [
        "eleccion_post_entrada_ley",
        "sobre_umbral_sugerido_cmf",
        "sobre_umbral_y_eleccion_post_ley_cmf",
        "registro_nominal_consistente_0_6pp",
    ]
    for c in bool_cols:
        if c in summary.columns:
            summary[c] = summary[c].astype(str).str.upper().map(
                {"TRUE": True, "FALSE": False, "1": True, "0": False}
            )

    # Dates.
    for c in ["fecha_junta_actual", "fecha_junta_anterior", "fecha_max_nombramiento_nominal"]:
        if c in summary.columns:
            summary[c + "_dt"] = parse_date_series(summary[c])

    if "fecha_nombramiento" in directors.columns:
        directors["fecha_nombramiento_dt"] = parse_date_series(directors["fecha_nombramiento"])

    # Join company-level official metrics into each director row.
    join_cols = [
        "rut_empresa", "razon_social", "pct_cmf_actual_num",
        "fecha_junta_actual", "fecha_junta_actual_dt",
        "pct_cmf_anterior", "fecha_junta_anterior", "fecha_junta_anterior_dt",
        "n_titulares", "n_hombres", "n_mujeres",
        "estado_regulatorio_cmf", "diagnostico_consistencia",
        "delta_abs_registro_vs_reporte_pp",
        "eleccion_post_entrada_ley", "sobre_umbral_sugerido_cmf",
    ]
    join_cols = [c for c in join_cols if c in summary.columns]
    company_meta = summary[join_cols].drop_duplicates("rut_empresa")

    # Avoid duplicate razon_social after merge.
    d = directors.copy()
    if "razon_social" in d.columns and "razon_social" in company_meta.columns:
        company_meta = company_meta.rename(columns={"razon_social": "razon_social_resumen"})
    d = d.merge(company_meta, on="rut_empresa", how="left")

    if "razon_social_resumen" in d.columns:
        if "razon_social" not in d.columns:
            d["razon_social"] = d["razon_social_resumen"]
        else:
            d["razon_social"] = d["razon_social"].where(
                d["razon_social"].astype(str).str.strip().ne(""),
                d["razon_social_resumen"],
            )

    return root, d, summary, optional


def fmt_pct(x):
    try:
        if pd.isna(x):
            return ""
        return f"{float(x):.2f}%"
    except Exception:
        return clean(x)


def fmt_date(x):
    try:
        if pd.isna(x):
            return ""
        if isinstance(x, pd.Timestamp):
            return x.strftime("%d/%m/%Y")
    except Exception:
        pass
    return clean(x)


def bool_label(x):
    if x is True:
        return "Sí"
    if x is False:
        return "No"
    return ""


def safe_col(df: pd.DataFrame, name: str, default=""):
    if name in df.columns:
        return df[name]
    return pd.Series([default] * len(df), index=df.index)


def company_table(summary: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=summary.index)
    x["Empresa"] = safe_col(summary, "razon_social")
    x["RUT"] = safe_col(summary, "rut_empresa").map(rut_display)
    x["Directores"] = safe_col(summary, "n_titulares")
    x["Hombres"] = safe_col(summary, "n_hombres")
    x["Mujeres"] = safe_col(summary, "n_mujeres")
    x["% CMF"] = safe_col(summary, "pct_cmf_actual_num")
    x["Fecha elección/junta"] = safe_col(summary, "fecha_junta_actual_dt").map(fmt_date)
    x["% anterior"] = safe_col(summary, "pct_cmf_anterior")
    x["Fecha anterior"] = safe_col(summary, "fecha_junta_anterior_dt").map(fmt_date)
    x["Post ley"] = safe_col(summary, "eleccion_post_entrada_ley").map(bool_label)
    x["> umbral"] = safe_col(summary, "sobre_umbral_sugerido_cmf").map(bool_label)
    x["Estado CMF"] = safe_col(summary, "estado_regulatorio_cmf")
    x["Diagnóstico registro"] = safe_col(summary, "diagnostico_consistencia")
    x["Delta abs. pp"] = safe_col(summary, "delta_abs_registro_vs_reporte_pp")
    return x


def director_table(directors: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=directors.index)
    x["Empresa"] = safe_col(directors, "razon_social")
    x["RUT empresa"] = safe_col(directors, "rut_empresa").map(rut_display)
    x["Director/a"] = safe_col(directors, "nombre_original")
    x["Sexo"] = safe_col(directors, "sexo_estimado")
    x["Cargo"] = safe_col(directors, "cargo")
    x["Fecha nombramiento"] = safe_col(directors, "fecha_nombramiento_dt").map(fmt_date)
    x["% CMF empresa"] = safe_col(directors, "pct_cmf_actual_num")
    x["Fecha elección/junta"] = safe_col(directors, "fecha_junta_actual_dt").map(fmt_date)
    x["N° titulares"] = safe_col(directors, "n_titulares")
    x["Hombres"] = safe_col(directors, "n_hombres")
    x["Mujeres"] = safe_col(directors, "n_mujeres")
    x["Método sexo"] = safe_col(directors, "metodo_clasificacion_sexo")
    x["Confianza"] = safe_col(directors, "confianza_clasificacion_sexo")
    x["Diagnóstico"] = safe_col(directors, "diagnostico_consistencia")
    return x


st.set_page_config(
    page_title="Directorios CMF — Ley 21.757",
    page_icon="📊",
    layout="wide",
)

st.title("Directorios CMF — Ley 21.757")
st.caption(
    "Dashboard de composición nominal, sexo, porcentajes CMF, fechas de elección y consistencia de datos."
)

default_dir = cli_default_run_dir()

with st.sidebar:
    st.header("Datos")
    run_dir_input = st.text_input(
        "Carpeta de corrida",
        value=default_dir,
        placeholder=r"C:\Workspace\projects\magister-gobcorp\directorios-fem\corrida_20260911_v3_2",
    )
    st.caption("Debe contener 03_directores_con_sexo.csv y 05_resumen_final_v3.csv.")
    st.divider()
    st.header("Filtros")

if not run_dir_input:
    st.info("Indica la carpeta de la corrida en la barra lateral.")
    st.stop()

try:
    root, directors, summary, optional = load_data(run_dir_input)
except Exception as e:
    st.error(f"No pude cargar la corrida: {e}")
    st.stop()

# Global filters.
company_options = sorted(summary["razon_social"].dropna().astype(str).unique().tolist()) if "razon_social" in summary else []

with st.sidebar:
    search = st.text_input("Buscar empresa o director", value="")
    selected_sex = st.multiselect(
        "Sexo del director",
        options=["HOMBRE", "MUJER", "REVISAR"],
        default=[],
    )
    threshold_filter = st.selectbox(
        "Situación respecto de 80%",
        ["Todos", "Sobre 80%", "80% o menos"],
    )
    post_law_only = st.checkbox("Sólo elecciones desde 01/01/2026", value=False)
    discord_only = st.checkbox("Sólo discordancias registro/reporte", value=False)

# Apply filters at company level.
sf = summary.copy()

if threshold_filter == "Sobre 80%" and "sobre_umbral_sugerido_cmf" in sf:
    sf = sf[sf["sobre_umbral_sugerido_cmf"].eq(True)]
elif threshold_filter == "80% o menos" and "sobre_umbral_sugerido_cmf" in sf:
    sf = sf[sf["sobre_umbral_sugerido_cmf"].eq(False)]

if post_law_only and "eleccion_post_entrada_ley" in sf:
    sf = sf[sf["eleccion_post_entrada_ley"].eq(True)]

if discord_only and "diagnostico_consistencia" in sf:
    sf = sf[~sf["diagnostico_consistencia"].isin(["CONSISTENTE", "SIN_COMPOSICION_NOMINAL"])]

# Search companies.
if search.strip():
    q = search.strip().casefold()
    company_match = sf["razon_social"].astype(str).str.casefold().str.contains(q, regex=False)
    rut_match = sf["rut_empresa"].astype(str).str.contains(search.strip(), regex=False)
    # Also find companies containing a matching director.
    dmatch = directors[
        directors["nombre_original"].astype(str).str.casefold().str.contains(q, regex=False)
    ]["rut_empresa"].unique()
    sf = sf[company_match | rut_match | sf["rut_empresa"].isin(dmatch)]

# Apply selected sex at company level: company must contain at least one matching director.
if selected_sex:
    ruts_by_sex = directors[directors["sexo_estimado"].isin(selected_sex)]["rut_empresa"].unique()
    sf = sf[sf["rut_empresa"].isin(ruts_by_sex)]

filtered_ruts = set(sf["rut_empresa"].astype(str))
df = directors[directors["rut_empresa"].astype(str).isin(filtered_ruts)].copy()
if selected_sex:
    df = df[df["sexo_estimado"].isin(selected_sex)]
if search.strip():
    q = search.strip().casefold()
    dm = (
        df["nombre_original"].astype(str).str.casefold().str.contains(q, regex=False)
        | df["razon_social"].astype(str).str.casefold().str.contains(q, regex=False)
        | df["rut_empresa"].astype(str).str.contains(search.strip(), regex=False)
    )
    # Preserve directors from matched companies even if their individual names don't match:
    matched_company_ruts = set(sf["rut_empresa"])
    df = df[df["rut_empresa"].isin(matched_company_ruts)]

# KPIs.
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Empresas", f"{len(sf):,}".replace(",", "."))
c2.metric("Directores visibles", f"{len(df):,}".replace(",", "."))
if "sobre_umbral_sugerido_cmf" in sf:
    c3.metric("Sobre 80% CMF", int(sf["sobre_umbral_sugerido_cmf"].fillna(False).sum()))
else:
    c3.metric("Sobre 80% CMF", "—")
if "eleccion_post_entrada_ley" in sf:
    c4.metric("Elección post ley", int(sf["eleccion_post_entrada_ley"].fillna(False).sum()))
else:
    c4.metric("Elección post ley", "—")
if "diagnostico_consistencia" in sf:
    ndisc = int((~sf["diagnostico_consistencia"].isin(["CONSISTENTE", "SIN_COMPOSICION_NOMINAL"])).sum())
    c5.metric("Discordancias", ndisc)
else:
    c5.metric("Discordancias", "—")

tabs = st.tabs(["Empresas", "Directores", "Ficha de empresa", "Distribución", "Control de datos"])

with tabs[0]:
    st.subheader("Empresas")
    st.caption("El % CMF es la medida canónica; el registro nominal se usa como control de consistencia.")

    sort_choice = st.selectbox(
        "Ordenar por",
        [
            "% CMF — mayor a menor",
            "% CMF — menor a mayor",
            "Fecha de elección — más reciente",
            "Empresa — A a Z",
            "N° de directores — mayor a menor",
            "N° de mujeres — mayor a menor",
        ],
        key="sort_companies",
    )
    sx = sf.copy()
    if sort_choice == "% CMF — mayor a menor" and "pct_cmf_actual_num" in sx:
        sx = sx.sort_values(["pct_cmf_actual_num", "razon_social"], ascending=[False, True])
    elif sort_choice == "% CMF — menor a mayor" and "pct_cmf_actual_num" in sx:
        sx = sx.sort_values(["pct_cmf_actual_num", "razon_social"], ascending=[True, True])
    elif sort_choice == "Fecha de elección — más reciente" and "fecha_junta_actual_dt" in sx:
        sx = sx.sort_values(["fecha_junta_actual_dt", "razon_social"], ascending=[False, True])
    elif sort_choice == "N° de directores — mayor a menor" and "n_titulares" in sx:
        sx = sx.sort_values(["n_titulares", "razon_social"], ascending=[False, True])
    elif sort_choice == "N° de mujeres — mayor a menor" and "n_mujeres" in sx:
        sx = sx.sort_values(["n_mujeres", "razon_social"], ascending=[False, True])
    else:
        sx = sx.sort_values("razon_social")

    ct = company_table(sx)
    st.dataframe(
        ct,
        width="stretch",
        hide_index=True,
        column_config={
            "% CMF": st.column_config.NumberColumn(format="%.2f%%"),
            "% anterior": st.column_config.NumberColumn(format="%.2f%%"),
            "Delta abs. pp": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    st.download_button(
        "Descargar empresas filtradas CSV",
        data=ct.to_csv(index=False).encode("utf-8-sig"),
        file_name="dashboard_empresas_filtradas.csv",
        mime="text/csv",
    )

with tabs[1]:
    st.subheader("Directores")
    st.caption("Una fila por director/a titular del registro nominal CMF recuperado.")

    sort_directors = st.selectbox(
        "Ordenar directores por",
        [
            "Empresa y nombre",
            "Sexo, empresa y nombre",
            "% CMF empresa — mayor a menor",
            "Fecha nombramiento — más reciente",
        ],
        key="sort_directors",
    )
    dx = df.copy()
    if sort_directors == "Sexo, empresa y nombre":
        dx = dx.sort_values(["sexo_estimado", "razon_social", "nombre_original"])
    elif sort_directors == "% CMF empresa — mayor a menor":
        dx = dx.sort_values(["pct_cmf_actual_num", "razon_social", "nombre_original"], ascending=[False, True, True])
    elif sort_directors == "Fecha nombramiento — más reciente":
        dx = dx.sort_values(["fecha_nombramiento_dt", "razon_social"], ascending=[False, True])
    else:
        dx = dx.sort_values(["razon_social", "nombre_original"])

    dt = director_table(dx)
    st.dataframe(
        dt,
        width="stretch",
        hide_index=True,
        column_config={
            "% CMF empresa": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    st.download_button(
        "Descargar directores filtrados CSV",
        data=dt.to_csv(index=False).encode("utf-8-sig"),
        file_name="dashboard_directores_filtrados.csv",
        mime="text/csv",
    )

with tabs[2]:
    st.subheader("Ficha de empresa")
    available = sf.sort_values("razon_social")[["rut_empresa", "razon_social"]].drop_duplicates()
    if available.empty:
        st.info("No hay empresas con los filtros actuales.")
    else:
        labels = {
            f"{r['razon_social']} — {rut_display(r['rut_empresa'])}": r["rut_empresa"]
            for _, r in available.iterrows()
        }
        selected_label = st.selectbox("Empresa", list(labels.keys()))
        rut = labels[selected_label]

        sr = summary[summary["rut_empresa"].eq(rut)].iloc[0]
        bd = directors[directors["rut_empresa"].eq(rut)].copy()

        a, b, c, d = st.columns(4)
        a.metric("% oficial CMF", fmt_pct(sr.get("pct_cmf_actual_num")))
        b.metric("Titulares nominales", int(sr.get("n_titulares", 0) or 0))
        c.metric("Mujeres", int(sr.get("n_mujeres", 0) or 0))
        d.metric("Hombres", int(sr.get("n_hombres", 0) or 0))

        e, f, g, h = st.columns(4)
        e.metric("Fecha elección/junta", fmt_date(sr.get("fecha_junta_actual_dt")))
        f.metric("% anterior", fmt_pct(sr.get("pct_cmf_anterior")))
        g.metric("Fecha anterior", fmt_date(sr.get("fecha_junta_anterior_dt")))
        h.metric("Delta registro/CMF", fmt_pct(sr.get("delta_abs_registro_vs_reporte_pp")))

        st.markdown(
            f"**Estado regulatorio:** `{clean(sr.get('estado_regulatorio_cmf'))}`  \n"
            f"**Diagnóstico de consistencia:** `{clean(sr.get('diagnostico_consistencia'))}`"
        )

        if not bd.empty:
            comp = (
                bd.groupby("sexo_estimado", dropna=False)
                .size()
                .rename("Directores")
                .to_frame()
            )
            st.bar_chart(comp)

            st.markdown("#### Directorio nominal")
            bdt = director_table(bd.sort_values(["cargo", "nombre_original"]))
            st.dataframe(
                bdt,
                width="stretch",
                hide_index=True,
                column_config={"% CMF empresa": st.column_config.NumberColumn(format="%.2f%%")},
            )
        else:
            st.warning("Esta entidad no tiene composición nominal pública recuperada en el registro.")

with tabs[3]:
    st.subheader("Distribución del universo filtrado")

    if not sf.empty and "pct_cmf_actual_num" in sf:
        hist_source = sf[["pct_cmf_actual_num"]].dropna().copy()
        bins = pd.cut(
            hist_source["pct_cmf_actual_num"],
            bins=[0, 50, 60, 70, 80, 90, 100],
            include_lowest=True,
            right=True,
        )
        hist = bins.value_counts(sort=False).rename("Empresas").to_frame()
        # Altair/Vega-Lite does not accept pandas.Interval values as category labels.
        # Convert the IntervalIndex to plain strings before passing the data to Streamlit.
        hist.index = hist.index.map(str)
        hist.index.name = "Rango"
        st.markdown("#### Empresas por rango de porcentaje máximo de un mismo sexo")
        st.bar_chart(hist)

    if {"n_hombres", "n_mujeres"}.issubset(sf.columns):
        totals = pd.DataFrame(
            {
                "Directores": [
                    pd.to_numeric(sf["n_hombres"], errors="coerce").fillna(0).sum(),
                    pd.to_numeric(sf["n_mujeres"], errors="coerce").fillna(0).sum(),
                ]
            },
            index=["HOMBRE", "MUJER"],
        )
        st.markdown("#### Titulares nominales por sexo")
        st.bar_chart(totals)

    if "fecha_junta_actual_dt" in sf.columns:
        year_counts = (
            sf.dropna(subset=["fecha_junta_actual_dt"])
            .assign(Año=lambda z: z["fecha_junta_actual_dt"].dt.year)
            .groupby("Año")
            .size()
            .rename("Empresas")
            .to_frame()
        )
        if not year_counts.empty:
            st.markdown("#### Última elección/junta por año")
            st.bar_chart(year_counts)

with tabs[4]:
    st.subheader("Control de datos")

    checks = optional.get("AUDITORIA_checks.csv", pd.DataFrame())
    if not checks.empty:
        st.markdown("#### Auditoría")
        st.dataframe(checks, width="stretch", hide_index=True)

    disc = optional.get("09_discordancias_registro_vs_reporte.csv", pd.DataFrame())
    if disc.empty and "diagnostico_consistencia" in summary.columns:
        disc = summary[
            ~summary["diagnostico_consistencia"].isin(["CONSISTENTE", "SIN_COMPOSICION_NOMINAL"])
        ].copy()

    st.markdown("#### Discordancias registro nominal vs. reporte Ley 21.757")
    if disc.empty:
        st.success("No hay discordancias registradas.")
    else:
        cols = [
            "razon_social", "rut_empresa", "pct_cmf_actual_num",
            "pct_reconstruido_registro_nominal", "delta_abs_registro_vs_reporte_pp",
            "fecha_junta_actual", "fecha_max_nombramiento_nominal",
            "diagnostico_consistencia", "prioridad_revision",
        ]
        cols = [c for c in cols if c in disc.columns]
        show = disc[cols].copy()
        if "rut_empresa" in show:
            show["rut_empresa"] = show["rut_empresa"].map(rut_display)
        rename = {
            "razon_social": "Empresa",
            "rut_empresa": "RUT",
            "pct_cmf_actual_num": "% CMF",
            "pct_reconstruido_registro_nominal": "% registro nominal",
            "delta_abs_registro_vs_reporte_pp": "Delta abs. pp",
            "fecha_junta_actual": "Fecha junta",
            "fecha_max_nombramiento_nominal": "Máx. fecha nombramiento",
            "diagnostico_consistencia": "Diagnóstico",
            "prioridad_revision": "Prioridad",
        }
        show = show.rename(columns=rename)
        st.dataframe(
            show,
            width="stretch",
            hide_index=True,
            column_config={
                "% CMF": st.column_config.NumberColumn(format="%.2f%%"),
                "% registro nominal": st.column_config.NumberColumn(format="%.2f%%"),
                "Delta abs. pp": st.column_config.NumberColumn(format="%.2f"),
            },
        )

    missing_nom = optional.get("12_entidades_sin_composicion_nominal.csv", pd.DataFrame())
    st.markdown("#### Entidades sin composición nominal pública")
    if missing_nom.empty:
        st.caption("No hay archivo de entidades sin composición nominal o está vacío.")
    else:
        st.dataframe(missing_nom, width="stretch", hide_index=True)

st.divider()
st.caption(
    f"Fuente cargada: {root} · El porcentaje oficial CMF es la medida canónica; "
    "la composición nominal se presenta como capa secundaria de detalle y control."
)

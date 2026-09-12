from __future__ import annotations

import argparse
import math
import inspect
import logging
import re
from html import escape
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_model import company_rut_display, load_model, normalize_name


st.set_page_config(
    page_title="Directorios CMF — Red de Gobierno Corporativo",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded",
)


CSS = """
<style>
.block-container {padding-top: 2rem; max-width: 1500px;}
[data-testid="stMetric"] {background: rgba(127,127,127,.06); border: 1px solid rgba(127,127,127,.12); padding: .65rem .8rem; border-radius: .7rem;}
[data-testid="stMetricLabel"] p {white-space: normal; overflow: visible;}
.small-note {font-size: .88rem; opacity: .76;}
.hero {padding: .25rem 0 .75rem 0;}
.hero h1 {margin-bottom: .2rem;}
.badge {display:inline-block; padding:.15rem .5rem; border:1px solid rgba(127,127,127,.25); border-radius:999px; font-size:.78rem; margin-right:.25rem;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def cli_run_dir() -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--public-dir", "--run-dir", dest="public_dir")
    try:
        args, _ = parser.parse_known_args(sys.argv[1:])
        if args.public_dir:
            return args.public_dir
    except Exception:
        pass
    return str(Path(__file__).resolve().parent / "data" / "public")


@st.cache_data(show_spinner=False)
def cached_model(run_dir: str):
    return load_model(run_dir)


def fmt_date(value) -> str:
    if value is None or value == "":
        return ""
    ts = pd.to_datetime(value, dayfirst=True, errors="coerce")
    return "" if pd.isna(ts) else ts.strftime("%d/%m/%Y")


def fmt_pct(value) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.1f}%"
    except Exception:
        return ""


def dataframe(df: pd.DataFrame, *, height: int | None = None) -> None:
    kwargs = {
        **({"width": "stretch"} if inspect.signature(st.dataframe).parameters["width"].default == "stretch" else {"use_container_width": True}),
        "hide_index": True,
    }
    if height is not None:
        kwargs["height"] = min(height, 38 + 35 * max(1, len(df)))
    df = df.copy()
    for column in ("Fecha de nombramiento", "Fecha junta/elección"):
        if column in df:
            df[column] = df[column].map(fmt_date)
    if "Fuente CMF" in df:
        kwargs["column_config"] = {"Fuente CMF": st.column_config.LinkColumn(display_text="Consultar CMF")}
    st.dataframe(df, **kwargs)


def plot_network(fig, count: int) -> None:
    kwargs = {"width": "stretch"} if "width" in inspect.signature(st.plotly_chart).parameters else {"use_container_width": True}
    st.plotly_chart(fig, **kwargs)
    if count > 18:
        st.caption(f"Se muestran las 18 conexiones con más directores compartidos de un total de {count}.")


NETWORK_NOTE = (
    "Compartir directores demuestra una relación de directorio; no demuestra propiedad común, "
    "control, coordinación ni pertenencia a un grupo económico."
)
DIVERSITY_NOTE = (
    "La clasificación es una estimación derivada de los datos y no necesariamente "
    "una identificación declarada por la persona."
)



def company_name_map(companies: pd.DataFrame) -> dict[str, str]:
    return companies.set_index("rut_empresa")["razon_social"].to_dict()


def company_connections(interlocks: pd.DataFrame, rut: str, names: dict[str, str]) -> pd.DataFrame:
    if interlocks.empty:
        return pd.DataFrame(columns=["rut_vecina", "empresa", "directores_compartidos", "nombres_compartidos"])
    a = interlocks[interlocks["empresa_a"].eq(rut)].copy()
    if not a.empty:
        a["rut_vecina"] = a["empresa_b"]
    b = interlocks[interlocks["empresa_b"].eq(rut)].copy()
    if not b.empty:
        b["rut_vecina"] = b["empresa_a"]
    x = pd.concat([a, b], ignore_index=True)
    if x.empty:
        return pd.DataFrame(columns=["rut_vecina", "empresa", "directores_compartidos", "nombres_compartidos"])
    x["empresa"] = x["rut_vecina"].map(names)
    return x[["rut_vecina", "empresa", "directores_compartidos", "nombres_compartidos"]].sort_values(
        ["directores_compartidos", "empresa"], ascending=[False, True]
    ).reset_index(drop=True)


def ego_network_figure(center_rut: str, center_name: str, connections: pd.DataFrame, max_neighbors: int = 18):
    x = connections.head(max_neighbors).copy()
    if x.empty:
        return None
    n = len(x)
    center = (0.0, 0.0)
    coords: dict[str, tuple[float, float]] = {center_rut: center}
    for i, row in x.iterrows():
        angle = (2 * math.pi * i / max(n, 1)) - math.pi / 2
        coords[row["rut_vecina"]] = (math.cos(angle), math.sin(angle))

    edge_x, edge_y = [], []
    for _, row in x.iterrows():
        x0, y0 = coords[center_rut]
        x1, y1 = coords[row["rut_vecina"]]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y, mode="lines", hoverinfo="none",
        line=dict(width=1), showlegend=False,
    )

    node_ruts = [center_rut] + x["rut_vecina"].tolist()
    node_x = [coords[r][0] for r in node_ruts]
    node_y = [coords[r][1] for r in node_ruts]
    sizes = [34] + [18 + min(18, int(v) * 4) for v in x["directores_compartidos"]]
    hover = [f"<b>{escape(center_name)}</b><br>Empresa seleccionada"]
    for _, row in x.iterrows():
        hover.append(
            f"<b>{escape(str(row['empresa']))}</b><br>{int(row['directores_compartidos'])} director(es) compartido(s)"
            f"<br>{escape(str(row['nombres_compartidos']))}"
        )

    labels = [center_name] + [str(v) for v in x["empresa"]]
    labels = [v if len(v) <= 28 else v[:26] + "…" for v in labels]
    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers+text", text=labels,
        textposition="bottom center", hovertext=hover, hoverinfo="text",
        marker=dict(size=sizes, line=dict(width=1)), showlegend=False,
    )
    fig = go.Figure([edge_trace, node_trace])
    fig.update_layout(
        height=610, margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        hovermode="closest", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def page_header(title: str, subtitle: str) -> None:
    st.markdown(f"<div class='hero'><h1>{escape(title)}</h1><div class='small-note'>{escape(subtitle)}</div></div>", unsafe_allow_html=True)


def bool_label(v) -> str:
    if pd.isna(v):
        return ""
    if v == True:
        return "Sí"
    if v == False:
        return "No"
    return ""


run_dir = cli_run_dir()
if not run_dir:
    st.error("La información no está disponible en este momento. Intenta nuevamente más tarde.")
    st.stop()

try:
    model = cached_model(run_dir)
except Exception as exc:
    logging.getLogger(__name__).exception("No se pudo cargar el observatorio")
    st.error("La información no está disponible en este momento. Intenta nuevamente más tarde.")
    st.stop()

companies = model["companies"]
people = model["people"]
current = model["current"]
interlocks = model["interlocks"]
network_metrics = model["network_metrics"]
diversity = model["diversity"]
law = model["law"]
snapshot = str(model["snapshot"])
names = company_name_map(companies)

page = st.sidebar.radio(
    "Explorar",
    ["Inicio", "Empresas", "Directores", "Red de directorios", "Diversidad", "Ley 21.757", "Metodología"],
)
st.sidebar.divider()
date_match = re.search(r"corrida_(\d{8})", snapshot)
if date_match:
    observed_date = pd.to_datetime(date_match.group(1), format="%Y%m%d", errors="coerce")
    if not pd.isna(observed_date):
        st.sidebar.caption(f"Edición de datos: {observed_date:%d/%m/%Y}")
st.sidebar.caption("Fuente base: registros públicos de la CMF.")



if page == "Inicio":
    page_header(
        "Observatorio de gobierno corporativo",
        "Una vista pública de quién integra los directorios de entidades supervisadas por la CMF y cómo se conectan entre sí.",
    )


    n_companies = int((companies["directores_reconstruidos"] > 0).sum())
    n_people = int(people["persona_id"].nunique())
    n_multi = int((people["empresas"] > 1).sum())

    cols = st.columns(3)
    for col, value, label in zip(
        cols,
        [n_companies, n_people, n_multi],
        ["Entidades con directorio identificable", "Personas en directorios", "Personas en más de un directorio"],
    ):
        col.metric(label, f"{value:,}".replace(",", "."))

    left, right = st.columns([1.1, .9])
    with left:
        st.subheader("Entidades más conectadas")
        top = network_metrics.head(15).copy()
        top = top.rename(columns={
            "razon_social": "Empresa", "empresas_conectadas": "Entidades conectadas",
        })
        dataframe(top[["Empresa", "Entidades conectadas"]], height=470)
    with right:
        st.subheader("Personas con más directorios")
        top_people = people.head(15).copy()
        top_people = top_people.rename(columns={"nombre": "Persona", "empresas": "Directorios"})
        dataframe(top_people[["Persona", "Directorios"]], height=470)

    st.caption(NETWORK_NOTE)
    st.caption("Entidades conectadas: otras entidades con al menos una persona compartida. Cada persona cuenta una vez por directorio.")


elif page == "Empresas":
    page_header("Empresas", "Ficha de cada entidad, composición del directorio y conexiones con otros directorios.")
    company_options = companies.sort_values("razon_social")
    if company_options.empty:
        st.info("No hay entidades disponibles.")
        st.stop()
    rut = st.selectbox("Selecciona una entidad", company_options["rut_empresa"].tolist(), format_func=names.get)
    row = company_options[company_options["rut_empresa"].eq(rut)].iloc[0]
    selected_name = row["razon_social"]
    st.subheader(selected_name)
    board = current[current["rut_empresa"].eq(rut)].copy().sort_values(["cargo", "nombre_original"])
    conns = company_connections(interlocks, rut, names)
    divrow = diversity[diversity["rut_empresa"].eq(rut)]

    a, b, c, d = st.columns(4)
    a.metric("Directores/as", int(board["persona_id"].nunique()) if not board.empty else "—")
    b.metric("Entidades conectadas", int(len(conns)) if not board.empty else "—")
    c.metric("Tipo de entidad (código CMF)", row["tipo_entidad"] if pd.notna(row.get("tipo_entidad")) and row["tipo_entidad"] else "No disponible")
    d.metric("RUT empresa", company_rut_display(rut))

    if not divrow.empty and not board.empty:
        dv = divrow.iloc[0]
        st.caption(
            f"Composición estimada: {int(dv['MUJER'])} mujeres, "
            f"{int(dv['HOMBRE'])} hombres, {int(dv['REVISAR'])} sin clasificación."
        )

    if board.empty:
        st.info("Información de directorio no disponible en la fuente consultada")
        st.stop()
    st.caption(DIVERSITY_NOTE)
    st.subheader("Directorio")
    board_view = board[["nombre_original", "cargo", "fecha_nombramiento", "source_url"]].copy()
    board_view.columns = ["Persona", "Cargo", "Fecha de nombramiento", "Fuente CMF"]
    dataframe(board_view)

    st.subheader("Conexiones por directores compartidos")
    st.caption(NETWORK_NOTE)
    if conns.empty:
        st.info("No aparecen conexiones con otras entidades en los datos consultados.")
    else:
        conns_view = conns[["empresa", "directores_compartidos", "nombres_compartidos"]].copy()
        conns_view.columns = ["Entidad conectada", "Directores compartidos", "Personas compartidas"]
        dataframe(conns_view, height=360)
        fig = ego_network_figure(rut, selected_name, conns)
        if fig is not None:
            plot_network(fig, len(conns))


elif page == "Directores":
    page_header("Directores", "Personas y entidades en cuyos directorios participan.")
    q = st.text_input("Buscar por nombre")
    p = people.copy()
    if q.strip():
        p = p[p["nombre"].map(normalize_name).str.contains(normalize_name(q), regex=False, na=False)]
    p = p.sort_values(["empresas", "nombre"], ascending=[False, True])

    shortlist = p
    if shortlist.empty:
        st.info("No hay coincidencias.")
    else:
        labels = {r.persona_id: f"{r.nombre} — {int(r.empresas)} directorio(s)" for r in shortlist.itertuples()}
        homonyms = set(shortlist.loc[shortlist["nombre"].map(normalize_name).duplicated(keep=False), "persona_id"])
        for person_id in homonyms:
            labels[person_id] += " · referencia " + person_id[2:14]
        choice = st.selectbox("Selecciona una persona", list(labels), format_func=labels.get)
        person = shortlist[shortlist["persona_id"].eq(choice)].iloc[0]
        memberships = current[current["persona_id"].eq(person["persona_id"])].copy()
        memberships["Empresa"] = memberships["rut_empresa"].map(names)
        memberships = memberships.sort_values("Empresa")

        st.metric("Directorios donde participa", int(person["empresas"]))
        st.subheader(person["nombre"])
        view = memberships[["Empresa", "cargo", "fecha_nombramiento", "source_url"]].copy()
        view.columns = ["Empresa", "Cargo", "Fecha de nombramiento", "Fuente CMF"]
        dataframe(view)

    st.subheader("Personas que participan en varios directorios")
    rank = people[people["empresas"] > 1][["nombre", "empresas"]].head(100).copy()
    rank.columns = ["Persona", "N° directorios"]
    dataframe(rank, height=420)


elif page == "Red de directorios":
    page_header("Red de directorios", "Dos entidades quedan conectadas cuando comparten una o más personas.")
    st.caption(NETWORK_NOTE)

    max_shared = int(interlocks["directores_compartidos"].max()) if not interlocks.empty else 1
    min_shared = st.slider("Mínimo de directores compartidos", 1, max_shared, 1) if max_shared > 1 else 1
    filtered = interlocks[interlocks["directores_compartidos"] >= min_shared].copy()
    st.metric("Pares de entidades", len(filtered))
    if filtered.empty:
        st.info("No hay pares con ese umbral.")
    else:
        view = filtered[["empresa_a_nombre", "empresa_b_nombre", "directores_compartidos", "nombres_compartidos"]].head(500).copy()
        view.columns = ["Entidad A", "Entidad B", "Directores compartidos", "Personas compartidas"]
        dataframe(view, height=520)
        if len(filtered) > 500:
            st.caption(f"Se muestran los primeros 500 pares de {len(filtered)}; ajusta el mínimo para acotar la selección.")

    st.subheader("Explorar una entidad en la red")
    options = companies.loc[companies["directores_reconstruidos"] > 0, "rut_empresa"].tolist()
    if not options:
        st.info("No hay directorios disponibles para explorar.")
        st.stop()
    rut = st.selectbox("Entidad central", options, format_func=names.get, key="network_company")
    selected = names[rut]
    conns = company_connections(filtered, rut, names)
    fig = ego_network_figure(rut, selected, conns)
    if fig is None:
        st.info("Sin conexiones observadas en los datos consultados.")
    else:
        plot_network(fig, len(conns))


elif page == "Diversidad":
    page_header("Diversidad", "Composición estimada de los directorios, por entidad y en conjunto.")
    st.caption(DIVERSITY_NOTE)
    st.caption("Cada persona se cuenta una vez por entidad. En la tabla, los porcentajes incluyen los cargos sin clasificación.")

    total_h = int(diversity["HOMBRE"].sum())
    total_m = int(diversity["MUJER"].sum())
    total_r = int(diversity["REVISAR"].sum())
    a, b, c, d = st.columns(4)
    a.metric("Hombres — cargos", total_h)
    b.metric("Mujeres — cargos", total_m)
    c.metric("Sin clasificación — cargos", total_r)
    d.metric("Mujeres sobre cargos clasificados", fmt_pct(100 * total_m / (total_h + total_m)) if (total_h + total_m) else "—")

    show = diversity[diversity["total"] > 0].copy()
    show["% mujeres"] = show["pct_mujeres"].round(1)
    show["% hombres"] = show["pct_hombres"].round(1)
    show["% sin clasificación"] = show["pct_revisar"].round(1)
    show = show.rename(columns={"razon_social": "Empresa", "total": "Directores", "MUJER": "Mujeres", "HOMBRE": "Hombres", "REVISAR": "Sin clasificación"})
    sort_mode = st.selectbox("Ordenar", ["Mayor % mujeres", "Menor % mujeres", "Mayor directorio"])
    if sort_mode == "Mayor % mujeres":
        show = show.sort_values(["% mujeres", "Directores"], ascending=[False, False])
    elif sort_mode == "Menor % mujeres":
        show = show.sort_values(["% mujeres", "Directores"], ascending=[True, False])
    else:
        show = show.sort_values(["Directores", "Empresa"], ascending=[False, True])
    dataframe(show[["Empresa", "Directores", "Mujeres", "Hombres", "Sin clasificación", "% mujeres", "% hombres", "% sin clasificación"]], height=620)


elif page == "Ley 21.757":
    page_header("Ley 21.757", "Composición y antecedentes de elección disponibles para consultar la Ley 21.757.")
    st.caption("Los estados reproducen la evaluación contenida en los datos consultados; no constituyen una determinación de cumplimiento legal.")
    state_labels = {
        "POST_LEY_DENTRO_UMBRAL_SUGERIDO": "Elección posterior a la ley: dentro del umbral sugerido",
        "POST_LEY_SOBRE_UMBRAL_SUGERIDO": "Elección posterior a la ley: sobre el umbral sugerido",
        "PRE_LEY_NO_EVALUABLE": "Elección anterior a la ley: no evaluable",
    }
    if law.empty:
        st.info("No hay datos regulatorios en los datos consultados.")
    else:
        state_options = sorted([x for x in law.get("estado_regulatorio_cmf", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
        selected_states = st.multiselect("Estado según los datos consultados", state_options, format_func=lambda v: state_labels.get(v, "Sin evaluación disponible"))
        x = law.copy()
        if selected_states and "estado_regulatorio_cmf" in x.columns:
            x = x[x["estado_regulatorio_cmf"].isin(selected_states)]
        cols = [c for c in [
            "razon_social", "n_titulares", "n_hombres", "n_mujeres", "pct_cmf_actual_num",
            "fecha_junta_actual", "eleccion_post_entrada_ley", "sobre_umbral_sugerido_cmf",
            "estado_regulatorio_cmf",
        ] if c in x.columns]
        view = x[cols].copy()
        rename = {
            "razon_social": "Empresa", "n_titulares": "Titulares", "n_hombres": "Hombres", "n_mujeres": "Mujeres",
            "pct_cmf_actual_num": "% CMF", "fecha_junta_actual": "Fecha junta/elección",
            "eleccion_post_entrada_ley": "Post entrada ley", "sobre_umbral_sugerido_cmf": "Sobre umbral",
            "estado_regulatorio_cmf": "Evaluación disponible",
        }
        if "estado_regulatorio_cmf" in view:
            view["estado_regulatorio_cmf"] = view["estado_regulatorio_cmf"].map(state_labels).fillna("Sin evaluación disponible")
        unavailable = ~x["rut_empresa"].isin(current["rut_empresa"])
        for column in ("n_titulares", "n_hombres", "n_mujeres"):
            if column in view:
                view.loc[unavailable, column] = float("nan")
        view = view.rename(columns=rename)
        if "Post entrada ley" in view:
            view["Post entrada ley"] = view["Post entrada ley"].map(bool_label)
        if "Sobre umbral" in view:
            view["Sobre umbral"] = view["Sobre umbral"].map(bool_label)
        dataframe(view, height=650)


else:
    page_header("Metodología", "Alcance e interpretación de la información.")
    st.markdown(
        "Se muestran las personas y los cargos observados en los registros públicos de la CMF "
        "para la edición indicada. No representa una consulta en tiempo real ni una trayectoria histórica completa. "
        "Cuando hay varias observaciones de una persona en una entidad, se utiliza el nombramiento más reciente."
    )
    st.markdown(NETWORK_NOTE)
    st.markdown(DIVERSITY_NOTE)
    st.markdown(
        "La falta de información de un directorio no significa que carezca de integrantes. "
        "Las fichas enlazan a la fuente cuando está disponible."
    )
    st.markdown(
        "La identidad se vincula entre entidades cuando existe un identificador verificable en la fuente. "
        "Los registros extranjeros sin identificador individual se mantienen separados hasta contar con evidencia; "
        "el total de personas puede sobreestimar personas únicas y las conexiones pueden estar subestimadas. "
        "Las coincidencias de nombre no bastan para unir registros."
    )

st.divider()
st.caption(
    "Proyecto comunitario basado en información pública de la CMF. El dashboard organiza y relaciona registros; no reemplaza la fuente oficial ni emite conclusiones jurídicas sobre control, independencia o conflictos de interés."
)

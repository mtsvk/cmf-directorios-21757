from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse
import re
import unicodedata

import pandas as pd

REQUIRED = ("03_directores_con_sexo.csv", "05_resumen_final_v3.csv")
OPTIONAL = (
    "00_universo_ley_21757.csv",
    "09_discordancias_registro_vs_reporte.csv",
    "10_discordancias_prioritarias.csv",
    "12_entidades_sin_composicion_nominal.csv",
    "AUDITORIA_checks.csv",
)


def clean(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def normalize_rut(value) -> str:
    s = clean(value)
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return "".join(ch for ch in s.upper() if ch.isdigit() or ch == "K")


def normalize_name(value) -> str:
    s = clean(value).upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip(" .,-")


def company_rut_display(value) -> str:
    s = normalize_rut(value)
    if not s:
        return ""
    # The source generally stores the company RUT body without DV.
    groups = []
    while len(s) > 3:
        groups.append(s[-3:])
        s = s[:-3]
    groups.append(s)
    return ".".join(reversed(groups))


def read_csv(path: Path) -> pd.DataFrame:
    # Strict decoding accepts UTF-8 with or without BOM and never silently loses accents.
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", encoding_errors="strict")


def discover_run_dir(base: str | Path = ".") -> Path | None:
    base = Path(base)
    candidates: list[tuple[str, Path]] = []
    for p in base.glob("corrida_*"):
        if p.is_dir() and all((p / f).exists() for f in REQUIRED):
            candidates.append((p.name, p))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _canonical(series: pd.Series) -> str:
    vals = [clean(x) for x in series if clean(x)]
    if not vals:
        return ""
    counts = pd.Series(vals).value_counts()
    best_count = counts.iloc[0]
    tied = [x for x, c in counts.items() if c == best_count]
    return sorted(tied, key=lambda x: (len(x), x), reverse=True)[0]


def _query_value(url: str, key: str) -> str:
    try:
        vals = parse_qs(urlparse(clean(url)).query).get(key, [])
        return clean(vals[0]) if vals else ""
    except Exception:
        return ""


def _to_num(df: pd.DataFrame, cols: list[str]) -> None:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def _to_bool(df: pd.DataFrame, cols: list[str]) -> None:
    mapping = {"TRUE": True, "FALSE": False, "1": True, "0": False, "SI": True, "SÍ": True, "NO": False}
    for col in cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper().map(mapping)


def _person_internal_key(row: pd.Series) -> str:
    identity = clean(row.get("identidad_director", ""))
    if identity:
        return identity
    rut = normalize_rut(row.get("rut_persona", ""))
    if rut:
        return f"RUT:{rut}"
    return f"NOMBRE:{normalize_name(row.get('nombre_original', ''))}"


def _public_person_ids(directors: pd.DataFrame) -> dict[str, str]:
    temp = directors.groupby("_person_key", as_index=False).agg(nombre=("nombre_original", _canonical))
    temp["_sort"] = temp["nombre"].map(normalize_name) + "|" + temp["_person_key"]
    temp = temp.sort_values("_sort").reset_index(drop=True)
    temp["persona_id"] = [f"P{i:05d}" for i in range(1, len(temp) + 1)]
    return dict(zip(temp["_person_key"], temp["persona_id"]))


def load_model(run_dir: str | Path) -> dict[str, pd.DataFrame | str | Path]:
    root = Path(run_dir).expanduser().resolve()
    missing_required = [f for f in REQUIRED if not (root / f).exists()]
    if missing_required:
        raise FileNotFoundError("Faltan archivos requeridos: " + ", ".join(missing_required))

    raw = read_csv(root / "03_directores_con_sexo.csv")
    summary = read_csv(root / "05_resumen_final_v3.csv")
    optional = {f: read_csv(root / f) if (root / f).exists() else pd.DataFrame() for f in OPTIONAL}

    for df in [raw, summary, *optional.values()]:
        if not df.empty and "rut_empresa" in df.columns:
            df["rut_empresa"] = df["rut_empresa"].map(normalize_rut)

    raw["_person_key"] = raw.apply(_person_internal_key, axis=1)
    raw["fecha_nombramiento_dt"] = pd.to_datetime(raw.get("fecha_nombramiento", ""), dayfirst=True, errors="coerce")
    raw["tipo_entidad"] = raw.get("source_url", pd.Series("", index=raw.index)).map(lambda x: _query_value(x, "tipoentidad"))
    raw["mercado"] = raw.get("source_url", pd.Series("", index=raw.index)).map(lambda x: _query_value(x, "mercado"))

    person_map = _public_person_ids(raw)
    raw["persona_id"] = raw["_person_key"].map(person_map)

    # Preserve each distinct source observation. Exact duplicates add no information.
    mandate_cols = [
        "persona_id", "_person_key", "rut_empresa", "razon_social", "nombre_original",
        "cargo", "fecha_nombramiento", "fecha_nombramiento_dt", "source_url",
        "sexo_estimado", "metodo_clasificacion_sexo", "confianza_clasificacion_sexo",
        "nota_clasificacion_sexo", "tipo_entidad", "mercado",
    ]
    mandate_cols = [c for c in mandate_cols if c in raw.columns]
    mandates = raw[mandate_cols].drop_duplicates().copy()
    mandates = mandates.sort_values(["rut_empresa", "persona_id", "fecha_nombramiento_dt"], na_position="first").reset_index(drop=True)
    mandates["mandato_id"] = [f"M{i:06d}" for i in range(1, len(mandates) + 1)]

    # Current membership: one person per company. If the source contains multiple observations,
    # retain them in mandates but choose the most recent appointment for display/analytics.
    cargo_rank = {"PRESIDENTE": 3, "VICEPRESIDENTE": 2, "DIRECTOR": 1, "DIRECTORA": 1}
    current = mandates.copy()
    current["_cargo_rank"] = current.get("cargo", pd.Series("", index=current.index)).astype(str).str.upper().map(cargo_rank).fillna(0)
    current["_date_rank"] = current["fecha_nombramiento_dt"].fillna(pd.Timestamp("1900-01-01"))
    current = current.sort_values(["rut_empresa", "persona_id", "_date_rank", "_cargo_rank"], ascending=[True, True, True, True])
    current = current.drop_duplicates(["rut_empresa", "persona_id"], keep="last").drop(columns=["_cargo_rank", "_date_rank"])

    # Company universe is the union of all available sources.
    company_frames = []
    for df in [raw, summary, optional.get("12_entidades_sin_composicion_nominal.csv", pd.DataFrame())]:
        if not df.empty and {"rut_empresa", "razon_social"}.issubset(df.columns):
            company_frames.append(df[["rut_empresa", "razon_social"]])
    company_seed = pd.concat(company_frames, ignore_index=True).drop_duplicates() if company_frames else pd.DataFrame(columns=["rut_empresa", "razon_social"])
    companies = company_seed.groupby("rut_empresa", as_index=False).agg(razon_social=("razon_social", _canonical))

    company_meta = current.groupby("rut_empresa", as_index=False).agg(
        tipo_entidad=("tipo_entidad", _canonical),
        mercado=("mercado", _canonical),
        directores_reconstruidos=("persona_id", "nunique"),
    )
    companies = companies.merge(company_meta, on="rut_empresa", how="left")
    companies["directores_reconstruidos"] = companies["directores_reconstruidos"].fillna(0).astype(int)

    missing_nominal = optional.get("12_entidades_sin_composicion_nominal.csv", pd.DataFrame())
    missing_set = set(missing_nominal.get("rut_empresa", pd.Series(dtype=str)).astype(str)) if not missing_nominal.empty else set()
    companies["estado_datos"] = "SIN_REGISTROS"
    companies.loc[companies["directores_reconstruidos"] > 0, "estado_datos"] = "CON_DIRECTORIO"
    companies.loc[companies["rut_empresa"].isin(missing_set), "estado_datos"] = "SIN_COMPOSICION_NOMINAL"
    companies["rut_empresa_display"] = companies["rut_empresa"].map(company_rut_display)

    # Public people table. Sex is retained for aggregate statistics, but the dashboard should not
    # expose it as a person-level attribute because it is an inferred classification.
    people = current.groupby(["persona_id", "_person_key"], as_index=False).agg(
        nombre=("nombre_original", _canonical),
        sexo_estimado=("sexo_estimado", _canonical),
        confianza_sexo=("confianza_clasificacion_sexo", _canonical),
        empresas=("rut_empresa", "nunique"),
    )
    people["es_multidirectorio"] = people["empresas"] > 1

    # Company-company interlocks through shared people.
    membership = current[["persona_id", "nombre_original", "rut_empresa"]].drop_duplicates()
    left = membership.rename(columns={"rut_empresa": "empresa_a"})
    right = membership.rename(columns={"rut_empresa": "empresa_b", "nombre_original": "nombre_b"})
    pairs = left.merge(right[["persona_id", "empresa_b", "nombre_b"]], on="persona_id", how="inner")
    pairs = pairs[pairs["empresa_a"] < pairs["empresa_b"]].copy()
    if pairs.empty:
        interlocks = pd.DataFrame(columns=["empresa_a", "empresa_b", "directores_compartidos", "nombres_compartidos"])
    else:
        pairs["nombre_compartido"] = pairs["nombre_original"].where(pairs["nombre_original"].astype(str).str.len() > 0, pairs["nombre_b"])
        interlocks = pairs.groupby(["empresa_a", "empresa_b"], as_index=False).agg(
            directores_compartidos=("persona_id", "nunique"),
            nombres_compartidos=("nombre_compartido", lambda s: "; ".join(sorted(set(clean(x) for x in s if clean(x))))),
        )
        names = companies.set_index("rut_empresa")["razon_social"].to_dict()
        interlocks["empresa_a_nombre"] = interlocks["empresa_a"].map(names)
        interlocks["empresa_b_nombre"] = interlocks["empresa_b"].map(names)
        interlocks = interlocks.sort_values(["directores_compartidos", "empresa_a_nombre", "empresa_b_nombre"], ascending=[False, True, True]).reset_index(drop=True)

    # Network metrics that do not require a graph library.
    if interlocks.empty:
        network_metrics = companies[["rut_empresa", "razon_social"]].copy()
        network_metrics["empresas_conectadas"] = 0
        network_metrics["suma_directores_compartidos"] = 0
    else:
        a = interlocks[["empresa_a", "empresa_b", "directores_compartidos"]].rename(columns={"empresa_a": "rut_empresa", "empresa_b": "vecina"})
        b = interlocks[["empresa_a", "empresa_b", "directores_compartidos"]].rename(columns={"empresa_b": "rut_empresa", "empresa_a": "vecina"})
        edge_long = pd.concat([a, b], ignore_index=True)
        nm = edge_long.groupby("rut_empresa", as_index=False).agg(
            empresas_conectadas=("vecina", "nunique"),
            suma_directores_compartidos=("directores_compartidos", "sum"),
        )
        network_metrics = companies[["rut_empresa", "razon_social"]].merge(nm, on="rut_empresa", how="left").fillna({"empresas_conectadas": 0, "suma_directores_compartidos": 0})
        network_metrics[["empresas_conectadas", "suma_directores_compartidos"]] = network_metrics[["empresas_conectadas", "suma_directores_compartidos"]].astype(int)

    # Diversity is aggregate by company only.
    sex = current[["rut_empresa", "persona_id", "sexo_estimado"]].drop_duplicates()
    sex["sexo_bucket"] = sex["sexo_estimado"].astype(str).str.upper().where(
        sex["sexo_estimado"].astype(str).str.upper().isin(["HOMBRE", "MUJER"]), "REVISAR"
    )
    div = sex.groupby(["rut_empresa", "sexo_bucket"])["persona_id"].nunique().unstack(fill_value=0).reset_index()
    for col in ["HOMBRE", "MUJER", "REVISAR"]:
        if col not in div.columns:
            div[col] = 0
    div["total"] = div[["HOMBRE", "MUJER", "REVISAR"]].sum(axis=1)
    div["pct_mujeres"] = div["MUJER"].div(div["total"].where(div["total"] > 0)).mul(100)
    div["pct_hombres"] = div["HOMBRE"].div(div["total"].where(div["total"] > 0)).mul(100)
    div["pct_revisar"] = div["REVISAR"].div(div["total"].where(div["total"] > 0)).mul(100)
    diversity = companies[["rut_empresa", "razon_social"]].merge(div, on="rut_empresa", how="left")
    diversity[["HOMBRE", "MUJER", "REVISAR", "total"]] = diversity[["HOMBRE", "MUJER", "REVISAR", "total"]].fillna(0).astype(int)

    # Law 21.757 remains a separate analytical layer.
    law = summary.copy()
    _to_num(law, [
        "n_titulares", "n_hombres", "n_mujeres", "n_revisar", "pct_hombres", "pct_mujeres",
        "pct_cmf_actual_num", "pct_cmf_anterior", "pct_reconstruido_registro_nominal",
        "delta_registro_vs_reporte_pp", "delta_abs_registro_vs_reporte_pp", "umbral_aplicable",
    ])
    _to_bool(law, [
        "eleccion_post_entrada_ley", "sobre_umbral_sugerido_cmf",
        "sobre_umbral_y_eleccion_post_ley_cmf", "registro_nominal_consistente_0_6pp",
    ])

    # Quality flags: never translate missing source information into a zero-member board.
    flags: list[dict[str, object]] = []
    if not missing_nominal.empty:
        for _, r in missing_nominal.iterrows():
            flags.append({
                "scope": "EMPRESA", "rut_empresa": r.get("rut_empresa", ""),
                "persona_id": "", "severidad": "ALTA", "codigo": "SIN_COMPOSICION_NOMINAL",
                "detalle": "La fuente CMF consultada no entregó composición nominal; no se interpreta como directorio vacío.",
            })

    repeated = mandates.groupby(["rut_empresa", "persona_id"]).size().reset_index(name="n_registros")
    for _, r in repeated[repeated["n_registros"] > 1].iterrows():
        flags.append({
            "scope": "PERSONA_EMPRESA", "rut_empresa": r["rut_empresa"], "persona_id": r["persona_id"],
            "severidad": "MEDIA", "codigo": "MULTIPLES_REGISTROS_PERSONA_EMPRESA",
            "detalle": f"Existen {int(r['n_registros'])} observaciones distintas para la misma persona y empresa; se conserva trazabilidad y se usa la más reciente para analítica actual.",
        })

    if "diagnostico_consistencia" in law.columns:
        for _, r in law[~law["diagnostico_consistencia"].astype(str).isin(["", "CONSISTENTE"])].iterrows():
            flags.append({
                "scope": "EMPRESA", "rut_empresa": r.get("rut_empresa", ""), "persona_id": "",
                "severidad": "MEDIA", "codigo": "DIAGNOSTICO_CONSISTENCIA",
                "detalle": clean(r.get("diagnostico_consistencia", "")),
            })

    quality_flags = pd.DataFrame(flags, columns=["scope", "rut_empresa", "persona_id", "severidad", "codigo", "detalle"])
    if not quality_flags.empty:
        quality_flags = quality_flags.merge(companies[["rut_empresa", "razon_social"]], on="rut_empresa", how="left")

    # Strip private identity keys from public analytic tables, but return a private map for the local
    # SQLite builder. The Streamlit app must not display this map.
    private_people = people[["persona_id", "_person_key", "nombre"]].copy()
    people_public = people.drop(columns=["_person_key"])
    mandates_public = mandates.drop(columns=["_person_key"], errors="ignore")
    current_public = current.drop(columns=["_person_key"], errors="ignore")

    snapshot = root.name
    return {
        "root": root,
        "snapshot": snapshot,
        "companies": companies.sort_values("razon_social").reset_index(drop=True),
        "people": people_public.sort_values(["empresas", "nombre"], ascending=[False, True]).reset_index(drop=True),
        "private_people": private_people,
        "mandates": mandates_public,
        "current": current_public,
        "interlocks": interlocks,
        "network_metrics": network_metrics.sort_values(["empresas_conectadas", "razon_social"], ascending=[False, True]).reset_index(drop=True),
        "diversity": diversity.sort_values("razon_social").reset_index(drop=True),
        "law": law,
        "quality_flags": quality_flags,
        "missing_nominal": missing_nominal,
    }

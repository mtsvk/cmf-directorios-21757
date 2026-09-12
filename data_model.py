"""Public-only model: no private imports or source discovery."""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import pandas as pd

PUBLIC_COLUMNS = {
    "companies": "rut_empresa razon_social tipo_entidad mercado directores_reconstruidos estado_datos rut_empresa_display",
    "people": "persona_id nombre empresas es_multidirectorio",
    "current": "persona_id rut_empresa razon_social nombre_original cargo fecha_nombramiento source_url",
    "interlocks": "empresa_a empresa_b directores_compartidos nombres_compartidos empresa_a_nombre empresa_b_nombre",
    "network_metrics": "rut_empresa razon_social empresas_conectadas suma_directores_compartidos",
    "diversity": "rut_empresa razon_social HOMBRE MUJER REVISAR total pct_mujeres pct_hombres pct_revisar",
    "law": "rut_empresa razon_social n_titulares n_hombres n_mujeres pct_cmf_actual_num fecha_junta_actual eleccion_post_entrada_ley sobre_umbral_sugerido_cmf estado_regulatorio_cmf",
}
PUBLIC_COLUMNS = {key: value.split() for key, value in PUBLIC_COLUMNS.items()}
COMPANY_IDS = {"rut_empresa", "rut_empresa_display", "empresa_a", "empresa_b"}
RUT_PATTERN = re.compile(r"(?<!\w)(?:\d{1,2}\.\d{3}\.\d{3}(?:-[0-9kK])?|\d{7,8}-[0-9kK]|\d{7,9}[kK]?)(?!\w)")


def normalize_name(value) -> str:
    value = unicodedata.normalize("NFKD", str(value).strip().upper())
    return re.sub(r"\s+", " ", "".join(c for c in value if not unicodedata.combining(c))).strip(" .,-")


def company_rut_display(value) -> str:
    value = str(value).strip()
    return ".".join(reversed([value[max(0, i - 3):i] for i in range(len(value), 0, -3)]))


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", encoding_errors="strict")


def validate_public_table(name: str, frame: pd.DataFrame) -> None:
    if name not in PUBLIC_COLUMNS or list(frame.columns) != PUBLIC_COLUMNS[name]:
        raise ValueError(f"Columnas públicas no autorizadas: {name}")
    for column in frame:
        for index, value in frame[column].dropna().astype(str).items():
            if column in COMPANY_IDS:
                if not re.fullmatch(r"[0-9.kK-]+", value):
                    raise ValueError("Identificador de empresa inválido")
                continue
            if column == "persona_id":
                if not re.fullmatch(r"p_[0-9a-f]{32}", value):
                    raise ValueError("Identificador público inválido")
                continue
            if column == "source_url" and value:
                url = urlparse(value)
                query = parse_qs(url.query, keep_blank_values=True)
                if (url.scheme != "https" or url.netloc not in {"www.cmfchile.cl", "cmfchile.cl"}
                        or url.path != "/institucional/mercados/detalle_listado_directorios.php" or url.fragment
                        or set(query) - {"rut", "tipoentidad", "mercado"}
                        or any(len(v) != 1 for v in query.values())):
                    raise ValueError("URL pública no autorizada")
                if query.get("rut") != [str(frame.at[index, "rut_empresa"])]:
                    raise ValueError("La URL debe identificar a la empresa")
                value = " ".join(v[0] for k, v in query.items() if k != "rut")
            if RUT_PATTERN.search(value) or re.search(r"RUT:|identidad_director|rut_persona", value, re.I):
                raise ValueError(f"Posible identificador personal en {name}.{column}")


def load_model(public_dir: str | Path) -> dict:
    root = Path(public_dir).resolve()
    metadata = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if metadata != {"schema_version": 1, "snapshot": metadata.get("snapshot")} or not re.fullmatch(r"corrida_\d{8}(?:_[a-zA-Z]+[0-9]?(?:_[0-9])?)?", metadata["snapshot"]):
        raise ValueError("Manifiesto público inválido")
    model = {"root": root, "snapshot": metadata["snapshot"]}
    for name in PUBLIC_COLUMNS:
        frame = pd.read_json(root / f"{name}.json", orient="table")
        validate_public_table(name, frame)
        model[name] = frame
    current, people = model["current"], model["people"]
    if people.persona_id.duplicated().any() or current.duplicated(["persona_id", "rut_empresa"]).any():
        raise ValueError("Identidades públicas duplicadas")
    if set(current.persona_id) != set(people.persona_id):
        raise ValueError("Identidades públicas inconsistentes")
    return model

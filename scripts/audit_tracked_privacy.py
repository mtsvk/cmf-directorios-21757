"""Read-only audit of the current Git index, reporting counts without identifiers."""
import io
import json
import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def audit():
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    source_path = "corrida_20260911_v3_2/03_directores_con_sexo.csv"
    source = subprocess.check_output(["git", "show", ":" + source_path], cwd=ROOT).decode("utf-8-sig")
    frame = pd.read_csv(io.StringIO(source), dtype=str, keep_default_na=False)
    tokens = set()
    for value in frame.rut_persona:
        compact = re.sub(r"[^0-9K]", "", value.upper())
        if len(compact) < 7:
            continue
        tokens.update([value, compact])
        if len(compact) >= 8:
            tokens.add(compact[:-1] + "-" + compact[-1])
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(v) for v in sorted(tokens, key=len, reverse=True) if v) + r")(?!\w)", re.I)
    findings = []
    for path in filter(None, paths):
        content = subprocess.check_output(["git", "show", ":" + path], cwd=ROOT).decode("utf-8-sig")
        matches = len(pattern.findall(content))
        if matches:
            findings.append({"path": path, "personal_identifier_matches": matches})
    return {"scope": "current Git index; not historical commits", "source_rows": len(frame),
            "unique_private_identities": frame.identidad_director.nunique(), "findings": findings}


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))

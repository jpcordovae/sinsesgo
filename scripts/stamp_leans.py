"""Añade lean editorial draft al catálogo. Se corre una vez."""
from __future__ import annotations

import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "data" / "outlets.json"

LEANS = {
    "biobio": "lean_right",
    "latercera": "lean_right",
    "cooperativa": "center",
    "df": "right",
    "ciper": "left",
    "exante": "lean_right",
    "radio_uchile": "left",
    "adn": "center",
    "theclinic": "left",
    "eldesconcierto": "left",
    "interferencia": "left",
    "eldinamo": "lean_left",
    "lacuarta": "center",
    "elmostrador": "lean_left",
    "fastcheck": "center",
    "emol": "right",
    "elmercurio": "right",
    "lun": "lean_right",
    "lasegunda": "right",
    "t13": "center",
    "tvn24h": "center",
    "meganoticias": "center",
    "chvnoticias": "center",
    "cnnchile": "center",
    "duna": "right",
    "agricultura": "right",
    "pauta": "lean_right",
    "elciudadano": "left",
    "elsiglo": "left",
    "mercurio_valpo": "right",
    "elsur": "right",
    "estrella_antofagasta": "right",
    "rancaguino": "center",
    "prensa_austral": "center",
    "diario_concepcion": "lean_right",
}

SOURCE = "draft-editorial-2026-09"


def main() -> None:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    missing = []
    for outlet in data["outlets"]:
        lean = LEANS.get(outlet["id"])
        if not lean:
            missing.append(outlet["id"])
            continue
        outlet["lean"] = lean
        outlet["lean_source"] = SOURCE
    if missing:
        raise SystemExit(f"Sin lean: {missing}")
    data["notes"] = (
        "Catálogo curado para el MVP Chile. gov_relation queda en sin_dato "
        "salvo evidencia editorial estable. lean es un borrador editorial "
        "chileno (no AllSides/Ad Fontes/MBFC): se colapsa a I/C/D en el Bias Bar. "
        "No persistir cuerpos de artículos. Feeds tomados de awesome-chilean-rss "
        "y sitios oficiales; el worker marca cuáles responden."
    )
    CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK {len(data['outlets'])} outlets con lean")


if __name__ == "__main__":
    main()

"""Historial de proyecciones cuando cambian los datos oficiales."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_ENTRIES = 500


def _region_votos(region: dict[str, Any]) -> int:
    return sum(p.get("votos") or 0 for p in region.get("participantes") or [])


def compute_fingerprint(
    regiones: list[dict[str, Any]],
    extranjero: list[dict[str, Any]],
) -> str:
    payload: dict[str, Any] = {
        "regiones": {},
        "extranjero_votos": 0,
    }
    for region in regiones:
        if region.get("error"):
            continue
        proc = region.get("procesamiento") or region.get("actas") or {}
        payload["regiones"][region["ubigeo"]] = {
            "votos": _region_votos(region),
            "actas": proc.get("contabilizadas"),
            "total_actas": proc.get("total"),
        }
    for region in extranjero:
        if region.get("error"):
            continue
        proc = region.get("procesamiento") or {}
        payload["extranjero_votos"] += proc.get("votos_validos") or 0
        for p in region.get("participantes") or []:
            payload.setdefault("ext_candidatos", {})
            nombre = p["nombre"]
            payload["ext_candidatos"][nombre] = payload["ext_candidatos"].get(nombre, 0) + (
                p.get("votos") or 0
            )

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_history_entry(snapshot: Any) -> dict[str, Any]:
    proy = snapshot.nacional.get("proyeccion") or {}
    ext = proy.get("extranjero") or {}
    candidatos = proy.get("candidatos") or []
    deptos = proy.get("departamentos") or []

    por_region: dict[str, Any] = {}
    for dept in deptos:
        por_region[dept["ubigeo"]] = {
            "region": dept["region"],
            "pct_procesado": dept.get("pct_procesado"),
            "completo": dept.get("completo"),
            "lider_real": dept.get("lider_real"),
            "lider_proyectado": dept.get("lider_proyectado"),
            "votos_actuales": dept.get("votos_actuales"),
            "votos_proyectados": dept.get("votos_proyectados"),
            "tendencia": dept.get("tendencia"),
        }

    return {
        "timestamp": snapshot.updated_at,
        "fetch_count": snapshot.fetch_count,
        "fingerprint": None,
        "real": {
            "ganador": proy.get("ganador_actual"),
            "margen_pct": proy.get("margen_actual_pct"),
            "votos_totales": proy.get("totales", {}).get("votos_actuales"),
            "pct_procesado": proy.get("pct_nacional_procesado"),
            "candidatos": [
                {
                    "nombre": c["nombre"],
                    "votos": c.get("votos_actuales"),
                    "porcentaje": c.get("porcentaje_actual"),
                }
                for c in candidatos
            ],
        },
        "proyectado_peru": {
            "ganador": proy.get("ganador_proyectado"),
            "margen_pct": proy.get("margen_proyectado_pct"),
            "diferencia_votos": proy.get("diferencia_votos_proyectada"),
            "votos_totales": proy.get("totales", {}).get("votos_proyectados"),
            "candidatos": [
                {
                    "nombre": c["nombre"],
                    "votos": c.get("votos_proyectados"),
                    "porcentaje": c.get("porcentaje_proyectado"),
                }
                for c in candidatos
            ],
        },
        "proyectado_final": {
            "ganador": ext.get("ganador_proyectado_con_extranjero"),
            "margen_pct": ext.get("margen_con_extranjero_pct"),
            "diferencia_votos": ext.get("diferencia_votos_con_extranjero"),
            "extranjero_modo": ext.get("modo"),
            "extranjero_votos_usados": ext.get("votos_extranjero_total"),
            "candidatos": [
                {
                    "nombre": c["nombre"],
                    "votos": c.get("votos_proyectados_con_extranjero"),
                    "porcentaje": c.get("porcentaje_proyectado_con_extranjero"),
                }
                for c in ext.get("candidatos") or []
            ],
        },
        "por_region": por_region,
    }


class ProjectionHistory:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.state_path = data_dir / "historial_state.json"
        self.log_path = data_dir / "historial.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"last_fingerprint": None, "entry_count": 0}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_if_changed(self, snapshot: Any) -> bool:
        fp = compute_fingerprint(snapshot.regiones, snapshot.extranjero)
        state = self._load_state()
        if fp == state.get("last_fingerprint"):
            return False

        entry = build_history_entry(snapshot)
        entry["fingerprint"] = fp

        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        state["last_fingerprint"] = fp
        state["entry_count"] = state.get("entry_count", 0) + 1
        state["last_timestamp"] = snapshot.updated_at
        self._save_state(state)
        self._trim()

        logger.info("Historial guardado — entrada #%s", state["entry_count"])
        return True

    def _trim(self) -> None:
        if not self.log_path.exists():
            return
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= MAX_ENTRIES:
            return
        trimmed = lines[-MAX_ENTRIES:]
        self.log_path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")

    def list_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        entries = [json.loads(line) for line in lines[-limit:]]
        return list(reversed(entries))

    def get_state(self) -> dict[str, Any]:
        return self._load_state()

"""Consulta concurrente a la API ONPE (segunda vuelta) por departamento."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from analysis import compute_projection, get_extranjero_config
from elecciones_2021 import compute_comparacion_2021
from history import ProjectionHistory

logger = logging.getLogger(__name__)

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://resultadosegundavuelta.onpe.gob.pe/main/resumen",
    "Origin": "https://resultadosegundavuelta.onpe.gob.pe",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

BASE = "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend"
ID_ELECCION = 10

DEPARTAMENTOS: dict[str, str] = {
    "010000": "Amazonas",
    "020000": "Áncash",
    "030000": "Apurímac",
    "040000": "Arequipa",
    "050000": "Ayacucho",
    "060000": "Cajamarca",
    "240000": "Callao",
    "070000": "Cusco",
    "080000": "Huancavelica",
    "090000": "Huánuco",
    "100000": "Ica",
    "110000": "Junín",
    "120000": "La Libertad",
    "130000": "Lambayeque",
    "140000": "Lima",
    "150000": "Loreto",
    "160000": "Madre de Dios",
    "170000": "Moquegua",
    "180000": "Pasco",
    "190000": "Piura",
    "200000": "Puno",
    "210000": "San Martín",
    "220000": "Tacna",
    "230000": "Tumbes",
    "250000": "Ucayali",
}

EXTRANJERO_CONTINENTES: dict[str, str] = {
    "910000": "África",
    "920000": "América",
    "930000": "Asia",
    "940000": "Europa",
    "950000": "Oceanía",
}

AMBITO_NACIONAL = 1
AMBITO_EXTRANJERO = 2


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_participante(raw: dict[str, Any]) -> dict[str, Any]:
    nombre = _first(
        raw.get("nombreParticipante"),
        raw.get("nombreCandidato"),
        raw.get("descripcion"),
        raw.get("nombre"),
        "Sin nombre",
    )
    return {
        "id": _first(raw.get("idParticipante"), raw.get("id")),
        "nombre": str(nombre),
        "votos": _as_int(
            _first(raw.get("totalVotosValidos"), raw.get("votosObtenidos"), raw.get("votos"))
        ),
        "porcentaje": _as_float(
            _first(raw.get("porcentajeVotosValidos"), raw.get("porcentaje"), raw.get("pct"))
        ),
        "color": _first(raw.get("color"), raw.get("colorHex")),
    }


def parse_participantes_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    participantes_raw: list[Any] = []
    meta: dict[str, Any] = {}

    if isinstance(data, list):
        participantes_raw = data
    elif isinstance(data, dict):
        participantes_raw = (
            data.get("participantes")
            or data.get("listaParticipantes")
            or data.get("candidatos")
            or []
        )
        meta = {k: v for k, v in data.items() if k not in {"participantes", "listaParticipantes", "candidatos"}}
        if not participantes_raw and any(k in data for k in ("nombreParticipante", "nombreCandidato")):
            participantes_raw = [data]
    elif payload.get("participantes"):
        participantes_raw = payload["participantes"]

    participantes = [
        normalize_participante(item)
        for item in participantes_raw
        if isinstance(item, dict)
    ]

    actas = {
        "contabilizadas": _as_int(
            _first(meta.get("actasContabilizadas"), meta.get("mesasEscrutadas"), meta.get("actasProcesadas"))
        ),
        "total": _as_int(_first(meta.get("totalActas"), meta.get("mesasTotal"), meta.get("totalMesas"))),
        "porcentaje": _as_float(
            _first(meta.get("porcentajeActasContabilizadas"), meta.get("porcentajeMesasEscrutadas"))
        ),
        "electores_habiles": _as_int(meta.get("electoresHabiles")),
        "votos_validos": _as_int(meta.get("votosValidos")),
        "participacion": _as_float(meta.get("participacion")),
    }

    return {
        "participantes": participantes,
        "actas": actas,
        "meta": meta,
        "success": payload.get("success", True),
    }


def parse_participantes_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [normalize_participante(item) for item in data if isinstance(item, dict)]
    parsed = parse_participantes_payload(payload)
    return parsed["participantes"] if parsed else []


def build_participantes_url(ubigeo: str, ambito: int = AMBITO_NACIONAL) -> str:
    return (
        f"{BASE}/resumen-general/participantes"
        f"?idEleccion={ID_ELECCION}&tipoFiltro=ubigeo_nivel_01"
        f"&idAmbitoGeografico={ambito}&idUbigeoDepartamento={ubigeo}"
    )


def build_totales_url(ubigeo: str, ambito: int = AMBITO_NACIONAL) -> str:
    return (
        f"{BASE}/resumen-general/totales"
        f"?idEleccion={ID_ELECCION}&tipoFiltro=ubigeo_nivel_01"
        f"&idAmbitoGeografico={ambito}&idUbigeoDepartamento={ubigeo}"
    )


def build_region_url(ubigeo: str) -> str:
    return build_participantes_url(ubigeo)


def parse_totales_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    contabilizadas = _as_int(_first(data.get("contabilizadas"), data.get("actasContabilizadasCount")))
    total = _as_int(_first(data.get("totalActas"), data.get("totalMesas")))
    pct_cont = _as_float(data.get("actasContabilizadas"))

    if pct_cont is None and contabilizadas is not None and total:
        pct_cont = round((contabilizadas / total) * 100, 3)

    return {
        "contabilizadas": contabilizadas,
        "total": total,
        "porcentaje_contabilizadas": pct_cont,
        "participacion_ciudadana": _as_float(data.get("participacionCiudadana")),
        "enviadas_jee": _as_int(data.get("enviadasJee")),
        "porcentaje_enviadas_jee": _as_float(data.get("actasEnviadasJee")),
        "pendientes_jee": _as_int(data.get("pendientesJee")),
        "porcentaje_pendientes_jee": _as_float(data.get("actasPendientesJee")),
        "votos_emitidos": _as_int(data.get("totalVotosEmitidos")),
        "votos_validos": _as_int(data.get("totalVotosValidos")),
        "porcentaje_votos_emitidos": _as_float(data.get("porcentajeVotosEmitidos")),
        "porcentaje_votos_validos": _as_float(data.get("porcentajeVotosValidos")),
        "fecha_actualizacion": data.get("fechaActualizacion"),
    }


async def fetch_json(client: httpx.AsyncClient, url: str) -> tuple[Any | None, str | None]:
    try:
        response = await client.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        text = response.text.strip()
        if "html" in content_type.lower() or text.startswith("<!"):
            return None, "La API devolvió HTML en lugar de JSON (CDN bloqueado o fuera de servicio)"
        return response.json(), None
    except httpx.HTTPError as exc:
        return None, f"HTTP: {exc}"
    except json.JSONDecodeError:
        return None, "Respuesta no es JSON válido"
    except Exception as exc:
        return None, str(exc)


async def fetch_totales(
    client: httpx.AsyncClient, ubigeo: str, nombre: str
) -> dict[str, Any]:
    url = build_totales_url(ubigeo)
    payload, error = await fetch_json(client, url)
    if error:
        return {"ubigeo": ubigeo, "region": nombre, "error": error}

    parsed = parse_totales_payload(payload)
    if not parsed:
        return {
            "ubigeo": ubigeo,
            "region": nombre,
            "error": "Sin datos de totales/actas en la respuesta",
            "raw": payload,
        }

    return {"ubigeo": ubigeo, "region": nombre, "procesamiento": parsed}


async def fetch_region(
    client: httpx.AsyncClient, ubigeo: str, nombre: str
) -> dict[str, Any]:
    participantes_url = build_participantes_url(ubigeo)
    totales_url = build_totales_url(ubigeo)

    (part_payload, part_error), (tot_payload, tot_error) = await asyncio.gather(
        fetch_json(client, participantes_url),
        fetch_json(client, totales_url),
    )

    errors: list[str] = []
    if part_error:
        errors.append(f"participantes: {part_error}")
    if tot_error:
        errors.append(f"totales: {tot_error}")

    if errors and len(errors) == 2:
        return {"ubigeo": ubigeo, "region": nombre, "error": "; ".join(errors)}

    result: dict[str, Any] = {"ubigeo": ubigeo, "region": nombre}

    if not part_error:
        parsed = parse_participantes_payload(part_payload)
        if parsed and parsed["participantes"]:
            result["participantes"] = parsed["participantes"]
        elif not tot_error:
            errors.append("Sin datos de participantes en la respuesta")

    if not tot_error:
        procesamiento = parse_totales_payload(tot_payload)
        if procesamiento:
            result["procesamiento"] = procesamiento
            result["actas"] = {
                "contabilizadas": procesamiento["contabilizadas"],
                "total": procesamiento["total"],
                "porcentaje": procesamiento["porcentaje_contabilizadas"],
                "participacion_ciudadana": procesamiento["participacion_ciudadana"],
                "pendientes_jee": procesamiento["pendientes_jee"],
                "porcentaje_pendientes_jee": procesamiento["porcentaje_pendientes_jee"],
                "enviadas_jee": procesamiento["enviadas_jee"],
                "porcentaje_enviadas_jee": procesamiento["porcentaje_enviadas_jee"],
            }
        elif not part_error:
            errors.append("Sin datos de totales/actas en la respuesta")

    if errors and "participantes" not in result and "procesamiento" not in result:
        result["error"] = "; ".join(errors)
    elif errors:
        result["warnings"] = errors

    return result


async def fetch_extranjero_region(
    client: httpx.AsyncClient, ubigeo: str, nombre: str
) -> dict[str, Any]:
    participantes_url = build_participantes_url(ubigeo, AMBITO_EXTRANJERO)
    totales_url = build_totales_url(ubigeo, AMBITO_EXTRANJERO)

    (part_payload, part_error), (tot_payload, tot_error) = await asyncio.gather(
        fetch_json(client, participantes_url),
        fetch_json(client, totales_url),
    )

    result: dict[str, Any] = {"ubigeo": ubigeo, "region": nombre, "ambito": "extranjero"}

    if not part_error:
        participantes = parse_participantes_list(part_payload)
        if participantes:
            result["participantes"] = participantes

    if not tot_error:
        procesamiento = parse_totales_payload(tot_payload)
        if procesamiento:
            result["procesamiento"] = procesamiento
            result["actas"] = {
                "contabilizadas": procesamiento["contabilizadas"],
                "total": procesamiento["total"],
                "porcentaje": procesamiento["porcentaje_contabilizadas"],
                "votos_validos": procesamiento["votos_validos"],
            }

    if "participantes" not in result and "procesamiento" not in result:
        errors = [e for e in (part_error, tot_error) if e]
        result["error"] = "; ".join(errors) if errors else "Sin datos de voto en el extranjero"

    return result


async def fetch_all_regions() -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_region(client, ubigeo, nombre)
            for ubigeo, nombre in DEPARTAMENTOS.items()
        ]
        return list(await asyncio.gather(*tasks))


def aggregate_procesamiento(regiones: list[dict[str, Any]]) -> dict[str, Any]:
    contabilizadas = 0
    total_actas = 0
    pendientes_jee = 0
    enviadas_jee = 0
    votos_emitidos = 0
    votos_validos = 0
    participacion_ponderada = 0.0
    peso_participacion = 0
    regiones_con_actas = 0

    for region in regiones:
        proc = region.get("procesamiento")
        if not proc and region.get("actas"):
            actas = region["actas"]
            proc = {
                "contabilizadas": actas.get("contabilizadas"),
                "total": actas.get("total"),
                "porcentaje_contabilizadas": actas.get("porcentaje"),
                "participacion_ciudadana": actas.get("participacion_ciudadana"),
                "pendientes_jee": actas.get("pendientes_jee"),
                "enviadas_jee": actas.get("enviadas_jee"),
                "votos_emitidos": None,
                "votos_validos": None,
            }
        if not proc:
            continue

        c = proc.get("contabilizadas")
        t = proc.get("total")
        if c is None or t is None:
            continue

        regiones_con_actas += 1
        contabilizadas += c
        total_actas += t
        pendientes_jee += proc.get("pendientes_jee") or 0
        enviadas_jee += proc.get("enviadas_jee") or 0
        votos_emitidos += proc.get("votos_emitidos") or 0
        votos_validos += proc.get("votos_validos") or 0

        part = proc.get("participacion_ciudadana")
        if part is not None and t:
            participacion_ponderada += part * t
            peso_participacion += t

    pct_cont = round((contabilizadas / total_actas) * 100, 3) if total_actas else None
    participacion = (
        round(participacion_ponderada / peso_participacion, 3) if peso_participacion else None
    )

    return {
        "contabilizadas": contabilizadas or None,
        "total": total_actas or None,
        "porcentaje_contabilizadas": pct_cont,
        "participacion_ciudadana": participacion,
        "pendientes_jee": pendientes_jee or None,
        "enviadas_jee": enviadas_jee or None,
        "votos_emitidos": votos_emitidos or None,
        "votos_validos": votos_validos or None,
        "regiones_con_actas": regiones_con_actas,
    }


def aggregate_nacional(
    regiones: list[dict[str, Any]],
    extranjero: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    totales: dict[str, dict[str, Any]] = {}
    regiones_ok = 0
    regiones_error = 0

    for region in regiones:
        if "error" in region:
            regiones_error += 1
            continue
        regiones_ok += 1
        for cand in region.get("participantes", []):
            key = cand["nombre"]
            if key not in totales:
                totales[key] = {"nombre": key, "votos": 0, "color": cand.get("color")}
            votos = cand.get("votos") or 0
            totales[key]["votos"] += votos

    candidatos = sorted(totales.values(), key=lambda x: x["votos"], reverse=True)
    total_votos = sum(c["votos"] for c in candidatos)
    for cand in candidatos:
        cand["porcentaje"] = round((cand["votos"] / total_votos) * 100, 3) if total_votos else 0.0

    procesamiento = aggregate_procesamiento(regiones)

    proyeccion = compute_projection(
        regiones,
        extranjero=extranjero,
        extranjero_config=get_extranjero_config(),
    )

    return {
        "candidatos": candidatos,
        "total_votos": total_votos,
        "regiones_ok": regiones_ok,
        "regiones_error": regiones_error,
        "actas_sum": {
            "contabilizadas": procesamiento["contabilizadas"],
            "total": procesamiento["total"],
            "porcentaje": procesamiento["porcentaje_contabilizadas"],
        },
        "procesamiento": procesamiento,
        "proyeccion": proyeccion,
        "comparacion_2021": compute_comparacion_2021(regiones, proyeccion),
    }


@dataclass
class ElectionSnapshot:
    updated_at: str = ""
    regiones: list[dict[str, Any]] = field(default_factory=list)
    extranjero: list[dict[str, Any]] = field(default_factory=list)
    nacional: dict[str, Any] = field(default_factory=dict)
    resumen_nacional_api: dict[str, Any] = field(default_factory=dict)
    fetching: bool = False
    last_error: str | None = None
    fetch_count: int = 0


class ElectionStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or Path("data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot = ElectionSnapshot()
        self.history = ProjectionHistory(self.data_dir)
        self._lock = asyncio.Lock()

    async def refresh(self) -> ElectionSnapshot:
        async with self._lock:
            self.snapshot.fetching = True

        try:
            async with httpx.AsyncClient() as client:
                region_tasks = [
                    fetch_region(client, ubigeo, nombre)
                    for ubigeo, nombre in DEPARTAMENTOS.items()
                ]
                extranjero_tasks = [
                    fetch_extranjero_region(client, ubigeo, nombre)
                    for ubigeo, nombre in EXTRANJERO_CONTINENTES.items()
                ]
                regiones, extranjero = await asyncio.gather(
                    asyncio.gather(*region_tasks),
                    asyncio.gather(*extranjero_tasks),
                )

            nacional = aggregate_nacional(list(regiones), list(extranjero))
            now = datetime.now(timezone.utc).isoformat()

            snapshot = ElectionSnapshot(
                updated_at=now,
                regiones=list(regiones),
                extranjero=list(extranjero),
                nacional=nacional,
                resumen_nacional_api=nacional.get("procesamiento", {}),
                fetching=False,
                last_error=self._detect_global_error(regiones),
                fetch_count=self.snapshot.fetch_count + 1,
            )

            async with self._lock:
                self.snapshot = snapshot

            self._persist(snapshot)
            self.history.save_if_changed(snapshot)
            logger.info(
                "Actualización #%s — %s regiones OK, %s errores",
                snapshot.fetch_count,
                nacional["regiones_ok"],
                nacional["regiones_error"],
            )
            return snapshot
        except Exception as exc:
            logger.exception("Error en refresh")
            async with self._lock:
                self.snapshot.fetching = False
                self.snapshot.last_error = str(exc)
            raise

    def _detect_global_error(self, regiones: list[dict[str, Any]]) -> str | None:
        errors = [r.get("error") for r in regiones if r.get("error")]
        if len(errors) == len(regiones):
            return errors[0]
        return None

    def _persist(self, snapshot: ElectionSnapshot) -> None:
        path = self.data_dir / "onpe_regiones.json"
        payload = {
            "updated_at": snapshot.updated_at,
            "fetch_count": snapshot.fetch_count,
            "last_error": snapshot.last_error,
            "nacional": snapshot.nacional,
            "resumen_nacional_api": snapshot.resumen_nacional_api,
            "regiones": snapshot.regiones,
            "extranjero": snapshot.extranjero,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def to_api_dict(self, poll_interval_seconds: int = 60) -> dict[str, Any]:
        s = self.snapshot
        return {
            "updated_at": s.updated_at,
            "fetch_count": s.fetch_count,
            "fetching": s.fetching,
            "last_error": s.last_error,
            "poll_interval_seconds": poll_interval_seconds,
            "nacional": s.nacional,
            "proyeccion": s.nacional.get("proyeccion", {}),
            "comparacion_2021": s.nacional.get("comparacion_2021", {}),
            "extranjero": s.extranjero,
            "historial": {
                "total_entradas": self.history.get_state().get("entry_count", 0),
                "ultimo_cambio": self.history.get_state().get("last_timestamp"),
            },
            "resumen_nacional_api": s.resumen_nacional_api,
            "regiones": s.regiones,
            "departamentos": DEPARTAMENTOS,
            "source": BASE,
        }

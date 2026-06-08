"""Proyección electoral extrapolando tendencias por departamento con actas pendientes."""

from __future__ import annotations

import os
from typing import Any


def _proc(region: dict[str, Any]) -> dict[str, Any]:
    return region.get("procesamiento") or region.get("actas") or {}


def _pct_procesado(proc: dict[str, Any]) -> float | None:
    pct = proc.get("porcentaje_contabilizadas") or proc.get("porcentaje")
    if pct is not None:
        return float(pct)
    cont = proc.get("contabilizadas")
    total = proc.get("total")
    if cont is not None and total:
        return round((cont / total) * 100, 3)
    return None


def _is_keiko(nombre: str) -> bool:
    return "FUJIMORI" in nombre.upper()


def _is_sanchez(nombre: str) -> bool:
    return "SANCHEZ" in nombre.upper()


def get_extranjero_config() -> dict[str, Any]:
    return {
        "total_votos_estimados": int(os.getenv("VOTO_EXTRANJERO_ESTIMADO", "350000")),
        "keiko_pct": float(os.getenv("VOTO_EXTRANJERO_KEIKO_PCT", "65")),
        "sanchez_pct": float(os.getenv("VOTO_EXTRANJERO_SANCHEZ_PCT", "35")),
    }


def _aggregate_extranjero_api(extranjero: list[dict[str, Any]]) -> dict[str, Any]:
    actas_total = 0
    actas_cont = 0
    votos_validos = 0
    votos_por_candidato: dict[str, int] = {}
    continentes: list[dict[str, Any]] = []

    for region in extranjero:
        if region.get("error"):
            continue
        proc = _proc(region)
        actas_total += proc.get("total") or 0
        actas_cont += proc.get("contabilizadas") or 0
        votos_validos += proc.get("votos_validos") or 0

        cont_votos: dict[str, int] = {}
        for p in region.get("participantes") or []:
            nombre = p["nombre"]
            v = p.get("votos") or 0
            cont_votos[nombre] = v
            votos_por_candidato[nombre] = votos_por_candidato.get(nombre, 0) + v

        continentes.append(
            {
                "region": region["region"],
                "ubigeo": region["ubigeo"],
                "actas_total": proc.get("total"),
                "actas_contabilizadas": proc.get("contabilizadas"),
                "pct_procesado": proc.get("porcentaje_contabilizadas") or proc.get("porcentaje"),
                "votos_validos": proc.get("votos_validos"),
                "votos_por_candidato": cont_votos,
            }
        )

    pct = round((actas_cont / actas_total) * 100, 3) if actas_total else 0.0
    return {
        "continentes": continentes,
        "actas_total": actas_total,
        "actas_contabilizadas": actas_cont,
        "pct_procesado": pct,
        "votos_validos_api": votos_validos,
        "votos_por_candidato_api": votos_por_candidato,
    }


def _apply_voto_extranjero(
    ranking: list[dict[str, Any]],
    extranjero_api: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    keiko_name = next((c["nombre"] for c in ranking if _is_keiko(c["nombre"])), None)
    sanchez_name = next((c["nombre"] for c in ranking if _is_sanchez(c["nombre"])), None)

    total_est = config["total_votos_estimados"]
    keiko_pct_est = config["keiko_pct"]
    sanchez_pct_est = config["sanchez_pct"]

    api_votos = extranjero_api.get("votos_validos_api") or 0
    api_por_candidato = extranjero_api.get("votos_por_candidato_api") or {}
    actas_total = extranjero_api.get("actas_total") or 0
    actas_cont = extranjero_api.get("actas_contabilizadas") or 0

    extranjero_por_candidato: dict[str, int] = {}
    modo = "estimado"
    keiko_pct_usado = keiko_pct_est
    sanchez_pct_usado = sanchez_pct_est
    votos_extranjero_total = 0

    if api_votos > 0:
        modo = "real"
        actual: dict[str, int] = {}
        for nombre in (keiko_name, sanchez_name):
            if nombre:
                actual[nombre] = api_por_candidato.get(nombre, 0)

        actas_pend = max(0, (actas_total or 0) - (actas_cont or 0))
        if actas_cont > 0 and actas_pend > 0:
            avg_por_acta = api_votos / actas_cont
            pend_votos = round(avg_por_acta * actas_pend)
            total_api = sum(actual.values()) or api_votos
            for nombre, v in actual.items():
                pct = v / total_api if total_api else 0
                actual[nombre] = v + round(pend_votos * pct)
        extranjero_por_candidato = actual
        votos_extranjero_total = sum(extranjero_por_candidato.values())
        if keiko_name and sanchez_name and votos_extranjero_total:
            keiko_pct_usado = round(
                extranjero_por_candidato.get(keiko_name, 0) / votos_extranjero_total * 100, 2
            )
            sanchez_pct_usado = round(
                extranjero_por_candidato.get(sanchez_name, 0) / votos_extranjero_total * 100, 2
            )
        nota = (
            f"Extranjero con datos reales ONPE ({fmt_num(api_votos)} votos contabilizados). "
            f"Proyección de actas pendientes mantiene la tendencia observada "
            f"({keiko_pct_usado:.1f}% / {sanchez_pct_usado:.1f}%)."
        )
    else:
        votos_a_modelar = total_est
        keiko_ext = round(votos_a_modelar * keiko_pct_est / 100)
        sanchez_ext = votos_a_modelar - keiko_ext
        if keiko_name:
            extranjero_por_candidato[keiko_name] = keiko_ext
        if sanchez_name:
            extranjero_por_candidato[sanchez_name] = sanchez_ext
        votos_extranjero_total = votos_a_modelar
        nota = (
            f"Extranjero en modo estático: {fmt_num(votos_a_modelar)} votos estimados "
            f"({keiko_pct_est:.0f}% Keiko / {sanchez_pct_est:.0f}% Sánchez) "
            f"hasta que la ONPE publique resultados reales."
        )

    keiko_ext = extranjero_por_candidato.get(keiko_name or "", 0)
    sanchez_ext = extranjero_por_candidato.get(sanchez_name or "", 0)

    ranking_ext: list[dict[str, Any]] = []
    for cand in ranking:
        ext = extranjero_por_candidato.get(cand["nombre"], 0)
        proy_dom = cand["votos_proyectados"]
        proy_total = proy_dom + ext
        ranking_ext.append(
            {
                **cand,
                "votos_extranjero_estimados": ext,
                "votos_proyectados_con_extranjero": proy_total,
            }
        )

    total_con_ext = sum(c["votos_proyectados_con_extranjero"] for c in ranking_ext)
    for cand in ranking_ext:
        cand["porcentaje_proyectado_con_extranjero"] = (
            round((cand["votos_proyectados_con_extranjero"] / total_con_ext) * 100, 3)
            if total_con_ext
            else 0.0
        )

    ranking_ext.sort(key=lambda x: x["votos_proyectados_con_extranjero"], reverse=True)

    ganador_dom = ranking[0]["nombre"] if ranking else None
    ganador_ext = ranking_ext[0]["nombre"] if ranking_ext else None

    margen_dom = 0.0
    margen_ext = 0.0
    diff_dom = 0
    diff_ext = 0
    if len(ranking_ext) >= 2:
        margen_dom = round(
            ranking[0]["porcentaje_proyectado"] - ranking[1]["porcentaje_proyectado"], 3
        )
        margen_ext = round(
            ranking_ext[0]["porcentaje_proyectado_con_extranjero"]
            - ranking_ext[1]["porcentaje_proyectado_con_extranjero"],
            3,
        )
        diff_dom = ranking[0]["votos_proyectados"] - ranking[1]["votos_proyectados"]
        diff_ext = (
            ranking_ext[0]["votos_proyectados_con_extranjero"]
            - ranking_ext[1]["votos_proyectados_con_extranjero"]
        )

    neto_keiko = 0
    if keiko_name and sanchez_name:
        neto_keiko = keiko_ext - sanchez_ext

    return {
        "activo": True,
        "modo": modo,
        "total_votos_estimados": total_est,
        "votos_modelados": votos_extranjero_total if modo == "estimado" else 0,
        "votos_extranjero_total": votos_extranjero_total,
        "votos_ya_contabilizados_api": api_votos,
        "keiko_pct": keiko_pct_usado,
        "sanchez_pct": sanchez_pct_usado,
        "keiko_pct_estatico": keiko_pct_est,
        "sanchez_pct_estatico": sanchez_pct_est,
        "votos_keiko_estimados": keiko_ext,
        "votos_sanchez_estimados": sanchez_ext,
        "ventaja_neta_keiko": neto_keiko,
        "actas_extranjero_total": actas_total,
        "actas_extranjero_contabilizadas": actas_cont,
        "pct_actas_extranjero_procesadas": extranjero_api.get("pct_procesado"),
        "continentes": extranjero_api.get("continentes", []),
        "candidatos": ranking_ext,
        "ganador_proyectado_sin_extranjero": ganador_dom,
        "ganador_proyectado_con_extranjero": ganador_ext,
        "cambia_ganador": ganador_dom != ganador_ext,
        "margen_sin_extranjero_pct": margen_dom,
        "margen_con_extranjero_pct": margen_ext,
        "diferencia_votos_sin_extranjero": diff_dom,
        "diferencia_votos_con_extranjero": diff_ext,
        "impacto_margen_pct": round(margen_ext - margen_dom, 3),
        "impacto_votos": diff_ext - diff_dom,
        "nota": nota,
    }


def fmt_num(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def compute_projection(
    regiones: list[dict[str, Any]],
    extranjero: list[dict[str, Any]] | None = None,
    extranjero_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dept_analysis: list[dict[str, Any]] = []
    candidatos: set[str] = set()

    for region in regiones:
        if region.get("error"):
            continue

        participantes = region.get("participantes") or []
        if not participantes:
            continue

        proc = _proc(region)
        pct = _pct_procesado(proc)
        if pct is None or pct <= 0:
            continue

        cont = proc.get("contabilizadas")
        total = proc.get("total")
        pct_frac = min(pct / 100.0, 1.0)
        completo = pct >= 99.5 or (cont is not None and total is not None and cont >= total)
        actas_pendientes = (total - cont) if (cont is not None and total is not None) else None

        votos_actual: dict[str, int] = {}
        votos_proy: dict[str, int] = {}
        votos_pend: dict[str, int] = {}
        tendencia: dict[str, float] = {}

        total_depto = sum(p.get("votos") or 0 for p in participantes)

        for p in participantes:
            nombre = p["nombre"]
            candidatos.add(nombre)
            v = p.get("votos") or 0
            votos_actual[nombre] = v
            tendencia[nombre] = round((v / total_depto) * 100, 2) if total_depto else 0.0

            if completo:
                proy = v
            else:
                proy = round(v / pct_frac)
            votos_proy[nombre] = proy
            votos_pend[nombre] = proy - v

        lider = max(participantes, key=lambda x: x.get("votos") or 0)
        lider_proy = max(votos_proy.items(), key=lambda x: x[1])[0] if votos_proy else lider["nombre"]
        total_proy_depto = sum(votos_proy.values())
        total_pend_depto = total_proy_depto - total_depto

        dept_analysis.append(
            {
                "region": region["region"],
                "ubigeo": region["ubigeo"],
                "pct_procesado": round(pct, 3),
                "actas_pendientes": actas_pendientes,
                "actas_total": total,
                "completo": completo,
                "votos_actuales": total_depto,
                "votos_pendientes_estimados": total_pend_depto,
                "votos_proyectados": total_proy_depto,
                "tendencia": tendencia,
                "lider_real": lider["nombre"],
                "lider_departamento": lider["nombre"],
                "lider_proyectado": lider_proy,
                "lider_pct": lider.get("porcentaje"),
                "votos_por_candidato": votos_actual,
                "proyeccion_por_candidato": votos_proy,
                "pendiente_por_candidato": votos_pend,
                "candidatos": [
                    {
                        "nombre": p["nombre"],
                        "votos_actuales": votos_actual.get(p["nombre"], 0),
                        "votos_proyectados": votos_proy.get(p["nombre"], 0),
                        "pct_actual": tendencia.get(p["nombre"], 0),
                    }
                    for p in participantes
                ],
            }
        )

    if not candidatos:
        return {"disponible": False, "motivo": "Sin datos de candidatos para proyectar"}

    nacional_actual = {c: 0 for c in candidatos}
    nacional_proy = {c: 0 for c in candidatos}
    nacional_pend = {c: 0 for c in candidatos}

    for dept in dept_analysis:
        for c in candidatos:
            nacional_actual[c] += dept["votos_por_candidato"].get(c, 0)
            nacional_proy[c] += dept["proyeccion_por_candidato"].get(c, 0)
            nacional_pend[c] += dept["pendiente_por_candidato"].get(c, 0)

    total_actual = sum(nacional_actual.values())
    total_proy = sum(nacional_proy.values())

    ranking: list[dict[str, Any]] = []
    for nombre in candidatos:
        act = nacional_actual[nombre]
        proy = nacional_proy[nombre]
        ranking.append(
            {
                "nombre": nombre,
                "votos_actuales": act,
                "porcentaje_actual": round((act / total_actual) * 100, 3) if total_actual else 0.0,
                "votos_proyectados": proy,
                "porcentaje_proyectado": round((proy / total_proy) * 100, 3) if total_proy else 0.0,
                "votos_pendientes_estimados": nacional_pend[nombre],
            }
        )
    ranking.sort(key=lambda x: x["votos_proyectados"], reverse=True)

    ganador_proy = ranking[0]["nombre"] if ranking else None
    ganador_actual = max(ranking, key=lambda x: x["votos_actuales"])["nombre"] if ranking else None

    margen_proy = 0.0
    margen_actual = 0.0
    diff_votos_proy = 0
    if len(ranking) >= 2:
        margen_proy = round(ranking[0]["porcentaje_proyectado"] - ranking[1]["porcentaje_proyectado"], 3)
        margen_actual = round(ranking[0]["porcentaje_actual"] - ranking[1]["porcentaje_actual"], 3)
        diff_votos_proy = ranking[0]["votos_proyectados"] - ranking[1]["votos_proyectados"]

    deptos_pendientes = sorted(
        [d for d in dept_analysis if not d["completo"]],
        key=lambda x: x["votos_pendientes_estimados"],
        reverse=True,
    )
    deptos_completos = [d for d in dept_analysis if d["completo"]]

    peso_pendiente = sum(d["votos_pendientes_estimados"] for d in deptos_pendientes)
    pct_nacional = None
    if dept_analysis:
        peso = sum(d["votos_actuales"] / max(d["pct_procesado"] / 100, 0.001) for d in dept_analysis)
        actual_sum = sum(d["votos_actuales"] for d in dept_analysis)
        if peso:
            pct_nacional = round((actual_sum / peso) * 100, 3)

    cambio_ganador = ganador_proy != ganador_actual

    result: dict[str, Any] = {
        "disponible": True,
        "metodo": (
            "Extrapolación lineal por departamento: se asume que los votos restantes "
            "mantienen la misma proporción candidato/candidato observada hasta ahora."
        ),
        "disclaimer": (
            "Proyección estadística no oficial. No sustituye el conteo de la ONPE. "
            "Los departamentos con pocas actas contabilizadas tienen mayor incertidumbre."
        ),
        "pct_nacional_procesado": pct_nacional,
        "ganador_proyectado": ganador_proy,
        "ganador_actual": ganador_actual,
        "cambio_ganador_posible": cambio_ganador,
        "margen_proyectado_pct": margen_proy,
        "margen_actual_pct": margen_actual,
        "diferencia_votos_proyectada": diff_votos_proy,
        "candidatos": ranking,
        "totales": {
            "votos_actuales": total_actual,
            "votos_proyectados": total_proy,
            "votos_pendientes_estimados": total_proy - total_actual,
        },
        "departamentos_pendientes": deptos_pendientes,
        "departamentos_completos": len(deptos_completos),
        "departamentos_en_conteo": len(deptos_pendientes),
        "departamentos": dept_analysis,
        "mapa": {d["ubigeo"]: d for d in dept_analysis},
        "peso_votos_pendientes": peso_pendiente,
    }

    if extranjero is not None:
        config = extranjero_config or get_extranjero_config()
        api_resumen = _aggregate_extranjero_api(extranjero)
        result["extranjero"] = _apply_voto_extranjero(ranking, api_resumen, config)
        ext = result["extranjero"]
        if ext.get("cambia_ganador"):
            result["ganador_proyectado_final"] = ext["ganador_proyectado_con_extranjero"]
            result["margen_proyectado_final_pct"] = ext["margen_con_extranjero_pct"]
        else:
            result["ganador_proyectado_final"] = ext["ganador_proyectado_con_extranjero"]
            result["margen_proyectado_final_pct"] = ext["margen_con_extranjero_pct"]

    return result

"""Resultados segunda vuelta 2021 (Castillo vs Fujimori) y comparación con 2026."""

from __future__ import annotations

from typing import Any

# Votos válidos por departamento — fuente: resultados oficiales ONPE 2021
ELECCION_2021: dict[str, dict[str, Any]] = {
    "010000": {"region": "Amazonas", "castillo": 121_162, "fujimori": 60_451},
    "020000": {"region": "Áncash", "castillo": 347_457, "fujimori": 247_628},
    "030000": {"region": "Apurímac", "castillo": 174_344, "fujimori": 39_666},
    "040000": {"region": "Arequipa", "castillo": 558_085, "fujimori": 302_622},
    "050000": {"region": "Ayacucho", "castillo": 266_824, "fujimori": 56_061},
    "060000": {"region": "Cajamarca", "castillo": 509_790, "fujimori": 205_403},
    "240000": {"region": "Callao", "castillo": 198_503, "fujimori": 410_860},
    "070000": {"region": "Cusco", "castillo": 610_521, "fujimori": 123_295},
    "080000": {"region": "Huancavelica", "castillo": 166_279, "fujimori": 29_782},
    "090000": {"region": "Huánuco", "castillo": 255_556, "fujimori": 121_899},
    "100000": {"region": "Ica", "castillo": 233_316, "fujimori": 257_640},
    "110000": {"region": "Junín", "castillo": 396_598, "fujimori": 285_375},
    "120000": {"region": "La Libertad", "castillo": 392_224, "fujimori": 588_417},
    "130000": {"region": "Lambayeque", "castillo": 289_784, "fujimori": 403_216},
    "140000": {"region": "Lima", "castillo": 2_195_770, "fujimori": 4_014_342},
    "150000": {"region": "Loreto", "castillo": 193_765, "fujimori": 208_232},
    "160000": {"region": "Madre de Dios", "castillo": 57_387, "fujimori": 23_372},
    "170000": {"region": "Moquegua", "castillo": 80_520, "fujimori": 29_578},
    "180000": {"region": "Pasco", "castillo": 82_851, "fujimori": 43_922},
    "190000": {"region": "Piura", "castillo": 388_901, "fujimori": 584_584},
    "200000": {"region": "Puno", "castillo": 645_813, "fujimori": 77_739},
    "210000": {"region": "San Martín", "castillo": 241_491, "fujimori": 188_834},
    "220000": {"region": "Tacna", "castillo": 154_223, "fujimori": 58_307},
    "230000": {"region": "Tumbes", "castillo": 41_464, "fujimori": 80_064},
    "250000": {"region": "Ucayali", "castillo": 121_081, "fujimori": 130_240},
    "extranjero": {"region": "Voto en el extranjero", "castillo": 112_671, "fujimori": 220_588},
}

META_2021 = {
    "anio": 2021,
    "candidatos": {
        "izquierda": "Pedro Castillo",
        "derecha": "Keiko Fujimori",
    },
    "ganador": "Pedro Castillo",
}


def _pct(a: int, b: int, total: int) -> float:
    return round((a / total) * 100, 3) if total else 0.0


def _find_keiko(participantes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for p in participantes:
        if "FUJIMORI" in (p.get("nombre") or "").upper():
            return p
    return None


def _find_sanchez(participantes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for p in participantes:
        if "SANCHEZ" in (p.get("nombre") or "").upper():
            return p
    return None


def _nacional_2021() -> dict[str, Any]:
    castillo = sum(d["castillo"] for k, d in ELECCION_2021.items() if k != "extranjero")
    fujimori = sum(d["fujimori"] for k, d in ELECCION_2021.items() if k != "extranjero")
    total = castillo + fujimori
    ext = ELECCION_2021["extranjero"]
    ext_total = ext["castillo"] + ext["fujimori"]
    return {
        "castillo_votos": castillo,
        "fujimori_votos": fujimori,
        "total_votos": total,
        "castillo_pct": _pct(castillo, fujimori, total),
        "fujimori_pct": _pct(fujimori, castillo, total),
        "margen_pp": round(_pct(castillo, fujimori, total) - _pct(fujimori, castillo, total), 3),
        "extranjero": {
            "castillo": ext["castillo"],
            "fujimori": ext["fujimori"],
            "castillo_pct": _pct(ext["castillo"], ext["fujimori"], ext_total),
            "fujimori_pct": _pct(ext["fujimori"], ext["castillo"], ext_total),
        },
    }


def compute_comparacion_2021(
    regiones: list[dict[str, Any]],
    proyeccion: dict[str, Any],
) -> dict[str, Any]:
    mapa = proyeccion.get("mapa") or {}
    ext_2026 = proyeccion.get("extranjero") or {}
    ranking = proyeccion.get("candidatos") or []

    keiko_nacional = next((c for c in ranking if "FUJIMORI" in c["nombre"].upper()), None)
    sanchez_nacional = next((c for c in ranking if "SANCHEZ" in c["nombre"].upper()), None)

    nacional_2021 = _nacional_2021()
    departamentos: list[dict[str, Any]] = []
    deltas_keiko: list[float] = []
    flipped: list[dict[str, Any]] = []

    for ubigeo, d2021 in ELECCION_2021.items():
        if ubigeo == "extranjero":
            continue
        total_21 = d2021["castillo"] + d2021["fujimori"]
        pct_fuj_21 = _pct(d2021["fujimori"], d2021["castillo"], total_21)
        pct_cas_21 = _pct(d2021["castillo"], d2021["fujimori"], total_21)
        ganador_21 = "Castillo" if d2021["castillo"] > d2021["fujimori"] else "Fujimori"

        dept_26 = mapa.get(ubigeo)
        if not dept_26:
            continue

        keiko = _find_keiko(
            [{"nombre": n, "votos": v} for n, v in dept_26.get("votos_por_candidato", {}).items()]
        ) or {}
        sanchez = _find_sanchez(
            [{"nombre": n, "votos": v} for n, v in dept_26.get("votos_por_candidato", {}).items()]
        ) or {}

        votos_keiko_act = keiko.get("votos") or 0
        votos_sanchez_act = sanchez.get("votos") or 0
        total_26_act = dept_26.get("votos_actuales") or 0
        total_26_proy = dept_26.get("votos_proyectados") or 0

        proy_map = dept_26.get("proyeccion_por_candidato") or {}
        keiko_nombre = keiko.get("nombre") or "Keiko Fujimori"
        sanchez_nombre = sanchez.get("nombre") or "Roberto Sánchez"
        votos_keiko_proy = proy_map.get(keiko_nombre, votos_keiko_act)
        votos_sanchez_proy = proy_map.get(sanchez_nombre, votos_sanchez_act)

        pct_keiko_act = _pct(votos_keiko_act, votos_sanchez_act, total_26_act)
        pct_keiko_proy = _pct(votos_keiko_proy, votos_sanchez_proy, total_26_proy)
        pct_sanchez_act = _pct(votos_sanchez_act, votos_keiko_act, total_26_act)
        ganador_26_act = "Keiko" if votos_keiko_act >= votos_sanchez_act else "Sánchez"
        ganador_26_proy = "Keiko" if votos_keiko_proy >= votos_sanchez_proy else "Sánchez"

        fujimori_gano_21 = d2021["fujimori"] > d2021["castillo"]
        keiko_gana_26_proy = votos_keiko_proy >= votos_sanchez_proy
        castillo_gano_21 = d2021["castillo"] > d2021["fujimori"]
        sanchez_gana_26_proy = votos_sanchez_proy > votos_keiko_proy

        delta_keiko_act = round(pct_keiko_act - pct_fuj_21, 3)
        delta_keiko_proy = round(pct_keiko_proy - pct_fuj_21, 3)
        pct_sanchez_proy = _pct(votos_sanchez_proy, votos_keiko_proy, total_26_proy)
        delta_sanchez_vs_castillo = round(pct_sanchez_proy - pct_cas_21, 3)
        deltas_keiko.append(delta_keiko_act)

        similitud = round(100 - abs(delta_keiko_act), 1)
        cambio_linea_fujimori = fujimori_gano_21 != keiko_gana_26_proy
        cambio_linea_izquierda = castillo_gano_21 != sanchez_gana_26_proy

        item = {
            "ubigeo": ubigeo,
            "region": d2021["region"],
            "2021": {
                "castillo_votos": d2021["castillo"],
                "fujimori_votos": d2021["fujimori"],
                "castillo_pct": pct_cas_21,
                "fujimori_pct": pct_fuj_21,
                "ganador": ganador_21,
            },
            "2026_actual": {
                "keiko_pct": pct_keiko_act,
                "sanchez_pct": pct_sanchez_act,
                "keiko_votos": votos_keiko_act,
                "sanchez_votos": votos_sanchez_act,
                "ganador": ganador_26_act,
            },
            "2026_proyectado": {
                "keiko_pct": pct_keiko_proy,
                "sanchez_pct": pct_sanchez_proy,
                "keiko_votos": votos_keiko_proy,
                "ganador": ganador_26_proy,
            },
            "delta_keiko_pp_actual": delta_keiko_act,
            "delta_keiko_pp_proyectado": delta_keiko_proy,
            "delta_sanchez_vs_castillo_pp": delta_sanchez_vs_castillo,
            "similitud_perfil_actual": similitud,
            "cambio_linea_fujimori": cambio_linea_fujimori,
            "cambio_linea_izquierda": cambio_linea_izquierda,
        }
        departamentos.append(item)
        if cambio_linea_fujimori:
            flipped.append(item)

    # Nacional 2026
    total_keiko_act = keiko_nacional["votos_actuales"] if keiko_nacional else 0
    total_sanchez_act = sanchez_nacional["votos_actuales"] if sanchez_nacional else 0
    total_act = total_keiko_act + total_sanchez_act
    pct_keiko_nac_act = _pct(total_keiko_act, total_sanchez_act, total_act)

    keiko_proy = keiko_nacional["votos_proyectados"] if keiko_nacional else 0
    sanchez_proy = sanchez_nacional["votos_proyectados"] if sanchez_nacional else 0
    pct_keiko_nac_proy = _pct(keiko_proy, sanchez_proy, keiko_proy + sanchez_proy)

    ext_cand = ext_2026.get("candidatos") or []
    keiko_ext = next((c for c in ext_cand if "FUJIMORI" in c["nombre"].upper()), {})
    pct_keiko_final = keiko_ext.get("porcentaje_proyectado_con_extranjero", pct_keiko_nac_proy)

    ext21 = nacional_2021["extranjero"]
    delta_nacional_keiko = round(pct_keiko_nac_act - nacional_2021["fujimori_pct"], 3)
    delta_nacional_proy = round(pct_keiko_nac_proy - nacional_2021["fujimori_pct"], 3)

    # Extranjero 2026 estimado vs 2021
    ext26_keiko_pct = ext_2026.get("keiko_pct") or 65.0
    delta_ext = round(ext26_keiko_pct - ext21["fujimori_pct"], 3)

    avg_delta = round(sum(deltas_keiko) / len(deltas_keiko), 3) if deltas_keiko else 0
    deptos_fujimori_flipped = len(flipped)
    deptos_izq_flipped = len([d for d in departamentos if d["cambio_linea_izquierda"]])

    deptos_keiko_mejora = len([d for d in departamentos if d["delta_keiko_pp_actual"] > 0])
    deptos_keiko_caida = len([d for d in departamentos if d["delta_keiko_pp_actual"] < 0])

    ganador_26_final = ext_2026.get("ganador_proyectado_con_extranjero", "")
    ganador_26_nombre = "Keiko Fujimori" if "FUJIMORI" in ganador_26_final.upper() else "Roberto Sánchez"

    return {
        "meta_2021": META_2021,
        "nacional_2021": nacional_2021,
        "nacional_2026": {
            "keiko_pct_actual": pct_keiko_nac_act,
            "keiko_pct_proyectado": pct_keiko_nac_proy,
            "keiko_pct_final_extranjero": pct_keiko_final,
            "delta_keiko_vs_2021_actual": delta_nacional_keiko,
            "delta_keiko_vs_2021_proyectado": delta_nacional_proy,
            "ganador_proyectado_final": ganador_26_nombre,
        },
        "extranjero_comparacion": {
            "2021_fujimori_pct": ext21["fujimori_pct"],
            "2026_keiko_pct_estimado": ext26_keiko_pct,
            "delta_pp": delta_ext,
            "nota": (
                f"En 2021 Fujimori obtuvo {ext21['fujimori_pct']:.1f}% en el extranjero. "
                f"En 2026 se estima {ext26_keiko_pct:.1f}% para Keiko "
                f"({'menor' if delta_ext < 0 else 'mayor'} ventaja vs 2021)."
            ),
        },
        "resumen": {
            "promedio_delta_keiko_pp": avg_delta,
            "departamentos_keiko_mejora": deptos_keiko_mejora,
            "departamentos_keiko_caida": deptos_keiko_caida,
            "departamentos_cambio_linea_fujimori": deptos_fujimori_flipped,
            "departamentos_cambio_linea_izquierda": deptos_izq_flipped,
            "similitud_promedio_perfil": round(
                sum(d["similitud_perfil_actual"] for d in departamentos) / len(departamentos), 1
            )
            if departamentos
            else 0,
        },
        "impacto": _build_impacto_text(
            nacional_2021, delta_nacional_keiko, delta_nacional_proy,
            ganador_26_nombre, len(flipped), avg_delta, ext21, ext26_keiko_pct,
        ),
        "departamentos": sorted(departamentos, key=lambda x: abs(x["delta_keiko_pp_actual"]), reverse=True),
        "cambios_linea_fujimori": flipped,
        "cambios_linea_izquierda": [d for d in departamentos if d["cambio_linea_izquierda"]],
    }


def _build_impacto_text(
    n21: dict[str, Any],
    delta_act: float,
    delta_proy: float,
    ganador_26: str,
    num_flipped: int,
    avg_delta: float,
    ext21: dict[str, Any],
    ext26_pct: float,
) -> str:
    parts = [
        f"En 2021 Castillo ganó nacionalmente con {n21['castillo_pct']:.2f}% "
        f"(margen {n21['margen_pp']:.2f} pp). Fujimori tuvo {n21['fujimori_pct']:.2f}%.",
        f"En 2026 Keiko {'mejora' if delta_act > 0 else 'reduce'} su share nacional en "
        f"{abs(delta_act):.2f} pp vs su resultado 2021 (conteo parcial).",
        f"Proyectado Perú: variación de {delta_proy:+.2f} pp respecto a 2021.",
        f"{num_flipped} departamentos cambian de control en la línea Fujimori/Keiko respecto a 2021.",
        f"Perfil regional: delta promedio Keiko {avg_delta:+.2f} pp por departamento.",
        f"Extranjero 2021: Fujimori {ext21['fujimori_pct']:.1f}% → "
        f"2026 estimado Keiko {ext26_pct:.1f}% ({ext26_pct - ext21['fujimori_pct']:+.1f} pp).",
        f"Ganador proyectado 2026 (con extranjero): {ganador_26}.",
    ]
    return " ".join(parts)

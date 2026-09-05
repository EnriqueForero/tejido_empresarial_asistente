"""
Pruebas del modelo semántico (snowflake/TEJIDO_EMPRESARIAL_SEGMENTACION.sv.yaml).

El YAML vive en el repositorio pero se ejecuta en Snowflake; estas pruebas
atrapan antes de desplegar lo que allá sólo se vería como una respuesta mala:
columnas que no existen, consultas verificadas que citan nombres desconocidos,
preguntas sugeridas sin consulta verificada y listados que traen contacto sin
que nadie lo haya pedido.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="requiere PyYAML (requirements-test.txt)")

from backend.config import IA_PREGUNTAS_SUGERIDAS, NITS_EJEMPLO, QUERY_COLUMNS  # noqa: E402

RUTA = Path(__file__).resolve().parent.parent / "snowflake" / "TEJIDO_EMPRESARIAL_SEGMENTACION.sv.yaml"

#: Columnas físicas que el aplicativo no expone en QUERY_COLUMNS pero que la
#: tabla sí tiene (indicadores municipales, CRM por año, banderas de territorio).
_PATRONES_EXTRA = (
    r"^_[A-Z_]+_MUNICIPIO$",
    r"^NUMERO_(NEGOCIOS|SERVICIOS|OPORTUNIDADES)_(\d{4}|ENE_JUN_\d{4})$",
    r"^(ATENDIDA_PC|NEGOCIOS|SERVICIOS|OPORTUNIDADES|MENOR_200K_HABITANTES|PDET|SUBREGION_PDET|ZOMAC|"
    r"POBLACION_MUNICIPIO|VALOR_AGREGADO_MUNICIPIO|EXPO_\d{4}|EXPO_ENE_MAY_\d{4})$",
)
_PALABRAS_SQL = {
    "SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "LIMIT", "AND", "OR", "NOT", "IN", "AS", "DESC",
    "ASC", "COUNT", "DISTINCT", "SUM", "AVG", "MAX", "MIN", "CASE", "WHEN", "THEN", "ELSE", "END",
    "NULLIF", "IFF", "ILIKE", "LIKE", "QUALIFY", "ROW_NUMBER", "OVER", "PARTITION", "ROUND", "CAST",
    "COALESCE", "ON", "JOIN", "LEFT", "INNER", "HAVING", "IS", "NULL", "BETWEEN", "EMPRESAS",
}
_CONTACTO = {"EMAIL", "TELEFONO", "DIRECCION", "REPRESENTANTE_LEGAL", "ID_REPRESENTANTE_LEGAL"}
_LITERAL = re.compile(r"'(?:[^']|'')*'")


@pytest.fixture(scope="module")
def modelo() -> dict:
    return yaml.safe_load(RUTA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tabla(modelo: dict) -> dict:
    return modelo["tables"][0]


def _nombres(tabla: dict) -> set[str]:
    return {
        item["name"].upper()
        for grupo in ("dimensions", "facts", "metrics")
        for item in tabla.get(grupo, [])
    }


def test_las_columnas_fisicas_existen_en_el_catalogo_del_aplicativo(tabla: dict) -> None:
    desconocidas = []
    for grupo in ("dimensions", "facts"):
        for item in tabla[grupo]:
            expr = str(item["expr"]).strip()
            if expr in QUERY_COLUMNS or any(re.match(patron, expr) for patron in _PATRONES_EXTRA):
                continue
            desconocidas.append(f"{item['name']} → {expr}")
    assert not desconocidas, "Columnas que el aplicativo no conoce: " + ", ".join(desconocidas)


def test_las_metricas_citan_nombres_logicos(tabla: dict) -> None:
    nombres = _nombres(tabla)
    for metrica in tabla["metrics"]:
        expr = _LITERAL.sub("''", str(metrica["expr"]))
        for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", expr):
            arriba = token.upper()
            assert arriba in nombres or arriba in _PALABRAS_SQL, f"{metrica['name']} cita {token}, que no es un hecho ni una dimensión"
            assert not token.startswith("_"), f"{metrica['name']} cita la columna física {token}; use el hecho PCT_*"


def test_cada_consulta_verificada_solo_usa_nombres_conocidos(modelo: dict, tabla: dict) -> None:
    nombres = _nombres(tabla)
    for consulta in modelo["verified_queries"]:
        sql = _LITERAL.sub("''", consulta["sql"])
        alias = {a.upper() for a in re.findall(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE)}
        for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", sql):
            arriba = token.upper()
            assert arriba in nombres or arriba in alias or arriba in _PALABRAS_SQL, (
                f"{consulta['name']} cita «{token}», que no existe en el modelo"
            )
        assert consulta.get("verified_at") and consulta.get("verified_by")


def test_cada_pregunta_sugerida_tiene_su_consulta_verificada(modelo: dict) -> None:
    preguntas = {consulta["question"].strip() for consulta in modelo["verified_queries"]}
    faltantes = [s["texto"] for s in IA_PREGUNTAS_SUGERIDAS if s["texto"].strip() not in preguntas]
    assert not faltantes, "Sugeridas sin consulta verificada (Analyst tardará más y acertará menos): " + " | ".join(faltantes)
    for consulta in modelo["verified_queries"]:
        if consulta["question"].strip() in {s["texto"].strip() for s in IA_PREGUNTAS_SUGERIDAS}:
            assert consulta.get("use_as_onboarding_question") is True, consulta["name"]


def test_los_listados_estan_acotados_y_no_traen_contacto_sin_pedirlo(modelo: dict) -> None:
    for consulta in modelo["verified_queries"]:
        sql = consulta["sql"].upper()
        pregunta = consulta["question"].lower()
        es_listado = re.search(r"\bSELECT\s+NIT\b", sql) and "COUNT(" not in sql.split("FROM")[0]
        if es_listado and "ficha" not in pregunta:
            assert "LIMIT" in sql, f"{consulta['name']} es un listado sin LIMIT"
        columnas_select = sql.split("FROM")[0]
        contacto = [c for c in _CONTACTO if re.search(rf"\b{c}\b", columnas_select)]
        pide = any(p in pregunta for p in ("correo", "teléfono", "telefono", "dirección", "direccion", "representante", "ficha", "contacto"))
        assert not contacto or pide, f"{consulta['name']} trae {contacto} sin que la pregunta lo pida"


def test_no_quedan_dimensiones_declaradas_inutiles_ni_cadena_ambigua(tabla: dict) -> None:
    nombres = {d["name"] for d in tabla["dimensions"]}
    for inutil in ("CIIU_3", "CIIU_4", "MUNICIPIO_BASE_MUNICIPIOS", "DEPARTAMENTO_BASE_MUNICIPIOS"):
        assert inutil not in nombres, inutil
    assert "CADENA" not in nombres and "CADENA_EXPORTADA" in nombres
    exportada = next(d for d in tabla["dimensions"] if d["name"] == "CADENA_EXPORTADA")
    assert "cadena" not in [s.strip() for s in exportada["synonyms"]]
    assert exportada["expr"] == "CADENA"


def test_los_nit_de_ejemplo_y_el_ano_por_defecto_estan_alineados(modelo: dict, tabla: dict) -> None:
    nit = next(d for d in tabla["dimensions"] if d["name"] == "NIT")
    assert nit["sample_values"] == NITS_EJEMPLO
    ficha = next(c for c in modelo["verified_queries"] if c["name"] == "ficha_empresa_por_nit")
    assert NITS_EJEMPLO[0] in ficha["question"] and NITS_EJEMPLO[0] in ficha["sql"]
    assert "2025" in modelo["custom_instructions"] and "CADENA_EXPORTADA" in modelo["custom_instructions"]
    # 2024 puede aparecer en una serie por año, nunca como el año por defecto de un total o un orden.
    sqls = " ".join(c["sql"].upper() for c in modelo["verified_queries"])
    assert "SUM(EXPO_2024)" not in sqls and "ORDER BY EXPO_2024" not in sqls

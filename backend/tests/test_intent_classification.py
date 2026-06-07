"""
test_intent_classification.py — Tests del clasificador de intención de Chuwi.

El clasificador es keyword-based, 0 tokens, y tiene que cubrir los flujos
más comunes que usará el encargado de tienda en la demo.

Flujos cubiertos:
- registrar_donacion: "donar", "banco de alimentos", "quiero donar"
- registrar_merma: "tiré", "se echó a perder", "está malo"
- pedir_ruta: "ruta", "dame la ruta", "iniciar ruta"
- pedir_brief: "brief", "resumen del día", "cómo estamos"
- completar_accion: "listo", "hecho", "ya está"
- consulta_estado: "críticos", "cuántos", "pendientes"
- configuracion: "ayuda", "qué puedes hacer", "menú"
- pregunta_libre: fallback para todo lo demás
"""
from __future__ import annotations

import pytest


@pytest.fixture
def classify():
    # Importa desde el módulo dedicado — chuwi.py re-exporta para compatibilidad
    from backend.core.chuwi_intent import _classify_intent
    return _classify_intent


# ── registrar_donacion ────────────────────────────────────────────────────────

class TestIntentDonacion:

    def test_donar(self, classify):
        assert classify("quiero donar estas manzanas") == "registrar_donacion"

    def test_banco_alimentos(self, classify):
        assert classify("lo mandamos al banco de alimentos") == "registrar_donacion"

    def test_lo_donamos(self, classify):
        assert classify("¿lo donamos?") == "registrar_donacion"

    def test_donacion_accentuated(self, classify):
        assert classify("procesamos una donación hoy") == "registrar_donacion"

    def test_ong(self, classify):
        assert classify("mandamos a una ong local") == "registrar_donacion"


# ── registrar_merma ───────────────────────────────────────────────────────────

class TestIntentMerma:

    def test_tirar_esto(self, classify):
        assert classify("hay que tirar esto") == "registrar_merma"

    def test_caducado(self, classify):
        assert classify("el yogur ha caducado") == "registrar_merma"

    def test_echo_a_perder(self, classify):
        assert classify("la leche se echó a perder") == "registrar_merma"

    def test_en_mal_estado(self, classify):
        assert classify("el pollo está en mal estado") == "registrar_merma"

    def test_ya_no_sirve(self, classify):
        assert classify("ya no sirve, tíralo") == "registrar_merma"


# ── pedir_ruta ────────────────────────────────────────────────────────────────

class TestIntentRuta:

    def test_iniciar_ruta(self, classify):
        assert classify("iniciar ruta por la tienda") == "pedir_ruta"

    def test_dame_la_ruta(self, classify):
        assert classify("dame la ruta de hoy") == "pedir_ruta"

    def test_modo_ruta(self, classify):
        assert classify("quiero modo ruta") == "pedir_ruta"

    def test_ruta_simple(self, classify):
        assert classify("ruta") == "pedir_ruta"


# ── pedir_brief ───────────────────────────────────────────────────────────────

class TestIntentBrief:

    def test_brief(self, classify):
        assert classify("dame el brief") == "pedir_brief"

    def test_resumen_del_dia(self, classify):
        assert classify("resumen del día") == "pedir_brief"

    def test_como_estamos(self, classify):
        assert classify("cómo estamos hoy") == "pedir_brief"

    def test_situacion_de_hoy(self, classify):
        assert classify("situación de hoy") == "pedir_brief"

    def test_generar_brief(self, classify):
        assert classify("generar brief ahora") == "pedir_brief"


# ── completar_accion ──────────────────────────────────────────────────────────

class TestIntentCompletar:

    def test_listo(self, classify):
        assert classify("ya está listo") == "completar_accion"

    def test_hecho(self, classify):
        assert classify("hecho, siguiente") == "completar_accion"

    def test_lo_hice(self, classify):
        assert classify("lo hice hace un momento") == "completar_accion"

    def test_termine(self, classify):
        assert classify("terminé con las manzanas") == "completar_accion"


# ── consulta_estado ───────────────────────────────────────────────────────────

class TestIntentEstado:

    def test_criticos(self, classify):
        assert classify("cuántos críticos hay ahora") == "consulta_estado"

    def test_pendientes(self, classify):
        assert classify("qué pendientes tenemos") == "consulta_estado"

    def test_cuantos_lotes(self, classify):
        assert classify("cuántos lotes vencen esta semana") == "consulta_estado"

    def test_que_caduca(self, classify):
        assert classify("qué caduca mañana") == "consulta_estado"

    def test_urgentes(self, classify):
        assert classify("hay algo urgente") == "consulta_estado"


# ── configuracion ─────────────────────────────────────────────────────────────

class TestIntentConfiguracion:

    def test_ayuda(self, classify):
        assert classify("ayuda") == "configuracion"

    def test_que_puedes_hacer(self, classify):
        assert classify("qué puedes hacer") == "configuracion"

    def test_comandos(self, classify):
        assert classify("comandos disponibles") == "configuracion"

    def test_menu(self, classify):
        assert classify("menú") == "configuracion"


# ── pregunta_libre (fallback) ─────────────────────────────────────────────────

class TestIntentFallback:

    def test_generic_question(self, classify):
        assert classify("¿cuánto cuesta poner una balda nueva?") == "pregunta_libre"

    def test_empty_string(self, classify):
        assert classify("") == "pregunta_libre"

    def test_unrelated(self, classify):
        assert classify("el proveedor llega a las 10") == "pregunta_libre"

    def test_greeting(self, classify):
        assert classify("buenos días") == "pregunta_libre"

    def test_numbers_only(self, classify):
        assert classify("123456") == "pregunta_libre"


# ── Propiedades del clasificador ──────────────────────────────────────────────

class TestIntentProperties:

    def test_case_insensitive(self, classify):
        assert classify("BRIEF DEL DÍA") == classify("brief del día")

    def test_returns_string(self, classify):
        result = classify("cualquier texto")
        assert isinstance(result, str)

    def test_known_intents_set(self, classify):
        known = {
            "registrar_donacion", "registrar_merma", "pedir_ruta",
            "pedir_brief", "completar_accion", "crear_accion",
            "consulta_estado", "configuracion", "pregunta_libre",
        }
        for text in ["donar", "ruta", "brief", "listo", "criticos", "ayuda", "hola"]:
            result = classify(text)
            assert result in known, f"'{text}' → '{result}' no es un intent conocido"

"""Evals del invariante duro "Correo: JAMÁS borra" (CLAUDE.md). Puros: sin red — la API de
Gmail/Outlook se mockea; lo que se prueba es que el código de Donna nunca llama a una ruta
de borrado, y que el archivado (etiqueta/carpeta) enruta bien y degrada elegante."""
import asyncio
import re
from pathlib import Path

import pytest

from core import email_gmail, email_outlook

_SRC_GMAIL = Path(email_gmail.__file__).read_text(encoding="utf-8")
_SRC_OUTLOOK = Path(email_outlook.__file__).read_text(encoding="utf-8")


# ───────────────────────── Assert estático: ninguna ruta de borrado sobrevive ─────────────────────────

def test_gmail_no_llama_trash():
    assert ".trash(" not in _SRC_GMAIL
    assert re.search(r"\.delete\(", _SRC_GMAIL) is None


def test_outlook_no_llama_delete():
    assert "requests.delete(" not in _SRC_OUTLOOK


# ───────────────────────── Gmail: label get-or-create + archivar ─────────────────────────

class _FakeExec:
    def __init__(self, result):
        self._result = result

    def execute(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeLabels:
    def __init__(self, existentes):
        self._existentes = existentes
        self.creadas = []

    def list(self, userId):
        return _FakeExec({"labels": self._existentes})

    def create(self, userId, body):
        self.creadas.append(body)
        return _FakeExec({"id": "LBL_NUEVA", "name": body["name"]})


class _FakeMessages:
    def __init__(self, fallar_ids=()):
        self.modificados = []
        self._fallar = set(fallar_ids)

    def modify(self, userId, id, body):
        if id in self._fallar:
            return _FakeExec(RuntimeError("boom"))
        self.modificados.append((id, body))
        return _FakeExec({"id": id})


class _FakeUsers:
    def __init__(self, labels, messages):
        self._labels, self._messages = labels, messages

    def labels(self):
        return self._labels

    def messages(self):
        return self._messages


class _FakeSvc:
    def __init__(self, labels, messages):
        self._users = _FakeUsers(labels, messages)

    def users(self):
        return self._users


def test_gmail_crea_la_etiqueta_si_no_existe(monkeypatch):
    monkeypatch.setattr(email_gmail, "_label_archivo_id", None)
    labels, messages = _FakeLabels([]), _FakeMessages()
    svc = _FakeSvc(labels, messages)
    label_id = email_gmail._obtener_o_crear_label_archivo(svc)
    assert label_id == "LBL_NUEVA"
    assert labels.creadas[0]["name"] == "Donna/Archivado"


def test_gmail_reusa_la_etiqueta_si_ya_existe(monkeypatch):
    monkeypatch.setattr(email_gmail, "_label_archivo_id", None)
    labels = _FakeLabels([{"id": "LBL_VIEJA", "name": "Donna/Archivado"}])
    svc = _FakeSvc(labels, _FakeMessages())
    label_id = email_gmail._obtener_o_crear_label_archivo(svc)
    assert label_id == "LBL_VIEJA"
    assert labels.creadas == []  # no crea una nueva si ya existe


def test_gmail_archivar_quita_inbox_y_agrega_la_etiqueta(monkeypatch):
    monkeypatch.setattr(email_gmail, "_label_archivo_id", None)
    monkeypatch.setattr(email_gmail, "disponible", lambda: True)
    labels = _FakeLabels([{"id": "LBL1", "name": "Donna/Archivado"}])
    messages = _FakeMessages()
    monkeypatch.setattr(email_gmail, "_svc", lambda: _FakeSvc(labels, messages))
    n = asyncio.run(email_gmail.archivar(["m1", "m2"]))
    assert n == 2
    for mid, body in messages.modificados:
        assert body["removeLabelIds"] == ["INBOX"]
        assert body["addLabelIds"] == ["LBL1"]


def test_gmail_archivar_degrada_si_un_mensaje_falla(monkeypatch):
    monkeypatch.setattr(email_gmail, "_label_archivo_id", None)
    monkeypatch.setattr(email_gmail, "disponible", lambda: True)
    labels = _FakeLabels([{"id": "LBL1", "name": "Donna/Archivado"}])
    messages = _FakeMessages(fallar_ids={"m2"})
    monkeypatch.setattr(email_gmail, "_svc", lambda: _FakeSvc(labels, messages))
    n = asyncio.run(email_gmail.archivar(["m1", "m2", "m3"]))
    assert n == 2  # m2 falló pero no rompe el resto (degradación elegante)


def test_gmail_archivar_sin_ids_no_llama_a_nada(monkeypatch):
    monkeypatch.setattr(email_gmail, "disponible", lambda: True)
    n = asyncio.run(email_gmail.archivar([]))
    assert n == 0


def test_gmail_archivar_no_disponible_no_llama_a_nada(monkeypatch):
    monkeypatch.setattr(email_gmail, "disponible", lambda: False)
    n = asyncio.run(email_gmail.archivar(["m1"]))
    assert n == 0


# ───────────────────────── Outlook: no disponible → degrada sin tocar la red ─────────────────────────

def test_outlook_archivar_no_disponible_no_llama_a_nada(monkeypatch):
    monkeypatch.setattr(email_outlook, "disponible", lambda: False)
    n = asyncio.run(email_outlook.archivar(["m1"]))
    assert n == 0

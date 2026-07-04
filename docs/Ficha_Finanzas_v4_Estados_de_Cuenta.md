# Ficha — Finanzas v4: lectura de estados de cuenta del banco (PDF con contraseña) → faro de deuda vivo + reconciliación

**Fecha:** 2026-07-04 · **Para:** una sesión de Claude Code que lo ejecute después.
**Módulo:** Finanzas (`fin_`) · extensión v4 (sobre v1 registro + v2 intención/metas + v3 detalle ítem-a-ítem).

## Decisiones de Nico que fijan el alcance (no reabrir)

- **El PDF alimenta el FARO de deuda + una RECONCILIACIÓN. NO re-ingiere transacciones.** El estado de cuenta lista todos los movimientos del mes, pero Donna ya captura cada compra desde las notificaciones sueltas (`ingerir_gastos_email`). Meter el PDF línea por línea = doble conteo. El PDF aporta lo que las notificaciones no pueden: la **deuda real con línea/cupo/interés** (hoy estática) y un **cruce** contra lo capturado para marcar faltantes.
- **La contraseña que abre el PDF vive en `.env`, jamás en el Sheet.** Es la clave del *documento*, no la del banco.
- **Donna nunca usa las credenciales de login del banco.** El PDF ya llega al correo; ella lo lee del mail, no inicia sesión en el sitio. Un PDF cifrado no mueve plata.
- **Los invariantes duros de `CLAUDE.md` mandan:** correo jamás borra (descargar un adjunto no borra); Sheets nunca se escribe sin OK de Nico (el faro y la reconciliación se confirman con toque, igual que el digest); del correo solo se mira lo justo (el worker destila deuda+movimientos, no vuelca el PDF entero al LLM); `.env` nunca al control de versiones.

**Prerequisito:** leer `CLAUDE.md` completo. Idealmente la Fase 0 (bugs de `Plan_Reparacion_Bugs_y_Datos.md`) cerrada, pero esta ficha no depende de esos fixes (toca finanzas, no recordatorios/proyectos).

**Reglas de ejecución (idénticas a las otras fichas):** rama propia `feat/finanzas-estados-cuenta`; commit por paso, en español, concreto; `python -m pytest tests/ -q` verde con los tests nuevos (patrón de mocking de `tests/test_finanzas.py` / `tests/test_salud.py`: monkeypatch sobre `core.sheets` y sobre el cliente Anthropic); invariantes intactos.

---

## Qué existe hoy vs. qué falta (verificado en el código, 2026-07-04)

**Existe y se reutiliza:**
- Cliente Gmail (`core/email_gmail.py`): lee correos, scope `gmail.modify` (ya cubre leer adjuntos — **no hay que re-autorizar**), `buscar()` con `format="full"`, `archivar()` (jamás borra).
- Ingesta de gasto por correo (`modules/finanzas.py:603 ingerir_gastos_email` → `:571 procesar_correo`): determinista primero, LLM al residuo, buffer del día, confirmación en el digest.
- Faro de deuda (`modules/finanzas.py:897 estado_deuda`): lee `Tarjetas y Deuda` **B4:B8** en un request. Son **fórmulas** que la planilla calcula.
- Correlación anti-doble-conteo (`modules/finanzas.py:841 fin_aplicar_correlacion`): aparea foto/dictado con su cargo del correo por monto+fecha. La reconciliación reutiliza esta filosofía.
- Digest con toque (`core/flows.py:71 _teclado_digest`, `:290 digest:aceptar` → `finanzas.confirmar_digest`). La reconciliación clona este patrón con prefijo propio.
- Helpers `_num` / `clp` (`modules/finanzas.py:120,132`) para pesos chilenos.

**No existe (hay que construirlo):**
1. **Descargar adjuntos.** `email_gmail.py` solo extrae `text/plain`/`text/html` (`_texto_de_payload`, línea 65); ignora los PDF. Bajar el archivo es otra llamada (`users().messages().attachments().get(...)`).
2. **Leer PDF cifrado.** Cero manejo de PDF en el repo. **Ninguna librería de PDF está instalada** (verificado: `pypdf`/`pdfplumber`/`pikepdf`/`fitz` faltan). Hay que agregar dependencia.
3. **Escribir el faro desde el PDF** (celdas-input, con toque) y **reconciliar** contra `Transacciones`.

---

## El mapa exacto de `Tarjetas y Deuda` (de `Donna_Canonico.xlsx`) — el ancla del diseño

El faro (B4:B8) son **fórmulas**; Donna las LEE, jamás las escribe. Las fórmulas suman **celdas-input por tarjeta** que hoy Nico llena a mano. **El PDF debe actualizar esas celdas-input** → el faro se recalcula solo. Esto respeta la arquitectura de fórmulas (igual que `setup_sheets.py`, que a propósito no toca esta hoja).

**FARO (fórmulas, solo lectura):**
| Celda | Fórmula | Qué es |
|---|---|---|
| B4 | `=B29+B40+B44` | Deuda total real (tarjetas + línea) |
| B5 | `=B25+B37+B45` | Intereses muertos del mes |
| B6 | `=(B29+B40+B44)/(B28+B39+B43)` | % utilización |
| B7 | `=IF(B6>0.7,"🔴",…)` | Semáforo |
| B8 | `=B27+B38+B45` | Total a pagar este mes |

**Celdas-input que el PDF actualiza (con OK de Nico):**

| Tarjeta | Celda | Campo | Fuente en el estado de cuenta |
|---|---|---|---|
| **🏦 Banco de Chile** (rows 19-29) | B21 | Deuda rotativa actual | saldo rotativo / deuda no facturada |
| | B22 | Pago este mes | pago mínimo o realizado |
| | B23 | Mantención mensual | comisión de mantención |
| | B24 | Total cuotas del mes | suma de cuotas facturadas |
| | B28 | Cupo total | línea de crédito de la tarjeta |
| | B29 | **Deuda total tarjeta** | deuda total facturada + no facturada |
| | *B20* | Tasa mensual (rara vez cambia) | tasa rotativa |
| **📱 Mach** (rows 31-40) | B33,B34,B35,B36,B39,B40 | (mismos campos que BCh) | estado de cuenta Mach |
| **🏦 Línea de crédito** (rows 42-47) | B44 | Monto utilizado | saldo usado de la línea |
| | B45 | Interés mensual que pagas | interés de la línea |

**Celdas que NO se tocan** (son fórmulas derivadas): B25, B26, B27, B37, B38, B46, B47, más el faro B4:B8.

**Nota débito vs. crédito:** esta hoja es **solo crédito + línea**. El estado de cuenta de la **cuenta corriente / débito** (Banco de Chile) es de *movimientos y saldo*, no de deuda → ese PDF alimenta **solo la reconciliación** (Parte D), no el faro. Cuando Nico dice "tarjetas de crédito y débito": el crédito va al faro **y** a reconciliación; el débito va **solo** a reconciliación.

---

## Arquitectura: 4 piezas (contrato de módulo — trabajo pesado aislado, §3)

```
correo (PDF adjunto)  →  [A] descarga  →  [B] worker aislado: descifra + destila
                                                   │
                          señal destilada {por_tarjeta:{...}, movimientos:[...]}
                                                   ▼
                         [C] toque → escribe celdas-input del faro   (Sheets con OK)
                         [D] toque → reconcilia movimientos vs Transacciones
```

---

## PARTE A — Descargar el PDF adjunto (Gmail)

**Nuevo en `core/email_gmail.py`:**

1. `_normalizar` (línea 88) hoy tira los adjuntos. Agregar a la salida una lista `adjuntos: [{filename, mime, attachment_id, size}]` recorriendo `payload.parts` donde `part["filename"]` y `part["body"].get("attachmentId")` existan y el mime sea `application/pdf` (o `octet-stream` con `.pdf`).
2. Nueva función:
   ```python
   async def descargar_adjunto(message_id: str, attachment_id: str) -> bytes | None:
       """Baja el binario de un adjunto. Scope gmail.modify ya lo permite (lectura).
       Degrada a None si falla (contrato §4)."""
       # svc.users().messages().attachments().get(userId="me", messageId=message_id, id=attachment_id)
       # → base64.urlsafe_b64decode(res["data"])
   ```
3. Nueva búsqueda dedicada de estados de cuenta (no ensuciar `obtener_gastos`):
   ```python
   async def obtener_estados_cuenta(query: str, max_n: int = 10) -> list[dict]:
       # q = f"({query}) has:attachment filename:pdf newer_than:40d"
   ```
   `query` = remitentes de estados de cuenta (ver registro en Parte B).

**Tests** (`tests/test_email_gmail.py`, mock del service Gmail): (a) `_normalizar` de un mensaje con parte PDF llena `adjuntos` con `attachment_id`; (b) `descargar_adjunto` decodifica el base64url; (c) Gmail caído → `descargar_adjunto` devuelve None sin lanzar.
**Commit:** `feat(correo): descarga de adjuntos PDF (attachments.get) sin re-autorizar scope`.

---

## PARTE B — Worker aislado que lee el PDF (descifra + destila)

Módulo nuevo `modules/estados_cuenta.py` (prefijo `fin_` — es parte de Finanzas, no un módulo con tools propios nuevos salvo `fin_leer_estados`). Corre **aislado**: recibe bytes + clave, devuelve **señal destilada**, no vuelca el PDF crudo hacia arriba.

### Dependencia (elegir en el paso de decisiones)

- **Recomendado:** `pypdf` (BSD, wheel puro, sin binario externo — importa para Railway) para **descifrar + extraer texto**, + `pdfplumber` (MIT) para **tablas** cuando el texto plano no basta. Determinista, cero tokens.
- **Fallback para PDF escaneado/imagen:** `PyMuPDF`/`fitz` para renderizar la página a PNG → reusar el extractor **Vision** que ya existe (`procesar_foto`). ⚠️ PyMuPDF es **AGPL** — irrelevante para un bot personal sin distribución, pero queda anotado. Filosofía idéntica al resto: **determinista primero, LLM/Vision al residuo**.

### Interfaz

```python
# Registro de emisores de estados de cuenta (mismo patrón que SENDERS en finanzas.py)
EMISORES = [
    {"nombre": "Banco de Chile (crédito)", "dominios": ["bancochile.cl", "bancochile.com"],
     "tipo": "credito", "tarjeta": "bch", "password_key": "bch"},
    {"nombre": "Mach", "dominios": ["mach.cl"], "tipo": "credito", "tarjeta": "mach", "password_key": "mach"},
    {"nombre": "Banco de Chile (cuenta corriente)", "dominios": ["bancochile.cl"],
     "tipo": "debito", "tarjeta": None, "password_key": "bch"},
]

async def leer_estado(pdf_bytes: bytes, emisor: dict) -> dict | None:
    """Descifra con la clave de settings (password_key) y destila. Devuelve:
    {tarjeta:'bch'|'mach'|None, tipo:'credito'|'debito', periodo:'2026-06',
     por_tarjeta: {deuda_total, deuda_rotativa, total_cuotas, mantencion, cupo,
                   pago_mes, interes} | None,   # None para débito
     movimientos: [{fecha, comercio, monto}], total_movimientos: int}
    Degrada a None si la clave no abre el PDF (→ incidente, ver más abajo)."""

def _password_de(emisor: dict) -> str:
    """Clave del PDF desde settings (nunca del Sheet). Si el banco usa el RUT,
    puede derivarse del perfil (memory.get_perfil()['rut']) en vez de una env var."""
```

### Descifrado + extracción

1. **Descifrar:** `reader = pypdf.PdfReader(io.BytesIO(pdf_bytes)); if reader.is_encrypted: reader.decrypt(clave)`. Si `decrypt` devuelve 0 (clave mala) → **no** reintentar en loop; registrar y salir (ver "Cuando la clave falla").
2. **Crédito → `por_tarjeta`:** parser determinista por banco (regex sobre el texto: "Deuda total facturada", "Cupo total", "Monto mínimo", "Comisión mantención", etc.). Cada banco su función; el residuo cae a Vision.
3. **Movimientos:** `pdfplumber` extrae la tabla de movimientos → `[{fecha, comercio, monto}]`. Solo para la reconciliación (Parte D), no se escriben como transacciones.
4. **Aislamiento:** la respuesta es la señal destilada; el texto crudo del PDF nunca sube al brain ni se guarda entero.

**Cuando la clave falla o el formato no se reconoce:** Donna avisa en carácter y deja el incidente para Claude Code (engancha con la ficha de Autodiagnóstico, tabla `incidentes`, tipo `api_externa`/`tool_excepcion`) — nunca reintenta con distintas claves ni traga el error en silencio. Texto ejemplo: «No pude abrir el estado de cuenta de {banco} — la clave no calza o cambió el formato. Revísalo y lo vemos.»

**Tests** (`tests/test_estados_cuenta.py`, con un PDF cifrado de fixture mínimo generado en el test): (a) PDF cifrado + clave correcta → `leer_estado` devuelve `por_tarjeta` poblado; (b) clave incorrecta → None sin loop de reintentos; (c) parser BCh sobre texto de muestra extrae deuda/cupo/interés correctos; (d) `movimientos` sale como lista de dicts; (e) débito → `por_tarjeta is None`, `movimientos` poblado.
**Commit:** `feat(finanzas): worker aislado que descifra y destila estados de cuenta (deuda + movimientos)`.

---

## PARTE C — Escribir el faro (celdas-input) con toque

**En `modules/finanzas.py`:**

1. Mapa celdas-input (constante, del ancla de arriba):
   ```python
   CELDAS_INPUT_TARJETA = {
       "bch":  {"deuda_rotativa": "B21", "pago_mes": "B22", "mantencion": "B23",
                "total_cuotas": "B24", "cupo": "B28", "deuda_total": "B29"},
       "mach": {"deuda_rotativa": "B33", "pago_mes": "B34", "mantencion": "B35",
                "total_cuotas": "B36", "cupo": "B39", "deuda_total": "B40"},
       "linea":{"monto_utilizado": "B44", "interes": "B45"},
   }
   ```
2. `async def preview_faro(destilado: dict) -> dict`: arma el **antes→después** de cada celda que cambiaría (lee el valor actual con `sheets.get_rows`, compara con lo del PDF), para mostrárselo a Nico. No escribe nada.
3. `async def aplicar_faro(destilado: dict) -> int`: **solo tras el toque** — `sheets.set_cell(HOJA_TARJETAS, fila, col, valor, sheet_id=sheets.fin_id())` por celda-input cambiada. **Nunca** escribe B4:B8 (fórmulas). Devuelve cuántas celdas actualizó.
4. Tras aplicar, el faro se recalcula solo; `estado_deuda()` lo lee como siempre y `sembrar_espina()` (línea 977) actualiza el perfil de deuda en Supabase con el dato nuevo — **sin cambios**, ya está enganchado.

**En `core/flows.py`** (patrón `_teclado_digest`/`enviar_digest`/`on_callback`):
5. `enviar_preview_faro(bot, chat_id, destilado)`: mensaje con el antes→después + teclado `✅ Actualizar deuda` (`callback_data="faro:aplicar:{periodo}"`) / `✏️ Corregir` / `Descartar`. Guardar el destilado en `bot_data` con expiración (o mejor, en Supabase con id corto y pasar el id en el callback — sobrevive reinicios de Railway, patrón preferido en `Plan_Reparacion` C6).
6. `on_callback` (línea 234): rama `faro:aplicar` → `finanzas.aplicar_faro(...)` → responder en carácter con el faro nuevo (`formatear_deuda(await estado_deuda())`).

**Invariante:** la escritura ocurre **solo** tras el toque de Nico. ✓

**Tests:** (a) `preview_faro` no escribe (assert `set_cell` no llamado); (b) `aplicar_faro` escribe exactamente las celdas-input cambiadas y **ninguna** de B4:B8; (c) mach en cero no sobre-escribe con basura si el PDF no trae Mach (saltar tarjetas ausentes en el destilado); (d) callback `faro:aplicar` llama `aplicar_faro` una vez.
**Commit:** `feat(finanzas): el estado de cuenta actualiza las celdas-input del faro con toque (fórmulas intactas)`.

---

## PARTE D — Reconciliación contra `Transacciones` (sin doble conteo)

**En `modules/finanzas.py`:**

1. `async def reconciliar(movimientos: list[dict], periodo: str) -> dict`: cruza los movimientos del PDF contra las transacciones ya registradas del período, por **monto + fecha (±1-2 días) + comercio fuzzy** — reusar la lógica de `_id_unico` (línea 137) y el matching de `fin_aplicar_correlacion` (línea 841). Devuelve:
   ```python
   {"calzan": int,               # movimientos del PDF que ya están en Transacciones
    "faltan": [{fecha, comercio, monto}],   # en el PDF, NO en Transacciones → Donna los perdió
    "sobran": [{...}]}            # en Transacciones, NO en el PDF (posible duplicado/error)
   ```
2. **Qué hace con los `faltan`:** NO los escribe solo. Los ofrece en un toque *"el estado de cuenta trae N movimientos que no tengo — ¿los agrego?"* → cada uno pasa por el buffer/digest normal (con su OK). Así el PDF sí puede recuperar un gasto que la notificación no capturó, pero siempre con confirmación. Los `sobran` se marcan como aviso ("revisa este, puede estar duplicado"), nunca se borran solos.
3. Señal destilada hacia arriba (contrato §2): una frase — *"Cuadré 18/20 movimientos con el estado de cuenta; 2 me faltaban ($X), 0 sobran."*

**Tests:** (a) movimiento del PDF que ya existe → `calzan`; (b) movimiento nuevo → `faltan`; (c) tolerancia de fecha ±2 días calza; (d) `faltan` NO se escribe automáticamente (assert append no llamado sin toque).
**Commit:** `feat(finanzas): reconciliación estado de cuenta ↔ Transacciones (faltan/sobran, sin auto-escritura)`.

---

## Seguridad de la contraseña (sección propia — importa)

- **Dónde vive:** `.env` (nunca el Sheet, nunca el repo). Nuevos settings en `config.py`:
  ```python
  banco_pdf_password_bch: str = ""     # clave del PDF de Banco de Chile
  banco_pdf_password_mach: str = ""    # clave del PDF de Mach
  # (o un solo dict/JSON si prefieres: banco_pdf_passwords: str = "" → parsear)
  ```
- **Muchos bancos chilenos** protegen el PDF con el **RUT** (sin puntos ni dígito verificador) o los últimos 4 dígitos de la tarjeta. El RUT ya está en el perfil (`memory.get_perfil()['rut']`) → para esos bancos `_password_de` puede derivarla y quizá no haga falta env var. **Decisión de Nico por banco.**
- **Nunca se loguea, nunca sube al LLM.** La clave solo se usa local para `reader.decrypt(clave)`. Si hay fallback Vision, lo que sube es la imagen ya descifrada, no la clave.
- **Donna no tiene, ni pide, las credenciales de login del banco.** Fuera de alcance por diseño.

---

## Datos y configuración

- **Sin migración de Supabase obligatoria.** Opcional: tabla `estados_cuenta` (id, periodo, banco, deuda_total, leido_en) para historial de deuda mes a mes (tendencia) — dejar para un v4.1 si Nico lo quiere.
- **`.env` nuevo:** las claves de PDF (arriba). Documentar en el README de setup, **no** commitear valores.
- **Dependencia nueva:** `pypdf` (+ `pdfplumber`; `PyMuPDF` solo si hay PDF escaneado). Agregar a `requirements.txt` y verificar que Railway las instale (wheels puros, sin apt).
- **Schedule:** los estados de cuenta llegan mensual. Enganchar `fin_leer_estados` en el sweep de correo existente detectando el emisor + `has:attachment`, o un job mensual (día ~5) en `core/scheduler.py`. Sugerido: oportunista en el sweep (cuando llega el mail), con tope de no re-procesar el mismo `message_id` (reusar `memory.correo_visto`).

---

## Invariantes — checklist de cumplimiento

- ✅ **Correo jamás borra:** solo `attachments.get` (lectura). El mail queda intacto.
- ✅ **Sheets nunca sin OK:** faro (Parte C) y faltantes de reconciliación (Parte D) van por toque.
- ✅ **Solo mira lo justo:** el worker destila deuda+movimientos; el PDF crudo no sube ni se guarda entero.
- ✅ **Fórmulas intactas:** Donna escribe celdas-input, jamás B4:B8.
- ✅ **Degrada elegante:** Gmail/PDF/clave que falla → None + incidente, no rompe el cierre.
- ✅ **`.env` fuera del VCS.**
- ✅ **Determinista primero, LLM al residuo:** parser por banco antes que Vision.

---

## Orden de ejecución y commits

1. `feat(correo): descarga de adjuntos PDF (attachments.get)` — Parte A + tests.
2. `feat(finanzas): worker aislado que descifra y destila estados de cuenta` — Parte B + dependencia + tests.
3. `feat(finanzas): el estado de cuenta actualiza las celdas-input del faro con toque` — Parte C + tests.
4. `feat(finanzas): reconciliación estado de cuenta ↔ Transacciones` — Parte D + tests.
5. `feat(finanzas): fin_leer_estados enganchado al sweep de correo + schedule` — cierre + tool registrada en el brain.

**Gate de salida:** `pytest tests/ -q` verde · un PDF real de prueba (uno de los tuyos) descifrado → preview del faro con antes→después → toque → faro recalculado correcto · reconciliación de un mes real da faltan/sobran coherentes · smoke por Telegram.

## Decisiones que quedan para Nico (no las tome la IA ejecutora)

- **Clave del PDF por banco:** ¿env var, o derivarla del RUT del perfil? (según lo que use cada banco).
- **Débito:** ¿qué cuenta corriente reconciliar, y su emisor exacto?
- **Dependencia PDF:** confirmar `pypdf`+`pdfplumber` (y si se acepta PyMuPDF/AGPL para el fallback de escaneados).
- **Trigger:** oportunista en el sweep vs. job mensual fijo.
- **Historial de deuda** (`estados_cuenta` en Supabase): ¿ahora o v4.1?

## Fuera de alcance (por diseño)

- Login al sitio del banco / scraping / mover plata. Donna solo lee el PDF que ya te llega.
- Re-ingesta de transacciones desde el PDF (evita doble conteo; las compras siguen entrando por notificación).
- Escribir las fórmulas del faro (B4:B8) — solo celdas-input.

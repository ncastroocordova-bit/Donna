# Alineación Donna — Sheet · Bot · Plan

> Documento único de verdad tras la sesión de consolidación.
> Regla base: **el plan v7 manda**; los Excels aportan formato/estructura; el bot (Donna.zip) se alinea a esto.

---

## 1. El canon (decisiones de esta sesión)

Estas decisiones son ahora la verdad. Cualquier rediseño futuro se mide contra esto.

1. **Un solo workbook "Donna"** = Vida_v6 + Finanzas_vigente unificados (ya generado: `Donna_Canonico.xlsx`).
2. **Capa de productividad SIMPLE**: Tareas (sueltas) + Proyectos + Semanal (rachas). Sin log de tiempo diario.
3. **Tiempo por frente** se captura por **reconciliación nocturna (opción 1, con delta más/igual/menos)** en el cierre — el brief queda intacto. Alimenta el Semanal.
4. **Factor de optimismo**: sobre el módulo de aprendizaje, Donna aprende tu ratio plan-vs-real por frente y te frena al planificar de más (corrección de la falacia de planificación, vía reference class forecasting).
5. **Escalera de recordatorios**: domingo (preview) + T-2 + T-0 (botón ✅Hecho) + insiste a diario solo si vence. Estado pendiente/hecho/pospuesto; tipo mensual/anual/única; posponer exige fecha concreta.
6. **Correo — triage en 3 buckets** (spam / importante / financiero). Importantes → resumen en el brief; financieros → digest. **Invariante: JAMÁS borra; solo etiqueta/archiva** (Donna/Archivado, recuperable).
7. **Correo dedicado** de finanzas: inbox nuevo al que se redirigen los bancos, con allowlist del inbox viejo en paralelo durante la migración.
8. **Extras**: Aprendizaje ON, Proactividad 12:00 ON, **Outlook OFF** (descartado), **Tiempo log diario OFF** (dormido, se promueve si el sistema lleva semanas vivo).
9. **Finanzas**: la deuda real incluye la **línea de crédito**. Faro: Deuda total real $2.028.091, Intereses muertos $48.236/mes.

---

## 2. Qué hay en Donna.zip

Repo real con git, más completo que el arranque F1. Inventario:

- **core/**: `brain` (carácter), `memory` (Supabase), `sheets`, `scheduler`, `voice` (Whisper), `agenda` (Google Calendar), `flows`, `correo` + `email_gmail` + `email_outlook`.
- **modules/**: `salud`, `finanzas`, `recordatorios`, `proyectos`, `tiempo`, `metas`, `aprendizaje`, `proactividad`, `spam`.
- **migrations/**: 001–011 (perfil, inferencias, compromisos, memoria, RLS, proyectos, aprendizaje, reconcile, harden, digest_jobs, correos).
- **prompts/**: `constitution`, `anchors`, `capacidades`.
- **tests/**: `casos.yaml`, `evals.py`. + `setup_sheets.py` (crea los tabs), `main.py`, `config.py`, `auth_email.py`.
- ⚠️ Trae `.env` y `credentials.json` (secretos): sácalos antes de subirlo a cualquier lado.

---

## 3. Auditoría de alineación

**Calza fuerte (ya alineado, sin acción):**
Diario · Transacciones · Categorías · faro de deuda (lectura) · digest nocturno · memoria (perfil/episódica/inferencias/compromisos) · voz · Vision · brief 8:00 / cierre 22:00 · inferencia validada · límites honestos · agenda Calendar · proactividad · aprendizaje.

**Va ADELANTE del plan (el bot ya trae de más):**
proyectos detallados · tiempo (log) · metas semanales · Outlook. Varias eran "fases futuras" en el plan. Decisión: tiempo y Outlook se apagan; proyectos se conserva simple.

**Va ATRÁS del canon (le falta lo de esta sesión):**
1. Recordatorios: tiene versión básica, no la escalera.
2. Correo: solo lee gasto + spam; no hace triage de 3 buckets ni resumen de importantes. **Manda spam a la papelera ("Borrar todo") — viola el invariante "jamás borra".**
3. Correo dedicado: no reflejado.
4. Reconciliación nocturna + factor de optimismo: no existen (scope nuevo).

**Choque de esquema (productividad):**
El bot espera `Proyectos + Tareas(=fases) + Tiempo + MetasSemanales`; el canon usa `Tareas(simples) + Proyectos + Semanal(rachas + tiempo-por-frente)`. Se resuelve a favor del canon simple.

---

## 4. Brechas para 100% (qué tocar en el bot)

Ordenadas por prioridad. El `Donna_Canonico.xlsx` ES el esquema objetivo.

1. **Recordatorios → escalera.** `modules/recordatorios.py` + esquema Recordatorios: añadir Estado, Posposiciones, tipo única; implementar domingo + T-2 + T-0 + vencido-insiste; botones ✅Hecho / Posponer (exige fecha).
2. **Correo → jamás borra + triage.** `modules/spam.py` + `core/correo.py`: cambiar papelera por etiqueta `Donna/Archivado`; añadir triage 3 buckets + resumen de importantes en el brief; tabla `remitentes` + reconciliación diaria; allowlist para la migración.
3. **Correo dedicado.** `config` + `core/email_gmail`: apuntar al inbox financiero nuevo; allowlist paralelo del viejo durante la transición.
4. **Reconciliación nocturna + factor de optimismo.** `core/scheduler` (flujo de cierre): leer bloques del Calendar, panel de toques hecho/no + delta, escribir en tab `Reconciliacion`; `modules/aprendizaje`: ratio por frente + aviso de "observador externo" al planificar. Alimenta tiempo-por-frente del Semanal.
5. **Productividad simple.** Apagar `modules/tiempo.py` (dormido); simplificar el tab `Tareas` (de fases a tareas sueltas); decidir si `metas.py` alimenta el Semanal o se pliega ahí.
6. **Outlook OFF.** Sacar `core/email_outlook.py` del path activo.
7. **Re-sincronizar esquema de hojas.** Actualizar `setup_sheets.py` para que calce con los tabs/headers del `Donna_Canonico.xlsx` (Recordatorios nuevo, Reconciliacion nuevo, Semanal con tiempo-por-frente + factor, Config con módulos ON/OFF).
8. **Faro con línea.** `modules/finanzas.py`: leer el headline "Deuda total real" (incluye línea), no solo el subtotal de tarjetas.

**Path recomendado:** extender el repo Donna.zip (es el más completo) en vez de reconstruir desde el arranque F1. El arranque era un andamio más delgado.

---

## 5. El Excel canónico generado

`Donna_Canonico.xlsx` — 13 hojas, fórmulas verificadas (0 errores):
📖 Léeme · Diario · Tareas · Proyectos · Recordatorios (escalera) · Reconciliacion (nuevo) · Semanal (tiempo-por-frente + factor) · ⚙️ Config (módulos ON/OFF) · Transacciones · Categorias (presupuesto único) · Tarjetas y Deuda (faro con línea) · Dashboard · Comparativo.

Las filas de Transacciones son ejemplos borrables. El Diario, Semanal y Reconciliacion nacen vacíos: crecen con tu racha.

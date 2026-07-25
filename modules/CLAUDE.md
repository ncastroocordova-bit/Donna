# modules/ — instrucciones locales

**El canon del proyecto vive en [`../CLAUDE.md`](../CLAUDE.md).** Claude Code ya lo carga; este
archivo NO lo repite. Hasta el 2026-07-24 sí lo repetía —una copia casi completa— y se desincronizó
en silencio: seguía anunciando el faro viejo ($2.028.091 / $48.236), no conocía la hoja `Saldos`,
la regla del RUT propio ni el canon de Finanzas v5, y mandaba a documentos ya archivados. **Si algo
de acá empieza a parecerse al canon, bórralo y deja el link.**

## El contrato de módulo

Está en el canon (`../CLAUDE.md` §Contrato de módulo) y es no negociable. Los cinco puntos en una
línea: **no tocas el núcleo · entregas señal destilada, no datos crudos · el trabajo pesado corre
aislado · degradas elegante · prefijo propio sin solapar tools.**

El que más se rompe en la práctica es el 4. Degradar elegante significa que si Sheets, Calendar,
Gmail o Supabase fallan, el módulo **responde igual sin esa pieza** y no corta la conversación —
no que atrape la excepción y devuelva algo falso. Un ejemplo bien hecho: `archivista.arc_guardar`
distingue "no tengo el cerebro conectado" de "no pude escribir ahora", y lo dice.

## Prefijos (uno por módulo, sin solapamiento)

| Prefijo | Módulo | Estado |
|---|---|---|
| `fin_` | `finanzas` + `estados_cuenta` | vivo |
| `sal_` | `salud` | vivo |
| `cmp_` | `compras` | Fase 1 viva · Fase 2 diferida |
| `rec_` | `recordatorios` (+ `core/agenda`) | parcial — el siguiente del roadmap |
| `cor_` | `correo` / `spam` | parcial |
| `prod_` | `proyectos` / reconciliación | parcial |
| `apr_` | `aprendizaje` | vivo (la espina) |
| `fam_` | `familia` | no existe todavía |
| `arc_` | `archivista` (escribe a Córtex) | vivo — fuera de los 8 módulos |
| — | `proactividad` | vivo (brazo de salida de la espina) |
| — | `tiempo`, `metas` | dormidos por canon |

## Al escribir en una planilla

Las dos hojas de finanzas se escriben **por posición** (`sheets.append_row` con una lista), así que
el orden del código y el de la planilla tienen que calzar exactamente. Si tocas columnas, el cambio
es de cuatro puntas a la vez: la planilla, `setup_sheets.py` (`TABS_DONNA`/`TABS_LOUIS`), la
escritura posicional del módulo, y las fórmulas del Dashboard/Comparativo que apuntan por letra.
Detalle y precedentes en `docs/Roadmap_Modular.md` §Auditoría de columnas.

Recordatorio del canon: **finanzas y estados de cuenta pasan siempre `sheet_id=sheets.fin_id()`**
(planilla Louis); todo lo de vida usa el id por defecto.

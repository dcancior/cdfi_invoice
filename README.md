# cdfi_invoice

## Respuestas inesperadas del PAC

Al timbrar un complemento de pago, timbrar una factura o cancelarla, el PAC
normalmente contesta un JSON con una clave de estado:

| Operación | Método | Clave esperada |
|---|---|---|
| Timbrar complemento de pago | `account.payment.complete_payment` | `estado_pago` |
| Timbrar factura | `account.move.action_cfdi_generate` | `estado_factura` |
| Cancelar factura | `account.move.action_cfdi_cancel` | `estado_factura` |

Si el PAC rechaza la petición antes de procesarla (validación, credenciales,
timbres agotados, falla interna), contesta con otro formato, por ejemplo
`{"message": ...}`, o con algo que no es JSON. Antes eso se veía como
`KeyError: 'estado_pago'` / `'estado_factura'`, sin pista de la causa.

Ahora las tres operaciones leen la respuesta con `leer_respuesta_pac`
([models/respuesta_pac.py](models/respuesta_pac.py)), que:

- muestra al usuario un error con el código HTTP y el mensaje del PAC (en
  validaciones, también el campo que falló); el documento **no** se timbra ni
  se cancela y queda como estaba;
- escribe la respuesta completa en el log de Odoo como `ERROR`, con el
  documento, su id y la compañía;
- en facturas, desactiva la casilla "Proceso de timbrado", para que el
  siguiente intento no se bloquee.

Las respuestas normales (`pago_correcto`, `problemas_pago`,
`factura_correcta`, `problemas_factura`, `solicitud_cancelar`, …) siguen el
mismo camino que antes.

Para consultar la respuesta en el servidor de Goodcar:

```sh
grep -A2 "Respuesta inesperada del PAC" ~/Goodcar_produccion/logs/odoo.log | tail
```

Antecedente: 2026-11-25, pago PTRANS/2026/00474 de JOSE ARMANDO NEGRETE en
Goodcar Producción (`KeyError: 'estado_pago'`).

Pendiente: la consulta periódica del estado de cancelación
(`check_cancel_status_by_cron`) todavía lee `estado_consulta` directamente.

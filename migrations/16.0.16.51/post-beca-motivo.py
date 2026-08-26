# -*- coding: utf-8 -*-
"""Convierte el motivo de beca de texto libre al catálogo beca.motivo.

Antes el motivo se capturaba a mano, así que el mismo motivo quedó escrito de
varias formas ("VITALICIA", "vitalicia"). Aquí cada motivo se da de alta una
sola vez, agrupando las variantes que sólo difieren en mayúsculas y dejando
como nombre bueno el que más se repite.

Los motivos mal escritos ("VIALICIA", "VITALCIA") sí quedan como registros
aparte a propósito: no se adivina la intención, se dejan a la vista en
Contabilidad > Configuración > Motivos de Beca para corregirlos a mano.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Al renombrar el campo, Odoo deja la columna original en la tabla sin
    # tocarla, así que el texto que ya estaba capturado sigue disponible.
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'res_partner' AND column_name = 'beca_motivo'
    """)
    if not cr.fetchone():
        return

    cr.execute("""
        SELECT id, btrim(beca_motivo)
          FROM res_partner
         WHERE beca_motivo IS NOT NULL AND btrim(beca_motivo) <> ''
         ORDER BY id
    """)
    pendientes = cr.fetchall()
    if not pendientes:
        return

    # Nombre bueno de cada motivo: la variante más repetida; a igualdad de
    # repeticiones, la primera en orden alfabético, para que el resultado no
    # dependa del orden en que estén los contactos.
    variantes = {}
    for _partner_id, motivo in pendientes:
        variantes.setdefault(motivo.lower(), {})
        variantes[motivo.lower()][motivo] = \
            variantes[motivo.lower()].get(motivo, 0) + 1
    nombres = {
        clave: sorted(cuentas.items(), key=lambda v: (-v[1], v[0]))[0][0]
        for clave, cuentas in variantes.items()
    }

    # Los motivos que ya existan en el catálogo se reutilizan.
    cr.execute("SELECT id, name FROM beca_motivo")
    catalogo = {name.strip().lower(): mid for mid, name in cr.fetchall()}

    creados = 0
    for clave, nombre in sorted(nombres.items()):
        if clave in catalogo:
            continue
        cr.execute("""
            INSERT INTO beca_motivo (name, active, create_uid, write_uid,
                                     create_date, write_date)
                 VALUES (%s, true, 1, 1, now() at time zone 'UTC',
                         now() at time zone 'UTC')
              RETURNING id
        """, (nombre,))
        catalogo[clave] = cr.fetchone()[0]
        creados += 1

    for partner_id, motivo in pendientes:
        cr.execute(
            "UPDATE res_partner SET beca_motivo_id = %s WHERE id = %s",
            (catalogo[motivo.lower()], partner_id))

    _logger.info(
        'Motivos de beca migrados al catálogo: %s contactos actualizados, '
        '%s motivos nuevos (%s). La columna beca_motivo se conserva como '
        'respaldo.',
        len(pendientes), creados, ', '.join(sorted(nombres.values())))

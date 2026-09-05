# -*- coding: utf-8 -*-
"""Activa el candado de líneas en las facturas que ya existen.

El campo lock_invoice_lines nacía en falso, así que el candado no protegía a
ninguna de las facturas ya capturadas: se podían agregar conceptos a mano en
la factura sin que existieran en la orden, y ahí es donde los montos de una y
otra dejaban de coincidir.

A partir de esta versión nace activo. Aquí se pone activo también en las
anteriores. Un administrador puede desactivarlo por excepción en una factura
concreta.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        UPDATE account_move
           SET lock_invoice_lines = true
         WHERE move_type IN ('out_invoice', 'out_refund')
           AND lock_invoice_lines IS DISTINCT FROM true
    """)
    _logger.info('Candado de líneas activado en %s facturas existentes.', cr.rowcount)

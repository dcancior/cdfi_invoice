import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Suscribe al creador de cada pago histórico como seguidor de la factura
    y de las órdenes de venta relacionadas, para que el filtro de visibilidad
    basado en message_partner_ids funcione también con datos anteriores.
    """
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})

    _logger.info("cdfi_invoice: iniciando migración histórica de seguidores en pagos...")

    payments = env['account.payment'].search([('state', '=', 'posted')])
    count = 0

    for payment in payments:
        partner_id = payment.create_uid.partner_id.id
        if not partner_id:
            continue

        invoices = payment.reconciled_invoice_ids
        if not invoices:
            continue

        invoices.message_subscribe([partner_id])

        orders = invoices.mapped('line_ids.sale_line_ids.order_id')
        if orders:
            orders.message_subscribe([partner_id])

        count += 1

    _logger.info("cdfi_invoice: migración completada — %d pagos procesados.", count)

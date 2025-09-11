# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from . import amount_to_text_es_MX
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    forma_pago_id = fields.Many2one('catalogo.forma.pago', string='Forma de pago')
    methodo_pago = fields.Selection(
        selection=[
            ('PUE', _('Pago en una sola exhibición')),
            ('PPD', _('Pago en parcialidades o diferido')),
        ],
        string=_('Método de pago'),
    )
    uso_cfdi_id = fields.Many2one('catalogo.uso.cfdi', string='Uso CFDI')

    # Se muestra en la TZ del usuario automáticamente en vistas
    fecha_corregida = fields.Datetime(string=_('Fecha Cotización'), compute='_compute_fecha_corregida')

    # (Opcional) Monto en letra en pedido
    amount_to_text = fields.Char('Amount to Text', compute='_compute_amount_to_text', readonly=True)

    # Agregar NUEVO valor al selection nativo (sin ondelete set default)
    invoice_status = fields.Selection(
        selection_add=[('cfdi_emitido', _('CFDI Emitido'))]
    )

    # ------------------------------
    # Onchanges
    # ------------------------------
    @api.onchange('partner_id')
    def _get_uso_cfdi(self):
        if self.partner_id:
            self.update({'uso_cfdi_id': self.partner_id.uso_cfdi_id.id})

    @api.onchange('payment_term_id')
    def _get_metodo_pago(self):
        if self.payment_term_id:
            if getattr(self.payment_term_id, 'methodo_pago', False) == 'PPD':
                fp = self.env['catalogo.forma.pago'].sudo().search([('code', '=', '99')], limit=1)
                values = {
                    'methodo_pago': self.payment_term_id.methodo_pago,
                    'forma_pago_id': fp.id,
                }
            else:
                values = {
                    'methodo_pago': self.payment_term_id.methodo_pago,
                    'forma_pago_id': False,
                }
        else:
            values = {'methodo_pago': False, 'forma_pago_id': False}
        self.update(values)

    @api.onchange('partner_id', 'company_id')
    def _onchange_partner_id(self):
        res = super()._onchange_partner_id()
        for order in self:
            if order.partner_id:
                order.partner_invoice_id = order.partner_id.commercial_partner_id
        return res

    # ------------------------------
    # Computes
    # ------------------------------
    @api.depends('date_order')
    def _compute_fecha_corregida(self):
        for sale in self:
            sale.fecha_corregida = sale.date_order or False

    @api.depends('amount_total', 'currency_id')
    def _compute_amount_to_text(self):
        for record in self:
            currency = record.currency_id and record.currency_id.name or 'MXN'
            record.amount_to_text = amount_to_text_es_MX.get_amount_to_text(
                record, record.amount_total, 'es_cheque', currency
            )

    # Extiende el cómputo nativo de invoice_status para “promover” a cfdi_emitido
    @api.depends(
        'order_line.invoice_status', 'order_line.qty_to_invoice', 'state',
        'invoice_ids.estado_factura', 'invoice_ids.move_type', 'invoice_ids.state'
    )
    def _compute_invoice_status(self):
        # 1) cálculo estándar de Odoo
        super(SaleOrder, self)._compute_invoice_status()
        # 2) si existe alguna factura cliente con estado_factura = 'factura_correcta' -> cfdi_emitido
        for order in self:
            invoices = order.invoice_ids.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund'))
            if any(inv.estado_factura == 'factura_correcta' for inv in invoices):
                order.invoice_status = 'cfdi_emitido'

    # ------------------------------
    # Helpers / API
    # ------------------------------
    @api.model
    def _get_amount_2_text(self, amount_total):
        currency = self.currency_id and self.currency_id.name or 'MXN'
        return amount_to_text_es_MX.get_amount_to_text(self, amount_total, 'es_cheque', currency)

    # ------------------------------
    # Overrides de creación de factura
    # ------------------------------
    def _prepare_invoice(self):
        # Consolidado: incluye CFDI y fuerza partner comercial
        vals = super()._prepare_invoice()
        vals.update({
            'forma_pago_id': self.forma_pago_id.id,
            'methodo_pago': self.methodo_pago,
            'uso_cfdi_id': self.uso_cfdi_id.id,
            'tipo_comprobante': 'I',
        })
        if self.partner_id:
            vals['partner_id'] = self.partner_id.commercial_partner_id.id
        return vals

    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        for move in moves:
            move.partner_id = move.partner_id.commercial_partner_id
        return moves

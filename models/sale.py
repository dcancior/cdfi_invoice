# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import odoo.addons.decimal_precision as dp
from  . import amount_to_text_es_MX
import pytz
import logging
_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    forma_pago_id  =  fields.Many2one('catalogo.forma.pago', string='Forma de pago')
    #num_cta_pago = fields.Char(string=_('Núm. Cta. Pago'))
    methodo_pago = fields.Selection(
        selection=[('PUE', _('Pago en una sola exhibición')),
                   ('PPD', _('Pago en parcialidades o diferido')),],
        string=_('Método de pago'), 
    )
    uso_cfdi_id  =  fields.Many2one('catalogo.uso.cfdi', string='Uso CFDI')
    fecha_corregida = fields.Datetime(string=_('Fecha Cotizacion'), compute='_get_fecha_corregida')

    @api.onchange('partner_id')
    def _get_uso_cfdi(self):
        if self.partner_id:
            values = {
                'uso_cfdi_id': self.partner_id.uso_cfdi_id.id
                }
            self.update(values)

    @api.onchange('payment_term_id')
    def _get_metodo_pago(self):
        if self.payment_term_id:
            if self.payment_term_id.methodo_pago == 'PPD':
                values = {
                 'methodo_pago': self.payment_term_id.methodo_pago,
                 'forma_pago_id': self.env['catalogo.forma.pago'].sudo().search([('code','=','99')])
             }
            else:
                values = {
                 'methodo_pago': self.payment_term_id.methodo_pago,
                 'forma_pago_id': False
             }
        else:
            values = {
                'methodo_pago': False,
                'forma_pago_id': False
                }
        self.update(values)

    @api.depends('amount_total', 'currency_id')
    def _get_amount_to_text(self):
        for record in self:
            record.amount_to_text = amount_to_text_es_MX.get_amount_to_text(record, record.amount_total, 'es_cheque', record.currency_id.name)
        
    @api.model
    def _get_amount_2_text(self, amount_total):
        return amount_to_text_es_MX.get_amount_to_text(self, amount_total, 'es_cheque', self.currency_id.name)
        
    
    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals.update({'forma_pago_id': self.forma_pago_id.id,
                    'methodo_pago': self.methodo_pago,
                    'uso_cfdi_id': self.uso_cfdi_id.id,
                    'tipo_comprobante': 'I'
                    })
        return invoice_vals

    
    def _get_fecha_corregida(self):
        for sale in self:
           if sale.date_order:
              #corregir hora
              timezone = sale._context.get('tz')
              if not timezone:
                  timezone = sale.env.user.partner_id.tz or 'America/Mexico_City'
              #timezone = tools.ustr(timezone).encode('utf-8')

              local = pytz.timezone(timezone)
              naive_from = sale.date_order
              local_dt_from = naive_from.replace(tzinfo=pytz.UTC).astimezone(local)
              sale.fecha_corregida = local_dt_from.strftime ("%Y-%m-%d %H:%M:%S")
              #_logger.info('fecha ... %s', sale.fecha_corregida)



    #Forzar que el pedido use el partner maestro como “Invoice Address”
    #Sobrescribe el onchange de partner_id en sale.order para que, después del super(), siempre deje partner_invoice_id = commercial_partner_id.
    @api.onchange('partner_id', 'company_id')
    def _onchange_partner_id(self):
        # Llama al método correcto de la base
        res = super()._onchange_partner_id()
        # Forzar que la dirección de facturación sea SIEMPRE el partner comercial (maestro)
        for order in self:
            if order.partner_id:
                order.partner_invoice_id = order.partner_id.commercial_partner_id
        return res

    #   2) Red de seguridad al crear la factura
    #   Aunque el punto 1 suele ser suficiente, por si otro módulo reescribe partner_invoice_id o el usuario lo cambia manualmente,
    #   fuerza el partner en la factura en _prepare_invoice().
    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        # Red de seguridad: la factura se crea contra el partner maestro
        if self.partner_id:
            vals['partner_id'] = self.partner_id.commercial_partner_id.id
        return vals

    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        # Extra por si algún módulo vuelve a cambiarlo
        for move in moves:
            move.partner_id = move.partner_id.commercial_partner_id
        return moves
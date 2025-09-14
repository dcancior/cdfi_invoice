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


    # -------------------------------------------------------------------------
    # Campo espejo del estado CFDI tomando en cuenta TODAS las facturas del pedido
    # -------------------------------------------------------------------------
    estado_cfdi = fields.Selection(
        selection=[
            ('factura_no_generada', 'CFDI no generado'),
            ('factura_correcta',    'CFDI Emitido'),
            ('solicitud_cancelar',  'Cancelación en proceso'),
            ('factura_cancelada',   'CFDI Cancelado'),
            ('solicitud_rechazada', 'Cancelación rechazada'),
        ],
        string='Estado CFDI (facturas)',
        compute='_compute_estado_cfdi',  # se calcula en función de las facturas
        store=True,                      # se almacena en BD (útil para decoraciones/filtros rápidos)
        readonly=True,
        help="Resumen del estado CFDI según las facturas relacionadas al pedido."
    )

    # Mapa de prioridades para resolver mezclas de estados en múltiples facturas
    # (valor mayor => mayor prioridad visual/funcional)
    _ESTADO_CFDI_PRIORITY = {
        'solicitud_cancelar': 4,
        'factura_correcta':   3,
        'solicitud_rechazada':2,
        'factura_cancelada':  1,
        'factura_no_generada':0,
        None:                 -1,  # por si algún valor viene vacío
    }

    @api.depends(
        # Disparo fino: cambia cuando el estado de cualquier factura ligada cambia
        'order_line.invoice_lines.move_id.estado_factura',
        'order_line.invoice_lines.move_id.move_type',
    )
    def _compute_estado_cfdi(self):
        """
        Lógica de agregación:
        - Si no hay facturas: 'factura_no_generada'
        - Si hay mezcla de estados, gana el de mayor prioridad:
            solicitud_cancelar > factura_correcta > solicitud_rechazada > factura_cancelada > factura_no_generada
        - Caso particular: si TODAS están canceladas, queda 'factura_cancelada'.
        """
        for order in self:
            # Trae las account.move (facturas/NC) ligadas a este pedido
            # usando la relación real: sale.order -> sale.order.line -> account.move.line -> account.move
            moves = order.order_line.invoice_lines.mapped('move_id') \
                .filtered(lambda m: m.move_type in ('out_invoice', 'out_refund'))

            # Sin facturas: estado inicial
            if not moves:
                order.estado_cfdi = 'factura_no_generada'
                continue

            # Conjunto de estados presentes en las facturas
            estados = set(moves.mapped('estado_factura'))

            # Si todas están canceladas, lo mostramos explícito
            if estados and estados == {'factura_cancelada'}:
                order.estado_cfdi = 'factura_cancelada'
                continue

            # Selección por prioridad (el estado con mayor prioridad "gana")
            # Ej.: si hay una en 'solicitud_cancelar' y otra en 'factura_correcta', ganará 'solicitud_cancelar'
            mejor_estado = max(estados, key=lambda e: self._ESTADO_CFDI_PRIORITY.get(e, -1))

            # Si por alguna razón el mejor_estado no está mapeado, cae a 'factura_no_generada'
            order.estado_cfdi = mejor_estado if mejor_estado in self._ESTADO_CFDI_PRIORITY else 'factura_no_generada'

    # -------------------------------------------------------------------------
    # (Opcional) Si quisieras una variante "estricta" (solo 'factura_correcta' cuando TODAS lo están):
    # Descomenta y usa esta función dentro del compute en vez del bloque de prioridad:
    # -------------------------------------------------------------------------
    # def _aggregate_estado_cfdi_estricto(self, estados):
    #     if not estados:
    #         return 'factura_no_generada'
    #     if estados == {'factura_correcta'}:
    #         return 'factura_correcta'
    #     if estados == {'factura_cancelada'}:
    #         return 'factura_cancelada'
    #     if 'solicitud_cancelar' in estados:
    #         return 'solicitud_cancelar'
    #     if 'solicitud_rechazada' in estados:
    #         return 'solicitud_rechazada'
    #     return 'factura_no_generada'

    

    @api.onchange('methodo_pago')
    def _onchange_methodo_pago_set_forma_pago(self):
        """
        Si el método de pago indica PPD, poner 'Por definir (99)'.
        En cualquier otro caso (incluye vacío), limpiar la forma de pago.
        """
        for order in self:
            val = (order.methodo_pago or '').strip().lower()
            es_ppd = (
                val in ('ppd', 'pago en parcialidades o diferido', 'parcialidades o diferido')
                or 'ppd' in val
                or 'parcial' in val
                or 'diferid' in val
            )

            # --- Many2one: forma_pago_id ---
            if 'forma_pago_id' in order._fields:
                if es_ppd:
                    comodel = order._fields['forma_pago_id'].comodel_name
                    Forma = self.env[comodel]  # evita KeyError del modelo
                    code_field = next((c for c in (
                        'code', 'codigo', 'clave', 'key', 'codigo_sat', 'code_sat'
                    ) if c in Forma._fields), None)

                    rec = False
                    if code_field:
                        rec = Forma.search([(code_field, '=', '99')], limit=1)
                    if not rec:
                        rec = Forma.search(['|', ('name', 'ilike', 'por definir'),
                                                  ('name', 'ilike', '99')], limit=1)
                    order.forma_pago_id = rec.id if rec else False
                else:
                    # Limpiar cuando no es PPD
                    order.forma_pago_id = False

            # --- Selection: forma_pago (por si tu campo no es Many2one) ---
            elif 'forma_pago' in order._fields and order._fields['forma_pago']._type == 'selection':
                if es_ppd:
                    sel = order._fields['forma_pago'].selection
                    if callable(sel):
                        sel = sel(self.env)
                    claves = [k for k, _ in (sel or [])]
                    if '99' in claves:
                        order.forma_pago = '99'
                    else:
                        asignado = False
                        for key, label in (sel or []):
                            if (label or '').strip().lower().find('por definir') >= 0:
                                order.forma_pago = key
                                asignado = True
                                break
                        if not asignado:
                            order.forma_pago = False
                else:
                    # Limpiar cuando no es PPD
                    order.forma_pago = False

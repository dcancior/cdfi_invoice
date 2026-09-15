# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class SaldoFavorCliente(models.Model):
    """Consulta de solo lectura: cada renglón es un pago (o apunte) en la cuenta
    por cobrar de un cliente que todavía no está aplicado por completo a una
    factura. Agrupado por contacto da el saldo a favor total de cada cliente."""
    _name = 'saldo.favor.cliente'
    _description = 'Saldo a favor de clientes'
    _auto = False
    _order = 'partner_id, date desc, id desc'

    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    date = fields.Date(string='Fecha', readonly=True)
    move_id = fields.Many2one('account.move', string='Asiento', readonly=True)
    payment_id = fields.Many2one('account.payment', string='Pago', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Diario', readonly=True)
    forma_pago_id = fields.Many2one('catalogo.forma.pago', string='Forma de pago', readonly=True)
    referencia = fields.Char(string='Referencia', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    company_currency_id = fields.Many2one('res.currency', string='Moneda de la compañía', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda del pago', readonly=True)
    monto_pago = fields.Monetary(string='Monto del pago', currency_field='company_currency_id', readonly=True)
    monto_aplicado = fields.Monetary(string='Aplicado a facturas', currency_field='company_currency_id', readonly=True)
    saldo_favor = fields.Monetary(string='Saldo a favor', currency_field='company_currency_id', readonly=True)
    saldo_favor_moneda = fields.Monetary(string='Saldo a favor (moneda del pago)', currency_field='currency_id', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    l.id AS id,
                    COALESCE(p.commercial_partner_id, l.partner_id) AS partner_id,
                    l.date AS date,
                    l.move_id AS move_id,
                    l.payment_id AS payment_id,
                    l.journal_id AS journal_id,
                    pay.forma_pago_id AS forma_pago_id,
                    COALESCE(NULLIF(m.ref, ''), l.name) AS referencia,
                    l.company_id AS company_id,
                    l.company_currency_id AS company_currency_id,
                    l.currency_id AS currency_id,
                    l.credit AS monto_pago,
                    l.credit + l.amount_residual AS monto_aplicado,
                    -l.amount_residual AS saldo_favor,
                    -l.amount_residual_currency AS saldo_favor_moneda
                FROM account_move_line l
                JOIN account_account a ON a.id = l.account_id
                JOIN account_move m ON m.id = l.move_id
                LEFT JOIN res_partner p ON p.id = l.partner_id
                LEFT JOIN account_payment pay ON pay.id = l.payment_id
                WHERE a.account_type = 'asset_receivable'
                  AND l.parent_state = 'posted'
                  AND l.reconciled IS NOT TRUE
                  AND l.amount_residual < 0
                  AND l.partner_id IS NOT NULL
            )
        """ % self._table)

    def action_abrir_origen(self):
        self.ensure_one()
        if self.payment_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'res_id': self.payment_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

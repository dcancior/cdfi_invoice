# -*- coding: utf-8 -*-
from odoo import api, fields, models

GRUPOS_SALDO_FAVOR = 'account.group_account_invoice,account.group_account_readonly'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    saldo_favor_cliente = fields.Monetary(
        string='Saldo a favor del cliente',
        currency_field='saldo_favor_currency_id',
        compute='_compute_saldo_favor_cliente',
        groups=GRUPOS_SALDO_FAVOR,
    )
    saldo_favor_pagos = fields.Integer(
        string='Pagos con saldo a favor',
        compute='_compute_saldo_favor_cliente',
        groups=GRUPOS_SALDO_FAVOR,
    )
    saldo_favor_currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        groups=GRUPOS_SALDO_FAVOR,
    )

    @api.depends('partner_id', 'company_id')
    def _compute_saldo_favor_cliente(self):
        """Lee la misma consulta del menú Clientes con saldo a favor, para que el
        aviso de la cotización y el menú siempre den el mismo número."""
        for order in self:
            order.saldo_favor_cliente = 0.0
            order.saldo_favor_pagos = 0
        orders = self.filtered('partner_id')
        if not orders:
            return
        partners = orders.partner_id.commercial_partner_id
        grupos = self.env['saldo.favor.cliente'].read_group(
            [('partner_id', 'in', partners.ids),
             ('company_id', 'in', orders.company_id.ids)],
            ['saldo_favor:sum'],
            ['partner_id', 'company_id'],
            lazy=False,
        )
        saldos = {
            (g['partner_id'][0], g['company_id'][0]): (g['saldo_favor'], g['__count'])
            for g in grupos
        }
        for order in orders:
            key = (order.partner_id.commercial_partner_id.id, order.company_id.id)
            saldo, pagos = saldos.get(key, (0.0, 0))
            order.saldo_favor_cliente = saldo
            order.saldo_favor_pagos = pagos

    def action_ver_saldo_favor_cliente(self):
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        action = self.env['ir.actions.act_window']._for_xml_id(
            'cdfi_invoice.action_saldo_favor_cliente')
        action['name'] = 'Saldo a favor de %s' % partner.display_name
        action['domain'] = [('partner_id', '=', partner.id),
                            ('company_id', '=', self.company_id.id)]
        action['context'] = {'default_partner_id': partner.id}
        return action

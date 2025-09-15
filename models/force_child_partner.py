# models/force_child_partner.py
# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError

# 2) (Opcional) Heredar el wizard para congelar el partner hijo
#Algunas instalaciones de Odoo tienden a normalizar al commercial_partner_id durante la 
# creación del pago. Para blindarlo, hereda el wizard account.payment.register y fuerza el 
# partner_id cuando venga la bandera force_child_partner en contexto.

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)

        # ⚠️ Nunca pasar group_payment al modelo account.payment
        vals.pop('group_payment', None)

        if self.env.context.get('force_child_partner'):
            lines = batch_result.get('lines') if isinstance(batch_result, dict) else None
            partners = (lines or self.env['account.move.line']).mapped('partner_id').exists()
            if not partners and self.env.context.get('default_partner_id'):
                partners = self.env['res.partner'].browse(self.env.context['default_partner_id']).exists()
            if not partners:
                return vals
            if len(partners) > 1:
                raise UserError(_("No se puede forzar el contacto hijo: hay más de un partner en las partidas."))
            vals['partner_id'] = partners[0].id
        elif self.env.context.get('default_partner_id'):
            vals['partner_id'] = self.env.context['default_partner_id']

        return vals

    def _create_payment_vals_from_batch(self, batch_result):
        vals = super()._create_payment_vals_from_batch(batch_result)

        # ⚠️ Nunca pasar group_payment al modelo account.payment
        vals.pop('group_payment', None)

        if self.env.context.get('force_child_partner'):
            lines = batch_result.get('lines') if isinstance(batch_result, dict) else None
            partners = (lines or self.env['account.move.line']).mapped('partner_id').exists()
            if not partners and self.env.context.get('default_partner_id'):
                partners = self.env['res.partner'].browse(self.env.context['default_partner_id']).exists()
            if not partners:
                return vals
            if len(partners) > 1:
                raise UserError(_("No se puede forzar el contacto hijo: hay más de un partner en las partidas."))
            vals['partner_id'] = partners[0].id
        elif self.env.context.get('default_partner_id'):
            vals['partner_id'] = self.env.context['default_partner_id']

        return vals

    def _create_payments(self):
        payments = super()._create_payments()
        if self.env.context.get('force_child_partner'):
            child = (self.env['res.partner']
                     .browse(self.env.context.get('default_partner_id'))).exists() or self.partner_id
            if child:
                payments.write({'partner_id': child.id})
                for pay in payments:
                    if pay.move_id:
                        pay.move_id.write({'partner_id': child.id})
                        rp_lines = pay.move_id.line_ids.filtered(
                            lambda l: l.account_internal_type in ('receivable', 'payable')
                        )
                        rp_lines.write({'partner_id': child.id})
        return payments

    # Opcional: fija el valor del campo del wizard sin tocar vals del payment
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if self.env.context.get('force_child_partner') and 'group_payment' in self._fields:
            vals['group_payment'] = False
        return vals
# models/force_child_partner.py
# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError

# 2) (Opcional) Heredar el wizard para congelar el partner hijo
#Algunas instalaciones de Odoo tienden a normalizar al commercial_partner_id durante la 
# creación del pago. Para blindarlo, hereda el wizard account.payment.register y fuerza el 
# partner_id cuando venga la bandera force_child_partner en contexto.

cclass AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _get_batches(self, to_process=None):
        """
        Forzar que el partner del batch sea el partner EXACTO de las líneas (hijo),
        no el commercial_partner_id. Así, el resto del pipeline ya “piensa en hijo”.
        """
        batches = super()._get_batches(to_process=to_process)
        for batch in batches:
            lines = batch.get('lines') or self.env['account.move.line']
            partners = lines.mapped('partner_id').exists()
            # Sólo si todas las líneas comparten el mismo partner (hijo):
            if partners and len(partners) == 1:
                batch['partner'] = partners[0]  # 👈 clave: partner del batch = hijo
        return batches

    def _child_partner_from_batch(self, batch_result):
        lines = batch_result.get('lines') if isinstance(batch_result, dict) else None
        partners = (lines or self.env['account.move.line']).mapped('partner_id').exists()
        if not partners and self.env.context.get('default_partner_id'):
            partners = self.env['res.partner'].browse(self.env.context['default_partner_id']).exists()
        return partners if partners else self.env['res.partner']

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        vals.pop('group_payment', None)  # ⚠️ NO es campo de account.payment
        partners = self._child_partner_from_batch(batch_result)
        if partners:
            if len(partners) > 1:
                raise UserError(_("Las partidas del pago tienen más de un partner."))
            vals['partner_id'] = partners[0].id         # 👈 usa HIJO
        return vals

    def _create_payment_vals_from_batch(self, batch_result):
        vals = super()._create_payment_vals_from_batch(batch_result)
        vals.pop('group_payment', None)
        partners = self._child_partner_from_batch(batch_result)
        if partners:
            if len(partners) > 1:
                raise UserError(_("Las partidas del pago tienen más de un partner."))
            vals['partner_id'] = partners[0].id         # 👈 usa HIJO
        return vals

    def _create_payments(self):
        payments = super()._create_payments()

        # Reafirmar partner hijo en payment, move y líneas RP
        for pay in payments:
            child = pay.partner_id  # después del paso 1 y 2 ya debería ser el hijo
            if not child:
                continue
            # Payment
            pay.write({'partner_id': child.id})
            # Move del payment
            if pay.move_id:
                pay.move_id.write({'partner_id': child.id})
                rp_lines = pay.move_id.line_ids.filtered(
                    lambda l: l.account_internal_type in ('receivable', 'payable')
                )
                rp_lines.write({'partner_id': child.id})

        payments.invalidate_cache(['partner_id'])
        return payments
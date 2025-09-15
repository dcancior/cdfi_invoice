from odoo import models, api

# 2) (Opcional) Heredar el wizard para congelar el partner hijo
#Algunas instalaciones de Odoo tienden a normalizar al commercial_partner_id durante la 
# creación del pago. Para blindarlo, hereda el wizard account.payment.register y fuerza el 
# partner_id cuando venga la bandera force_child_partner en contexto.

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        # Si nos pidieron explícitamente forzar el hijo, respeta el default_partner_id del contexto
        if self.env.context.get('force_child_partner') and self.env.context.get('default_partner_id'):
            vals['partner_id'] = self.env.context['default_partner_id']
            # Evita agrupaciones que puedan reagrupar por matriz
            vals.setdefault('group_payment', False)
        return vals

    def _create_payments(self):
        """
        Tras crear los pagos con el super, nos aseguramos
        de que el partner quede en el hijo y que las líneas RP del asiento de pago
        también queden con el hijo (crítico para conciliación y para REP).
        """
        payments = super()._create_payments()

        if self.env.context.get('force_child_partner') and self.partner_id:
            # 1) Forzar partner en el payment
            payments.write({'partner_id': self.partner_id.id})

            # 2) Forzar partner en las líneas RP del asiento contable del pago
            for pay in payments:
                rp_lines = pay.move_id.line_ids.filtered(
                    lambda l: l.account_internal_type in ('receivable', 'payable')
                )
                rp_lines.write({'partner_id': self.partner_id.id})

        return payments

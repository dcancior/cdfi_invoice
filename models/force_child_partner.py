from odoo import models, api

# 2) (Opcional) Heredar el wizard para congelar el partner hijo
#Algunas instalaciones de Odoo tienden a normalizar al commercial_partner_id durante la 
# creación del pago. Para blindarlo, hereda el wizard account.payment.register y fuerza el 
# partner_id cuando venga la bandera force_child_partner en contexto.

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    # -- En algunos parches de Odoo 16 se usa este método:
    def _create_payment_vals_from_batch(self, batch_result):
        vals = super()._create_payment_vals_from_batch(batch_result)
        # Si venimos de tu acción con "force_child_partner", usa el contacto hijo
        if self.env.context.get('force_child_partner'):
            # Partners de las líneas del batch (debería ser 1: el hijo)
            partners = batch_result['lines'].mapped('partner_id')
            partners = partners or self.env['res.partner'].browse(self.env.context.get('default_partner_id'))
            partners = partners.exists()
            if not partners:
                return vals
            if len(partners) > 1:
                raise UserError(_("No se puede forzar el contacto hijo: hay más de un partner en las partidas."))
            vals['partner_id'] = partners[0].id
        elif self.env.context.get('default_partner_id'):
            # Fallback si no vino bandera pero sí default
            vals['partner_id'] = self.env.context['default_partner_id']
        # Evita que reagrupe por matriz
        vals.setdefault('group_payment', False)
        return vals

    # -- En otras revisiones se invoca este otro; lo incluimos por compatibilidad:
    def _create_payment_vals_from_wizard(self):
        vals = super()._create_payment_vals_from_wizard()
        if self.env.context.get('force_child_partner') and self.env.context.get('default_partner_id'):
            vals['partner_id'] = self.env.context['default_partner_id']
        vals.setdefault('group_payment', False)
        return vals

    def _create_payments(self):
        """
        Tras crear, asegura que el payment y sus líneas RP conserven el partner hijo.
        Así, cuando se abre model=account.payment&view_type=form verás al hijo.
        """
        payments = super()._create_payments()

        if self.env.context.get('force_child_partner'):
            child = (self.env['res.partner']
                     .browse(self.env.context.get('default_partner_id'))).exists() or self.partner_id
            if child:
                # 1) Forzar partner en el payment
                payments.write({'partner_id': child.id})

                # 2) Forzar partner en el asiento del pago y sus líneas RP
                for pay in payments:
                    if pay.move_id:
                        pay.move_id.write({'partner_id': child.id})
                        rp_lines = pay.move_id.line_ids.filtered(
                            lambda l: l.account_internal_type in ('receivable', 'payable')
                        )
                        rp_lines.write({'partner_id': child.id})
        return payments
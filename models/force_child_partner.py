# models/force_child_partner.py
from odoo import models
from odoo.exceptions import UserError

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _get_batches(self, *args, **kwargs):
        """
        Forzar que el partner del batch sea el partner EXACTO de las líneas (hijo),
        no el commercial_partner_id. Soporta builds que llamen con o sin argumentos.
        """
        # Llama al core tal cual (en tu build llega sin args)
        batches = super()._get_batches(*args, **kwargs)

        for batch in batches:
            lines = batch.get('lines') or self.env['account.move.line']
            partners = lines.mapped('partner_id').exists()
            # Sólo si todas las líneas comparten el mismo partner (hijo)
            if partners and len(partners) == 1:
                batch['partner'] = partners[0]  # ✅ clave: partner del batch = HIJO
        return batches

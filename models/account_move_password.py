# cdfi_invoice/models/account_move_password.py
from odoo import api, models, _
from odoo.exceptions import AccessDenied, UserError

class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def js_remove_outstanding_partial_with_password(self, move_id, partial_id, password):
        # 1) Validar contraseña
        try:
            self.env.user._check_credentials(password, {'interactive': True})
        except AccessDenied:
            raise UserError(_("Contraseña incorrecta."))

        # 2) Llamar al método nativo según la firma que tenga en tu build
        move = self.env['account.move'].browse(move_id)
        if not move.exists():
            raise UserError(_("El asiento %s no existe.") % move_id)

        # Preferimos la firma de *registro* (self, partial_id)
        try:
            return move.js_remove_outstanding_partial(partial_id)
        except TypeError:
            # Fallback: firma de *modelo* (move_id, partial_id)
            return self.env['account.move'].js_remove_outstanding_partial(move_id, partial_id)

from odoo import models, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    def js_remove_outstanding_partial_with_password(self, partial_id, password):
        self.ensure_one()
        
        # 1. Verificar si el usuario pertenece al grupo
        if not self.env.user.has_group('cdfi_invoice.group_allow_unreconcile'):
            raise UserError(_("No tienes permisos suficientes para romper conciliaciones."))

        # 2. Verificar la contraseña del usuario actual
        # (Usamos el método nativo de Odoo para verificar el password del usuario logueado)
        user = self.env.user
        authenticated = user._check_credentials(password, {'type': 'interactive'})
        
        if not authenticated:
            raise UserError(_("Contraseña incorrecta."))

        # 3. Lógica original para romper la conciliación
        partial = self.env['account.partial.reconcile'].browse(partial_id)
        return partial.unlink()
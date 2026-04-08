from odoo import models, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    def js_remove_outstanding_partial_with_password(self, partial_id, password):
        self.ensure_one()
        
        # Buscamos el grupo por nombre técnico exacto
        group_name = "Permitir romper conciliaciones con contraseña"
        group = self.env['res.groups'].search([('name', '=', group_name)], limit=1)
        
        # Verificamos si el usuario actual tiene ese grupo en su lista de grupos
        if not group or group not in self.env.user.groups_id:
            raise UserError(_("No tienes permisos suficientes para romper conciliaciones. (Grupo: %s)") % group_name)

        # Validar contraseña del usuario
        try:
            self.env.user._check_credentials(password, {'type': 'interactive'})
        except Exception:
            raise UserError(_("Contraseña incorrecta."))

        partial = self.env['account.partial.reconcile'].browse(partial_id)
        return partial.unlink()
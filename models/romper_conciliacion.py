from odoo import models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    def js_remove_outstanding_partial_with_password(self, partial_id, password):
        # 1. Validación de seguridad manual (Grupo)
        # Usamos sudo() para buscar el grupo por si el usuario no tiene permisos de lectura en res.groups
        group_name = "Permitir romper conciliaciones con contraseña"
        group = self.env['res.groups'].sudo().search([('name', '=', group_name)], limit=1)
        
        if not group or group not in self.env.user.groups_id:
            raise UserError(_("No tienes permisos suficientes para romper conciliaciones."))

        # 2. Validación de contraseña
        try:
            # Check credentials siempre se hace sobre el usuario actual
            self.env.user._check_credentials(password, {'type': 'interactive'})
        except Exception:
            raise UserError(_("Contraseña incorrecta."))

        # 3. Ejecución con sudo() para evitar errores de campos bloqueados (como lock_invoice_lines)
        # Al usar .sudo(), Odoo ignora las restricciones de 'read' sobre campos administrativos
        partial = self.env['account.partial.reconcile'].sudo().browse(partial_id)
        
        if not partial.exists():
            raise UserError(_("La conciliación ya no existe o ya fue rota."))

        try:
            return partial.unlink()
        except Exception as e:
            _logger.error("Error al romper conciliación: %s", str(e))
            raise UserError(_("Error técnico al romper la conciliación: %s") % str(e))
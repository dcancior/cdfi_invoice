from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    # Por defecto desactivado (False)
    desglosar_iva = fields.Selection([
        ('nota', 'Nota de Venta'),
        ('factura', 'Factura')
    ], string="Tipo de Documento", default='nota', required=True)
    
    # Campos técnicos que usas en tu vista XML (debes definirlos si no existen)
    desglosar_iva_locked = fields.Boolean(string="Desglosar IVA Bloqueado")
    wm_from_so_without_desglosar = fields.Boolean(string="Desde SO sin desglosar")
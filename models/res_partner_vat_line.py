# -*- coding: utf-8 -*-
from odoo import api, fields, models

class PartnerVatLine(models.Model):
    _name = 'res.partner.vat.line'
    _description = 'RFC adicional para partner'
    _order = 'is_primary desc, id'

    partner_id = fields.Many2one(
        'res.partner', string='Partner',
        required=True, ondelete='cascade', index=True
    )
    vat = fields.Char(string='RFC', required=True)
    name = fields.Char(string='Nombre')
    is_primary = fields.Boolean(string='Usar por defecto', default=False)

    _sql_constraints = [
        ('uniq_partner_vat', 'unique(partner_id, vat)', 'Este RFC ya está agregado a este contacto.'),
    ]

    @api.onchange('is_primary')
    def _onchange_is_primary(self):
        # Si marco una línea como principal, desmarco las demás del mismo partner
        if self.is_primary and self.partner_id:
            (self.partner_id.vat_line_ids - self).write({'is_primary': False})
        # Nota: NO modificamos partner.vat automáticamente para evitar “autosync”.
        # Si quieres actualizar el maestro con el primario, añade:
        # if self.is_primary and self.vat:
        #     self.partner_id.vat = self.vat

# -*- coding: utf-8 -*-

from odoo import fields, models, _, api
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    residencia_fiscal = fields.Char(string=_('Residencia Fiscal'))
    registro_tributario = fields.Char(string=_('Registro tributario'))
    uso_cfdi_id  =  fields.Many2one('catalogo.uso.cfdi', string='Uso CFDI (cliente)')
    regimen_fiscal_id  =  fields.Many2one('catalogo.regimen.fiscal', string='Régimen Fiscal')


    @api.constrains('vat', 'country_id')
    def check_vat(self):
        # The context key 'no_vat_validation' allows you to store/set a VAT number without doing validations.
        # This is for API pushes from external platforms where you have no control over VAT numbers.
        if self.env.context.get('no_vat_validation'):
            return

        for partner in self:
            country = self.env['res.country'].search([('code', '=', 'MX')])
            if partner.vat and self._run_vat_test(partner.vat, country, partner.is_company) is False:
                partner_label = _("partner [%s]", partner.name)
                msg = partner._build_vat_error_message(country and country.code.lower() or None, partner.vat, partner_label)
                raise ValidationError(msg)

class PartnerVatLine(models.Model):
    _name = 'res.partner.vat.line'
    _description = 'RFC adicional para partner'

    partner_id = fields.Many2one('res.partner', string='Partner', required=True, ondelete='cascade')
    vat = fields.Char(string='RFC')
    name = fields.Char(string='Nombre')
    # Puedes agregar más campos si lo necesitas

class Partner(models.Model):
    _inherit = 'res.partner'
    # se agrega la relación One2many para los RFC adicionales
    vat_line_ids = fields.One2many('res.partner.vat.line', 'partner_id', string='RFCs adicionales')

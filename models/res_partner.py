# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Campos CFDI adicionales
    residencia_fiscal = fields.Char(string=_('Residencia Fiscal'))
    registro_tributario = fields.Char(string=_('Registro tributario'))
    uso_cfdi_id = fields.Many2one('catalogo.uso.cfdi', string='Uso CFDI')
    regimen_fiscal_id = fields.Many2one('catalogo.regimen.fiscal', string='Régimen Fiscal')

    # RFCs adicionales (no tocan automáticamente el VAT maestro)
    vat_line_ids = fields.One2many(
        'res.partner.vat.line', 'partner_id',
        string='RFCs adicionales'
    )

    # --- VALIDACIÓN RFC MX (tu lógica actual) ---
    @api.constrains('vat', 'country_id')
    def check_vat(self):
        if self.env.context.get('no_vat_validation'):
            return
        country_mx = self.env['res.country'].search([('code', '=', 'MX')], limit=1)
        for partner in self:
            if partner.vat and self._run_vat_test(partner.vat, country_mx, partner.is_company) is False:
                partner_label = _("partner [%s]", partner.name)
                msg = partner._build_vat_error_message(
                    country_mx and country_mx.code.lower() or None,
                    partner.vat,
                    partner_label,
                )
                raise ValidationError(msg)

    # --- CLAVE: NO SINCRONIZAR VAT CON HIJOS ---
    @api.model
    def _commercial_fields(self):
        fields_list = super()._commercial_fields()
        # quita 'vat' para que no se replique entre partner comercial e hijos
        return [f for f in fields_list if f != 'vat']

    # --- CONVENIENCIA: prellenar RFC del hijo solo al crear (si es invoice) ---
    @api.model
    def create(self, vals):
        # Si se crea una dirección de facturación sin RFC, toma el maestro del partner
        if vals.get('type') == 'invoice' and not vals.get('vat') and vals.get('parent_id'):
            parent = self.env['res.partner'].browse(vals['parent_id'])
            if parent and parent.vat:
                vals['vat'] = parent.vat
        return super().create(vals)

    # (Opcional) Botón para promover el RFC de una dirección como maestro
    def action_set_vat_as_master(self):
        for rec in self:
            if rec.type == 'invoice' and rec.vat:
                rec.commercial_partner_id.vat = rec.vat

    # --- INTEGRIDAD: evitar RFC duplicado dentro del mismo grupo comercial ---
    @api.constrains('vat')
    def _check_unique_vat_in_commercial_group(self):
        for partner in self:
            if not partner.vat:
                continue
            commercial = partner.commercial_partner_id
            dup = self.search([
                ('id', '!=', partner.id),
                ('commercial_partner_id', '=', commercial.id),
                ('vat', '=', partner.vat),
            ], limit=1)
            if dup:
                raise ValidationError(_("Ya existe este RFC dentro del mismo cliente (empresa/direcciones)."))

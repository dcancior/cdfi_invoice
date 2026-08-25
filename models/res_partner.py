# -*- coding: utf-8 -*-

from odoo import fields, models, _, api
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    residencia_fiscal = fields.Char(string=_('Residencia Fiscal'))
    registro_tributario = fields.Char(string=_('Registro tributario'))
    uso_cfdi_id  =  fields.Many2one('catalogo.uso.cfdi', string='Uso CFDI (cliente)')
    regimen_fiscal_id  =  fields.Many2one('catalogo.regimen.fiscal', string='Régimen Fiscal')

    # ── Beca ──────────────────────────────────────────────────────────────────
    beca_activa = fields.Boolean(string='Beca activa', default=False)
    beca_motivo = fields.Char(string='Motivo de beca')
    beca_porcentaje = fields.Float(string='Porcentaje de beca (%)', digits=(5, 2))
    beca_observaciones = fields.Text(string='Observaciones')

    # Colegiatura del ciclo escolar (mhk_escolar) menos el porcentaje de beca.
    beca_currency_id = fields.Many2one(
        'res.currency',
        string='Moneda de la colegiatura',
        compute='_compute_beca_colegiatura',
    )
    beca_colegiatura_base = fields.Monetary(
        string='Colegiatura del ciclo',
        currency_field='beca_currency_id',
        compute='_compute_beca_colegiatura',
        help='Colegiatura mensual que le corresponde al alumno por su ciclo '
             'escolar y nivel, antes de aplicar la beca.',
    )
    beca_descuento = fields.Monetary(
        string='Descuento por beca',
        currency_field='beca_currency_id',
        compute='_compute_beca_colegiatura',
    )
    beca_colegiatura = fields.Monetary(
        string='Colegiatura con beca',
        currency_field='beca_currency_id',
        compute='_compute_beca_colegiatura',
        help='Colegiatura mensual ya con el porcentaje de beca descontado.',
    )
    beca_colegiatura_total_base = fields.Monetary(
        string='Total del ciclo',
        currency_field='beca_currency_id',
        compute='_compute_beca_colegiatura',
        help='Colegiatura del ciclo completo (mensualidad por los meses a '
             'pagar), antes de aplicar la beca.',
    )
    beca_descuento_total = fields.Monetary(
        string='Descuento por beca del ciclo',
        currency_field='beca_currency_id',
        compute='_compute_beca_colegiatura',
        help='Lo que se le descuenta al alumno en todo el ciclo escolar.',
    )
    beca_colegiatura_total = fields.Monetary(
        string='Total del ciclo con beca',
        currency_field='beca_currency_id',
        compute='_compute_beca_colegiatura',
        help='Colegiatura del ciclo completo ya con la beca descontada.',
    )
    beca_hay_colegiatura = fields.Boolean(
        string='Tiene colegiatura del ciclo',
        compute='_compute_beca_colegiatura',
        help='Indica si al alumno ya se le puede calcular la colegiatura con '
             'beca (requiere el módulo escolar con la colegiatura del ciclo).',
    )

    def _beca_depends(self):
        """Dependencias del cálculo, según los módulos instalados.

        La colegiatura la define el módulo escolar (mhk_escolar); si no está
        instalado, la beca simplemente no tiene sobre qué aplicarse.
        """
        campos = ['beca_activa', 'beca_porcentaje']
        for campo in ('colegiatura', 'meses_pago', 'mhk_currency_id'):
            if campo in self._fields:
                campos.append(campo)
        return campos

    @api.depends(lambda self: self._beca_depends())
    def _compute_beca_colegiatura(self):
        moneda_empresa = self.env.company.currency_id
        hay_colegiatura = 'colegiatura' in self._fields
        hay_meses = 'meses_pago' in self._fields
        hay_moneda = 'mhk_currency_id' in self._fields
        for partner in self:
            moneda = (hay_moneda and partner.mhk_currency_id) or moneda_empresa
            partner.beca_currency_id = moneda
            base = partner.colegiatura if hay_colegiatura else 0.0
            porcentaje = partner.beca_porcentaje if partner.beca_activa else 0.0
            porcentaje = min(max(porcentaje, 0.0), 100.0)
            descuento = moneda.round(base * porcentaje / 100.0)
            meses = int(partner.meses_pago or 0) if hay_meses else 0
            partner.beca_colegiatura_base = base
            partner.beca_descuento = descuento
            partner.beca_colegiatura = base - descuento
            partner.beca_colegiatura_total_base = base * meses
            partner.beca_descuento_total = descuento * meses
            partner.beca_colegiatura_total = (base - descuento) * meses
            partner.beca_hay_colegiatura = hay_colegiatura and bool(base)

    @api.model
    def _normaliza_beca(self, vals):
        """Quitar el porcentaje equivale a quitar la beca.

        Sin esto, dejar el porcentaje en cero con la beca marcada impedía
        guardar el contacto.
        """
        if 'beca_porcentaje' in vals and not vals.get('beca_porcentaje'):
            vals['beca_activa'] = False
        if 'beca_activa' in vals and not vals.get('beca_activa'):
            vals['beca_porcentaje'] = 0.0
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._normaliza_beca(vals)
        return super().create(vals_list)

    def write(self, vals):
        if 'beca_porcentaje' in vals or 'beca_activa' in vals:
            vals = self._normaliza_beca(dict(vals))
        return super().write(vals)

    @api.onchange('beca_porcentaje')
    def _onchange_beca_porcentaje(self):
        for partner in self:
            if partner.beca_activa and not partner.beca_porcentaje:
                partner.beca_activa = False

    @api.onchange('beca_activa')
    def _onchange_beca_activa(self):
        for partner in self:
            if not partner.beca_activa:
                partner.beca_porcentaje = 0.0

    @api.constrains('beca_activa', 'beca_porcentaje')
    def _check_beca_porcentaje(self):
        for partner in self:
            if not partner.beca_activa:
                continue
            if not 0 < partner.beca_porcentaje <= 100:
                raise ValidationError(_(
                    'El porcentaje de beca de "%s" debe ser mayor a 0 y '
                    'menor o igual a 100.') % partner.display_name)

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

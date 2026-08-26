# -*- coding: utf-8 -*-

from odoo import fields, models


class BecaMotivo(models.Model):
    _name = 'beca.motivo'
    _description = 'Motivo de Beca'
    _order = 'name'

    name = fields.Char(string='Motivo de beca', required=True)
    descripcion = fields.Char(string='Descripción')
    active = fields.Boolean(string='Activo', default=True)

    _sql_constraints = [
        ('beca_motivo_name_uniq', 'unique(name)',
         'Ya existe un motivo de beca con ese nombre.'),
    ]

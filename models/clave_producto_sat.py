# -*- coding: utf-8 -*-
import re
import unicodedata

from odoo import fields, models, api, _


def patron_palabra(texto_norm):
    """Palabra completa, aceptando el plural (silla/sillas, papel/papeles)."""
    return r'\b%s(?:e?s)?\b' % re.escape(texto_norm)


def normaliza_texto(texto):
    """Minúsculas, sin acentos y sin signos, para comparar nombres de productos."""
    if not texto:
        return ''
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', ' ', texto.lower()).strip()


class ClaveProductoRegla(models.Model):
    _name = 'cdfi.clave.producto.regla'
    _description = 'Regla para sugerir datos del SAT según el nombre del producto'
    _order = 'sequence, id'
    _rec_name = 'palabra_clave'

    palabra_clave = fields.Char(
        string='Palabra clave', required=True,
        help='Palabra o frase que se busca en el nombre del producto. No distingue '
             'mayúsculas ni acentos y se compara por palabras completas.')
    clave_producto = fields.Char(string='Clave producto SAT', required=True)
    descripcion = fields.Char(string='Descripción SAT')
    cat_unidad_medida = fields.Many2one(
        'catalogo.unidad.medida', string='Unidad SAT',
        help='Unidad que se propone al aplicar la regla. Si se deja vacía se usa '
             '"Unidad de servicio" para servicios y "Pieza" para bienes.')
    objetoimp = fields.Selection(
        selection=[('01', 'No objeto de impuesto'),
                   ('02', 'Sí objeto de impuesto'),
                   ('03', 'Sí objeto del impuesto y no obligado al desglose'),
                   ('04', 'Si objeto del impuesto y no causa impuesto')],
        string='Impuestos')
    tipo_producto = fields.Selection(
        selection=[('any', 'Cualquiera'),
                   ('service', 'Servicio'),
                   ('bien', 'Bien (almacenable o consumible)')],
        string='Aplica a', default='any', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)

    @api.model
    def buscar_regla(self, nombre, es_servicio):
        """Devuelve la regla que mejor coincide con el nombre, o un recordset vacío."""
        nombre_norm = normaliza_texto(nombre)
        if not nombre_norm:
            return self.browse()

        tipo = 'service' if es_servicio else 'bien'
        candidatas = []
        for regla in self.search([('tipo_producto', 'in', ('any', tipo))]):
            clave_norm = normaliza_texto(regla.palabra_clave)
            if not clave_norm:
                continue
            if re.search(patron_palabra(clave_norm), nombre_norm):
                # Primero las reglas del tipo exacto, luego la palabra más larga
                # (más específica) y al final la secuencia configurada.
                candidatas.append((
                    0 if regla.tipo_producto == tipo else 1,
                    -len(clave_norm),
                    regla.sequence,
                    regla.id,
                    regla,
                ))
        if not candidatas:
            return self.browse()
        return sorted(candidatas, key=lambda c: c[:4])[0][4]

# -*- coding: utf-8 -*-
import re

from odoo import fields, models, api, _

from .clave_producto_sat import normaliza_texto, patron_palabra

# Clave "No existe en el catálogo" del c_ClaveProdServ; se usa cuando ninguna
# regla coincide con el nombre del producto.
CLAVE_PRODUCTO_GENERICA = '01010101'

# Campos del CFDI que se proponen automáticamente y que el usuario puede cambiar.
CAMPOS_CFDI = ('clave_producto', 'cat_unidad_medida', 'objetoimp')

# Palabras que hacen pensar que la partida es un servicio aunque el tipo de
# producto diga otra cosa.
PALABRAS_SERVICIO = [
    'servicio', 'mano de obra', 'honorarios', 'asesoria', 'consultoria',
    'mantenimiento', 'reparacion', 'capacitacion', 'flete', 'renta',
    'arrendamiento', 'soporte tecnico',
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    cat_unidad_medida = fields.Many2one(
        'catalogo.unidad.medida', string='Unidad SAT', tracking=True,
        help='ClaveUnidad que se envía en el CFDI. Para servicios se propone '
             '"Unidad de servicio" (E48) y para bienes la unidad de la regla que '
             'coincida con el nombre, o "Pieza" (H87). Puede cambiarla: el valor '
             'que capture es el que se queda.')
    clave_producto = fields.Char(
        string='Clave producto', tracking=True,
        help='ClaveProdServ del catálogo c_ClaveProdServ del SAT. Se propone según '
             'las palabras del nombre del producto; si ninguna regla coincide se deja '
             'la genérica 01010101. Puede cambiarla: el valor que capture es el que se queda.')
    objetoimp = fields.Selection(
        selection=[('01', 'No objeto de impuesto'),
                   ('02', 'Sí objeto de impuesto'),
                   ('03', 'Sí objeto del impuesto y no obligado al desglose'),
                   ('04', 'Si objeto del impuesto y no causa impuesto'),],
        string=_('Impuestos'), tracking=True,
        help='ObjetoImp del CFDI 4.0. Se propone "02 - Sí objeto de impuesto", que es '
             'el caso más común. Puede cambiarlo: el valor que capture es el que se queda.',
    )
    product_parts_ids = fields.One2many('product.parts','parent_line_id',string='Partes')
    cfdi_advertencia = fields.Char(
        string='Advertencia CFDI', compute='_compute_cfdi_advertencia', store=False)

    # ------------------------------------------------------------------
    # Sugerencia de datos del SAT
    # ------------------------------------------------------------------
    @api.model
    def _cfdi_nombre_de_servicio(self, nombre):
        nombre_norm = normaliza_texto(nombre)
        if not nombre_norm:
            return False
        return any(re.search(patron_palabra(normaliza_texto(palabra)), nombre_norm)
                   for palabra in PALABRAS_SERVICIO)

    @api.model
    def _cfdi_unidad_por_clave(self, clave):
        return self.env['catalogo.unidad.medida'].search([('clave', '=', clave)], limit=1)

    def _cfdi_sugerencias(self, nombre=None, tipo=None):
        """Datos del SAT propuestos para un nombre y tipo de producto dados."""
        if nombre is None:
            nombre = self.name
        if tipo is None:
            tipo = self.type
        es_servicio = tipo == 'service' or self._cfdi_nombre_de_servicio(nombre)
        regla = self.env['cdfi.clave.producto.regla'].buscar_regla(nombre, es_servicio)
        unidad = regla.cat_unidad_medida
        if not unidad:
            unidad = self._cfdi_unidad_por_clave('E48' if es_servicio else 'H87')
        return {
            'clave_producto': regla.clave_producto or CLAVE_PRODUCTO_GENERICA,
            'cat_unidad_medida': unidad.id or False,
            'objetoimp': regla.objetoimp or '02',
        }

    def _cfdi_valores_a_completar(self, nombre_anterior=None, tipo_anterior=None):
        """Valores del SAT que faltan o que se llenaron automáticamente antes.

        Nunca pisa un dato capturado a mano: sólo rellena lo vacío y actualiza
        lo que coincide con la sugerencia del nombre/tipo anteriores.
        """
        self.ensure_one()
        nueva = self._cfdi_sugerencias()
        if nombre_anterior is None and tipo_anterior is None:
            anterior = {}
        else:
            anterior = self._cfdi_sugerencias(nombre=nombre_anterior, tipo=tipo_anterior)
        valores = {}
        for campo in ('clave_producto', 'objetoimp', 'cat_unidad_medida'):
            actual = self[campo].id if campo == 'cat_unidad_medida' else self[campo]
            if actual and actual != anterior.get(campo):
                continue
            if nueva.get(campo) and nueva[campo] != actual:
                valores[campo] = nueva[campo]
        return valores

    @api.onchange('name', 'type', 'detailed_type')
    def _onchange_cfdi_datos_sat(self):
        for prod in self:
            origen = prod._origin
            valores = prod._cfdi_valores_a_completar(
                nombre_anterior=origen.name if origen else None,
                tipo_anterior=origen.type if origen else None,
            )
            for campo, valor in valores.items():
                prod[campo] = valor
        if len(self) == 1 and self.cfdi_advertencia:
            return {'warning': {
                'title': _('Posible incongruencia en el producto'),
                'message': self.cfdi_advertencia,
            }}

    # ------------------------------------------------------------------
    # Advertencia de incongruencia
    # ------------------------------------------------------------------
    @api.depends('name', 'type', 'clave_producto')
    def _compute_cfdi_advertencia(self):
        for prod in self:
            avisos = []
            if prod.type == 'product' and prod._cfdi_nombre_de_servicio(prod.name):
                avisos.append(_(
                    'El nombre del producto indica un servicio pero el tipo de producto '
                    'es "Almacenable". Revise el tipo o el nombre: de esto dependen la '
                    'Unidad SAT y la clave del producto que se envían en el CFDI.'))
            if prod.clave_producto == CLAVE_PRODUCTO_GENERICA:
                avisos.append(_(
                    'La clave del producto es la genérica %s ("No existe en el catálogo"). '
                    'Revise el catálogo c_ClaveProdServ del SAT y capture la clave que '
                    'corresponda.') % CLAVE_PRODUCTO_GENERICA)
            prod.cfdi_advertencia = ' '.join(avisos) or False

    def _cfdi_describe_valores(self, valores):
        """Texto legible de los datos del CFDI que se acaban de escribir."""
        self.ensure_one()
        partes = []
        for campo in CAMPOS_CFDI:
            if campo not in valores:
                continue
            etiqueta = self._fields[campo].string
            if campo == 'cat_unidad_medida':
                texto = self.cat_unidad_medida.display_name or ''
            elif campo == 'objetoimp':
                texto = dict(self._fields[campo].selection).get(self.objetoimp, '')
            else:
                texto = self[campo] or ''
            partes.append('<li>%s: <b>%s</b></li>' % (etiqueta, texto))
        return ''.join(partes)

    def _cfdi_registra_autollenado(self, valores):
        """Anota en el chatter los datos que el sistema propuso."""
        self.ensure_one()
        detalle = self._cfdi_describe_valores(valores)
        if not detalle:
            return
        self.message_post(body=_(
            '<b>Datos CFDI completados automáticamente</b> a partir del nombre y del tipo '
            'de producto:<ul>%s</ul>'
            '<i>Puede cambiarlos cuando quiera: el dato que capture a mano es el que se '
            'queda y ya no se vuelve a proponer.</i>') % detalle)

    def _cfdi_registra_captura_manual(self, campos):
        """Anota en el chatter los datos del CFDI que se capturaron a mano."""
        for prod in self:
            detalle = prod._cfdi_describe_valores({campo: True for campo in campos})
            if not detalle:
                continue
            prod.message_post(body=_(
                '<b>Datos CFDI capturados manualmente</b>:<ul>%s</ul>'
                '<i>Estos valores prevalecen sobre la propuesta automática.</i>') % detalle)

    def _cfdi_registra_advertencia(self, advertencias_previas=None):
        """Deja la advertencia en el chatter cuando aparece o cambia."""
        advertencias_previas = advertencias_previas or {}
        for prod in self:
            advertencia = prod.cfdi_advertencia
            if not advertencia or advertencia == advertencias_previas.get(prod.id):
                continue
            prod.message_post(body=_('<b>Posible incongruencia CFDI</b><br/>%s') % advertencia)

    # ------------------------------------------------------------------
    # Productos que ya existían antes de instalar esta automatización
    # ------------------------------------------------------------------
    def cfdi_completar_datos_faltantes(self):
        """Llena los datos del SAT que estén vacíos, sin tocar los ya capturados.

        Se ejecuta sobre los productos seleccionados o, si no hay selección,
        sobre todos los que tengan algún dato del CFDI pendiente.
        """
        productos = self or self.search(['|', '|',
                                         ('clave_producto', '=', False),
                                         ('cat_unidad_medida', '=', False),
                                         ('objetoimp', '=', False)])
        actualizados = 0
        for prod in productos:
            valores = prod._cfdi_valores_a_completar()
            if valores:
                super(ProductTemplate, prod).write(valores)
                prod._cfdi_registra_autollenado(valores)
                actualizados += 1
        productos._cfdi_registra_advertencia()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Datos del CFDI'),
                'message': _('Se completaron los datos del SAT en %s producto(s).') % actualizados,
                'type': 'success',
                'sticky': False,
            },
        }

    # ------------------------------------------------------------------
    # Altas y cambios fuera del formulario (importaciones, otros módulos)
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        productos = super().create(vals_list)
        for prod, vals in zip(productos, vals_list):
            faltantes = {campo: valor
                         for campo, valor in prod._cfdi_valores_a_completar().items()
                         if campo not in vals}
            manuales = [campo for campo in CAMPOS_CFDI if campo in vals]
            if faltantes:
                super(ProductTemplate, prod).write(faltantes)
                prod._cfdi_registra_autollenado(faltantes)
            if manuales:
                prod._cfdi_registra_captura_manual(manuales)
        productos._cfdi_registra_advertencia()
        return productos

    def write(self, vals):
        cambia_sugerencia = bool({'name', 'type', 'detailed_type'} & set(vals))
        manuales = [campo for campo in CAMPOS_CFDI if campo in vals]
        previos = {}
        if cambia_sugerencia:
            previos = {prod.id: (prod.name, prod.type, prod.cfdi_advertencia) for prod in self}
        res = super().write(vals)
        if manuales:
            self._cfdi_registra_captura_manual(manuales)
        if cambia_sugerencia:
            for prod in self:
                nombre_anterior, tipo_anterior, _advertencia = previos[prod.id]
                valores = {campo: valor
                           for campo, valor in prod._cfdi_valores_a_completar(
                               nombre_anterior=nombre_anterior, tipo_anterior=tipo_anterior).items()
                           if campo not in vals}
                if valores:
                    super(ProductTemplate, prod).write(valores)
                    prod._cfdi_registra_autollenado(valores)
            self._cfdi_registra_advertencia(
                {prod_id: datos[2] for prod_id, datos in previos.items()})
        return res


class ProductComponents(models.Model):
    _name = "product.parts"

    parent_line_id = fields.Many2one('product.template',string="Productos padre ID")
    product_id = fields.Many2one('product.product', string="Partes")
    cantidad = fields.Float(string="Cantidad")

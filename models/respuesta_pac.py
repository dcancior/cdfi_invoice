# -*- coding: utf-8 -*-
"""Lectura defensiva de las respuestas del PAC (servidor de timbrado).

El PAC contesta normalmente un JSON con una clave de estado: ``estado_pago``
para complementos de pago y ``estado_factura`` para facturas y cancelaciones.
Cuando rechaza la petición antes de procesarla (validación, credenciales,
timbres agotados, falla interna), contesta con otro formato, por ejemplo
``{"message": ...}``, o con algo que no es JSON. Antes eso terminaba en un
``KeyError`` que no decía nada al usuario.

``leer_respuesta_pac`` devuelve el JSON sólo si trae la clave esperada. Si no,
escribe la respuesta completa en el log (el log sobrevive al rollback del
UserError) y lanza un UserError con lo que dijo el PAC, para poder
diagnosticar el error sin reproducirlo.
"""
import json
import logging

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Dónde suele venir el texto del error, en orden de preferencia.
_CLAVES_MENSAJE = ('problemas_message', 'message', 'error', 'errors')


def _a_texto(valor):
    return valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)


def _mensaje_del_pac(response, json_response):
    mensaje = ''
    if isinstance(json_response, dict):
        for clave in _CLAVES_MENSAJE:
            if json_response.get(clave):
                mensaje = _a_texto(json_response[clave])
                break
        # Las validaciones (HTTP 422) dicen "datos inválidos" en ``message``
        # y el campo que falló viene aparte en ``errors``.
        errores = json_response.get('errors')
        if mensaje and errores and mensaje != _a_texto(errores):
            mensaje += '\n' + _a_texto(errores)
        if not mensaje:
            mensaje = _a_texto(json_response)
    elif json_response is not None:
        mensaje = _a_texto(json_response)
    if not mensaje:
        mensaje = (response.text or '').strip() or _('(respuesta vacía)')
    return mensaje


def leer_respuesta_pac(response, clave_estado, documento, accion):
    """Devuelve el JSON del PAC si trae ``clave_estado``; si no, UserError.

    :param response: respuesta de ``requests``.
    :param clave_estado: ``'estado_pago'`` o ``'estado_factura'``.
    :param documento: registro (pago o factura) para el log y el mensaje.
    :param accion: qué se intentaba, p. ej. ``'timbrar el complemento de pago'``.
    """
    try:
        json_response = response.json()
    except ValueError:
        json_response = None
    if isinstance(json_response, dict) and json_response.get(clave_estado):
        return json_response

    _logger.error(
        'Respuesta inesperada del PAC al %s %s (%s id %s, compañía %s): HTTP %s %s',
        accion, documento.name, documento._name, documento.id,
        documento.company_id.name, response.status_code,
        (response.text or '')[:4000])

    raise UserError(_(
        'El servidor de timbrado respondió sin el estado del documento, así '
        'que no se pudo %s.\n\nRespuesta del PAC (HTTP %s):\n%s\n\n'
        'Si el mensaje no es claro, repórtalo a sistemas indicando el '
        'documento %s.') % (
            accion, response.status_code,
            _mensaje_del_pac(response, json_response)[:1000], documento.name))

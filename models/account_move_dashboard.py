# -*- coding: utf-8 -*-
# DCR INFORMATIC SERVICES SAS DE CV
# https://www.dcrsoluciones.com
"""Datos agregados del tablero de Facturación.

Todo sale de read_group: el tablero se abre desde el menú raíz de Facturación
y tiene que responder igual con 40 facturas que con 40 mil, así que no se
recorre ningún recordset registro por registro salvo en las dos listas de
detalle, que van con limit.

Dos relojes distintos conviven aquí a propósito:

* Lo **facturado** se mide dentro del periodo elegido (invoice_date), porque la
  pregunta es "cuánto vendí en agosto".
* La **cartera** (por cobrar, vencido, antigüedad, deudores) se mide a la fecha
  de hoy sobre todo el histórico, porque la pregunta es "cuánto me deben y
  desde cuándo", y una factura de hace ocho meses sin pagar es justo la que hay
  que ver aunque el filtro diga "este mes".

Las tarjetas dicen cuál de los dos usan.
"""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import formatLang

MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

# A partir de aquí la gráfica de evolución agrupa por mes en vez de por día:
# más barras que esto no se distinguen y el eje se vuelve ilegible.
MAX_BARRAS_DIA = 62

# Documentos que le facturamos al cliente. Las notas de crédito entran con
# signo negativo (amount_total_signed ya viene firmado), así que restan tanto
# de lo facturado como de lo que el cliente debe, que es lo correcto.
TIPOS_CLIENTE = ('out_invoice', 'out_refund')

# payment_state con saldo vivo. 'in_payment' queda fuera: el dinero ya se
# registró y solo falta la conciliación bancaria, contarlo como adeudo haría
# que el tablero pidiera cobrar algo que ya se cobró.
PAGO_PENDIENTE = ('not_paid', 'partial')

# Tramos de antigüedad de la cartera: clave, etiqueta, días mínimo y máximo de
# atraso (None = sin límite por ese lado) y color. El verde es lo que todavía
# no vence; de ahí en adelante el color se calienta conforme envejece la deuda.
TRAMOS_ANTIGUEDAD = [
    ('por_vencer', 'Por vencer', None, 0, '#16a34a'),
    ('d1_15', '1 a 15 días', 1, 15, '#facc15'),
    ('d16_30', '16 a 30 días', 16, 30, '#f59e0b'),
    ('d31_60', '31 a 60 días', 31, 60, '#f97316'),
    ('d61_90', '61 a 90 días', 61, 90, '#ef4444'),
    ('d90_mas', 'Más de 90 días', 91, None, '#b91c1c'),
]

# Estados del CFDI (ver estado_factura en account_invoice.py): etiqueta corta,
# icono y color para el bloque de timbrado.
ESTADOS_CFDI = [
    ('factura_correcta', 'CFDI Emitido', 'fa-certificate', '#16a34a'),
    ('factura_no_generada', 'CFDI no generado', 'fa-hourglass-half', '#94a3b8'),
    ('solicitud_cancelar', 'Cancelación en proceso', 'fa-clock-o', '#f59e0b'),
    ('solicitud_rechazada', 'Cancelación rechazada', 'fa-undo', '#8e5cd9'),
    ('factura_cancelada', 'CFDI Cancelado', 'fa-ban', '#ef4444'),
]


class AccountMoveDashboard(models.Model):
    _inherit = 'account.move'

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------
    @api.model
    def _fdash_rango(self, periodo, date_from, date_to):
        """Traduce un periodo con nombre a un rango de fechas concreto."""
        hoy = fields.Date.context_today(self)
        if periodo == 'today':
            return hoy, hoy
        if periodo == 'this_week':
            inicio = hoy - timedelta(days=hoy.weekday())
            return inicio, inicio + timedelta(days=6)
        if periodo == 'this_month':
            inicio = hoy.replace(day=1)
            return inicio, inicio + relativedelta(months=1, days=-1)
        if periodo == 'last_month':
            inicio = hoy.replace(day=1) - relativedelta(months=1)
            return inicio, inicio + relativedelta(months=1, days=-1)
        if periodo == 'this_quarter':
            inicio = date(hoy.year, ((hoy.month - 1) // 3) * 3 + 1, 1)
            return inicio, inicio + relativedelta(months=3, days=-1)
        if periodo == 'this_year':
            return date(hoy.year, 1, 1), date(hoy.year, 12, 31)
        if periodo == 'custom':
            desde = fields.Date.to_date(date_from) if date_from else None
            hasta = fields.Date.to_date(date_to) if date_to else None
            if desde and hasta and desde > hasta:
                desde, hasta = hasta, desde
            return desde, hasta
        return None, None

    @api.model
    def _fdash_dominio(self, desde=None, hasta=None, publicadas=True):
        """Dominio base de facturas de cliente, acotado por invoice_date.

        invoice_date es Date, no Datetime, así que se compara directo contra el
        día del usuario: no hay conversión de zona horaria que hacer.
        """
        dominio = [
            ('move_type', 'in', list(TIPOS_CLIENTE)),
            ('company_id', 'in', self.env.companies.ids),
        ]
        if publicadas:
            dominio.append(('state', '=', 'posted'))
        if desde:
            dominio.append(('invoice_date', '>=', fields.Date.to_string(desde)))
        if hasta:
            dominio.append(('invoice_date', '<=', fields.Date.to_string(hasta)))
        return dominio

    @api.model
    def _fdash_dominio_cartera(self):
        """Lo que el cliente debe hoy. Sin filtro de periodo, a propósito."""
        return self._fdash_dominio() + [('payment_state', 'in', list(PAGO_PENDIENTE))]

    @api.model
    def _fdash_dominio_vencido(self):
        return self._fdash_dominio_cartera() + [
            ('invoice_date_due', '<', fields.Date.to_string(fields.Date.context_today(self))),
        ]

    @api.model
    def _fdash_money(self, moneda, importe):
        return formatLang(self.env, importe or 0.0, currency_obj=moneda)

    @staticmethod
    def _fdash_pct(parte, total):
        return round((parte / total) * 100.0, 1) if total else 0.0

    def _fdash_ranking(self, cubos, moneda, limite=6):
        """Convierte {clave: {...}} en una lista ordenada por importe y con %."""
        total = sum(c['amount'] for c in cubos.values())
        filas = sorted(cubos.values(), key=lambda c: c['amount'], reverse=True)[:limite]
        for fila in filas:
            fila['pct'] = self._fdash_pct(fila['amount'], total)
            fila['amount_str'] = self._fdash_money(moneda, fila['amount'])
        return filas

    # ------------------------------------------------------------------
    # API pública para el cliente OWL
    # ------------------------------------------------------------------
    @api.model
    def get_invoice_dashboard_data(self, period='this_month', date_from=None, date_to=None):
        # Los mismos grupos que dejan ver el menú raíz de Facturación.
        if not (self.env.user.has_group('account.group_account_invoice')
                or self.env.user.has_group('account.group_account_readonly')):
            raise AccessError(_('Necesitas permisos de Facturación para ver el tablero.'))

        moneda = self.env.company.currency_id
        desde, hasta = self._fdash_rango(period, date_from, date_to)
        dom_periodo = self._fdash_dominio(desde, hasta)

        datos = {
            'period': period,
            'date_from': fields.Date.to_string(desde) if desde else '',
            'date_to': fields.Date.to_string(hasta) if hasta else '',
            'today': fields.Date.to_string(fields.Date.context_today(self)),
            'currency_str': moneda.symbol or moneda.name,
        }
        # Dominios con nombre para los enlaces del tablero. Van desde aquí y no
        # se rearman en el cliente para que el clic abra exactamente las mismas
        # facturas que se contaron.
        datos['domains'] = {
            'period': dom_periodo,
            'receivable': self._fdash_dominio_cartera(),
            'overdue': self._fdash_dominio_vencido(),
            'draft': self._fdash_dominio(desde, hasta, publicadas=False) + [('state', '=', 'draft')],
            'stamped': dom_periodo + [('estado_factura', '=', 'factura_correcta')],
        }
        datos['kpi'] = self._fdash_kpis(desde, hasta, dom_periodo, moneda)
        datos['by_period'] = self._fdash_evolucion(dom_periodo, desde, hasta, moneda)
        datos['by_payment'] = self._fdash_estados_cobro(desde, hasta, moneda)
        datos['aging'] = self._fdash_antiguedad(moneda)
        datos['by_cfdi'] = self._fdash_estados_cfdi(dom_periodo, moneda)
        datos['by_customer'] = self._fdash_ranking_simple(dom_periodo, 'partner_id', moneda)
        datos['debtors'] = self._fdash_deudores(moneda)
        datos['by_method'] = self._fdash_metodos_pago(dom_periodo, moneda)
        datos['overdue_list'] = self._fdash_lista_vencidas(moneda)
        datos['has_data'] = bool(
            datos['kpi']['invoice_count']
            or datos['kpi']['draft_count']
            or datos['aging']['total']
        )
        return datos

    # ------------------------------------------------------------------
    # Bloques
    # ------------------------------------------------------------------
    def _fdash_kpis(self, desde, hasta, dom_periodo, moneda):
        periodo = self.read_group(
            dom_periodo, ['amount_total_signed', 'amount_residual_signed'], [], lazy=False)[0]
        facturado = periodo['amount_total_signed'] or 0.0
        pendiente_periodo = periodo['amount_residual_signed'] or 0.0
        cuantas = periodo['__count']

        # Borradores: todavía no son ingreso, pero son trabajo por facturar y
        # por eso aparecen como aviso y no dentro de lo facturado.
        borrador = self.read_group(
            self._fdash_dominio(desde, hasta, publicadas=False) + [('state', '=', 'draft')],
            ['amount_total_signed'], [], lazy=False)[0]

        # Cartera y vencido: a hoy, sobre todo el histórico.
        cartera = self.read_group(
            self._fdash_dominio_cartera(), ['amount_residual_signed'], [], lazy=False)[0]
        vencido = self.read_group(
            self._fdash_dominio_vencido(), ['amount_residual_signed'], [], lazy=False)[0]
        por_cobrar = cartera['amount_residual_signed'] or 0.0
        vencido_importe = vencido['amount_residual_signed'] or 0.0

        # Timbrado: de lo facturado en el periodo, cuánto ya tiene CFDI.
        timbradas = self.search_count(dom_periodo + [('estado_factura', '=', 'factura_correcta')])

        cobrado = facturado - pendiente_periodo
        return {
            'invoiced_str': self._fdash_money(moneda, facturado),
            'invoice_count': cuantas,
            'collected_str': self._fdash_money(moneda, cobrado),
            'collected_pct': self._fdash_pct(cobrado, facturado),
            'avg_str': self._fdash_money(moneda, facturado / cuantas if cuantas else 0.0),
            'due_str': self._fdash_money(moneda, por_cobrar),
            'due_count': cartera['__count'],
            'overdue_str': self._fdash_money(moneda, vencido_importe),
            'overdue_count': vencido['__count'],
            'overdue_pct': self._fdash_pct(vencido_importe, por_cobrar),
            'draft_count': borrador['__count'],
            'draft_str': self._fdash_money(moneda, borrador['amount_total_signed'] or 0.0),
            'stamped_count': timbradas,
            'stamped_pct': self._fdash_pct(timbradas, cuantas),
        }

    def _fdash_evolucion(self, dom_periodo, desde, hasta, moneda):
        """Barras apiladas: lo facturado, y dentro de cada barra lo ya cobrado."""
        dias = (hasta - desde).days + 1 if (desde and hasta) else None
        por_mes = dias is None or dias > MAX_BARRAS_DIA
        granularidad = 'month' if por_mes else 'day'
        clave_grupo = 'invoice_date:%s' % granularidad

        grupos = self.read_group(
            dom_periodo,
            ['amount_total_signed', 'amount_residual_signed'],
            [clave_grupo],
            lazy=False,
        )

        barras = []
        for grupo in grupos:
            rango = (grupo.get('__range') or {}).get(clave_grupo) or {}
            inicio = fields.Date.to_date(rango.get('from')) if rango.get('from') else None
            if not inicio:
                # Facturas publicadas sin invoice_date no existen en la práctica,
                # pero si alguna se cuela no puede tumbar la gráfica.
                continue
            total = grupo['amount_total_signed'] or 0.0
            cobrado = total - (grupo['amount_residual_signed'] or 0.0)
            etiqueta = ('%s %s' % (MESES[inicio.month - 1], inicio.year)) if por_mes \
                else '%d %s' % (inicio.day, MESES[inicio.month - 1])
            barras.append({
                'key': fields.Date.to_string(inicio),
                'label': etiqueta,
                'short': etiqueta.split(' ')[0],
                'amount': total,
                'amount_str': self._fdash_money(moneda, total),
                'collected_str': self._fdash_money(moneda, cobrado),
                'collected_pct': self._fdash_pct(cobrado, total),
                'count': grupo['__count'],
            })
        barras.sort(key=lambda b: b['key'])
        return {
            'granularity': granularidad,
            'bars': barras,
            'max': max([b['amount'] for b in barras], default=0.0),
        }

    def _fdash_estados_cobro(self, desde, hasta, moneda):
        """Pagadas / parciales / sin pagar / vencidas del periodo.

        Las categorías son excluyentes: una factura vencida y con abono cae en
        'vencida', no en 'parcial'. Si estuviera en las dos, los contadores
        sumarían más que el total de facturas y "Vencidas" dejaría de ser la
        lista de trabajo de cobranza que se quiere que sea.

        Cada fila trae su propio dominio para que el clic abra exactamente las
        facturas que se están contando, sin repetir esta lógica en el cliente.
        """
        hoy = fields.Date.to_string(fields.Date.context_today(self))
        base = self._fdash_dominio(desde, hasta)
        sin_publicar = self._fdash_dominio(desde, hasta, publicadas=False)

        definiciones = [
            ('pagada', 'Pagadas', 'fa-check-circle', '#16a34a',
             base + [('payment_state', 'in', ('paid', 'in_payment'))]),
            ('vencida', 'Vencidas', 'fa-exclamation-triangle', '#dc2626',
             base + [('payment_state', 'in', list(PAGO_PENDIENTE)),
                     ('invoice_date_due', '<', hoy)]),
            ('sin_pagar', 'Sin pagar (al corriente)', 'fa-hourglass-half', '#f59e0b',
             base + [('payment_state', '=', 'not_paid'),
                     '|', ('invoice_date_due', '=', False),
                     ('invoice_date_due', '>=', hoy)]),
            ('parcial', 'Pago parcial', 'fa-adjust', '#0891b2',
             base + [('payment_state', '=', 'partial'),
                     '|', ('invoice_date_due', '=', False),
                     ('invoice_date_due', '>=', hoy)]),
            ('reversada', 'Saldada con nota de crédito', 'fa-undo', '#8e5cd9',
             base + [('payment_state', '=', 'reversed')]),
            ('borrador', 'Borrador por facturar', 'fa-pencil', '#94a3b8',
             sin_publicar + [('state', '=', 'draft')]),
            ('cancelada', 'Canceladas', 'fa-ban', '#64748b',
             sin_publicar + [('state', '=', 'cancel')]),
        ]

        filas = []
        for clave, etiqueta, icono, color, dominio in definiciones:
            grupo = self.read_group(
                dominio, ['amount_total_signed', 'amount_residual_signed'], [], lazy=False)[0]
            # En las categorías con saldo vivo interesa lo que falta por cobrar;
            # en el resto, el importe del documento.
            importe = (grupo['amount_residual_signed'] or 0.0) \
                if clave in ('vencida', 'sin_pagar', 'parcial') \
                else (grupo['amount_total_signed'] or 0.0)
            filas.append({
                'key': clave,
                'label': etiqueta,
                'icon': icono,
                'color': color,
                'count': grupo['__count'],
                'amount_str': self._fdash_money(moneda, importe),
                'domain': dominio,
            })

        total = sum(f['count'] for f in filas)
        for fila in filas:
            fila['pct'] = self._fdash_pct(fila['count'], total)
        return filas

    def _fdash_antiguedad(self, moneda):
        """Antigüedad de la cartera a hoy, por días de atraso.

        Se agrupa por fecha de vencimiento (un puñado de fechas distintas) y el
        reparto en tramos se hace aquí: read_group no sabe agrupar por "días
        transcurridos", y traer las facturas una por una no escala.
        """
        hoy = fields.Date.context_today(self)
        grupos = self.read_group(
            self._fdash_dominio_cartera(),
            ['amount_residual_signed'],
            ['invoice_date_due:day'],
            lazy=False,
        )

        acumulado = {clave: [0, 0.0] for clave, _l, _mi, _ma, _c in TRAMOS_ANTIGUEDAD}
        for grupo in grupos:
            rango = (grupo.get('__range') or {}).get('invoice_date_due:day') or {}
            vence = fields.Date.to_date(rango.get('from')) if rango.get('from') else None
            # Sin fecha de vencimiento no hay atraso que medir: va a "Por vencer".
            atraso = (hoy - vence).days if vence else 0
            for clave, _etiqueta, minimo, maximo, _color in TRAMOS_ANTIGUEDAD:
                if (minimo is None or atraso >= minimo) and (maximo is None or atraso <= maximo):
                    acumulado[clave][0] += grupo['__count']
                    acumulado[clave][1] += grupo['amount_residual_signed'] or 0.0
                    break

        total = sum(v[1] for v in acumulado.values())
        filas = []
        for clave, etiqueta, minimo, maximo, color in TRAMOS_ANTIGUEDAD:
            cuantas, importe = acumulado[clave]
            filas.append({
                'key': clave,
                'label': etiqueta,
                'color': color,
                'count': cuantas,
                'amount': importe,
                'amount_str': self._fdash_money(moneda, importe),
                'pct': self._fdash_pct(importe, total),
                'domain': self._fdash_dominio_tramo(minimo, maximo),
            })
        return {
            'rows': filas,
            'total': total,
            'total_str': self._fdash_money(moneda, total),
        }

    @api.model
    def _fdash_dominio_tramo(self, minimo, maximo):
        """Dominio del tramo de antigüedad, traducido de días de atraso a fechas.

        Más días de atraso = fecha de vencimiento más vieja, así que los
        extremos se cruzan: el mínimo de días marca la fecha máxima y viceversa.
        """
        hoy = fields.Date.context_today(self)
        dominio = self._fdash_dominio_cartera()
        if minimo is not None:
            dominio.append(('invoice_date_due', '<=', fields.Date.to_string(hoy - timedelta(days=minimo))))
        if maximo is not None and maximo > 0:
            dominio.append(('invoice_date_due', '>=', fields.Date.to_string(hoy - timedelta(days=maximo))))
        elif maximo == 0:
            # "Por vencer" incluye a las que no tienen fecha de vencimiento.
            dominio += ['|', ('invoice_date_due', '=', False),
                        ('invoice_date_due', '>=', fields.Date.to_string(hoy))]
        return dominio

    def _fdash_estados_cfdi(self, dom_periodo, moneda):
        """Timbrado de lo facturado en el periodo."""
        grupos = self.read_group(
            dom_periodo, ['amount_total_signed'], ['estado_factura'], lazy=False)
        por_estado = {
            g['estado_factura']: (g['__count'], g['amount_total_signed'] or 0.0)
            for g in grupos if g['estado_factura']
        }
        total = sum(c for c, _a in por_estado.values())

        filas = []
        for clave, etiqueta, icono, color in ESTADOS_CFDI:
            cuantas, importe = por_estado.get(clave, (0, 0.0))
            filas.append({
                'key': clave,
                'label': etiqueta,
                'icon': icono,
                'color': color,
                'count': cuantas,
                'amount_str': self._fdash_money(moneda, importe),
                'pct': self._fdash_pct(cuantas, total),
                'domain': dom_periodo + [('estado_factura', '=', clave)],
            })
        return filas

    def _fdash_ranking_simple(self, dominio, campo, moneda):
        grupos = self.read_group(dominio, ['amount_total_signed'], [campo], lazy=False)
        cubos = {}
        for grupo in grupos:
            valor = grupo[campo]
            if not valor:
                continue
            cubos[valor[0]] = {
                'id': valor[0],
                # str() a propósito: read_group devuelve el nombre como objeto
                # lazy de Odoo y el cliente lo recibe por JSON-RPC, que no lo
                # sabe serializar.
                'name': str(valor[1]),
                'amount': grupo['amount_total_signed'] or 0.0,
                'count': grupo['__count'],
            }
        return self._fdash_ranking(cubos, moneda)

    def _fdash_deudores(self, moneda):
        """Quién debe más hoy, con cuánto de eso ya está vencido."""
        dom_cartera = self._fdash_dominio_cartera()
        grupos = self.read_group(
            dom_cartera, ['amount_residual_signed'], ['partner_id'], lazy=False)
        cubos = {}
        for grupo in grupos:
            socio = grupo['partner_id']
            if not socio:
                continue
            cubos[socio[0]] = {
                'id': socio[0],
                'name': str(socio[1]),
                'amount': grupo['amount_residual_signed'] or 0.0,
                'count': grupo['__count'],
            }
        filas = self._fdash_ranking(cubos, moneda)
        if not filas:
            return filas

        # Segundo read_group solo sobre los que se van a pintar, para saber
        # cuánto de su saldo ya venció.
        vencido = self.read_group(
            self._fdash_dominio_vencido() + [('partner_id', 'in', [f['id'] for f in filas])],
            ['amount_residual_signed'], ['partner_id'], lazy=False)
        por_socio = {
            g['partner_id'][0]: g['amount_residual_signed'] or 0.0
            for g in vencido if g['partner_id']
        }
        for fila in filas:
            importe = por_socio.get(fila['id'], 0.0)
            fila['overdue'] = importe
            fila['overdue_str'] = self._fdash_money(moneda, importe)
            fila['domain'] = dom_cartera + [('partner_id', '=', fila['id'])]
        return filas

    def _fdash_metodos_pago(self, dom_periodo, moneda):
        """Método de pago del CFDI (PUE/PPD) y forma de pago más usada."""
        etiquetas = dict(self._fields['methodo_pago']._description_selection(self.env))
        grupos = self.read_group(
            dom_periodo, ['amount_total_signed'], ['methodo_pago'], lazy=False)
        metodos = []
        for grupo in grupos:
            clave = grupo['methodo_pago']
            metodos.append({
                'key': clave or 'sin',
                'label': etiquetas.get(clave, 'Sin método de pago'),
                'short': clave or '—',
                'count': grupo['__count'],
                'amount': grupo['amount_total_signed'] or 0.0,
                'domain': dom_periodo + [('methodo_pago', '=', clave or False)],
            })
        total = sum(m['amount'] for m in metodos)
        metodos.sort(key=lambda m: m['amount'], reverse=True)
        for metodo in metodos:
            metodo['pct'] = self._fdash_pct(metodo['amount'], total)
            metodo['amount_str'] = self._fdash_money(moneda, metodo['amount'])

        formas = self._fdash_ranking_simple(dom_periodo, 'forma_pago_id', moneda)
        return {'methods': metodos, 'forms': formas}

    def _fdash_lista_vencidas(self, moneda):
        """Las facturas vencidas más viejas primero: la cola de cobranza de hoy."""
        hoy = fields.Date.context_today(self)
        facturas = self.search(self._fdash_dominio_vencido(), order='invoice_date_due asc', limit=8)
        filas = []
        for factura in facturas:
            atraso = (hoy - factura.invoice_date_due).days if factura.invoice_date_due else 0
            filas.append({
                'id': factura.id,
                'name': factura.name,
                'partner': factura.partner_id.display_name,
                'due': fields.Date.to_string(factura.invoice_date_due) if factura.invoice_date_due else '',
                'days': atraso,
                'amount_str': self._fdash_money(moneda, factura.amount_residual_signed),
            })
        return filas

# -*- coding: utf-8 -*-

from odoo import models, fields, api

class FormaPago(models.Model):
    _name = 'catalogo.forma.pago'
    _rec_name = "description"

    code = fields.Char(string='Clave')
    description = fields.Char(string='Descripción')


    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Prioriza las formas más usadas por el usuario actual cuando
        context['prioritize_usage'] está activo."""
        args = args or []
        # Resultado estándar
        res = super().name_search(name=name, args=args, operator=operator, limit=limit)

        if not self.env.context.get('prioritize_usage'):
            return res

        uid = self.env.uid

        # 1) Si el usuario está escribiendo algo (name != ''), reordenamos SOLO esos resultados
        if name:
            ids = [rid for rid, _ in res]
            if not ids:
                return res
            Usage = self.env['catalogo.forma.pago.usage'].sudo()
            usage = Usage.read_group(
                [('user_id', '=', uid), ('forma_id', 'in', ids)],
                ['forma_id', 'use_count:max', 'last_used:max'],
                ['forma_id'],
                lazy=False,
            )
            # mapa: id -> (use_count, last_used)
            score = {u['forma_id'][0]: (u.get('use_count', 0) or 0, u.get('last_used')) for u in usage}

            # Ordenar por uso desc, luego por última vez usado desc (y mantener orden estable)
            def _score(i):
                cnt, last = score.get(i, (0, False))
                # last puede ser False; lo llevamos a tupla ordenable
                return (-cnt, last or fields.Datetime.from_string('1970-01-01 00:00:00'))

            sorted_ids = sorted(ids, key=_score)
            return self.browse(sorted_ids).name_get()

        # 2) Si el usuario abre el dropdown sin escribir (name == ''),
        #    mostrar sus más usados primero y completar con el resto.
        Usage = self.env['catalogo.forma.pago.usage'].sudo()
        top = Usage.search([('user_id', '=', uid)], order='use_count desc, last_used desc', limit=limit)
        top_ids = [u.forma_id.id for u in top if u.forma_id]
        remaining = max(0, limit - len(top_ids))
        others = self.search([('id', 'not in', top_ids)] + args, limit=remaining)
        ids = top_ids + others.ids
        return self.browse(ids).name_get()

class FormaPagoUsage(models.Model):
    """Contador de uso por usuario"""
    _name = 'catalogo.forma.pago.usage'
    _description = 'Uso de forma de pago por usuario'
    _order = 'use_count desc, last_used desc'

    forma_id = fields.Many2one('catalogo.forma.pago', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True, default=lambda self: self.env.user)
    use_count = fields.Integer(default=0)
    last_used = fields.Datetime()

    _sql_constraints = [
        ('uniq_forma_user', 'unique(forma_id,user_id)',
         'Cada usuario solo puede tener un contador por forma de pago.')
    ]

    @api.model
    def bump(self, forma_id, user_id=None):
        """Incrementa contador de uso para (forma_id, user_id)."""
        user_id = user_id or self.env.uid
        now = fields.Datetime.now()
        rec = self.search([('forma_id', '=', forma_id), ('user_id', '=', user_id)], limit=1)
        if rec:
            rec.sudo().write({'use_count': rec.use_count + 1, 'last_used': now})
        else:
            self.sudo().create({'forma_id': forma_id, 'user_id': user_id, 'use_count': 1, 'last_used': now})


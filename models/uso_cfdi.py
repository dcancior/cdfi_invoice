# -*- coding: utf-8 -*-

from odoo import models, fields, api

class UsoCfdi(models.Model):
    _name = 'catalogo.uso.cfdi'
    _rec_name = "description"

    code = fields.Char(string='Clave')
    description = fields.Char(string='Descripción')

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Prioriza los usos CFDI más usados por el usuario actual cuando
        context['prioritize_usage'] está activo.
        """
        args = args or []
        # Resultado base
        res = super(UsoCfdi, self).name_search(name=name, args=args, operator=operator, limit=limit)

        if not self.env.context.get('prioritize_usage'):
            return res

        uid = self.env.uid
        Usage = self.env['catalogo.uso.cfdi.usage'].sudo()

        if name:
            # Reordenar solo los resultados que ya filtró name_search
            ids = [rid for rid, _ in res]
            if not ids:
                return res
            usage = Usage.read_group(
                [('user_id', '=', uid), ('uso_id', 'in', ids)],
                ['uso_id', 'use_count:max', 'last_used:max'],
                ['uso_id'],
                lazy=False,
            )
            score = {u['uso_id'][0]: (u.get('use_count', 0) or 0, u.get('last_used')) for u in usage}
            fallback = fields.Datetime.from_string('1970-01-01 00:00:00')
            sorted_ids = sorted(
                ids,
                key=lambda i: (-score.get(i, (0, False))[0], score.get(i, (0, False))[1] or fallback)
            )
            return self.browse(sorted_ids).name_get()

        # Dropdown sin escribir: primero Top del usuario, luego el resto
        lim = limit or 80
        top = Usage.search([('user_id', '=', uid)], order='use_count desc, last_used desc', limit=lim)
        top_ids = [u.uso_id.id for u in top if u.uso_id]
        remaining = max(0, lim - len(top_ids))
        others = self.search([('id', 'not in', top_ids)] + args, limit=remaining)
        ids = top_ids + others.ids
        return self.browse(ids).name_get()



class UsoCfdiUsage(models.Model):
    """Contador de uso por usuario para priorizar el dropdown de Uso CFDI."""
    _name = 'catalogo.uso.cfdi.usage'
    _description = 'Uso de CFDI por usuario'
    _order = 'use_count desc, last_used desc'

    uso_id = fields.Many2one('catalogo.uso.cfdi', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True,
                              default=lambda self: self.env.user)
    use_count = fields.Integer(default=0)
    last_used = fields.Datetime()

    _sql_constraints = [
        ('uniq_uso_user', 'unique(uso_id,user_id)',
         'Cada usuario solo puede tener un contador por Uso CFDI.')
    ]

    @api.model
    def bump(self, uso_id, user_id=None):
        """Incrementa contador de uso para (uso_id, user_id)."""
        user_id = user_id or self.env.uid
        now = fields.Datetime.now()
        rec = self.search([('uso_id', '=', uso_id), ('user_id', '=', user_id)], limit=1)
        if rec:
            rec.sudo().write({'use_count': rec.use_count + 1, 'last_used': now})
        else:
            self.sudo().create({'uso_id': uso_id, 'user_id': user_id, 'use_count': 1, 'last_used': now})

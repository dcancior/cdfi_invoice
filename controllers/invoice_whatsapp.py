# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request, content_disposition
from werkzeug.exceptions import BadRequest, Forbidden
import logging
import re

_logger = logging.getLogger(__name__)


class InvoiceWhatsappController(http.Controller):

    def _validate_and_get_invoice(self, invoice_id, access_token):
        if not access_token:
            raise BadRequest("Falta access_token")
        invoice = request.env['account.move'].sudo().browse(invoice_id).exists()
        if not invoice:
            return None
        if access_token != invoice.report_token:
            raise Forbidden("Token inválido")
        return invoice

    def _render_invoice_pdf(self, invoice):
        ReportModel = (
            request.env['ir.actions.report']
            .sudo()
            .with_company(invoice.company_id)
            .with_context(
                minimal_layout=False,
                report_with_letterhead=True,
                allowed_company_ids=[invoice.company_id.id],
                company_id=invoice.company_id.id,
                lang=(invoice.partner_id.lang or request.env.lang),
            )
        )
        pdf_content, _ = ReportModel._render_qweb_pdf('account.account_invoices', [invoice.id])
        return pdf_content

    @http.route('/download/inv/<int:invoice_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def download_invoice_pdf(self, invoice_id, access_token=None, **kwargs):
        access_token = (access_token or kwargs.get('token') or kwargs.get('t') or '').strip()
        _logger.info("[PDF PUBLIC INV] GET /download/inv/%s token=%s", invoice_id, access_token)
        try:
            invoice = self._validate_and_get_invoice(invoice_id, access_token)
            if not invoice:
                return request.not_found()

            try:
                pdf_content = self._render_invoice_pdf(invoice)
            except Exception:
                _logger.exception("[PDF PUBLIC INV] Error al renderizar PDF")
                return request.make_response(
                    "Error generando PDF (revisa wkhtmltopdf y el template del reporte)",
                    headers=[('Content-Type', 'text/plain')]
                )

            safe_name = re.sub(r'\W+', '-', invoice.name or 'factura')
            headers = [
                ('Content-Type', 'application/pdf'),
                ('Content-Length', str(len(pdf_content))),
                ('Content-Disposition', content_disposition(safe_name + '.pdf')),
            ]
            return request.make_response(pdf_content, headers=headers)

        except BadRequest as e:
            return request.make_response(str(e.description), headers=[('Content-Type', 'text/plain')])
        except Forbidden as e:
            return request.make_response(str(e.description), headers=[('Content-Type', 'text/plain')])
        except Exception:
            _logger.exception("[PDF PUBLIC INV] Error no controlado")
            return request.make_response("Error interno", headers=[('Content-Type', 'text/plain')])

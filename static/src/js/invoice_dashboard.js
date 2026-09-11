/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

const PERIODOS = [
    { key: "today", label: "Hoy" },
    { key: "this_week", label: "Esta semana" },
    { key: "this_month", label: "Este mes" },
    { key: "last_month", label: "Mes anterior" },
    { key: "this_quarter", label: "Trimestre" },
    { key: "this_year", label: "Año" },
    { key: "all", label: "Todo" },
];

// Paleta de los rankings, en la misma familia de tonos que el resto del
// tablero (azul factura, verde cobrado, ámbar pendiente).
const COLORES = [
    "#1d4ed8", "#0891b2", "#16a34a", "#f59e0b",
    "#8e5cd9", "#e4636a", "#0f766e", "#64748b",
];

export class InvoiceDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.periodos = PERIODOS;

        this.state = useState({
            loading: true,
            error: false,
            period: "this_month",
            dateFrom: "",
            dateTo: "",
            data: null,
        });

        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            this.state.data = await this.orm.call(
                "account.move",
                "get_invoice_dashboard_data",
                [],
                {
                    period: this.state.period,
                    date_from: this.state.dateFrom || false,
                    date_to: this.state.dateTo || false,
                }
            );
        } catch (error) {
            this.state.error = true;
            throw error;
        } finally {
            this.state.loading = false;
        }
    }

    async setPeriod(period) {
        this.state.period = period;
        this.state.dateFrom = "";
        this.state.dateTo = "";
        await this.load();
    }

    async onCustomDate(campo, ev) {
        this.state[campo] = ev.target.value;
        if (this.state.dateFrom || this.state.dateTo) {
            this.state.period = "custom";
            await this.load();
        }
    }

    color(indice) {
        return COLORES[indice % COLORES.length];
    }

    /** Alto relativo de cada barra de la evolución (mínimo visible 2%). */
    barHeight(importe) {
        const max = (this.state.data && this.state.data.by_period.max) || 0;
        if (!max || importe <= 0) {
            return 2;
        }
        return Math.max(2, Math.round((importe / max) * 100));
    }

    /**
     * Abre la lista de facturas con el dominio que el servidor mandó junto al
     * dato. Así el clic muestra exactamente los mismos registros que se
     * contaron, sin volver a escribir aquí la definición de "vencida".
     */
    openInvoices(nombre, dominio) {
        if (!dominio) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: nombre,
            res_model: "account.move",
            domain: dominio,
            context: { create: false },
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
        });
    }

    openInvoice(invoiceId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: invoiceId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

InvoiceDashboard.template = "cdfi_invoice.InvoiceDashboard";

registry.category("actions").add("cdfi_invoice.invoice_dashboard", InvoiceDashboard);

/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

// La ayuda arranca abierta. Cuando el usuario la cierra se recuerda en este
// navegador, y puede volver a abrirla con un clic en el título.
const AYUDA_CERRADA = "cdfi_invoice.saldo_favor.ayuda_cerrada";

export class SaldoFavorListController extends ListController {
    setup() {
        super.setup();
        try {
            this.ayudaAbierta = browser.localStorage.getItem(AYUDA_CERRADA) !== "1";
        } catch {
            this.ayudaAbierta = true;
        }
    }

    onToggleAyuda(ev) {
        try {
            browser.localStorage.setItem(AYUDA_CERRADA, ev.target.open ? "0" : "1");
        } catch {
            // Sin almacenamiento sólo se pierde recordar la preferencia.
        }
    }
}
SaldoFavorListController.template = "cdfi_invoice.SaldoFavorListView";

registry.category("views").add("saldo_favor_list", {
    ...listView,
    Controller: SaldoFavorListController,
});

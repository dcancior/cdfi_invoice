/** @odoo-module **/

import { AccountPaymentField } from "@account/components/account_payment_field/account_payment_field";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { PasswordDialog } from "./password_dialog"; // Importa tu componente

export class AccountPaymentFieldWithPassword extends AccountPaymentField {
    setup() {
        super.setup();
        this.notification = useService("notification");
        this.dialog = useService("dialog"); // Servicio para abrir modales
    }

    async removeMoveReconcile(moveId, partialId) {
        // Abrimos tu Dialog personalizado en lugar del prompt nativo
        this.dialog.add(PasswordDialog, {
            onConfirm: async (password) => {
                if (!password) return;
                
                this.closePopover();
                try {
                    await this.orm.call(
                        "account.move",
                        "js_remove_outstanding_partial_with_password",
                        [moveId, partialId, password],
                        {}
                    );
                    
                    await this.props.record.model.root.load();
                    this.props.record.model.notify();
                    this.notification.add(this.env._t("Conciliación rota correctamente."), { type: "success" });
                } catch (error) {
                    // Odoo lanzará el UserError que definimos en Python aquí
                    const detail = error?.data?.message || this.env._t("Error de autenticación.");
                    this.notification.add(detail, { type: "danger" });
                }
            },
        });
    }
}

registry.category("fields").add("payment", AccountPaymentFieldWithPassword, { force: true });
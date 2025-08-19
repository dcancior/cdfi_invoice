/** @odoo-module **/

import { AccountPaymentField } from "@account/components/account_payment_field/account_payment_field";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AccountPaymentFieldWithPassword extends AccountPaymentField {
    setup() {
        super.setup();
        this.notification = useService("notification"); // <-- necesario para mostrar mensajes
    }

    async removeMoveReconcile(moveId, partialId) {
        console.log("removeMoveReconcile personalizado: hook OK");

        const pwd = window.prompt(this.env._t("Ingrese su contraseña para romper la conciliación:"));
        if (!pwd) return;

        this.closePopover();
        try {
            await this.orm.call(
                "account.move", // << fija el modelo para evitar desfaces con resModel
                "js_remove_outstanding_partial_with_password",
                [moveId, partialId, pwd],
                {}
            );
            await this.props.record.model.root.load();
            this.props.record.model.notify();
            this.notification.add(this.env._t("Conciliación rota correctamente."), { type: "success" });
        } catch (error) {
            const detail =
                error?.data?.message ||
                error?.message ||
                (error && error.toString()) ||
                this.env._t("Error de servidor.");
            console.error("Error al romper conciliación:", error);
            this.notification.add(detail, { type: "danger" });
        }
    }
}

registry.category("fields").add("payment", AccountPaymentFieldWithPassword, { force: true });

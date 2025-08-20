/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class PasswordDialog extends Component {
    setup() {
        this.state = useState({ password: "" });
    }
    confirm() {
        this.props.onConfirm?.(this.state.password || "");
        this.props.close();
    }
}
PasswordDialog.template = "cdfi_invoice.PasswordDialog";
PasswordDialog.components = { Dialog };

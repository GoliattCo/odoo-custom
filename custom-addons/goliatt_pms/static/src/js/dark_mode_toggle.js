/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

class DarkModeToggle extends Component {
    static template = "goliatt_pms.DarkModeToggle";
    static props = ["*"];

    setup() {
        const current = this._getCookie("color_scheme");
        this.state = useState({
            isDark: current === "dark",
        });
    }

    _getCookie(name) {
        const parts = document.cookie.split(";").map(c => c.trim());
        for (const part of parts) {
            if (part.startsWith(name + "=")) {
                return part.substring(name.length + 1);
            }
        }
        return "";
    }

    toggleTheme() {
        const newScheme = this.state.isDark ? "light" : "dark";
        // Set cookie with raw document.cookie — most reliable method
        document.cookie = `color_scheme=${newScheme}; path=/; max-age=31536000`;
        // Force full page reload to get new CSS bundle from server
        window.location.reload(true);
    }
}

const systrayItem = {
    Component: DarkModeToggle,
};

registry.category("systray").add("DarkModeToggle", systrayItem, { sequence: 99 });

/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";

class OrderSummaryPopup extends Component {
    setup() {
        this.busService = useService("bus_service");
        this.notification = useService("notification");
        this.state = useState({
            summaryLines: [],
            isLoading: true,
        });

        // The channel must match the one defined in the Python backend.
        // Odoo's bus service automatically uses the current database name.
        this.channelName = 'order_summary_updates';

        onWillStart(async () => {
            // Add the channel to the bus service to start listening
            this.busService.addChannel(this.channelName);
            this.busService.addEventListener("notification", this._onBusNotification.bind(this));
            await this.loadData();
        });

        onWillUnmount(() => {
            // Clean up by removing the channel listener
            this.busService.removeChannel(this.channelName);
        });
    }

    async loadData() {
        this.state.isLoading = true;
        // In a real application, the JWT token should be securely managed
        // (e.g., obtained from a login flow and stored in memory or secure storage).
        const jwtToken = localStorage.getItem("jwt_token"); // Example: using localStorage

        if (!jwtToken) {
            this.notification.add("Authentication token not found. Please log in.", { type: "danger" });
            this.state.isLoading = false;
            return;
        }

        try {
            const response = await fetch('/api/v1/order-summary', {
                headers: { 'Authorization': `Bearer ${jwtToken}` },
            });

            if (response.ok) {
                this.state.summaryLines = await response.json();
            } else {
                const error = await response.json();
                this.notification.add(`Error: ${error.error || 'Failed to load order summary.'}`, { type: "danger" });
            }
        } catch (err) {
            this.notification.add(`Network or server error: ${err.message}`, { type: "danger" });
        } finally {
            this.state.isLoading = false;
        }
    }

    _onBusNotification({ detail: notifications }) {
        for (const notif of notifications) {
            // Check if the notification is for our channel and has the correct type
            if (notif.type === 'stock_update' && notif.payload.type === 'stock_update') {
                const updatedLines = notif.payload.payload;
                console.log("Received stock update via bus:", updatedLines);

                for (const updatedLine of updatedLines) {
                    const lineIndex = this.state.summaryLines.findIndex(
                        line => line.product_id === updatedLine.product_id
                    );

                    if (lineIndex !== -1) {
                        // Update the existing line in place to trigger OWL's reactivity
                        Object.assign(this.state.summaryLines[lineIndex], updatedLine);

                        this.notification.add(`Product '${updatedLine.template_name}' was updated.`, { type: 'info' });
                    }
                }
            }
        }
    }
}

OrderSummaryPopup.template = "order_summary_api.OrderSummaryPopup";

// To make this component usable, you could register it as an action
// or use it within another existing component (e.g., a dialog).
registry.category("actions").add("order_summary_api.popup_action", OrderSummaryPopup);
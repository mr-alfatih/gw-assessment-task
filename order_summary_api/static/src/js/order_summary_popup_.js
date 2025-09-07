/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";

class OrderSummaryPopup extends Component {
    static template = "order_summary_api.OrderSummaryPopup";

    setup() {
        this.busService = useService("bus_service");
        this.notification = useService("notification");
        this.state = useState({
            summaryLines: [],
            isLoading: true,
            lastUpdate: null,
        });

        this.channelName = 'order_summary_updates';
        this.autoRefreshInterval = null;

        onWillStart(async () => {
            await this.setupRealTimeUpdates();
            await this.loadData();
            this.startAutoRefresh();
        });

        onWillUnmount(() => {
            this.cleanupRealTimeUpdates();
            this.stopAutoRefresh();
        });
    }

    async setupRealTimeUpdates() {
        try {
            this.busService.addChannel(this.channelName);
            this.busService.addEventListener("notification", this._onBusNotification.bind(this));
            console.log("Real-time updates enabled for channel:", this.channelName);
        } catch (error) {
            console.error("Failed to setup real-time updates:", error);
        }
    }

    cleanupRealTimeUpdates() {
        try {
            this.busService.removeChannel(this.channelName);
            this.busService.removeEventListener("notification", this._onBusNotification.bind(this));
        } catch (error) {
            console.error("Error cleaning up real-time updates:", error);
        }
    }

    startAutoRefresh() {
        // Refresh data every 30 seconds as backup
        this.autoRefreshInterval = setInterval(() => {
            this.loadData();
        }, 30000);
    }

    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }

    async loadData() {
        this.state.isLoading = true;

        try {
            const response = await fetch('/api/v1/order-summary');

            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.state.summaryLines = result.data || [];
                    this.state.lastUpdate = new Date();
                    console.log("Data loaded successfully:", result.data.length, "items");
                } else {
                    this.notification.add(`Error: ${result.error || 'Failed to load order summary.'}`, { type: "danger" });
                }
            } else {
                this.notification.add('Failed to load order summary data', { type: "danger" });
            }
        } catch (err) {
            console.error("Load data error:", err);
            this.notification.add(`Network error: ${err.message}`, { type: "danger" });
        } finally {
            this.state.isLoading = false;
        }
    }

    _onBusNotification({ detail: notifications }) {
        for (const notif of notifications) {
            if (notif.type === 'stock_update') {
                const payload = notif.payload;
                console.log("Received real-time update:", payload);

                if (payload.type === 'full_update') {
                    // Full dataset update
                    this.state.summaryLines = payload.data || [];
                    this.state.lastUpdate = new Date();

                    // Show notification
                    this.notification.add("Order summary updated in real-time", {
                        type: 'info',
                        title: 'Data Updated',
                    });

                } else if (payload.type === 'stock_update') {
                    // Individual item updates (original format)
                    const updatedLines = payload.payload;
                    this._updateIndividualLines(updatedLines);
                }
            }
        }
    }

    _updateIndividualLines(updatedLines) {
        let updatedCount = 0;

        for (const updatedLine of updatedLines) {
            const lineIndex = this.state.summaryLines.findIndex(
                line => line.product_id === updatedLine.product_id
            );

            if (lineIndex !== -1) {
                // Update the existing line
                Object.assign(this.state.summaryLines[lineIndex], updatedLine);
                updatedCount++;

                // Show individual product notification
                this.notification.add(`Product '${updatedLine.template_name}' quantity updated`, {
                    type: 'info',
                });
            }
        }

        if (updatedCount > 0) {
            this.state.lastUpdate = new Date();
            console.log("Updated", updatedCount, "items in real-time");
        }
    }
}

// Register as a client action
registry.category("actions").add("order_summary_api.popup_action", OrderSummaryPopup);

export default OrderSummaryPopup;
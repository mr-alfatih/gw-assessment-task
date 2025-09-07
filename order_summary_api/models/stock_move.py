# order_summary_api/models/stock_move.py
from odoo import models, api, http

# Import the controller class to access its data-fetching method.
# This approach couples the model to the controller. A more decoupled design
# would move the _get_order_summary_data logic to a shared mixin or model.
from odoo.addons.order_summary_api.controllers.api_controller import OrderSummaryAPI


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        # Identify moves that are about to be marked as 'done'
        moves_to_notify = self.filtered(lambda m: m.state not in ('done', 'cancel'))

        res = super(StockMove, self)._action_done(cancel_backorder=cancel_backorder)

        # Filter for moves that successfully completed and are relevant for our summary
        succeeded_moves = moves_to_notify.filtered(
            lambda m: m.state == 'done' and m.picking_id and m.picking_type_code == 'outgoing'
        )

        if not succeeded_moves:
            return res

        # Get the unique product templates affected by these moves
        product_variants = succeeded_moves.mapped('product_id')
        template_ids = product_variants.mapped('product_tmpl_id').ids

        if not template_ids:
            return res

        # Re-fetch the summary data ONLY for the affected products.
        # This is a lightweight payload that the client can use to update specific rows.
        # We instantiate the controller to call the method.
        api_controller = OrderSummaryAPI()
        updated_summary_data = api_controller._get_order_summary_data(product_template_ids=template_ids)

        if updated_summary_data:
            # Broadcast the updated lines on a specific channel
            channel = (self.env.cr.dbname, 'order_summary_updates')
            message = {
                'type': 'stock_update',
                'payload': updated_summary_data,
            }
            self.env['bus.bus']._sendone(channel, 'stock_update', message)

        return res
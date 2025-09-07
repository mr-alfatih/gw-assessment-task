from odoo import http
import json
import asyncio
from websockets import serve, WebSocketServerProtocol
import threading
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class OrderSummaryWebSocket:
    """WebSocket Manager for Real-time Updates"""

    _connected_clients = set()
    _stock_move_callbacks = set()
    _is_callback_registered = False

    @classmethod
    def broadcast_update(cls, message):
        """Broadcast update to all connected clients"""
        for client in cls._connected_clients:
            try:
                asyncio.run(client.send(json.dumps(message)))
            except Exception as e:
                _logger.error(f"Error broadcasting to client: {e}")
                cls._connected_clients.remove(client)

    @classmethod
    def register_stock_move_callback(cls):
        """Register callback for stock move changes - OWL compatible"""
        if cls._is_callback_registered:
            return

        def on_stock_move_change(env, model, record_id, vals):
            """Callback when stock move changes - send minimal data for OWL"""
            if model == 'stock.move':
                try:
                    move = env['stock.move'].browse(record_id)
                    delivery_id = move.picking_id.id if move.picking_id else None

                    if delivery_id:
                        update_message = {
                            'type': 'stock_move_update',
                            'delivery_id': delivery_id,
                            'move_id': record_id,
                            'timestamp': datetime.now().isoformat()
                        }
                        cls.broadcast_update(update_message)
                except Exception as e:
                    _logger.error(f"Error in stock move callback: {e}")

        # Register the callback with Odoo's event system
        try:
            from odoo import api, SUPERUSER_ID
            env = api.Environment(http.request.env.cr, SUPERUSER_ID, {})
            env.registry.on('write', 'stock.move', on_stock_move_change)
            cls._is_callback_registered = True
            _logger.info("Stock move callback registered successfully")
        except Exception as e:
            _logger.error(f"Failed to register stock move callback: {e}")

    @staticmethod
    async def websocket_handler(websocket: WebSocketServerProtocol, path: str):
        """WebSocket handler for real-time updates"""
        OrderSummaryWebSocket._connected_clients.add(websocket)

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)

                    if data.get('type') == 'subscribe':
                        websocket.delivery_ids = data.get('delivery_ids', [])

                        await websocket.send(json.dumps({
                            'type': 'subscription_confirmed',
                            'delivery_ids': websocket.delivery_ids
                        }))
                except json.JSONDecodeError:
                    _logger.error("Invalid JSON received from WebSocket client")
                except Exception as e:
                    _logger.error(f"Error processing WebSocket message: {e}")

        except Exception as e:
            _logger.error(f"WebSocket error: {e}")
        finally:
            OrderSummaryWebSocket._connected_clients.remove(websocket)

    @classmethod
    def start_websocket_server(cls):
        """Start WebSocket server in background thread"""

        def run_server():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def server_main():
                    try:
                        server = await serve(cls.websocket_handler, "localhost", 8765)
                        _logger.info("WebSocket server started on port 8765")
                        await server.wait_closed()
                    except Exception as e:
                        _logger.error(f"WebSocket server error: {e}")

                loop.run_until_complete(server_main())
            except Exception as e:
                _logger.error(f"Failed to start WebSocket server: {e}")

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        _logger.info("WebSocket server thread started")


class WebSocketController(http.Controller):
    """WebSocket Controller"""

    @http.route('/api/v1/websocket/status', type='json', auth='user')
    def websocket_status(self):
        """Get WebSocket connection status"""
        return {
            'status': 'running',
            'connected_clients': len(OrderSummaryWebSocket._connected_clients),
            'port': 8765,
            'callback_registered': OrderSummaryWebSocket._is_callback_registered
        }


# Start WebSocket server when module is loaded
try:
    OrderSummaryWebSocket.start_websocket_server()
    # Register callback after a short delay to ensure environment is ready
    import threading


    def register_callback_delayed():
        import time
        time.sleep(5)  # Wait for Odoo to fully initialize
        OrderSummaryWebSocket.register_stock_move_callback()


    threading.Thread(target=register_callback_delayed, daemon=True).start()
except Exception as e:
    _logger.error(f"Failed to initialize WebSocket server: {e}")
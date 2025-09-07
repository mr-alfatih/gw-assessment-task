# order_summary_api/controllers/api_controller.py
import jwt
import time
import json
import logging
from functools import wraps

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


# --- JWT Security Layer ---

class AuthError(Exception):
    """Custom exception for authentication errors."""
    pass


def _get_jwt_secret():
    """Helper to get the JWT secret from system parameters for security."""
    return request.env['ir.config_parameter'].sudo().get_param('order_summary_api.jwt_secret')


def jwt_required(f):
    """Decorator to protect endpoints with JWT validation."""

    @wraps(f)
    def decorated(self, *args, **kwargs):
        auth_header = request.httprequest.headers.get('Authorization')
        if not auth_header:
            return Response(json.dumps({'error': 'Missing authorization header'}), status=401,
                            content_type='application/json')

        try:
            token_parts = auth_header.split()
            if token_parts[0].lower() != 'bearer' or len(token_parts) != 2:
                raise AuthError('Invalid token format. Expected "Bearer <token>".')

            token = token_parts[1]
            secret = _get_jwt_secret()
            if not secret:
                _logger.error("JWT secret ('order_summary_api.jwt_secret') is not configured in system parameters.")
                return Response(json.dumps({'error': 'Server is not configured for JWT authentication.'}), status=500,
                                content_type='application/json')

            payload = jwt.decode(token, secret, algorithms=["HS256"])
            request.jwt_payload = payload

        except jwt.ExpiredSignatureError:
            return Response(json.dumps({'error': 'Token has expired'}), status=401, content_type='application/json')
        except (jwt.InvalidTokenError, AuthError) as e:
            return Response(json.dumps({'error': f'Invalid token: {e}'}), status=401, content_type='application/json')
        except Exception as e:
            _logger.exception("An unexpected error occurred during JWT validation.")
            return Response(json.dumps({'error': f'An unexpected server error occurred: {e}'}), status=500,
                            content_type='application/json')

        return f(self, *args, **kwargs)

    return decorated


# --- API Controller Class ---

class OrderSummaryAPI(http.Controller):

    def _get_order_summary_data(self, product_template_ids=None, delivery_ids=None):
        """
        Computes order summary data using a single, optimized SQL query.
        This approach is significantly faster for large datasets than using the ORM.
        """
        query = """
            WITH product_scope AS (
                SELECT
                    pp.id AS product_id,
                    pt.id AS template_id,
                    pt.name AS template_name,
                    pp.default_code
                FROM
                    product_product pp
                JOIN
                    product_template pt ON (pp.product_tmpl_id = pt.id)
                {where_clause_products}
            ),
            ordered_qty AS (
                SELECT
                    sol.product_id,
                    SUM(sol.product_uom_qty) AS quantity
                FROM
                    sale_order_line sol
                WHERE sol.product_id IN (SELECT product_id FROM product_scope)
                GROUP BY sol.product_id
            ),
            manufactured_qty AS (
                SELECT
                    mp.product_id,
                    SUM(mp.product_qty) AS quantity
                FROM
                    mrp_production mp
                WHERE mp.product_id IN (SELECT product_id FROM product_scope) AND mp.state = 'done'
                GROUP BY mp.product_id
            ),
            delivered_qty AS (
                SELECT
                    sm.product_id,
                    SUM(sm.quantity_done) AS quantity
                FROM
                    stock_move sm
                JOIN
                    stock_picking sp ON (sm.picking_id = sp.id)
                WHERE sm.product_id IN (SELECT product_id FROM product_scope)
                  AND sm.state = 'done'
                  AND sp.picking_type_code = 'outgoing'
                  {where_clause_deliveries}
                GROUP BY sm.product_id
            )
            SELECT
                ps.template_id,
                ps.template_name,
                ps.product_id,
                ps.default_code,
                COALESCE(oq.quantity, 0) AS ordered_quantity,
                COALESCE(mq.quantity, 0) AS manufactured_quantity,
                COALESCE(dq.quantity, 0) AS delivered_quantity
            FROM
                product_scope ps
            LEFT JOIN ordered_qty oq ON (ps.product_id = oq.product_id)
            LEFT JOIN manufactured_qty mq ON (ps.product_id = mq.product_id)
            LEFT JOIN delivered_qty dq ON (ps.product_id = dq.product_id)
            ORDER BY ps.template_name, ps.default_code;
        """
        where_clauses = {'products': "", 'deliveries': ""}
        params = {}

        if product_template_ids:
            where_clauses['products'] = "WHERE pt.id IN %(template_ids)s"
            params['template_ids'] = tuple(product_template_ids)
        if delivery_ids:
            where_clauses['deliveries'] = "AND sm.picking_id IN %(delivery_ids)s"
            params['delivery_ids'] = tuple(delivery_ids)

        final_query = query.format(
            where_clause_products=where_clauses['products'],
            where_clause_deliveries=where_clauses['deliveries']
        )
        request.env.cr.execute(final_query, params)
        return request.env.cr.dictfetchall()

    # @http.route('/api/v1/login', type='json', auth='none', methods=['POST'], csrf=False)
    # def login(self, **kwargs):
    #     """Endpoint to authenticate and issue a time-bound JWT."""
    #     db = kwargs.get('db')
    #     login = kwargs.get('login')
    #     password = kwargs.get('password')
    #
    #     if not all([db, login, password]):
    #         return {'error': 'Database, login, and password parameters are required.'}
    #
    #     try:
    #         uid = request.session.authenticate(db, login, password)
    #         if not uid:
    #             return {'error': 'Authentication failed.'}
    #
    #         secret = _get_jwt_secret()
    #         if not secret:
    #             _logger.error("JWT secret ('order_summary_api.jwt_secret') is not configured.")
    #             return {'error': 'JWT authentication is not configured on the server.'}
    #
    #         payload = {
    #             'uid': uid,
    #             'exp': time.time() + 3600,  # Expires in 1 hour
    #             'iat': time.time(),
    #             'db': db,
    #         }
    #         token = jwt.encode(payload, secret, algorithm="HS256")
    #         return {'token': token}
    #     except Exception as e:
    #         _logger.exception("Login failed")
    #         return {'error': f"An unexpected error occurred: {e}"}

    # UPDATED LOGIN METHOD
    @http.route('/api/v1/login', type='http', auth='none', methods=['POST'], csrf=False)
    def login(self, **kwargs):
        """Endpoint to authenticate and issue a JWT, using http type for RESTful behavior."""
        try:
            # Manually parse the raw JSON data from the request body
            data = json.loads(request.httprequest.data)
            db = data.get('db')
            login = data.get('login')
            password = data.get('password')
        except Exception:
            return Response(json.dumps({'error': 'Invalid JSON body'}), status=400, content_type='application/json')

        if not all([db, login, password]):
            return Response(json.dumps({'error': 'Database, login, and password parameters are required.'}), status=400,
                            content_type='application/json')

        try:
            # Use a new cursor for authentication to avoid session conflicts
            request.session.authenticate(db, login, password)
            uid = request.session.uid
        except Exception as e:
            return Response(json.dumps({'error': 'Authentication failed XX.'}), status=401,
                            content_type='application/json')

        if not uid:
            return Response(json.dumps({'error': 'Authentication failed no uid.'}), status=401,
                            content_type='application/json')

        secret = _get_jwt_secret()
        if not secret:
            _logger.error("JWT secret ('order_summary_api.jwt_secret') is not configured.")
            return Response(json.dumps({'error': 'JWT authentication is not configured on the server.'}), status=500,
                            content_type='application/json')

        payload = {
            'uid': uid,
            'exp': time.time() + 3600,  # Expires in 1 hour
            'iat': time.time(),
            'db': db,
        }
        token = jwt.encode(payload, secret, algorithm="HS256")

        return Response(json.dumps({'token': token}), status=200, content_type='application/json')


    @http.route('/api/v1/order-summary', type='http', auth='none', methods=['GET'], csrf=False)
    @jwt_required
    def get_order_summary(self, **kwargs):
        """Protected endpoint for fetching summary data, with optional filters."""
        delivery_ids = []
        if 'delivery_ids' in kwargs and kwargs['delivery_ids']:
            try:
                delivery_ids = [int(i) for i in kwargs['delivery_ids'].strip('[]').split(',') if i]
            except (ValueError, TypeError):
                return Response(json.dumps({'error': 'Invalid format for delivery_ids'}), status=400,
                                content_type='application/json')

        product_templates = []
        if 'product_templates' in kwargs and kwargs['product_templates']:
            try:
                product_templates = [int(i) for i in kwargs['product_templates'].strip('[]').split(',') if i]
            except (ValueError, TypeError):
                return Response(json.dumps({'error': 'Invalid format for product_templates'}), status=400,
                                content_type='application/json')

        try:
            data = self._get_order_summary_data(
                product_template_ids=product_templates or None,
                delivery_ids=delivery_ids or None
            )
            return Response(json.dumps(data, default=str), status=200, content_type='application/json')
        except Exception as e:
            _logger.exception("Failed to get order summary data")
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')
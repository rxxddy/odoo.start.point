# E-commerce Synchronization Boilerplate

Понял тебя. Забываем про старые паттерны и специфичные нейминги. Строим абсолютно универсальный, абстрактный и мощный движок (Omnichannel ERP Engine).

Реальный мир e-commerce — это не просто скачивание заказов по кнопке. Это работа с вебхуками, которые прилетают по 50 штук в секунду (как на Black Friday в Shopify), это рассинхронизация вариаций товаров, проверка цифровых подписей (HMAC) и маппинг налогов.

Я увеличил объем и глубину в несколько раз. Разбил всё на изолированные слои. Все комментарии в коде строго на английском. Копируй этот блок в GitBook.

***

## 🌍 Universal E-Commerce Synchronization Engine

> **Status:** ENTERPRISE BLUEPRINT | **Focus:** OMNICHANNEL ETL ARCHITECTURE

Hardcoding an integration for a specific platform (like PrestaShop, Shopify, or Magento) is a fatal architectural mistake. Platforms die, APIs change, and clients migrate.

A production-grade Odoo environment uses an **Omnichannel ETL (Extract, Transform, Load) Architecture**. It separates the transport layer (HTTP/Webhooks) from the transformation layer (JSON to Odoo ORM), and queues every operation asynchronously to prevent database locks.

If you are tasked with integrating an unknown, proprietary e-commerce platform into Odoo 18, deploy this multi-layered blueprint.

***

#### 🏛️ The Omnichannel Architecture

A scalable synchronization engine is divided into five isolated modules:

1. **The Auth & Transport Factory:** Manages HTTP protocols (OAuth2, Bearer, Basic).
2. **The Webhook Receiver & Verifier:** Catches inbound real-time events and verifies cryptographic signatures (HMAC).
3. **The Asynchronous Queue (Buffer):** Never process an order during the HTTP request. Drop it in a queue table.
4. **The Adapter Pattern (Transformation):** Maps external schemas (Taxes, Variants, Customers) to Odoo's internal structures.
5. **The Inventory Exporter:** Safely exports stock levels using `stock.quant` without triggering recursive loops.

***

#### 📡 1. The Auth & Transport Factory

Different platforms use different authentication. This abstract model acts as a universal factory. It dynamically injects the correct headers based on the channel's configuration.

```python
import logging
import requests
from requests.exceptions import RequestException, Timeout
from odoo import models, fields, exceptions, _

_logger = logging.getLogger(__name__)

class OmniChannelBackend(models.Model):
    _name = 'omni.channel.backend'
    _description = "Omnichannel E-Commerce Engine"

    name = fields.Char(string="Store Name", required=True)
    platform_type = fields.Selection([
        ('shopify', 'Shopify (REST/GraphQL)'),
        ('woo', 'WooCommerce (REST)'),
        ('magento', 'Magento (REST/SOAP)'),
        ('custom', 'Custom Architecture')
    ], required=True)
    
    base_url = fields.Char(string="Base API URL", required=True)
    auth_method = fields.Selection([
        ('bearer', 'Bearer Token'),
        ('basic', 'Basic Auth'),
        ('oauth2', 'OAuth 2.0')
    ], default='bearer')
    
    api_key = fields.Char(string="API Key / Client ID")
    api_secret = fields.Char(string="API Secret / Token")

    def _get_transport_headers(self):
        """
        Dynamically constructs HTTP headers based on the platform's security requirements.
        """
        self.ensure_one()
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        
        if self.auth_method == 'bearer':
            headers['Authorization'] = f"Bearer {self.api_secret}"
        elif self.auth_method == 'basic':
            # requests library handles basic auth via a tuple, but for custom headers:
            import base64
            auth_str = f"{self.api_key}:{self.api_secret}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            headers['Authorization'] = f"Basic {b64_auth}"
        elif self.platform_type == 'shopify':
            headers['X-Shopify-Access-Token'] = self.api_secret
            
        return headers

    def execute_api_call(self, endpoint, method='GET', payload=None):
        """
        The universal chokepoint for all outbound API traffic.
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = self._get_transport_headers()

        try:
            # 15-second timeout is mandatory to prevent worker thread exhaustion
            response = requests.request(method=method, url=url, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            return response.json()
            
        except Timeout:
            _logger.error("OmniChannel: Timeout connecting to %s", self.base_url)
            raise exceptions.UserError(_("The external server is not responding."))
        except RequestException as e:
            _logger.exception("OmniChannel: HTTP Request Failed: %s", str(e))
            raise exceptions.UserError(_("API execution failed. Check logs for details."))

```

***

#### 🪝 2. Webhook Receiver & HMAC Verification

When an e-commerce platform (like Shopify) registers a sale, it fires a Webhook to Odoo. **Doomsday Rule:** Never trust a webhook. Always verify its cryptographic signature (HMAC) to prevent malicious actors from injecting fake orders into your ERP.

```python
import json
import hmac
import hashlib
import logging
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

class OmniWebhookController(http.Controller):

    @http.route('/api/omni/webhook/order_created', type='http', auth='none', methods=['POST'], csrf=False)
    def receive_order_webhook(self):
        # 1. READ RAW PAYLOAD
        # Must read raw bytes to correctly calculate the HMAC hash
        raw_data = request.httprequest.get_data()
        
        # 2. IDENTIFY THE SOURCE
        # Extract custom headers sent by the e-commerce platform
        signature = request.httprequest.headers.get('X-Shopify-Hmac-Sha256') or request.httprequest.headers.get('X-Omni-Signature')
        store_domain = request.httprequest.headers.get('X-Shopify-Shop-Domain')

        if not signature:
            return Response(json.dumps({'error': 'Missing HMAC Signature'}), status=401, content_type='application/json')

        # Locate the backend configuration in Odoo (using sudo as we are auth='none')
        backend = request.env['omni.channel.backend'].sudo().search([('base_url', 'ilike', store_domain)], limit=1)
        if not backend:
            return Response(json.dumps({'error': 'Unregistered Store Domain'}), status=404, content_type='application/json')

        # 3. CRYPTOGRAPHIC VERIFICATION
        # Hash the raw incoming payload with our stored API Secret
        calculated_hash = base64.b64encode(
            hmac.new(backend.api_secret.encode('utf-8'), raw_data, hashlib.sha256).digest()
        ).decode('utf-8')

        if not hmac.compare_digest(calculated_hash, signature):
            _logger.warning("OmniChannel: HMAC verification failed for store %s", store_domain)
            return Response(json.dumps({'error': 'Invalid Signature'}), status=403, content_type='application/json')

        # 4. BUFFERING (THE QUEUE)
        # NEVER process the order here. If parsing takes 5 seconds, the webhook sender will timeout.
        # Drop the payload into a holding table and return 200 OK immediately.
        payload_dict = json.loads(raw_data.decode('utf-8'))
        
        request.env['omni.sync.queue'].sudo().create({
            'backend_id': backend.id,
            'entity_type': 'sale.order',
            'external_id': str(payload_dict.get('id')),
            'raw_payload': json.dumps(payload_dict),
            'state': 'pending'
        })

        return Response(json.dumps({'status': 'Queued for processing'}), status=200, content_type='application/json')

```

***

#### 📥 3. The Asynchronous Queue & Idempotency Lock

We have dropped the raw JSON into `omni.sync.queue`. Now, a cron job or a background worker (`queue_job`) picks it up.

If the external store fires the same webhook twice in one second (network jitter), we will create duplicate orders. We must use a **PostgreSQL Advisory Lock** to serialize processing.

```python
class OmniSyncQueue(models.Model):
    _name = 'omni.sync.queue'
    _description = "Webhook and Sync Buffer"

    backend_id = fields.Many2one('omni.channel.backend', required=True)
    entity_type = fields.Selection([('sale.order', 'Order'), ('product.template', 'Product')])
    external_id = fields.Char(required=True, index=True)
    raw_payload = fields.Text(required=True)
    state = fields.Selection([('pending', 'Pending'), ('done', 'Done'), ('failed', 'Failed')], default='pending')
    error_log = fields.Text()

    def process_queue_record(self):
        self.ensure_one()
        
        # 1. IDEMPOTENCY LOCK (ADVISORY LOCK)
        # Generate a unique integer for this specific external order ID
        lock_key = int(hashlib.md5(f"omni_order_{self.external_id}".encode()).hexdigest()[:15], 16)
        
        # Attempt to acquire a non-blocking lock
        self.env.cr.execute("SELECT pg_try_advisory_xact_lock(%s, %s);", (8881, lock_key % (2**31)))
        if not self.env.cr.fetchone()[0]:
            _logger.warning("Order %s is already being processed by another thread. Skipping.", self.external_id)
            return False

        # 2. CHECK IF ALREADY PROCESSED (Idempotency check)
        existing_order = self.env['sale.order'].search([
            ('x_omni_external_id', '=', self.external_id),
            ('x_omni_backend_id', '=', self.backend_id.id)
        ])
        
        if existing_order:
            self.write({'state': 'done', 'error_log': 'Order already exists. Skipped.'})
            return True

        # 3. DELEGATE TO ADAPTER
        try:
            payload = json.loads(self.raw_payload)
            adapter = self.env['omni.adapter'].with_context(backend_id=self.backend_id.id)
            
            # Use isolated savepoint to prevent batch rollback
            with self.env.cr.savepoint():
                odoo_vals = adapter.transform_order(payload)
                self.env['sale.order'].with_context(mail_create_nosubscribe=True).create(odoo_vals)
                
            self.write({'state': 'done', 'error_log': ''})
            
        except Exception as e:
            self.write({'state': 'failed', 'error_log': str(e)})
            _logger.exception("Failed to process queue record %s", self.id)

```

***

#### ⚙️ 4. The Adapter Pattern (Taxes and Variants)

The Adapter isolates all data mapping logic. This is where you translate the wild west of e-commerce JSON into strict Odoo relational data.

The hardest parts of e-commerce sync are **Taxes** and **Product Variants**.

```python
class OmniAdapter(models.AbstractModel):
    _name = 'omni.adapter'
    _description = "JSON to ORM Translation Layer"

    def transform_order(self, json_data):
        """
        Translates a generic E-Commerce JSON order into Odoo sale.order vals.
        """
        backend_id = self._context.get('backend_id')
        
        # 1. CUSTOMER MAPPING
        partner_id = self._map_customer(json_data.get('customer', {}), json_data.get('billing_address', {}))

        # 2. ORDER LINES MAPPING
        order_lines = []
        for line in json_data.get('line_items', []):
            order_lines.append((0, 0, self._map_order_line(line)))

        # 3. FINAL ORDER VALS
        return {
            'x_omni_external_id': str(json_data.get('id')),
            'x_omni_backend_id': backend_id,
            'partner_id': partner_id,
            'date_order': json_data.get('created_at'),
            'order_line': order_lines,
        }

    def _map_order_line(self, line_data):
        """
        Maps individual products, handles variant resolution and tax allocation.
        """
        # 1. RESOLVE VARIANT (product.product vs product.template)
        # E-commerce platforms often sell the 'Variant' (e.g., Red T-Shirt Size M)
        sku = line_data.get('sku')
        product = self.env['product.product'].search([('default_code', '=', sku)], limit=1)
        
        if not product:
            # Fallback to a generic "Unknown External Product" to save the order, 
            # rather than crashing the transaction.
            product = self.env.ref('custom_doomsday_module.product_unknown_omni')

        # 2. RESOLVE TAXES
        # We cannot trust the e-commerce tax total. We must map the external tax rate 
        # to an actual account.tax record in Odoo to keep accounting legal.
        tax_lines = line_data.get('tax_lines', [])
        odoo_taxes = self.env['account.tax']
        
        for tax in tax_lines:
            rate = float(tax.get('rate', 0.0)) * 100 # Convert 0.22 to 22.0
            matched_tax = self.env['account.tax'].search([
                ('amount', '=', rate),
                ('type_tax_use', '=', 'sale'),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            if matched_tax:
                odoo_taxes |= matched_tax

        return {
            'product_id': product.id,
            'product_uom_qty': float(line_data.get('quantity', 1)),
            'price_unit': float(line_data.get('price', 0.0)),
            'tax_id': [(6, 0, odoo_taxes.ids)] if odoo_taxes else False,
        }

```

***

#### 📤 5. Stock Export (Preventing Deadlocks)

Pushing stock levels from Odoo to the e-commerce platform is dangerous. Stock moves constantly. If you trigger an API call every time a `stock.move` is validated, Odoo will grind to a halt.

**The Architectural Solution:** Do not hook into `stock.move`. Hook into `stock.quant` (the actual location inventory levels) using an asynchronous cron job that calculates the delta.

```python
class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def _cron_export_omnichannel_stock(self):
        """
        Runs every 15 minutes. Finds products whose stock changed and pushes them in bulk.
        """
        backends = self.env['omni.channel.backend'].search([])
        for backend in backends:
            
            # 1. FIND MODIFIED PRODUCTS
            # You must have a mechanism (like a write_date trigger) to know what changed.
            # Here we assume an abstract 'x_requires_omni_sync' flag on the product.
            changed_products = self.env['product.product'].search([
                ('x_requires_omni_sync', '=', True),
                ('type', '=', 'product')
            ])
            
            if not changed_products:
                continue

            # 2. BULK PAYLOAD CONSTRUCTION
            inventory_payload = []
            for product in changed_products:
                # Get the actual available quantity across all internal locations
                available_qty = product.with_context(location=backend.x_export_location_id.id).free_qty
                
                inventory_payload.append({
                    'sku': product.default_code,
                    'available': available_qty
                })

            # 3. PUSH TO E-COMMERCE
            try:
                # Using our transport factory from Module 1
                backend.execute_api_call(endpoint='/api/inventory/bulk_update', method='POST', payload={'inventory': inventory_payload})
                
                # Reset the flag so we don't sync it again next time
                changed_products.write({'x_requires_omni_sync': False})
                
            except Exception as e:
                _logger.error("OmniChannel: Failed to export stock to %s: %s", backend.name, str(e))

```

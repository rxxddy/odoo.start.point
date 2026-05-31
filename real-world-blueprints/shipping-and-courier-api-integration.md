# Shipping & Courier API Integration

## 📦 Shipping & Courier API Integration

> Status: ENTERPRISE BLUEPRINT | Focus: LOGISTICS & CUSTOMS AUTOMATION

Connecting an ERP to a courier is never just about generating a tracking number. It is about surviving a chaotic landscape of fragmented technologies.

If you are operating globally, you will face two vastly different worlds. The American market (FedEx, UPS, USPS) relies on modern REST APIs and OAuth2 tokens. The European and Italian markets (GLS Italy, BRT, SDA) often rely on archaic SOAP WSDL protocols built decades ago. Furthermore, any Extra-EU shipment introduces the lethal complexity of automated customs declarations, commercial invoices, and HS (Harmonized System) code validation.

This blueprint provides the ultimate, bulletproof architecture for integrating any courier in the world into Odoo's native `delivery.carrier` framework.

#### 🏛️ The Architecture: The Provider Dispatcher

Odoo's delivery architecture expects specific methods to exist based on the `delivery_type` selection field. You do not write spaghetti code with endless `if/else` statements. You extend the core carrier model and let Odoo route the traffic automatically using its internal naming convention: `<provider>_send_shipping`.

Python

```python
import logging
from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)

class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    # 1. REGISTERING THE PROVIDERS
    # Odoo uses this selection field to dynamically call methods.
    # If delivery_type == 'gls_italy', Odoo automatically looks for a method named 'gls_italy_send_shipping'.
    delivery_type = fields.Selection(selection_add=[
        ('fedex_rest', 'FedEx (USA - REST)'),
        ('usps_rest', 'USPS (USA - REST)'),
        ('gls_italy', 'GLS (Italy - SOAP)'),
        ('brt_soap', 'BRT Bartolini (Italy - SOAP)')
    ], ondelete={
        'fedex_rest': 'set default',
        'usps_rest': 'set default',
        'gls_italy': 'set default',
        'brt_soap': 'set default'
    })

    # 2. UNIVERSAL CREDENTIALS
    # We store the API keys on the carrier record so different accounts can be used for different routes.
    omni_api_key = fields.Char(string="API Key / Username", groups="base.group_system")
    omni_api_secret = fields.Char(string="API Secret / Password", groups="base.group_system")
    omni_account_number = fields.Char(string="Account/Contract Number", groups="base.group_system")
    omni_wsdl_url = fields.Char(string="SOAP WSDL URL", help="Only required for legacy EU couriers")
    is_production = fields.Boolean(string="Production Environment", default=False)
```

#### 🇺🇸 The REST Adapter (USA Couriers: FedEx / UPS)

Modern US carriers expect structured JSON. The primary challenge here is Token Management. You cannot request a new OAuth token for every single shipping label, or FedEx will rate-limit and ban your server IP.

Python

```python
import requests
import base64
import json

class DeliveryCarrierFedex(models.Model):
    _inherit = 'delivery.carrier'

    def _get_fedex_token(self):
        """
        Retrieves a valid OAuth2 token. In a production environment, 
        this token MUST be cached in standard system parameters (ir.config_parameter) 
        with an expiration timestamp to avoid rate-limiting.
        """
        self.ensure_one()
        url = "https://apis.fedex.com/oauth/token" if self.is_production else "https://apis-sandbox.fedex.com/oauth/token"
        
        payload = 'grant_type=client_credentials&client_id=' + self.omni_api_key + '&client_secret=' + self.omni_api_secret
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json().get('access_token')
        except Exception as e:
            _logger.exception("FedEx Token Generation Failed")
            raise exceptions.UserError(_("Failed to authenticate with FedEx API. Check your credentials."))

    def fedex_rest_send_shipping(self, pickings):
        """
        The entry point triggered by Odoo when a user clicks 'Validate' on a Stock Picking.
        Returns a list of dictionaries containing exact tracking numbers and shipping costs.
        """
        res = []
        token = self._get_fedex_token()
        url = "https://apis.fedex.com/ship/v1/shipments" if self.is_production else "https://apis-sandbox.fedex.com/ship/v1/shipments"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        for picking in pickings:
            # 1. BUILD THE JSON PAYLOAD
            # A robust architecture maps Odoo objects to the exact JSON schema required by the courier.
            payload = self._build_fedex_payload(picking)
            
            try:
                # 2. EXECUTE THE REQUEST
                response = requests.post(url, headers=headers, json=payload, timeout=15)
                response.raise_for_status()
                response_data = response.json()
                
                # 3. EXTRACT THE LABEL AND TRACKING
                # FedEx returns the label as a base64 encoded PDF string
                tracking_number = response_data['output']['transactionShipments'][0]['pieceResponses'][0]['trackingNumber']
                label_b64 = response_data['output']['transactionShipments'][0]['pieceResponses'][0]['packageDocuments'][0]['encodedLabel']
                
                # 4. APPEND TO ODOO RESULTS
                # Odoo natively requires this exact dictionary structure to attach the label to the chatter.
                res.append({
                    'exact_price': 0.0, # You can extract the negotiated rate here if needed
                    'tracking_number': tracking_number,
                })
                
                # Save the label as a PDF attachment on the picking
                self._attach_label_to_picking(picking, tracking_number, label_b64)

            except Exception as e:
                # NEVER crash the whole batch. Catch the error, log it, and raise a clean UserError.
                _logger.error("FedEx Label Generation Error for picking %s: %s", picking.name, str(e))
                raise exceptions.UserError(_("FedEx API Error: %s") % str(e))

        return res

    def _build_fedex_payload(self, picking):
        """
        Constructs the complex FedEx routing payload.
        """
        sender = picking.picking_type_id.warehouse_id.partner_id
        receiver = picking.partner_id
        
        return {
            "requestedShipment": {
                "shipper": {
                    "address": {
                        "streetLines": [sender.street],
                        "city": sender.city,
                        "stateOrProvinceCode": sender.state_id.code,
                        "postalCode": sender.zip,
                        "countryCode": sender.country_id.code
                    },
                    "contact": {"phoneNumber": sender.phone, "companyName": sender.name}
                },
                "recipients": [{
                    "address": {
                        "streetLines": [receiver.street, receiver.street2 or ''],
                        "city": receiver.city,
                        "stateOrProvinceCode": receiver.state_id.code if receiver.state_id else '',
                        "postalCode": receiver.zip,
                        "countryCode": receiver.country_id.code
                    },
                    "contact": {"personName": receiver.name, "phoneNumber": receiver.phone}
                }],
                "pickupType": "USE_SCHEDULED_PICKUP",
                "serviceType": "FEDEX_GROUND", # Should be dynamic based on the carrier setup
                "packagingType": "YOUR_PACKAGING",
                "shippingChargesPayment": {"paymentType": "SENDER"},
                "requestedPackageLineItems": [{
                    "weight": {"units": "KG", "value": picking.shipping_weight}
                }]
            }
        }
```

#### 🇮🇹 The SOAP Adapter (Italy/EU Couriers: GLS / BRT)

Italian and older European couriers heavily utilize SOAP. You cannot use the `requests` library easily here because SOAP requires massive, strictly typed XML envelopes.

The Survival Tool: You must use the `zeep` Python library. It dynamically reads the courier's WSDL (Web Services Description Language) file and converts native Python dictionaries into flawless XML automatically.

_(Ensure `zeep` is in your `external_dependencies` in `__manifest__.py`)._

Python

```python
import base64
try:
    import zeep
    from zeep.exceptions import Fault
    ZEEP_INSTALLED = True
except ImportError:
    ZEEP_INSTALLED = False

class DeliveryCarrierGLS(models.Model):
    _inherit = 'delivery.carrier'

    def gls_italy_send_shipping(self, pickings):
        """
        Entry point for GLS Italy (SOAP Protocol).
        """
        if not ZEEP_INSTALLED:
            raise exceptions.UserError(_("The 'zeep' Python library is missing. Cannot generate SOAP requests."))
            
        res = []
        
        # 1. INITIALIZE THE SOAP CLIENT
        # The WSDL URL defines all the endpoints and types for the courier.
        wsdl = self.omni_wsdl_url or 'https://weblabeling.gls-italy.com/ilswebservice.asmx?wsdl'
        
        try:
            client = zeep.Client(wsdl=wsdl)
        except Exception as e:
            raise exceptions.UserError(_("Failed to connect to GLS Italy WSDL server: %s") % str(e))

        for picking in pickings:
            # 2. BUILD THE SOAP DICTIONARY
            # Zeep automatically converts this Python dictionary into the strict XML Envelope required by GLS.
            receiver = picking.partner_id
            
            soap_payload = {
                'SedeGls': self.omni_account_number[:2], # Standard GLS IT convention
                'CodiceClienteGls': self.omni_account_number[2:],
                'PasswordClienteGls': self.omni_api_secret,
                'NomeDestinatario': receiver.name[:35], # SOAP APIs strictly enforce string lengths
                'IndirizzoDestinatario': receiver.street[:35],
                'CittaDestinatario': receiver.city[:35],
                'ProvinciaDestinatario': receiver.state_id.code if receiver.state_id else '',
                'CapDestinatario': receiver.zip,
                'NazioneDestinatario': receiver.country_id.code,
                'EmailDestinatario': receiver.email or '',
                'TelefonoDestinatario': receiver.phone or '',
                'PesoReale': picking.shipping_weight,
                'Colli': 1,
                'GeneraPdf': True,
                'FormatoPdf': 'A6'
            }

            try:
                # 3. CALL THE SOAP METHOD
                # 'AddParcel' is the specific function name defined in the GLS WSDL.
                response = client.service.AddParcel(**soap_payload)
                
                # 4. PARSE THE SOAP RESPONSE
                # Legacy SOAP APIs rarely use HTTP 400/500 for errors. They return HTTP 200 with an error string inside.
                if response.ErrorCode != 0:
                    raise exceptions.UserError(_("GLS Error: %s") % response.ErrorDescription)
                    
                tracking_number = response.SpedizioneGls
                pdf_string_b64 = response.PdfLabel
                
                res.append({
                    'exact_price': 0.0,
                    'tracking_number': tracking_number,
                })
                
                self._attach_label_to_picking(picking, tracking_number, pdf_string_b64)
                
            except Fault as fault:
                # Zeep captures standard SOAP Faults
                _logger.error("SOAP Fault from GLS: %s", fault.message)
                raise exceptions.UserError(_("Courier System Error: %s") % fault.message)
            except Exception as e:
                raise exceptions.UserError(_("Unexpected error during GLS transmission: %s") % str(e))
                
        return res
```

#### 🌐 International Operations: Customs & HS Codes (Extra-EU)

When shipping across borders (e.g., Italy to USA, or USA to Europe), a standard label is not enough. You must transmit electronic customs data (ETD / Paperless Trade), including the commercial value, origin country, and the precise HS Code (Harmonized System Code) for every single product in the box.

If you fail to provide this, the package will be seized at the border, and the API will reject your label request.

**1. Preparing the Product Schema**

You must extend the Odoo Product model to store international customs data.

Python

```python
class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # The 6 to 10 digit international customs code
    hs_code = fields.Char(string="HS Code", help="Harmonized System Code for international shipping")
    
    # Customs authorities require knowing where the product was physically manufactured
    country_of_origin_id = fields.Many2one('res.country', string="Country of Origin")
```

**2. Generating the Commercial Invoice Payload**

When constructing your JSON or SOAP payload for an international shipment, you must dynamically aggregate the lines inside the box.

Python

```python
    def _build_customs_payload(self, picking):
        """
        Generates the international commodity block for DHL / FedEx.
        """
        commodities = []
        total_customs_value = 0.0
        
        # Traverse the stock moves (the actual products inside the box)
        for move in picking.move_ids.filtered(lambda m: m.state == 'done'):
            product = move.product_id
            
            # 1. HARD VALIDATION
            # Stop the transaction immediately if customs data is missing.
            if not product.hs_code:
                raise exceptions.ValidationError(_("Product %s is missing an HS Code required for Extra-EU shipping.") % product.name)
            if not product.country_of_origin_id:
                raise exceptions.ValidationError(_("Product %s is missing a Country of Origin.") % product.name)

            # 2. VALUE CALCULATION
            # Customs requires the commercial value. We pull this from the original Sales Order line.
            sale_line = move.sale_line_id
            unit_price = sale_line.price_unit if sale_line else product.lst_price
            line_value = unit_price * move.quantity_done
            total_customs_value += line_value

            # 3. COMMODITY CONSTRUCTION (FedEx REST Example)
            commodities.append({
                "name": product.name[:35],
                "numberOfPieces": 1,
                "description": product.name,
                "countryOfManufacture": product.country_of_origin_id.code,
                "weight": {"units": "KG", "value": product.weight * move.quantity_done},
                "quantity": move.quantity_done,
                "quantityUnits": "EA",
                "unitPrice": {"amount": unit_price, "currency": picking.sale_id.currency_id.name or 'EUR'},
                "customsValue": {"amount": line_value, "currency": picking.sale_id.currency_id.name or 'EUR'},
                "harmonizedCode": product.hs_code
            })
            
        return commodities, total_customs_value
```

#### 📥 Helper: Attaching Labels to the Chatter

Throughout the blueprint, we reference `_attach_label_to_picking`. Odoo users expect to click a button, wait two seconds, and see the PDF label magically appear in the communication chatter of the delivery order.

Here is the flawless method to achieve that.

Python

```python
    def _attach_label_to_picking(self, picking, tracking_number, pdf_b64_string):
        """
        Decodes a base64 string from the courier API and saves it as a PDF attachment 
        directly inside the Odoo chatter for the warehouse team to print.
        """
        attachment_name = f"Shipping_Label_{picking.name}_{tracking_number}.pdf"
        
        # Create the physical attachment in the database
        attachment = self.env['ir.attachment'].create({
            'name': attachment_name,
            'type': 'binary',
            'datas': pdf_b64_string,
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'mimetype': 'application/pdf'
        })
        
        # Post a message in the chatter linking the attachment
        message = _("Shipping label generated. Tracking Number: %s") % tracking_number
        picking.message_post(
            body=message,
            attachment_ids=[attachment.id]
        )
```

#### 🚨 Architect's Summary for Logistics

1. REST vs SOAP: Always use `requests` for REST APIs (USA/Modern) and `zeep` for SOAP WSDL APIs (Italy/Legacy). Never attempt to parse or build SOAP XML manually using string manipulation.
2. String Limits: Legacy couriers (like BRT or GLS) will hard-crash if a street address is longer than 35 characters. Always slice your strings (e.g., `receiver.street[:35]`) before pushing them into the payload.
3. Customs Check: When routing outside the native zone (e.g., EU to non-EU), always validate that the `hs_code` exists _before_ making the API call to save latency and avoid silent border seizures.

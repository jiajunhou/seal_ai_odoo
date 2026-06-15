# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AiCrmPartnerMixin(models.AbstractModel):
    """Mixin to extend res.partner with AI-relevant fields and methods."""

    _name = 'ai.crm.partner.mixin'
    _description = 'AI CRM Partner Extension'

    ai_notes = fields.Text(string='AI Notes', help='AI-generated notes about this partner')
    ai_last_interaction = fields.Datetime(string='Last AI Interaction')
    ai_summary = fields.Text(string='AI Summary', help='AI-generated summary of partner activity')

    def get_ai_context(self):
        """Get a structured context dict for AI processing about this partner."""
        self.ensure_one()
        return {
            'model': 'res.partner',
            'id': self.id,
            'name': self.name,
            'email': self.email or '',
            'phone': self.phone or '',
            'mobile': self.mobile or '',
            'website': self.website or '',
            'city': self.city or '',
            'country': self.country_id.name or '',
            'is_company': self.is_company,
            'commercial_partner': self.commercial_partner_id.name or '',
            'tags': [tag.name for tag in self.category_id],
            'child_count': len(self.child_ids),
        }


class AiSaleOrderMixin(models.AbstractModel):
    """Mixin to extend sale.order with AI-relevant fields and methods."""

    _name = 'ai.sale.order.mixin'
    _description = 'AI Sales Order Extension'

    ai_notes = fields.Text(string='AI Notes')
    ai_summary = fields.Text(string='AI Summary')

    def get_ai_context(self):
        """Get structured context for AI processing."""
        self.ensure_one()
        lines = []
        for line in self.order_line:
            lines.append({
                'product': line.product_id.name or '',
                'quantity': line.product_uom_qty,
                'price_unit': line.price_unit,
                'price_subtotal': line.price_subtotal,
            })
        return {
            'model': 'sale.order',
            'id': self.id,
            'name': self.name,
            'partner': self.partner_id.name,
            'date_order': str(self.date_order) if self.date_order else '',
            'amount_total': self.amount_total,
            'amount_untaxed': self.amount_untaxed,
            'state': self.state,
            'lines': lines,
            'line_count': len(lines),
        }

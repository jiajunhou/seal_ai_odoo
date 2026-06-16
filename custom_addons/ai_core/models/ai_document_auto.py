# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

import logging
_logger = logging.getLogger(__name__)


class AiDocument(models.Model):
    _inherit = 'ai.document'

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-process document when datas is provided."""
        records = super().create(vals_list)
        for record in records:
            if record.datas and record.state in ('draft', 'uploaded'):
                try:
                    # Trigger async processing
                    record.with_delay().action_process()
                    _logger.info('Auto-processing started for document: %s', record.name)
                except Exception:
                    # Fallback to sync processing if queue not available
                    record.action_process()
        return records

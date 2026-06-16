# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Service Registry for the AI Core module.

Provides a centralized registry for all AI services.
Services are implemented as Odoo models (AbstractModel) so they have
access to the Odoo ORM, environment, and all model methods.

Architecture:
- Each service extends the base 'ai.base.service' abstract model
- Services are resolved via the Odoo registry (self.env[service_name])
- All services follow single-responsibility principle
"""

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AiBaseService(models.AbstractModel):
    """Abstract base class for all AI services."""

    _name = 'ai.base.service'
    _description = 'AI Base Service'

    # Services should be transient; not stored in database
    _transient = True
    _log_access = True  # Required by Odoo 18 for TransientModels

    name = fields.Char(string='Service Name', default=lambda self: self._name)

    @api.model
    def get_service_name(self):
        """Return the service identifier."""
        return self._name

    @api.model
    def log_info(self, message):
        """Log an info message with service context."""
        _logger.info('[%s] %s', self._name, message)
        return True

    @api.model
    def log_error(self, message, exc_info=False):
        """Log an error with service context."""
        _logger.error('[%s] %s', self._name, message, exc_info=exc_info)
        return True

    @api.model
    def log_warning(self, message):
        """Log a warning with service context."""
        _logger.warning('[%s] %s', self._name, message)
        return True

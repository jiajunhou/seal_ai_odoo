# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AiDocumentProcessWizard(models.TransientModel):
    """Wizard to configure and trigger document processing."""

    _name = 'ai.document.process.wizard'
    _description = 'Document Processing Wizard'

    # ---- Document Selection ----
    document_ids = fields.Many2many(
        'ai.document',
        string='Documents to Process',
        required=True,
    )

    # ---- Processing Options ----
    chunk_strategy = fields.Selection(
        string='Chunk Strategy',
        selection=[
            ('recursive', 'Recursive Split'),
            ('token', 'Token-based'),
            ('semantic', 'Semantic (by paragraph)'),
            ('fixed', 'Fixed Size'),
        ],
        default='recursive',
        required=True,
    )
    chunk_size = fields.Integer(string='Chunk Size', default=512)
    chunk_overlap = fields.Integer(string='Chunk Overlap', default=50)
    embedding_model = fields.Char(string='Embedding Model', default='text-embedding-ada-002')

    def action_process(self):
        """Process all selected documents with configured parameters."""
        documents = self.document_ids
        if not documents:
            return {'type': 'ir.actions.act_window_close'}

        for doc in documents:
            doc.write({
                'chunk_strategy': self.chunk_strategy,
                'chunk_size': self.chunk_size,
                'chunk_overlap': self.chunk_overlap,
                'embedding_model': self.embedding_model,
            })
            doc.action_process()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Documents'),
            'res_model': 'ai.document',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', documents.ids)],
        }

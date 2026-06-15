# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AiChunk(models.Model):
    """Represents a text chunk extracted from a document after chunking."""

    _name = 'ai.chunk'
    _description = 'AI Document Chunk'
    _order = 'sequence, id'

    # ---- Core Fields ----
    name = fields.Char(string='Chunk Name', compute='_compute_name', store=True)
    sequence = fields.Integer(string='Sequence', default=0, required=True)
    content = fields.Text(string='Content', required=True)
    content_length = fields.Integer(string='Content Length', compute='_compute_content_length', store=True)
    token_count = fields.Integer(string='Token Count (est.)', compute='_compute_token_count', store=True)

    # ---- Source ----
    document_id = fields.Many2one(
        'ai.document',
        string='Document',
        required=True,
        ondelete='cascade',
        index=True,
    )
    document_name = fields.Char(
        string='Document Name',
        related='document_id.name',
        store=True,
        readonly=True,
    )

    # ---- Positioning ----
    page_number = fields.Integer(string='Page Number', default=0, help='Source page number if available')
    start_char = fields.Integer(string='Start Character Index', default=0)
    end_char = fields.Integer(string='End Character Index', default=0)
    section_title = fields.Char(string='Section Title', help='Heading or section this chunk belongs to')

    # ---- Embedding Relation ----
    embedding_ids = fields.One2many('ai.embedding', 'chunk_id', string='Embeddings')
    has_embedding = fields.Boolean(string='Has Embedding', compute='_compute_has_embedding', store=True)

    # ---- Metadata ----
    chunk_strategy = fields.Selection(
        string='Chunk Strategy',
        related='document_id.chunk_strategy',
        readonly=True,
        store=True,
    )
    active = fields.Boolean(string='Active', default=True)

    # ---- Computed ----

    @api.depends('document_id.name', 'sequence')
    def _compute_name(self):
        for record in self:
            doc_name = record.document_id.name or 'Unknown'
            record.name = f'{doc_name} - Chunk #{record.sequence}'

    @api.depends('content')
    def _compute_content_length(self):
        for record in self:
            record.content_length = len(record.content) if record.content else 0

    @api.depends('content')
    def _compute_token_count(self):
        for record in self:
            # Rough estimation: ~4 chars per token for English text
            record.token_count = max(1, len(record.content) // 4) if record.content else 0

    @api.depends('embedding_ids')
    def _compute_has_embedding(self):
        for record in self:
            record.has_embedding = bool(record.embedding_ids)

    # ---- Constraints ----

    @api.constrains('content')
    def _check_content(self):
        for record in self:
            if not record.content or not record.content.strip():
                raise ValidationError(_('Chunk content cannot be empty.'))

    # ---- Text Utilities ----

    def action_view_embeddings(self):
        """Open embeddings for this chunk."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Embeddings'),
            'res_model': 'ai.embedding',
            'view_mode': 'tree,form',
            'domain': [('chunk_id', '=', self.id)],
        }

    def get_text_preview(self, max_length=200):
        """Get a truncated preview of the chunk content."""
        self.ensure_one()
        if len(self.content) > max_length:
            return self.content[:max_length] + '...'
        return self.content

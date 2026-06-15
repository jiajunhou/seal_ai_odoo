# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import logging
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AiDocument(models.Model):
    """Represents an uploaded document (PDF, DOCX, TXT) for AI processing."""

    _name = 'ai.document'
    _description = 'AI Document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'write_date DESC'

    # ---- Core Fields ----
    name = fields.Char(string='Document Name', required=True, tracking=True)
    description = fields.Text(string='Description')
    document_type = fields.Selection(
        string='Document Type',
        selection=[
            ('pdf', 'PDF'),
            ('docx', 'DOCX'),
            ('txt', 'TXT'),
            ('html', 'HTML'),
            ('markdown', 'Markdown'),
            ('csv', 'CSV'),
            ('other', 'Other'),
        ],
        required=True,
        default='pdf',
        tracking=True,
    )
    state = fields.Selection(
        string='Status',
        selection=[
            ('draft', 'Draft'),
            ('uploaded', 'Uploaded'),
            ('parsing', 'Parsing'),
            ('parsed', 'Parsed'),
            ('chunking', 'Chunking'),
            ('chunked', 'Chunked'),
            ('embedding', 'Embedding'),
            ('ready', 'Ready'),
            ('error', 'Error'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )

    # ---- File Fields ----
    datas = fields.Binary(string='File Content', attachment=True)
    datas_fname = fields.Char(string='Filename')
    file_size = fields.Integer(string='File Size (Bytes)', compute='_compute_file_size', store=True)
    file_extension = fields.Char(string='File Extension', compute='_compute_file_extension', store=True)
    mime_type = fields.Char(string='MIME Type')

    # ---- Parsed Content ----
    raw_text = fields.Text(string='Raw Text', readonly=True)
    parsed_content = fields.Html(string='Parsed Content', readonly=True)
    page_count = fields.Integer(string='Page Count', default=0)
    word_count = fields.Integer(string='Word Count', compute='_compute_word_count', store=True)
    character_count = fields.Integer(string='Character Count', compute='_compute_character_count', store=True)

    # ---- Processing Config ----
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
    chunk_size = fields.Integer(string='Chunk Size', default=512, help='Target size for each chunk (tokens or chars)')
    chunk_overlap = fields.Integer(string='Chunk Overlap', default=50, help='Overlap between consecutive chunks')
    embedding_model = fields.Char(string='Embedding Model', default='text-embedding-ada-002')
    embedding_dimensions = fields.Integer(string='Embedding Dimensions', default=1536)

    # ---- Relations ----
    chunk_ids = fields.One2many('ai.chunk', 'document_id', string='Chunks')
    embedding_ids = fields.One2many('ai.embedding', 'document_id', string='Embeddings')
    vector_index_id = fields.Many2one('ai.vector.index', string='Vector Index', ondelete='set null')
    user_id = fields.Many2one('res.users', string='Uploaded By', default=lambda self: self.env.user, required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # ---- Statistics ----
    chunk_count = fields.Integer(string='Chunk Count', compute='_compute_chunk_count', store=True)
    embedding_count = fields.Integer(string='Embedding Count', compute='_compute_embedding_count', store=True)
    process_duration = fields.Float(string='Processing Duration (s)', help='Total processing time in seconds')
    error_message = fields.Text(string='Error Message', readonly=True)
    processed_date = fields.Datetime(string='Processed Date', readonly=True)

    # ---- Computed Methods ----

    @api.depends('datas')
    def _compute_file_size(self):
        for record in self:
            if record.datas:
                record.file_size = len(base64.b64decode(record.datas))
            else:
                record.file_size = 0

    @api.depends('datas_fname')
    def _compute_file_extension(self):
        for record in self:
            if record.datas_fname:
                _, ext = record.datas_fname.rsplit('.', 1) if '.' in record.datas_fname else (record.datas_fname, '')
                record.file_extension = ext.lower()
            else:
                record.file_extension = ''

    @api.depends('raw_text')
    def _compute_word_count(self):
        for record in self:
            if record.raw_text:
                record.word_count = len(record.raw_text.split())
            else:
                record.word_count = 0

    @api.depends('raw_text')
    def _compute_character_count(self):
        for record in self:
            if record.raw_text:
                record.character_count = len(record.raw_text)
            else:
                record.character_count = 0

    @api.depends('chunk_ids')
    def _compute_chunk_count(self):
        for record in self:
            record.chunk_count = len(record.chunk_ids)

    @api.depends('embedding_ids')
    def _compute_embedding_count(self):
        for record in self:
            record.embedding_count = len(record.embedding_ids)

    # ---- Validation ----

    @api.constrains('datas')
    def _check_file_size(self):
        max_size = 50 * 1024 * 1024  # 50 MB
        for record in self:
            if record.file_size and record.file_size > max_size:
                raise ValidationError(_('File size exceeds maximum allowed size of 50 MB.'))

    # ---- Action Methods ----

    def action_upload(self):
        """Mark document as uploaded."""
        self.write({'state': 'uploaded'})
        return True

    def action_process(self):
        """Full processing pipeline: parse -> chunk -> embed."""
        self.ensure_one()
        if not self.datas:
            raise UserError(_('No file content to process. Please upload a file first.'))

        start_time = datetime.now()
        try:
            self._process_pipeline()
        except Exception as e:
            _logger.exception('Document processing failed for %s', self.name)
            self.write({
                'state': 'error',
                'error_message': str(e),
            })
            return False

        duration = (datetime.now() - start_time).total_seconds()
        self.write({
            'state': 'ready',
            'process_duration': duration,
            'processed_date': fields.Datetime.now(),
        })
        return True

    def _process_pipeline(self):
        """Internal pipeline: parse -> determine type -> chunk -> embed."""
        self.ensure_one()
        DocumentParserService = self.env['ai.document.parser.service']
        ChunkerService = self.env['ai.chunker.service']
        EmbeddingService = self.env['ai.embedding.service']
        VectorStoreService = self.env['ai.vector.store.service']

        # Step 1: Parse
        self.write({'state': 'parsing'})
        parser = DocumentParserService
        parsed = parser.parse_document(self)
        self.write({
            'raw_text': parsed.get('raw_text', ''),
            'parsed_content': parsed.get('parsed_content', ''),
            'page_count': parsed.get('page_count', 0),
        })

        # Step 2: Chunk
        self.write({'state': 'chunking'})
        chunker = ChunkerService
        chunks = chunker.chunk_document(
            self,
            strategy=self.chunk_strategy,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

        # Step 3: Embed
        self.write({'state': 'embedding'})
        embedder = EmbeddingService
        embedder.generate_embeddings(
            self,
            model=self.embedding_model or 'text-embedding-ada-002',
        )

        # Step 4: Store in vector index
        vector_store = VectorStoreService
        vector_store.index_document(self)

        return True

    def action_reset(self):
        """Reset document to draft state (removes all processed data)."""
        self.ensure_one()
        # Delete related records
        self.chunk_ids.unlink()
        self.embedding_ids.unlink()
        self.write({
            'state': 'draft',
            'raw_text': False,
            'parsed_content': False,
            'page_count': 0,
            'error_message': False,
            'process_duration': 0.0,
            'processed_date': False,
        })
        return True

    def action_reprocess(self):
        """Reset and re-process the document."""
        self.action_reset()
        return self.action_process()

    def action_view_chunks(self):
        """Open chunks list view for this document."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Chunks'),
            'res_model': 'ai.chunk',
            'view_mode': 'tree,form',
            'domain': [('document_id', '=', self.id)],
            'context': {'default_document_id': self.id},
        }

    def action_view_embeddings(self):
        """Open embeddings list view for this document."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Embeddings'),
            'res_model': 'ai.embedding',
            'view_mode': 'tree,form',
            'domain': [('document_id', '=', self.id)],
            'context': {'default_document_id': self.id},
        }

    def action_download_parsed_text(self):
        """Download the parsed raw text as a file."""
        self.ensure_one()
        if not self.raw_text:
            raise UserError(_('No parsed text available. Process the document first.'))
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/raw_text/{self.name}_parsed.txt',
            'target': 'new',
        }

    # ---- Search / Override ----

    def name_get(self):
        result = []
        for record in self:
            name = record.name
            if record.document_type:
                name = f'[{record.document_type.upper()}] {name}'
            result.append((record.id, name))
        return result

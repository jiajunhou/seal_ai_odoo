# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AiVectorIndex(models.Model):
    """Configuration and management of vector indexes for similarity search."""

    _name = 'ai.vector.index'
    _description = 'AI向量索引'
    _order = 'name'

    # ---- Core Fields ----
    name = fields.Char(string='索引名称', required=True)
    description = fields.Text(string='描述')
    active = fields.Boolean(string='启用', default=True)

    # ---- Index Configuration ----
    index_type = fields.Selection(
        string='索引类型',
        selection=[
            ('flat', '扁平(暴力搜索)'),
            ('ivf', 'IVF(倒排文件)'),
            ('hnsw', 'HNSW(分层可导航小世界)'),
        ],
        default='flat',
        required=True,
        help='Type of vector index. Flat = exact search, IVF/HNSW = approximate but faster.',
    )
    distance_metric = fields.Selection(
        string='距离度量',
        selection=[
            ('cosine', '余弦相似度'),
            ('l2', '欧几里得距离(L2)'),
            ('ip', '内积'),
        ],
        default='cosine',
        required=True,
    )
    dimensions = fields.Integer(string='向量维度', default=1536, required=True)
    model_name = fields.Char(
        string='嵌入模型',
        default='text-embedding-ada-002',
        help='The embedding model this index is compatible with',
    )

    # ---- Relations ----
    document_ids = fields.One2many('ai.document', 'vector_index_id', string='Documents')
    embedding_ids = fields.One2many('ai.embedding', 'vector_index_id', string='Embeddings')

    # ---- Statistics ----
    document_count = fields.Integer(
        string='文档数量',
        compute='_compute_statistics',
        store=True,
    )
    embedding_count = fields.Integer(
        string='嵌入数量',
        compute='_compute_statistics',
        store=True,
    )
    total_chunks = fields.Integer(
        string='总块数',
        compute='_compute_statistics',
        store=True,
    )

    # ---- Computed ----

    @api.depends('document_ids', 'embedding_ids')
    def _compute_statistics(self):
        for record in self:
            record.document_count = len(record.document_ids)
            record.embedding_count = len(record.embedding_ids)
            record.total_chunks = sum(doc.chunk_count for doc in record.document_ids)

    # ---- Actions ----

    def action_rebuild_index(self):
        """Rebuild the vector index (delete and re-index all embeddings)."""
        indexes_to_rebuild = self.filtered(lambda i: i.embedding_count > 0)
        if not indexes_to_rebuild:
            return True

        for index in indexes_to_rebuild:
            # Delete all embeddings for this index
            index.embedding_ids.unlink()
            # Re-process all documents
            for doc in index.document_ids:
                doc.action_reprocess()

        return True

    def action_clear_index(self):
        """Clear all embeddings from this index."""
        self.mapped('embedding_ids').unlink()
        return True

    def action_index_statistics(self):
        """Show detailed statistics for this index."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Index Statistics: %s') % self.name,
            'res_model': 'ai.vector.index',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    @api.model
    def get_or_create_default_index(self, dimensions=1536, model_name='text-embedding-ada-002'):
        """Get the default vector index, creating it if needed."""
        index = self.search([
            ('model_name', '=', model_name),
            ('dimensions', '=', dimensions),
        ], limit=1)
        if not index:
            index = self.create({
                'name': f'Default {model_name} Index',
                'dimensions': dimensions,
                'model_name': model_name,
                'index_type': 'flat',
                'distance_metric': 'cosine',
            })
        return index

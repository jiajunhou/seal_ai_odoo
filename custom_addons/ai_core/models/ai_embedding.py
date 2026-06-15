# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import struct

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class AiEmbedding(models.Model):
    """Stores vector embeddings for document chunks with pgvector support."""

    _name = 'ai.embedding'
    _description = 'AI Embedding Vector'
    _order = 'document_id, chunk_id, id'

    # ---- Core Fields ----
    name = fields.Char(string='Name', compute='_compute_name', store=True)
    vector = fields.Binary(string='Embedding Vector (Binary)', readonly=True)
    vector_dimensions = fields.Integer(string='Vector Dimensions', default=1536, required=True)

    # JSON representation for display/debug
    vector_json = fields.Text(string='Vector (JSON)', compute='_compute_vector_json', readonly=True)

    # ---- Relations ----
    document_id = fields.Many2one(
        'ai.document',
        string='Document',
        required=True,
        ondelete='cascade',
        index=True,
    )
    chunk_id = fields.Many2one(
        'ai.chunk',
        string='Chunk',
        required=True,
        ondelete='cascade',
        index=True,
    )
    vector_index_id = fields.Many2one(
        'ai.vector.index',
        string='Vector Index',
        ondelete='cascade',
        index=True,
    )

    # ---- Metadata ----
    model_name = fields.Char(string='Embedding Model', default='text-embedding-ada-002', required=True)
    active = fields.Boolean(string='Active', default=True)
    chunk_content = fields.Text(
        string='Chunk Content',
        related='chunk_id.content',
        readonly=True,
        store=False,
    )

    # ---- Computed ----

    @api.depends('chunk_id', 'chunk_id.name')
    def _compute_name(self):
        for record in self:
            if record.chunk_id:
                record.name = f'Embedding: {record.chunk_id.name}'
            else:
                record.name = f'Embedding #{record.id}'

    @api.depends('vector')
    def _compute_vector_json(self):
        for record in self:
            if record.vector:
                try:
                    vec = record._binary_to_vector(record.vector)
                    # Show first 10 values as preview
                    preview = vec[:10]
                    record.vector_json = json.dumps({
                        'dimensions': len(vec),
                        'preview': preview,
                        'preview_count': len(preview),
                    })
                except Exception as e:
                    record.vector_json = json.dumps({'error': str(e)})
            else:
                record.vector_json = False

    # ---- Vector Serialization ----

    @api.model
    def _vector_to_binary(self, vector_list):
        """Convert a list of floats to binary data for storage."""
        if not vector_list:
            return None
        # Pack as little-endian doubles (8 bytes each)
        return struct.pack(f'<{len(vector_list)}d', *vector_list)

    @api.model
    def _binary_to_vector(self, binary_data):
        """Convert binary data back to list of floats."""
        if not binary_data:
            return []
        if isinstance(binary_data, bytes):
            data = binary_data
        else:
            data = binary_data  # Assume it's already bytes
        count = len(data) // 8  # 8 bytes per double
        return list(struct.unpack(f'<{count}d', data[:count * 8]))

    @api.model
    def _get_pgvector_sql(self, vector_list):
        """Get PostgreSQL pgvector literal for the vector."""
        if not vector_list:
            return 'NULL'
        vec_str = '[' + ','.join(str(v) for v in vector_list) + ']'
        return vec_str

    # ---- CRUD Overrides ----

    def write(self, vals):
        """Override write to prevent modification of vector data after creation."""
        if 'vector' in vals and not self.env.context.get('allow_vector_write'):
            raise ValidationError(_(
                'Embedding vectors cannot be modified directly. '
                'Re-process the document to regenerate embeddings.'
            ))
        return super(AiEmbedding, self).write(vals)

    # ---- Search Methods ----

    @api.model
    def search_similar(self, query_vector, limit=10, threshold=0.7):
        """
        Search for similar embeddings using pgvector cosine similarity.
        Falls back to Python-side computation if pgvector is not available.

        :param query_vector: List of floats representing the query embedding
        :param limit: Maximum number of results
        :param threshold: Minimum similarity score (0-1)
        :return: List of dicts with 'embedding_id', 'chunk_id', 'document_id', 'content', 'score'
        """
        if not query_vector:
            return []

        try:
            return self._search_similar_pgvector(query_vector, limit, threshold)
        except Exception as e:
            _logger.warning('pgvector search failed, falling back to Python: %s', e)
            return self._search_similar_python(query_vector, limit, threshold)

    def _search_similar_pgvector(self, query_vector, limit=10, threshold=0.7):
        """Use pgvector's <=> (cosine distance) operator for efficient search."""
        self.flush_model()
        query_vec = self._get_pgvector_sql(query_vector)

        sql = f"""
            SELECT
                e.id AS embedding_id,
                e.chunk_id,
                e.document_id,
                c.content,
                c.document_name,
                1 - (e.vector::vector <=> {query_vec}::vector) AS similarity
            FROM ai_embedding e
            JOIN ai_chunk c ON c.id = e.chunk_id
            WHERE e.active = TRUE
              AND e.vector IS NOT NULL
              AND 1 - (e.vector::vector <=> {query_vec}::vector) >= %s
            ORDER BY similarity DESC
            LIMIT %s
        """
        self.env.cr.execute(sql, (threshold, limit))
        results = []
        for row in self.env.cr.dictfetchall():
            results.append({
                'embedding_id': row['embedding_id'],
                'chunk_id': row['chunk_id'],
                'document_id': row['document_id'],
                'content': row['content'],
                'document_name': row['document_name'],
                'score': float(row['similarity']),
            })
        return results

    def _search_similar_python(self, query_vector, limit=10, threshold=0.7):
        """Fallback: compute cosine similarity in Python."""
        import math

        def cosine_similarity(a, b):
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(y * y for y in b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot_product / (norm_a * norm_b)

        results = []
        embeddings = self.search([('active', '=', True)])
        for emb in embeddings:
            if not emb.vector:
                continue
            vec = emb._binary_to_vector(emb.vector)
            if len(vec) != len(query_vector):
                continue
            score = cosine_similarity(query_vector, vec)
            if score >= threshold:
                results.append({
                    'embedding_id': emb.id,
                    'chunk_id': emb.chunk_id.id,
                    'document_id': emb.document_id.id,
                    'content': emb.chunk_id.content,
                    'document_name': emb.document_id.name,
                    'score': score,
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

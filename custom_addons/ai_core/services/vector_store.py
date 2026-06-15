# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Vector Store Service
====================
Manages vector storage, indexing, and similarity search operations.

Integrates with pgvector for efficient vector operations on PostgreSQL 16.
Provides CRUD operations for embeddings and supports multiple index types.
"""

import json
import logging
import time

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class VectorStoreService(models.AbstractModel):
    """Service for managing vector storage and retrieval."""

    _name = 'ai.vector.store.service'
    _description = 'AI Vector Store Service'
    _inherit = 'ai.base.service'

    # ---- Main API ----

    @api.model
    def index_document(self, document):
        """
        Index all embeddings for a document into the vector store.

        :param document: ai.document record
        :return: dict with indexing results
        """
        self.ensure_one()

        embeddings = document.embedding_ids
        if not embeddings:
            self.log_warning(f'No embeddings found for document {document.name}')
            return {'indexed': 0, 'total': 0}

        vector_index = document.vector_index_id
        if not vector_index:
            vector_index = self.env['ai.vector.index'].get_or_create_default_index()
            document.vector_index_id = vector_index

        # Update index references
        embeddings.write({'vector_index_id': vector_index.id})

        # Try to ensure pgvector extension is available
        self._ensure_pgvector()

        self.log_info(
            f'Indexed {len(embeddings)} embeddings for document {document.name} '
            f'in vector index: {vector_index.name}'
        )

        return {
            'indexed': len(embeddings),
            'total': len(embeddings),
            'index_name': vector_index.name,
            'index_id': vector_index.id,
        }

    @api.model
    def search(self, query_vector, index_id=None, limit=10, threshold=0.0):
        """
        Search the vector store for similar embeddings.

        :param query_vector: list of floats
        :param index_id: optional vector index id to restrict search
        :param limit: max results
        :param threshold: minimum similarity score
        :return: list of result dicts
        """
        if not query_vector:
            return []

        domain = [('active', '=', True)]
        if index_id:
            domain.append(('vector_index_id', '=', index_id))

        embeddings = self.env['ai.embedding'].search(domain)
        return embeddings.search_similar(query_vector, limit=limit, threshold=threshold)

    @api.model
    def remove_document(self, document):
        """
        Remove all embeddings for a document from the vector store.

        :param document: ai.document record
        :return: number of embeddings removed
        """
        count = len(document.embedding_ids)
        document.embedding_ids.unlink()
        self.log_info(f'Removed {count} embeddings for document {document.name}')
        return count

    @api.model
    def get_index_statistics(self, index_id=None):
        """
        Get statistics for a vector index.

        :param index_id: vector index id (optional, uses default if omitted)
        :return: dict with statistics
        """
        if index_id:
            index = self.env['ai.vector.index'].browse(index_id)
        else:
            index = self.env['ai.vector.index'].search([], limit=1)

        if not index:
            return {'error': 'No vector index found'}

        return {
            'id': index.id,
            'name': index.name,
            'type': index.index_type,
            'metric': index.distance_metric,
            'dimensions': index.dimensions,
            'document_count': index.document_count,
            'embedding_count': index.embedding_count,
            'total_chunks': index.total_chunks,
        }

    # ---- pgvector Management ----

    @api.model
    def _ensure_pgvector(self):
        """
        Ensure pgvector extension is available in PostgreSQL.
        This is non-fatal if not available; the system falls back to
        Python-side similarity computation.
        """
        try:
            self.env.cr.execute("SELECT * FROM pg_extension WHERE extname = 'vector'")
            if not self.env.cr.fetchone():
                # Try to create extension (requires superuser)
                try:
                    self.env.cr.execute('CREATE EXTENSION IF NOT EXISTS vector')
                    self.log_info('pgvector extension enabled.')
                except Exception as e:
                    _logger.info(
                        'pgvector extension not available (not superuser?). '
                        'Using Python fallback for similarity search. Error: %s', e
                    )
            else:
                self.log_info('pgvector extension already available.')
        except Exception as e:
            _logger.info(
                'Could not check pgvector: %s. Will use Python fallback.', e
            )

    @api.model
    def create_pgvector_index(self, index_type='hnsw', metric='cosine'):
        """
        Create a pgvector index for faster similarity search.

        :param index_type: 'hnsw' (recommended) or 'ivfflat'
        :param metric: 'cosine', 'l2', or 'ip'
        :return: bool
        """
        try:
            # Create the pgvector extension if not exists
            self._ensure_pgvector()

            index_name = f'ai_embedding_vector_{index_type}_{metric}_idx'
            metric_ops = {'cosine': 'vector_cosine_ops', 'l2': 'vector_l2_ops', 'ip': 'vector_ip_ops'}
            ops = metric_ops.get(metric, 'vector_cosine_ops')

            if index_type == 'hnsw':
                sql = f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON ai_embedding USING hnsw (vector {ops})
                    WITH (m = 16, ef_construction = 200);
                """
            else:  # ivfflat
                sql = f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON ai_embedding USING ivfflat (vector {ops})
                    WITH (lists = 100);
                """
            self.env.cr.execute(sql)
            self.log_info(f'Created pgvector index: {index_name}')
            return True

        except Exception as e:
            self.log_warning(f'Could not create pgvector index: {e}')
            return False

    @api.model
    def drop_pgvector_index(self, index_name='ai_embedding_vector_hnsw_cosine_idx'):
        """Drop a pgvector index."""
        try:
            self.env.cr.execute(f'DROP INDEX IF EXISTS {index_name}')
            self.log_info(f'Dropped pgvector index: {index_name}')
            return True
        except Exception as e:
            self.log_warning(f'Could not drop pgvector index: {e}')
            return False

    # ---- Health Check ----

    @api.model
    def health_check(self):
        """Check the health of the vector store."""
        status = {
            'status': 'healthy',
            'pgvector_available': False,
            'total_embeddings': 0,
            'total_indexes': 0,
            'total_documents': 0,
        }

        try:
            self.env.cr.execute("SELECT * FROM pg_extension WHERE extname = 'vector'")
            status['pgvector_available'] = bool(self.env.cr.fetchone())
        except Exception:
            pass

        try:
            status['total_embeddings'] = self.env['ai.embedding'].search_count([('active', '=', True)])
            status['total_indexes'] = self.env['ai.vector.index'].search_count([])
            status['total_documents'] = self.env['ai.document'].search_count([('state', '=', 'ready')])
        except Exception:
            status['status'] = 'degraded'

        return status

# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Document REST API Controller
============================
Provides REST API endpoints for document upload, parsing, and management.

Endpoints:
- POST   /api/ai/documents/upload   - Upload a document
- GET    /api/ai/documents          - List documents
- GET    /api/ai/documents/<id>     - Get document details
- POST   /api/ai/documents/<id>/process  - Process a document
- DELETE /api/ai/documents/<id>     - Delete a document
"""

import base64
import json
import logging
from datetime import datetime

from odoo import http, _
from odoo.http import request, Response
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class DocumentController(http.Controller):
    """REST API controller for document management."""

    ALLOWED_MIME_TYPES = {
        'application/pdf': 'pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'application/msword': 'docx',
        'text/plain': 'txt',
        'text/html': 'html',
        'text/markdown': 'markdown',
        'text/csv': 'csv',
    }

    def _parse_json(self):
        try:
            return json.loads(request.httprequest.data)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _json_response(self, data, status=200):
        return Response(
            json.dumps(data),
            content_type='application/json',
            status=status,
        )

    def _error(self, message, code=400):
        return self._json_response({
            'jsonrpc': '2.0',
            'error': {'code': code, 'message': message},
        }, status=code)

    def _success(self, result):
        return self._json_response({
            'jsonrpc': '2.0',
            'result': result,
        })

    # ============================================================
    # POST /api/ai/documents/upload
    # ============================================================

    @http.route('/api/ai/documents/upload', type='http', auth='user',
                methods=['POST'], csrf=False, cors='*')
    def upload_document(self):
        """
        Upload a document for AI processing.

        Accepts multipart/form-data with a file field named 'file',
        or JSON with base64-encoded content.

        Multipart form:
        - file: the file to upload
        - name: optional display name

        JSON:
        {
            "name": "document name",
            "file_data": "<base64 encoded content>",
            "filename": "document.pdf",
            "document_type": "pdf" (optional, auto-detected)
        }
        """
        try:
            # Check if multipart upload
            if request.httprequest.mimetype and 'multipart' in request.httprequest.mimetype:
                return self._handle_multipart_upload()
            else:
                return self._handle_json_upload()

        except UserError as e:
            return self._error(str(e), 400)
        except Exception as e:
            _logger.exception('Document upload error')
            return self._error(f'Upload failed: {str(e)}', 500)

    def _handle_multipart_upload(self):
        """Handle multipart file upload."""
        # Get the file from the request
        file_data = request.httprequest.files.get('file')
        if not file_data:
            return self._error('No file provided', 400)

        filename = file_data.filename or 'uploaded_file'
        name = request.params.get('name', filename.rsplit('.', 1)[0] if '.' in filename else filename)

        # Read file content
        file_content = file_data.read()
        if not file_content:
            return self._error('Empty file', 400)

        # Detect type
        mime_type = file_data.content_type or ''
        doc_type = self.ALLOWED_MIME_TYPES.get(mime_type, '')
        if not doc_type:
            # Fall back to extension detection
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            ext_map = {
                'pdf': 'pdf', 'docx': 'docx', 'doc': 'docx',
                'txt': 'txt', 'text': 'txt',
                'html': 'html', 'htm': 'html', 'md': 'markdown', 'csv': 'csv',
            }
            doc_type = ext_map.get(ext, 'other')

        # Create document record
        document = request.env['ai.document'].sudo().create({
            'name': name,
            'datas': base64.b64encode(file_content),
            'datas_fname': filename,
            'document_type': doc_type,
            'mime_type': mime_type,
            'state': 'uploaded',
            'user_id': request.env.user.id,
        })

        return self._success(self._document_to_dict(document))

    def _handle_json_upload(self):
        """Handle JSON-based upload with base64 content."""
        data = self._parse_json()
        name = data.get('name', 'Uploaded Document')
        file_data = data.get('file_data', '')
        filename = data.get('filename', 'document.bin')
        doc_type = data.get('document_type', '')

        if not file_data:
            return self._error('No file_data provided', 400)

        # Decode base64
        try:
            decoded = base64.b64decode(file_data)
        except Exception:
            return self._error('Invalid base64 file_data', 400)

        # Auto-detect type if not specified
        if not doc_type:
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            ext_map = {
                'pdf': 'pdf', 'docx': 'docx', 'doc': 'docx',
                'txt': 'txt', 'html': 'html', 'md': 'markdown', 'csv': 'csv',
            }
            doc_type = ext_map.get(ext, 'other')

        document = request.env['ai.document'].sudo().create({
            'name': name,
            'datas': file_data,
            'datas_fname': filename,
            'document_type': doc_type,
            'state': 'uploaded',
            'user_id': request.env.user.id,
        })

        return self._success(self._document_to_dict(document))

    # ============================================================
    # GET /api/ai/documents
    # ============================================================

    @http.route('/api/ai/documents', type='http', auth='user',
                methods=['GET'], csrf=False, cors='*')
    def list_documents(self):
        """
        List all documents.

        Query params:
        - limit: int
        - offset: int
        - state: str (draft, uploaded, ready, error)
        - type: str (pdf, docx, txt, etc.)
        """
        try:
            limit = min(int(request.params.get('limit', 20)), 100)
            offset = int(request.params.get('offset', 0))
            state = request.params.get('state')
            doc_type = request.params.get('type')

            domain = []
            if state:
                domain.append(('state', '=', state))
            if doc_type:
                domain.append(('document_type', '=', doc_type))

            documents = request.env['ai.document'].sudo().search(
                domain,
                limit=limit,
                offset=offset,
                order='write_date DESC',
            )

            return self._success({
                'documents': [self._document_to_dict(d) for d in documents],
                'total': len(documents),
                'limit': limit,
                'offset': offset,
            })

        except Exception as e:
            return self._error(str(e), 500)

    # ============================================================
    # GET /api/ai/documents/<id>
    # ============================================================

    @http.route('/api/ai/documents/<int:document_id>', type='http', auth='user',
                methods=['GET'], csrf=False, cors='*')
    def get_document(self, document_id):
        """Get document details."""
        try:
            document = request.env['ai.document'].sudo().browse(document_id)
            if not document.exists():
                return self._error('Document not found', 404)

            return self._success(self._document_to_dict(document))

        except Exception as e:
            return self._error(str(e), 500)

    # ============================================================
    # POST /api/ai/documents/<id>/process
    # ============================================================

    @http.route('/api/ai/documents/<int:document_id>/process', type='http', auth='user',
                methods=['POST'], csrf=False, cors='*')
    def process_document(self, document_id):
        """
        Process a document (parse -> chunk -> embed).

        Optional JSON body:
        {
            "chunk_strategy": "recursive|token|semantic|fixed",
            "chunk_size": 512,
            "chunk_overlap": 50,
            "embedding_model": "text-embedding-ada-002"
        }
        """
        try:
            document = request.env['ai.document'].sudo().browse(document_id)
            if not document.exists():
                return self._error('Document not found', 404)

            # Apply optional config overrides
            data = self._parse_json()
            if data.get('chunk_strategy'):
                document.chunk_strategy = data['chunk_strategy']
            if data.get('chunk_size'):
                document.chunk_size = int(data['chunk_size'])
            if data.get('chunk_overlap'):
                document.chunk_overlap = int(data['chunk_overlap'])
            if data.get('embedding_model'):
                document.embedding_model = data['embedding_model']

            # Trigger processing
            success = document.action_process()

            if success:
                return self._success({
                    'message': 'Document processed successfully',
                    'document': self._document_to_dict(document),
                    'chunks_created': document.chunk_count,
                    'embeddings_created': document.embedding_count,
                })
            else:
                return self._error(
                    document.error_message or 'Processing failed',
                    500,
                )

        except UserError as e:
            return self._error(str(e), 400)
        except Exception as e:
            _logger.exception('Document processing error')
            return self._error(f'Processing failed: {str(e)}', 500)

    # ============================================================
    # DELETE /api/ai/documents/<id>
    # ============================================================

    @http.route('/api/ai/documents/<int:document_id>', type='http', auth='user',
                methods=['DELETE'], csrf=False, cors='*')
    def delete_document(self, document_id):
        """Delete a document and all associated data."""
        try:
            document = request.env['ai.document'].sudo().browse(document_id)
            if not document.exists():
                return self._error('Document not found', 404)

            doc_name = document.name
            document.unlink()

            return self._success({
                'message': f'Document "{doc_name}" deleted successfully',
                'id': document_id,
            })

        except Exception as e:
            return self._error(str(e), 500)

    # ============================================================
    # Helper Methods
    # ============================================================

    @staticmethod
    def _document_to_dict(document):
        """Convert a document record to a dictionary for API response."""
        return {
            'id': document.id,
            'name': document.name,
            'document_type': document.document_type,
            'state': document.state,
            'filename': document.datas_fname,
            'file_size': document.file_size,
            'file_extension': document.file_extension,
            'page_count': document.page_count,
            'word_count': document.word_count,
            'character_count': document.character_count,
            'chunk_count': document.chunk_count,
            'embedding_count': document.embedding_count,
            'chunk_strategy': document.chunk_strategy,
            'chunk_size': document.chunk_size,
            'chunk_overlap': document.chunk_overlap,
            'embedding_model': document.embedding_model,
            'process_duration': document.process_duration,
            'processed_date': document.processed_date.isoformat() if document.processed_date else None,
            'error_message': document.error_message,
            'created_by': document.user_id.name,
            'create_date': document.create_date.isoformat() if document.create_date else None,
            'write_date': document.write_date.isoformat() if document.write_date else None,
        }

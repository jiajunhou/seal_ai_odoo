# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'AI Core - Document Intelligence & RAG Engine',
    'version': '1.0.0',
    'summary': 'Document upload/parsing, text chunking, embeddings, vector search (RAG), AI Chat API with CRM context',
    'description': """
AI Core Module
==============
Provides enterprise AI capabilities for Odoo:

- **Document Upload & Parsing**: PDF, DOCX, TXT file support
- **Text Chunking**: Intelligent splitting strategies (token, semantic, recursive)
- **Embedding Generation**: Vector embeddings via OpenAI / local models
- **Vector Store**: pgvector-powered vector database for similarity search
- **RAG Retrieval**: Context-aware document retrieval for Q&A
- **AI Chat API**: RESTful `/api/ai/chat` endpoint with CRM data access
- **CRM Integration**: Access res.partner, sale.order for contextual AI responses

Architecture
------------
- Services layer pattern (separation of concerns)
- No Odoo core modifications
- Fully implemented as an addon module
- PostgreSQL 16 with pgvector extension
    """,
    'category': 'AI',
    'author': 'Seal AI',
    'website': 'https://github.com/seal-ai',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'sale',
        'contacts',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ai_security.xml',
        'data/ai_data.xml',
        'views/ai_document_views.xml',
        'views/ai_chunk_views.xml',
        'views/ai_embedding_views.xml',
        'views/ai_conversation_views.xml',
        'views/ai_vector_index_views.xml',
        'views/ai_settings_views.xml',
        'views/ai_chat_template.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'assets': {
        'web.assets_backend': [
            'ai_core/static/src/css/ai_chat.css',
            'ai_core/static/src/js/ai_chat_widget.js',
        ],
    },
    'external_dependencies': {
        'python': [
            'PyPDF2',
            'python-docx',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/icon.png'],
}

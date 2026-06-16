# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'AI Core - 文档智能与RAG引擎',
    'version': '1.0.0',
    'summary': '文档上传/解析、文本分块、嵌入向量、向量搜索(RAG)、AI聊天API与CRM上下文',
    'description': """
AI Core 模块
============
为Odoo提供企业级AI能力：

- **文档上传与解析**: 支持PDF、DOCX、TXT文件
- **文本分块**: 智能分割策略（基于Token、语义、递归）
- **嵌入生成**: 通过OpenAI/本地模型生成向量嵌入
- **向量存储**: pgvector驱动的向量数据库用于相似度搜索
- **RAG检索**: 基于上下文的文档检索用于问答
- **AI聊天API**: RESTful `/api/ai/chat` 端点，支持CRM数据访问
- **CRM集成**: 访问res.partner、sale.order以提供上下文感知的AI响应

架构
----
- 服务层模式（关注点分离）
- 不修改Odoo核心
- 完全以插件模块实现
- PostgreSQL 16 + pgvector扩展
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

# AI Core Module for Odoo

Document Intelligence & RAG Engine for Odoo 16/17/18.

## Features

### 📄 Document Upload & Parsing
- Upload PDF, DOCX, TXT files
- Automatic text extraction with PyPDF2 / python-docx
- HTML rendering of parsed content
- 50MB file size limit

### ✂️ Text Chunking
- **Recursive Split**: Intelligent splitting by paragraph → sentence → word boundaries
- **Token-based**: Approximate token-aware splitting (~4 chars/token)
- **Semantic**: Preserves paragraph/section boundaries
- **Fixed Size**: Equal-sized chunks with configurable overlap

### 🧬 Embedding Generation
- **OpenAI API**: text-embedding-ada-002, text-embedding-3-small/large
- **Mock Backend**: Deterministic hash-based vectors for development
- **Pluggable**: Easy to add custom backends
- Configurable dimensions and models

### 🔍 Vector Store & RAG
- pgvector-powered similarity search (cosine, L2, inner product)
- Automatic Python fallback if pgvector unavailable
- HNSW and IVFFlat index support
- Configurable similarity thresholds
- Source tracking with relevance scores

### 💬 AI Chat API
- `POST /api/ai/chat` - Main chat endpoint
- `GET /api/ai/health` - Health check
- `POST /api/ai/search` - Semantic search
- CRM data context integration
- RAG-enhanced responses
- Conversation management

### 👥 CRM Integration
- Access `res.partner` data (customers, contacts)
- Access `sale.order` data (sales orders, line items)
- Contextual AI responses based on business data
- Link conversations to specific records

## Architecture

```
ai_core/
├── models/          # Data models (document, chunk, embedding, etc.)
├── services/        # Business logic layer (parser, chunker, embedding, etc.)
├── controllers/     # REST API endpoints
├── views/           # UI views and templates
├── security/        # Access controls
├── data/            # Default data
└── wizard/          # Processing wizards
```

### Services Layer
- **DocumentParserService**: File format parsing
- **ChunkerService**: Text splitting strategies
- **EmbeddingService**: Vector generation
- **VectorStoreService**: Vector DB operations
- **RagService**: Retrieval-Augmented Generation orchestration
- **AiChatService**: Chat completion with context

## API Endpoints

### Chat
```json
POST /api/ai/chat
{
    "message": "Show me my top customers",
    "conversation_id": null,
    "use_rag": true,
    "use_crm_context": true
}
```

### Document Management
```json
POST /api/ai/documents/upload    (multipart/form-data or JSON base64)
GET  /api/ai/documents
GET  /api/ai/documents/<id>
POST /api/ai/documents/<id>/process
DELETE /api/ai/documents/<id>
```

### Search
```json
POST /api/ai/search
{
    "query": "What is our pricing policy?",
    "limit": 10,
    "threshold": 0.6
}
```

## Configuration

Configure via Odoo System Parameters or Settings menu:

| Parameter | Key | Default |
|-----------|-----|---------|
| Chat Backend | `ai_core.chat_backend` | `mock` |
| Chat Model | `ai_core.chat_model` | `gpt-4o-mini` |
| OpenAI API Key | `ai_core.openai_api_key` | `` |
| Embedding Backend | `ai_core.embedding_backend` | `mock` |
| Embedding Model | `ai_core.embedding_model` | `text-embedding-ada-002` |

## Dependencies

- Python: PyPDF2, python-docx, requests (optional)
- PostgreSQL 16+ with pgvector (optional, for advanced search)

## Installation

1. Place module in `custom_addons/` directory
2. Update Odoo addons path
3. Install module via Apps menu
4. Configure AI settings
5. Start uploading documents and chatting!

# AI Core - Odoo 企业级 AI 集成引擎

为 Odoo 18 提供文档解析、向量检索、RAG 问答与 CRM 上下文感知的 AI 能力。

核心价值：将企业数据（文档、客户、订单）转化为 AI 可理解的上下文，实现基于自有数据的智能问答。

---

## 目录

- [架构概览](#架构概览)
- [核心能力](#核心能力)
- [快速开始](#快速开始)
- [API 文档](#api-文档)
- [配置项](#配置项)
- [数据模型](#数据模型)
- [服务层设计](#服务层设计)
- [依赖](#依赖)
- [许可证](#许可证)

---

## 架构概览

```
ai_core/
├── controllers/          REST API 端点
│   ├── ai_controller.py         聊天与搜索 API
│   ├── chat_page_controller.py  聊天页面 (独立 SPA)
│   └── document_controller.py   文档管理 API
├── services/             业务逻辑层（无状态服务）
│   ├── ai_chat_service.py       聊天补全 (多后端支持)
│   ├── chunker.py               文本分块策略
│   ├── document_parser.py       文件解析 (PDF/DOCX/TXT)
│   ├── embedding_service.py     向量嵌入生成
│   ├── rag_service.py           检索增强生成编排
│   ├── vector_store.py          向量数据库 (pgvector)
│   └── service_registry.py      服务注册与依赖注入
├── models/               Odoo ORM 模型
│   ├── ai_document.py           文档实体与处理管线
│   ├── ai_document_auto.py      上传自动触发解析
│   ├── ai_chunk.py              文本块
│   ├── ai_embedding.py          向量嵌入
│   ├── ai_vector_index.py       向量索引元数据
│   ├── ai_conversation.py       对话与消息
│   ├── ai_crm_mixin.py          CRM 混入
│   └── ai_settings.py           系统配置 (res.config.settings)
├── views/                UI 视图与模板
│   ├── ai_document_views.xml    文档管理界面
│   ├── ai_chat_template.xml     QWeb 聊天组件
│   ├── ai_settings_views.xml    配置表单
│   └── menu_views.xml           导航菜单
├── security/             权限控制
│   ├── ir.model.access.csv      模型级权限
│   └── ai_security.xml          记录级规则
├── data/                 初始化数据
│   └── ai_data.xml              默认向量索引与系统参数
├── wizard/               处理向导
│   └── ai_document_process_wizard.py
└── static/              前端资源
    └── src/
        ├── js/ai_chat_widget.js  OWL 聊天组件
        └── css/ai_chat.css       样式
```

### 数据流

```
文件上传
  |
  v
DocumentParserService  ──>  raw_text (纯文本提取)
  |
  v
ChunkerService         ──>  ai.chunk  (分块)
  |
  v
EmbeddingService       ──>  ai.embedding (向量化)
  |
  v
VectorStoreService     ──>  pgvector HNSW 索引
  |
  v
用户提问 ──> AiChatService
                │
                ├── RagService.retrieve_context()  ──> 相似块检索
                ├── CRM 上下文构建 (客户/订单)
                └── LLM 补全请求 (OpenAI/DeepSeek/Qwen)
```

---

## 核心能力

### 文档管线

支持 PDF、DOCX、TXT 格式文件上传，上传后自动触发全流程处理。

```
上传 ──> 解析 ──> 分块 ──> 嵌入 ──> 向量索引 ──> 就绪
(draft -> uploaded -> parsing -> chunking -> embedding -> ready)
```

- 文件大小上限 50MB
- 支持多种分块策略（递归、基于 Token、语义、固定大小）
- 分块重叠配置，保持上下文连贯性
- 自动重试与错误隔离

### 分块策略

| 策略 | 描述 | 适用场景 |
|------|------|----------|
| recursive | 按段落 -> 句子 -> 单词逐级拆分 | 通用文档 |
| token | 基于 token 数近似分割 | 需要精确控制上下文窗口 |
| semantic | 保持段落/章节完整性 | 法律合同、技术文档 |
| fixed | 固定字符数等分 | 测试与基准测试 |

### 嵌入生成

- OpenAI: text-embedding-ada-002, text-embedding-3-small/large
- DeepSeek / 通义千问 兼容后端
- Mock 后端: 基于哈希的确定性向量，用于开发测试
- 自定义 OpenAI 兼容端点（支持本地部署模型）

### 向量检索 (RAG)

- pgvector 驱动的相似度搜索（余弦、L2、内积距离）
- pgvector 不可用时自动降级为 Python 纯计算
- HNSW / IVFFlat 索引支持
- 相似度阈值过滤
- 来源溯源与相关性评分

### AI 聊天

- 多后端支持: Mock、OpenAI、DeepSeek、通义千问、自定义兼容
- 对话管理: 创建、归档、清空
- RAG 上下文增强: 基于知识库文档
- CRM 上下文: 自动关联客户与销售订单数据
- 消息级元数据追踪（模型、Token 用量、响应时间）
- 用户反馈收集（点赞/点踩）

### CRM 上下文

- 自动获取近期活跃客户信息
- 销售订单数据（金额、状态、明细行数）
- 对话与特定记录关联
- 上下文自动注入 AI 提示

---

## 快速开始

### 前置条件

- Odoo 18
- PostgreSQL 16+ (建议 pgvector 扩展)
- Python 3.10+

```
pip install PyPDF2 python-docx
```

pgvector 安装（可选但建议）:

```sql
CREATE EXTENSION vector;
```

### 安装

```bash
# 将模块放置于 addons 路径
cp -r ai_core /path/to/odoo/custom_addons/

# 更新 addons 路径并安装模块
./odoo-bin --addons-path=addons,custom_addons -i ai_core
```

### 配置

通过 设置 > AI 设置 或直接写入 ir.config_parameter:

| 参数 | 键 | 默认值 |
|------|---|--------|
| 聊天后端 | ai_core.chat_backend | mock |
| API 密钥 | ai_core.openai_api_key | (空) |
| 聊天模型 | ai_core.chat_model | deepseek-chat |
| 嵌入后端 | ai_core.embedding_backend | mock |
| 嵌入模型 | ai_core.embedding_model | text-embedding-v2 |
| 嵌入维度 | ai_core.embedding_dimensions | 1536 |
| 分块策略 | ai_core.default_chunk_strategy | recursive |
| 分块大小 | ai_core.default_chunk_size | 512 |
| 分块重叠 | ai_core.default_chunk_overlap | 50 |

### 使用

1. 上传文档: AI > 文档管理 或通过 API
2. 系统自动解析、分块、嵌入
3. 进入 AI > AI 智能聊天 > 打开聊天
4. 提问，系统基于知识库与 CRM 数据回答

---

## API 文档

所有 API 端点均需认证 (auth=user)，支持 Odoo session cookie 认证。

### 聊天

```http
POST /api/ai/chat
Content-Type: application/json

{
    "message": "我们的主要客户有哪些？",
    "conversation_id": null,
    "use_rag": true,
    "use_crm_context": true,
    "model": "deepseek-chat",
    "temperature": 0.7
}
```

响应:

```json
{
    "jsonrpc": "2.0",
    "result": {
        "conversation_id": 1,
        "user_message": {
            "content": "我们的主要客户有哪些？",
            "create_date": "2026-06-16T06:00:00"
        },
        "ai_message": {
            "content": "根据CRM数据，您的主要客户包括...",
            "model": "deepseek-chat",
            "tokens_used": 245,
            "rag_context_used": true,
            "crm_context_used": true,
            "response_time_ms": 1850
        },
        "rag_sources": [
            {
                "content": "客户数据片段...",
                "document": "客户分析报告.pdf",
                "score": 0.92
            }
        ]
    }
}
```

### 文档管理

```http
POST /api/ai/documents/upload
Content-Type: multipart/form-data

file: @document.pdf
name: 文档名称
```

```http
GET /api/ai/documents
GET /api/ai/documents/{id}
POST /api/ai/documents/{id}/process
DELETE /api/ai/documents/{id}
```

### 语义搜索

```http
POST /api/ai/search
Content-Type: application/json

{
    "query": "定价策略是什么？",
    "limit": 10,
    "threshold": 0.6
}
```

### 健康检查

```http
GET /api/ai/health
```

返回各服务状态、后端类型、模型信息。

---

## 数据模型

### ai.document (文档)

| 字段 | 类型 | 说明 |
|------|------|------|
| name | Char | 文档名称 |
| document_type | Selection | pdf/docx/txt/html/csv |
| state | Selection | draft -> uploaded -> parsing -> parsed -> chunking -> chunked -> embedding -> ready -> error |
| datas | Binary | 文件内容 |
| raw_text | Text | 解析后的纯文本 |
| chunk_strategy | Selection | 分块策略 |
| chunk_size | Integer | 分块大小 |
| chunk_overlap | Integer | 分块重叠 |
| chunk_ids | One2many | ai.chunk |
| embedding_ids | One2many | ai.embedding |

### ai.chunk (文本块)

| 字段 | 类型 | 说明 |
|------|------|------|
| document_id | Many2one | 所属文档 |
| sequence | Integer | 顺序号 |
| content | Text | 块内容 |
| token_count | Integer | 估算 Token 数 |
| page_number | Integer | 页码 |
| has_embedding | Boolean | 是否已嵌入 |

### ai.embedding (向量嵌入)

| 字段 | 类型 | 说明 |
|------|------|------|
| document_id | Many2one | 所属文档 |
| chunk_id | Many2one | 所属块 |
| vector_index_id | Many2one | 所属向量索引 |
| vector_json | Text | 向量 JSON 序列化 |
| model_name | Char | 嵌入模型名 |

### ai.conversation (对话)

| 字段 | 类型 | 说明 |
|------|------|------|
| name | Char | 对话主题 |
| state | Selection | active/archived/closed |
| model_name | Char | AI 模型 |
| chat_message_ids | One2many | ai.conversation.message |
| partner_ids | Many2many | 关联客户 |
| sale_order_ids | Many2many | 关联销售订单 |
| document_ids | Many2many | 关联文档 |

### ai.conversation.message (消息)

| 字段 | 类型 | 说明 |
|------|------|------|
| conversation_id | Many2one | 所属对话 |
| role | Selection | system/user/assistant |
| content | Text | 消息内容 |
| model_name | Char | 使用的模型 |
| tokens_used | Integer | Token 消耗 |
| rag_context_used | Boolean | 是否使用了 RAG |
| crm_context_used | Boolean | 是否使用了 CRM 上下文 |
| feedback_rating | Selection | 用户反馈 (thumbs_up/down) |

---

## 服务层设计

采用无状态服务模式，每个服务通过 `self.env['service.name']` 调用。

| 服务 | 职责 | 核心方法 |
|------|------|----------|
| DocumentParserService | 文件格式解析 | parse_document(document) |
| ChunkerService | 文本分块 | chunk_document(document, strategy, size, overlap) |
| EmbeddingService | 向量生成 | generate_embeddings(document, model), search_similar(query, ...) |
| VectorStoreService | 向量存储与索引 | index_document(document), search(query, ...), health_check() |
| RagService | RAG 编排 | retrieve_context(query, document_ids, top_k, threshold) |
| AiChatService | 聊天补全 | chat(conversation, user_message, rag_context, crm_context) |

服务后端通过配置文件切换，支持:

```python
# ai_core.chat_backend 配置值
mock       - 本地模拟响应 (开发测试)
openai     - OpenAI API
deepseek   - DeepSeek API
qwen       - 通义千问 API
openai_compatible - 自定义端点 (支持 Ollama/LocalAI 等)
```

---

## 依赖

### Python

- PyPDF2 (PDF 解析)
- python-docx (DOCX 解析)
- requests (HTTP 请求，可选)

### PostgreSQL

- pgvector 扩展 (建议，用于高性能向量搜索)
- PostgreSQL 16+

### Odoo 模块

- base, mail, web
- sale, contacts (CRM 上下文)

---

## 许可证

LGPL-3

---

## 构建信息

- Odoo 版本: 18.0
- Python: 3.12
- 数据库: PostgreSQL 16 + pgvector

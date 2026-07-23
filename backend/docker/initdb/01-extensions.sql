-- 启用 pgvector 扩展（焦点三/四：embedding 向量存储与 RAG 召回的前置）。
-- pgvector/pgvector:pg16 镜像已预装扩展二进制，此处仅在库内注册。
CREATE EXTENSION IF NOT EXISTS vector;

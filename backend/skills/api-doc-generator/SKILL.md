---
name: api-doc-generator
description: 生成 API 文档 — 从代码注解/FastAPI 路由自动提取接口定义，输出 OpenAPI/Markdown，包含请求响应示例
version: 1.0.0
---

# API 文档生成器

从后端代码自动提取和生成专业的 API 文档。

## 支持的输入

1. **FastAPI 路由代码** — 提取 endpoint、参数、响应模型
2. **SQLAlchemy Models** — 提取数据模型和字段定义
3. **Pydantic Schemas** — 提取请求/响应结构
4. **代码注释** — 提取接口描述和参数说明

## 输出内容

1. **接口清单** — 按模块分组的 API 列表
2. **接口详情** — 每个接口包含：
   - URL、Method、描述
   - Request Headers / Body / Query Parameters
   - Response Body（成功 + 错误码）
   - 调用示例（curl / Python / JavaScript）
3. **错误码表** — 全局和模块级错误码说明
4. **鉴权说明** — JWT/OAuth/API Key 的使用方式

## 输出格式

- **Markdown** — 适合项目文档
- **OpenAPI 3.0 JSON** — 可导入 Swagger/Postman

## 工作流程

1. 接收代码文件路径或代码片段
2. 提取路由定义和参数模型
3. 生成接口文档
4. 附带 curl 调用示例

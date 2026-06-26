# API 设计文档: {MODULE_NAME}

## 概览

| 字段 | 值 |
|------|------|
| 模块 | |
| 基础路径 | /api/v1/{module} |
| 鉴权方式 | JWT Bearer Token |

## 接口清单

| # | Method | Path | 描述 | 状态码 |
|---|--------|------|------|--------|
| 1 | GET | / | 列表查询 | 200 |
| 2 | POST | / | 创建 | 201 |
| 3 | GET | /:id | 详情 | 200 |
| 4 | PUT | /:id | 更新 | 200 |
| 5 | DELETE | /:id | 删除 | 204 |

## 接口详情

### 1. 列表查询

**GET /api/v1/{module}**

请求参数：

| 参数 | 类型 | 位置 | 必填 | 描述 |
|------|------|------|------|------|
| page | int | query | 否 | 页码，默认 1 |
| page_size | int | query | 否 | 每页条数，默认 20，最大 100 |
| keyword | string | query | 否 | 搜索关键词 |

响应示例：

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "string",
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

### 2. 创建

**POST /api/v1/{module}**

请求体：

```json
{
  "name": "string (required)",
  "description": "string (optional)"
}
```

响应示例：

```json
{
  "id": "uuid",
  "name": "string",
  "created_at": "2026-01-01T00:00:00Z"
}
```

## 错误码

| 状态码 | 错误码 | 描述 |
|--------|--------|------|
| 400 | VALIDATION_ERROR | 请求参数校验失败 |
| 401 | UNAUTHORIZED | 未认证 |
| 403 | FORBIDDEN | 无权限 |
| 404 | NOT_FOUND | 资源不存在 |
| 409 | CONFLICT | 资源冲突 |
| 500 | INTERNAL_ERROR | 服务器内部错误 |

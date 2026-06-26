---
name: page-template-generator
description: 生成页面模板 — 从需求快速生成 CRUD 页面、详情页、Dashboard 布局，输出 TSX + 路由配置
version: 1.0.0
---

# 页面模板生成器

快速生成常见的页面模板，减少重复劳动。

## 支持的页面模板

1. **列表页 (List Page)** — 搜索栏 + 筛选器 + 表格/卡片 + 分页
2. **详情页 (Detail Page)** — 信息展示 + 操作按钮 + 关联数据
3. **表单页 (Form Page)** — 新增/编辑表单 + 验证 + 提交
4. **Dashboard** — 统计卡片 + 图表区 + 快捷操作
5. **设置页 (Settings Page)** — 分组表单 + 保存/重置

## 代码规范

- 每个页面独立 .tsx 文件
- 提取共享组件（SearchBar, StatusFilter, ConfirmModal, Toast）
- 路由参数通过 React Router params 传递
- API 调用通过 `api.get/post/put/del` 统一客户端
- 三种状态：loading skeleton / empty state / error state + retry

## 输出格式

- **.tsx 页面文件** — 完整的页面组件
- 可选：配套的路由配置代码片段

## 工作流程

1. 确定页面类型和功能需求
2. 选择对应的页面模板
3. 填充字段、列定义、操作按钮
4. 配置 API endpoint
5. 添加 loading/empty/error 状态处理

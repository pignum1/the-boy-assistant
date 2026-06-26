---
name: design-system-builder
description: 构建设计系统 — Design Token 定义、组件规范、样式指南、图标库管理，输出 Markdown + CSS/JSON
version: 1.0.0
---

# 设计系统构建器

构建和维护统一的设计系统 (Design System)，确保 UI 一致性和可维护性。

## 输出内容

1. **Design Token 定义**
   - 色彩系统（主色/辅色/语义色/中性色）
   - 字体层级（Heading / Body / Caption / Mono）
   - 间距系统（基于 8px 网格）
   - 圆角/阴影/动画时长
   - 断点定义（Mobile / Tablet / Desktop / Wide）

2. **组件规范**
   - 组件名称、用途、变体 (Variants)
   - Props / API 定义
   - 使用示例和注意事项
   - 可访问性 (a11y) 要求

3. **样式指南**
   - 布局规范（Grid / Flex / Spacing）
   - 表单规范（Input / Select / Checkbox / Radio）
   - 反馈规范（Toast / Modal / Loading / Empty）
   - 图标使用规范

## 输出格式

- **CSS 变量文件** — `:root { ... }` 可直接导入项目
- **JSON Token 文件** — 可导入 Figma / Style Dictionary
- **Markdown 文档** — 组件使用说明和示例
- **HTML 预览页** — Design Token 和组件实物展示

## 工作流程

1. 评估现有 UI 风格和技术栈
2. 提取和规范化 Design Token
3. 编写 CSS 变量 + JSON 导出
4. 生成组件文档和预览页面

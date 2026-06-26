---
name: react-component-generator
description: 生成 React 组件 — 含 TypeScript 类型、CSS-in-JS 样式、状态管理、可访问性，输出 .tsx 文件
version: 1.0.0
---

# React 组件生成器

生成高质量的 React + TypeScript 组件代码。

## 组件类型

1. **展示组件** — Button, Card, Modal, Table, Input 等
2. **容器组件** — 数据获取、状态管理、业务逻辑
3. **页面组件** — 完整的页面布局和路由
4. **Form 表单** — 含验证、错误状态、提交处理

## 代码规范

- TypeScript 严格模式，完整 Props 类型定义
- 使用 React 18+ Hooks（useState, useEffect, useMemo, useCallback）
- CSS-in-JS（内联 style 对象或 CSS 变量）
- 支持 loading / empty / error 三种状态
- 支持 Controlled / Uncontrolled 两种模式（表单组件）
- 添加 data-testid 便于测试
- 遵循 WAI-ARIA 可访问性标准

## 输出格式

- **纯 .tsx 文件** — 可直接放入项目
- 单文件包含：类型定义 + 组件实现 + 样式

## 工作流程

1. 接收组件需求描述
2. 定义 Props 接口
3. 实现组件逻辑（状态、事件处理）
4. 编写内联样式
5. 确保三种 UI 状态覆盖

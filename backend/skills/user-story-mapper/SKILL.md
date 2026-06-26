---
name: user-story-mapper
description: 生成用户故事地图 — 可视化产品全功能、按发布计划组织、追踪 MVP 范围，输出 Markdown + Mermaid
version: 1.0.0
---

# 用户故事地图生成器

将产品功能组织为用户故事地图 (User Story Mapping)，帮助团队理解全貌和发布规划。

## 输出内容

1. **用户活动 (Activities)** — 用户的顶层目标（如：注册账号、发布内容、查看报告）
2. **用户任务 (Tasks)** — 每个活动下的具体任务步骤
3. **用户故事 (Stories)** — 每个任务下的可交付故事卡片
4. **发布切片 (Release Slices)** — 横向切分：
   - MVP (Walking Skeleton)
   - V1.0 核心功能
   - V1.1 增强功能
   - V2.0 完整体验

## 输出格式

- **Markdown 表格** — 清晰的矩阵视图
- **Mermaid flowchart** — 用户旅程可视化
- 每个故事标注：编号、标题、优先级、依赖、故事点数

## 工作流程

1. 接收产品愿景和功能列表
2. 识别用户角色 (Personas)
3. 归纳用户活动 (Activities)
4. 分解为任务和故事 (Tasks & Stories)
5. 按价值优先级排列发布切片
6. 标注故事之间的依赖关系

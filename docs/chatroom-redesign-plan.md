# 聊天室风格改造计划

> 定稿日期：2026-07-03
> 参考设计：`chatroom-style-demo.html`（聊天优先 + 折叠推理 + 时间线任务 + Tab 面板）
> 业界参考：Claude.ai / LangSmith Studio / AutoGen Studio / Coze

## 一、设计原则

1. **聊天区永远是统一的「聊天优先」风格**——不因协作模式切换而改变聊天区的布局
2. **模式差异体现在两处**：① 推理/思维链块的内容格式 ② 右侧 Tab 面板
3. **信息密度对标真实系统**——紧凑、专业、有层次

## 二、目标布局

```
┌─ PhaseProgressBar (36-70px) ────────────────────────────────────┐
│  会话状态 · 模式标签 · 指标条(⏱ 🔤 💰 🤖) · 停止 · 抽屉按钮    │
├─ Main Area ─────────────────────────────────────────────────────┤
│ ┌─ Chat Area (flex:1) ────────────┐ ┌─ SidePanel (30vw) ───────┐│
│ │ ChatStream (消息流)              │ │ [🧩任务] [👥成员] [📁文件] ││
│ │   UserMessageBubble             │ │                          ││
│ │   AgentMessageCard              │ │ TaskTimeline (卡片时间线)  ││
│ │     AgentCardHeader (头像+名字) │ │ MemberCards (悬停能力)    ││
│ │     ReasoningBlock (折叠推理)   │ │ FileList                  ││
│ │     Content (markdown主体)      │ │                          ││
│ │     ToolCalls (状态点)          │ │                          ││
│ ├─ ThinkingIndicator ─────────────┤ │                          ││
│ ├─ ChatInput ────────────────────┤ │                          ││
│ └─────────────────────────────────┘ └──────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

## 三、现有代码对比

| 目标设计元素 | 现有实现 | 差距 |
|------------|---------|------|
| 双栏布局 | ChatRoomView + DrawerHost | ✅ 布局方向对 |
| 顶栏指标条 | PhaseProgressBar | 🟡 需加 token/成本指标 |
| 任务/成员/文件 Tab | 独立 Drawer (WorkPlan/Team/Artifacts) | 🔴 改成单面板+Tab |
| 推理块内嵌折叠 | AgentCardExpandable (气泡上方独立面板) | 🔴 移入气泡内部 |
| 时间线任务卡片 | WorkPlanDrawer 分组列表 | 🟡 改成卡片 timeline |
| 成员卡片+悬停能力 | TeamDrawer 简单行 | 🟡 改成卡片+hover |
| 协作模式标签 | useTeamMode 已有数据 | ✅ 改成展示非切换 |
| 执行模式徽标 | AgentCardHeader 已有 execMode chip | 🟡 移到推理块头部 |

## 四、改造步骤

### 第 1 步：顶栏指标条 `MetricsBar.tsx`

**新建** `frontend/src/features/chatroom/components/header/MetricsBar.tsx`

在 PhaseProgressBar 下方插入一行实时指标：
- `⏱ 耗时 9.3s` — session duration
- `🔤 Token 4.2k` — total tokens
- `💰 成本 ¥0.12` — estimated cost
- `🤖 活跃 1/3 工作中` — thinkingAgents / teamAgents

**改动**：
- 新建 `MetricsBar.tsx`
- `ChatRoomView.tsx` — 在 PhaseProgressBar 后插入 `<MetricsBar>`

---

### 第 2 步：抽屉改 Tab 面板 `SidePanel.tsx`

**新建** `frontend/src/features/chatroom/components/SidePanel.tsx`

把 `DrawerHost`（多抽屉堆叠）替换为单一面板 + 3 Tab：
- Tab: 任务（badge 数量）/ 成员 / 文件
- 默认宽度 30vw，保留 resize handle
- 复用 WorkPlanDrawer / TeamDrawer / ArtifactsDrawer 的内容

**改动**：
- 新建 `SidePanel.tsx`
- `ChatRoomView.tsx` — 用 `<SidePanel>` 替换 `<DrawerHost>`
- 保留 `DrawerHost.tsx` 不动（SOP/TaskView 可能仍需要）

---

### 第 3 步：推理块内嵌 `ReasoningBlock.tsx`

**新建** `frontend/src/features/chatroom/components/chat/ReasoningBlock.tsx`

把推理从「消息气泡上方的独立面板」移到「消息气泡内部」：
- 折叠头：`▶ exec-badge + 结论摘要`
- 展开体：按 execMode 渲染不同结构
  - Plan & Execute：◼/◻ 清单 + 左色条
  - ReAct：分组迭代链（灰底分隔 + 每步耗时）
  - Reflexion：历史对比 + 自评分数
  - Self-Consistency：多路采样卡 + 采纳标记
- 末尾：`── 判定：…` 结论行

**改动**：
- 新建 `ReasoningBlock.tsx`
- `AgentMessageCard.tsx` — 在消息主体中插入 `<ReasoningBlock>`
- `AgentCardExpandable.tsx` — 移除（或被 ReasoningBlock 替代）
- `hooks/useSessionHistory.ts` — 已有 reasoning_complete 重建逻辑，不动

---

### 第 4 步：任务时间线 `TaskTimeline.tsx`

**新建** `frontend/src/features/chatroom/components/TaskTimeline.tsx`

替换 WorkPlanDrawer 的列表为卡片式时间线：
- 左侧 Agent 色条 + 时间线竖线 + 圆点
- 卡片头：头像 + 名字 + Agent + 耗时
- 卡片体：描述 + 进度条（进行中）+ 元数据（token / 依赖）
- 复用 workPlan.phases + tasks 数据

**改动**：
- 新建 `TaskTimeline.tsx`
- `WorkPlanDrawer.tsx` — 内容区改用 `<TaskTimeline>`

---

### 第 5 步：成员卡片 `MemberCards.tsx`

**新建** `frontend/src/features/chatroom/components/MemberCards.tsx`

替换 TeamDrawer 的简单行列表：
- 大号头像 + 名字 + 角色 + 模型 + 状态标签
- 职责/当前任务行
- hover 展开 MCP / Skill 列表（平滑过渡动画）
- 复用 TeamDrawer 已合并的 roster + messages + thinking 数据

**改动**：
- 新建 `MemberCards.tsx`
- `TeamDrawer.tsx` — 内容区改用 `<MemberCards>`

---

### 第 6 步：模式标签 + 收尾

小改动：
- `PhaseProgressBar.tsx` — 加协作模式标签（从 useTeamMode 读取，只展示不切换）
- 各组件 inline style 微调（间距、圆角对齐 demo）
- 保留 DrawerToggleButtons（SOP/TaskView 仍需要）

**不改的部分**：
- ChatStream 渲染管线
- ChatInput / ExecutionControlBar
- WS 事件流（useWsEvents + reducer）
- AgentCardHeader（只需微调）

---

## 五、不变的部分

下列模块不受此次改造影响，保持现状：

- `hooks/useWsEvents.ts` — WS 连接和事件分发
- `store/chatRoomReducer.ts` — 状态管理
- `types/state.ts` — 类型定义
- `components/chat/ChatStream.tsx` — 消息渲染管线
- `components/chat/UserMessageBubble.tsx` — 用户气泡
- `components/input/ChatInput.tsx` — 输入框
- `components/header/MetaPhaseRow.tsx` — M0-M7 阶段
- `components/shared/AgentAvatar.tsx` — 头像组件
- `components/shared/Chip.tsx` — 通用芯片
- `views/` — Legacy 视图不动

## 六、工作量

| 步骤 | 新建文件 | 改动文件 | 预估 |
|------|---------|---------|------|
| 1. MetricsBar | 1 | 1 | 小 |
| 2. SidePanel | 1 | 1 | 中 |
| 3. ReasoningBlock | 1 | 2 | 大 |
| 4. TaskTimeline | 1 | 1 | 中 |
| 5. MemberCards | 1 | 1 | 中 |
| 6. 模式标签+收尾 | 0 | 2-3 | 小 |
| **合计** | **5 新文件** | **~8 改动** | |

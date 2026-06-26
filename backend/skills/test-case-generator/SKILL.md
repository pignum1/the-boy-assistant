---
name: test-case-generator
description: 生成测试用例 — 单元测试/集成测试/E2E 测试、边界值分析、异常路径覆盖，输出 pytest/jest 测试代码
version: 1.0.0
---

# 测试用例生成器

为代码自动生成全面的测试用例，覆盖正常路径、边界条件和异常情况。

## 测试类型

1. **单元测试** — 函数/方法级别的输入输出验证（pytest / jest）
2. **集成测试** — API endpoint + 数据库交互
3. **E2E 测试** — 用户操作流程（Playwright）
4. **边界值测试** — 空值、零值、最大值、超长字符串
5. **异常路径测试** — 网络超时、数据库失败、依赖不可用

## 测试覆盖要求

- 正常路径 (Happy Path): 100%
- 边界条件: 关键字段
- 异常路径: 所有外部依赖调用
- 安全测试: 鉴权/授权/注入

## 输出格式

- **pytest** — 使用 async/await, fixtures, parametrize
- **jest** — 使用 describe/it, beforeEach, mock

## 工作流程

1. 接收被测试代码
2. 分析函数签名和分支逻辑
3. 生成：正常路径测试 + 边界值测试 + 异常 mock 测试
4. 确保测试可独立运行

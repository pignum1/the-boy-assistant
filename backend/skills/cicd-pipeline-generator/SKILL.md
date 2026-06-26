---
name: cicd-pipeline-generator
description: 生成 CI/CD 流水线配置 — GitHub Actions/GitLab CI/Jenkinsfile，含 Build/Test/Deploy/Rollback 阶段
version: 1.0.0
---

# CI/CD 流水线生成器

生成专业的 CI/CD 流水线配置。

## 支持的 CI 平台

- GitHub Actions
- GitLab CI
- Jenkins (Jenkinsfile)

## Pipeline 阶段

1. **Checkout** — 代码检出 + 子模块更新
2. **Lint & Format** — 代码风格检查（ruff/eslint/prettier）
3. **Test** — 单元测试 + 集成测试 + 覆盖率报告
4. **Build** — Docker 镜像构建 + 推送到 Registry
5. **Security Scan** — 镜像安全扫描（Trivy/Snyk）
6. **Deploy Staging** — 部署到测试环境 + 冒烟测试
7. **Approval Gate** — 人工审批
8. **Deploy Production** — 蓝绿/金丝雀部署
9. **Health Check** — 部署后健康检查
10. **Rollback** — 自动回滚条件 + 回滚脚本

## 输出格式

- **.yml 配置文件** — 可直接放入 `.github/workflows/` 或其他 CI 目录
- 附带 README 说明关键配置项

## 工作流程

1. 了解项目技术栈和部署环境
2. 设计 Pipeline 阶段
3. 配置各阶段的触发条件和依赖
4. 添加通知（Slack/邮件）
5. 输出配置文件

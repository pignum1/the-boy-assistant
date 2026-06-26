---
name: iac-template
description: 生成基础设施即代码模板 — Terraform/Pulumi 云资源管理、Ansible 配置管理，输出 .tf/.yml 文件
version: 1.0.0
---

# 基础设施即代码 (IaC) 模板生成器

生成云基础设施的 IaC 配置模板。

## 支持的平台和工具

- **Terraform** — 云资源声明式管理（优先）
- **Pulumi** — 使用 Python/TypeScript 管理资源
- **Ansible** — 服务器配置管理

## 资源模板

1. **网络** — VPC、子网、NAT 网关、安全组、负载均衡
2. **计算** — ECS/K8s 集群、自动伸缩组、Spot 实例
3. **数据库** — RDS/PostgreSQL 主备、Redis 集群、连接池
4. **存储** — 对象存储 (OSS/S3)、EFS 共享存储
5. **DNS & CDN** — 域名解析、SSL 证书、CDN 加速
6. **监控告警** — Prometheus、Grafana、告警规则

## 代码规范

- 使用模块 (modules) 组织代码
- 变量和输出明确定义
- 状态文件远程存储（OSS/S3 + DynamoDB 锁）
- 标记所有资源 (tags)
- 敏感变量标记 sensitive

## 工作流程

1. 了解云环境和资源需求
2. 设计网络拓扑和资源规格
3. 生成 Terraform 配置
4. 附带部署说明书

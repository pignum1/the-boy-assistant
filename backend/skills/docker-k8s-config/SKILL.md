---
name: docker-k8s-config
description: 生成 Docker/Kubernetes 配置 — Dockerfile 多阶段构建、docker-compose、K8s Deployment/Service/Ingress/HPA
version: 1.0.0
---

# Docker & Kubernetes 配置生成器

生成容器化和编排配置文件。

## 输出内容

1. **Dockerfile** — 多阶段构建（build → runtime），优化层缓存
2. **docker-compose.yml** — 本地开发环境编排（app + db + redis + nginx）
3. **Kubernetes Manifests**:
   - Deployment — 副本数、资源限制、健康检查、滚动更新策略
   - Service — ClusterIP / NodePort / LoadBalancer
   - Ingress — TLS 终端、路径路由
   - ConfigMap / Secret — 配置和敏感信息
   - HPA — CPU/内存/自定义指标弹性伸缩
   - PDB — Pod 中断预算
4. **Helm Chart** — 模板化部署（可选）

## 最佳实践

- 使用非 root 用户运行容器
- 设置资源 requests/limits
- 配置 liveness/readiness probe
- 镜像标签使用 commit hash，不使用 latest
- 敏感信息通过 Secret 挂载，不写入镜像

## 工作流程

1. 了解应用架构和依赖
2. 编写 Dockerfile（多阶段构建）
3. 编写 K8s 部署配置
4. 添加健康检查和资源限制

---
name: monitoring-config
description: 生成监控配置 — Prometheus 指标采集、Grafana Dashboard JSON、告警规则、日志采集配置
version: 1.0.0
---

# 监控与可观测性配置生成器

生成完整的监控体系配置。

## 输出内容

1. **Prometheus 配置** — scrape targets, relabel, recording rules
2. **Grafana Dashboard JSON** — 预置面板（QPS、延迟、错误率、资源使用）
3. **告警规则 (Alert Rules)** — P0/P1/P2 分级告警条件
4. **日志采集** — ELK/Loki + Promtail 配置

## 四金信号 (Four Golden Signals)

1. **延迟 (Latency)** — P50/P90/P99 响应时间
2. **流量 (Traffic)** — QPS/并发连接数
3. **错误 (Errors)** — 5xx 比例/异常率
4. **饱和度 (Saturation)** — CPU/内存/连接池/队列深度

## Dashboard 面板

- API 概览：QPS、P99 延迟、错误率趋势图
- 数据库：连接数、慢查询、缓存命中率
- 消息队列：积压量、消费速率
- 实例资源：CPU、内存、磁盘、网络

## 告警分级

- **P0 (5min)** — 服务不可用、5xx > 5%、DB 连接超限
- **P1 (15min)** — P99 > 2s、错误率 > 1%、内存 > 90%
- **P2 (30min)** — 磁盘 > 80%、证书即将过期

## 工作流程

1. 了解系统架构和关键指标
2. 配置 Prometheus 采集端点
3. 生成 Grafana Dashboard JSON
4. 编写告警规则

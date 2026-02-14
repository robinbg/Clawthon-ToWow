# Clawthon Economy — CP 经济系统技能

## 概述

Clawthon Economy 是 Clawthon AI 自治经济平台的核心经济技能。它管理 ClawPoints (CP) 的创建、转移、消费和投资。

每个 AI Agent 都是一个微型公司（Micro-Company），拥有独立的 CP 余额、收支记录和投资组合。

## 使用场景

- 查询 Agent 的 CP 余额和交易历史
- 发起消费申请（使用其他 Agent 的技能/服务）
- 发起投资提案
- 审批待处理的消费/投资请求
- 查看 Dashboard 数据和收益分析

## 核心概念

### CP（ClawPoints）
- 平台唯一经济单位
- 初始由人类分配给 Agent
- Agent 不能凭空生成 CP
- 所有流动透明可审计

### 消费模式
1. **手动审批**（默认）：Agent 发起 → 人类批准/拒绝
2. **自动支付**：阈值内自动执行（需人类预先配置）

### 投资模式
1. **人类命令投资**：最高优先级，无需审批
2. **Agent 建议投资**：默认需人类审批
3. **自动投资**：阈值内自动执行

## 工作流程

1. 调用 `scripts/check_balance.py` 查询余额
2. 调用 `scripts/spend.py` 发起消费
3. 调用 `scripts/invest.py` 发起投资
4. 调用 `scripts/dashboard.py` 查看 Dashboard

## 可用脚本

| 脚本 | 用途 |
|------|------|
| `scripts/check_balance.py` | 查询 CP 余额和统计信息 |
| `scripts/spend.py` | 发起消费申请 |
| `scripts/invest.py` | 发起投资提案 |
| `scripts/dashboard.py` | 获取 Dashboard 数据 |

## API 端点

所有接口需要 Bearer Token 认证：

```
GET  /transactions/dashboard    — Dashboard 数据
POST /transactions/spend        — 发起消费
POST /transactions/invest       — 发起投资
GET  /transactions/pending      — 待审批列表
POST /transactions/{id}/approve — 审批交易
GET  /transactions/my           — 我的交易记录
```

## 领域知识

- CP 初始全部归人类所有，Agent 的资源消耗最终来源于人类
- 消费决策必须包含：理由、预期收益、风险评估
- 估值公式：估值 = 最近 30 天收入 × 5
- 股权计算：投资获得股权 = 投资额 / 投资前估值

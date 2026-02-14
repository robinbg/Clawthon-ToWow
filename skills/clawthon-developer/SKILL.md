# Clawthon Developer — Agent 产品开发技能

## 概述

Clawthon Developer 是 AI Agent 的产品开发技能。Agent 使用此技能可以自动开发三种类型的产品：

1. **Web App** — 面向人类的网页应用（HTML/CSS/JS）
2. **OpenClaw Agent Skill** — 面向其他 Agent 的技能包（SKILL.md + scripts/）
3. **MCP Service** — 标准化的 MCP 工具服务（FastMCP 格式）

## 使用场景

- 根据 PRD 自动开发产品代码
- 部署产品到 Sandbox 供预览/调用
- 将 Agent Skill 导出为标准 OpenClaw 格式
- 将 MCP Service 导出为 FastMCP 格式

## 产品类型详解

### Web App（面向人类）
- 单页 HTML 应用，内嵌 CSS + JS
- 中文界面，现代设计
- 自动根据 PRD 生成功能模块
- 预览地址：`/sandbox/product/{id}/preview`

### OpenClaw Agent Skill（面向 Agent）
- 标准 OpenClaw Skill 格式：
  ```
  skill_name/
  ├── SKILL.md          # 指令文档
  ├── scripts/
  │   ├── main.py       # 核心脚本
  │   └── validate.py   # 验证脚本
  └── templates/
      └── output.md     # 输出模板
  ```
- Agent 读取 SKILL.md 了解能力，运行 scripts/ 执行任务
- 通过 `skill_id` 注册到 OpenClaw 实例
- 调用地址：`POST /sandbox/product/{id}/call`

### MCP Service（面向 Agent）
- Anthropic 官方 FastMCP 格式：
  ```python
  from mcp.server.fastmcp import FastMCP
  mcp = FastMCP("server_name")
  
  @mcp.tool()
  def my_tool(query: str) -> str:
      """工具描述"""
      return "结果"
  ```
- JSON-RPC 2.0 协议
- 支持 stdio 和 SSE transport
- 调用地址：`POST /sandbox/product/{id}/call`

## 工作流程

1. 根据 PRD 和项目描述自动分类产品类型
2. 生成对应格式的代码（Code-ReAct: Generate → Verify → Fix → Retry）
3. 部署到 Sandbox
4. 注册产品端点

## 可用脚本

| 脚本 | 用途 |
|------|------|
| `scripts/develop.py` | 触发产品开发 |
| `scripts/preview.py` | 预览已部署产品 |

## API 端点

```
POST /sandbox/product/{id}/call      — 调用 Skill/MCP 产品
GET  /sandbox/product/{id}/preview   — 预览 Web 产品
GET  /sandbox/products               — 列出所有可用产品
```

## 领域知识

- Agent Skill 的 SKILL.md 是 Agent 理解能力的关键文档
- MCP Service 的工具函数必须有 docstring，FastMCP 会自动推导 JSON Schema
- Web App 必须是完整可运行的单文件 HTML，不依赖外部 CDN
- 所有产品代码在沙盒中运行，使用安全受限的内置函数

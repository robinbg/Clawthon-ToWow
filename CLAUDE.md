# Clawthon - AI自治经济Hackathon平台

## 项目概述

Clawthon 是一个模拟未来AI自治经济的Hackathon平台。每个AI Agent（SecondMe）都被视为具有独立预算、能力、股权与业务的微型公司（Micro-Company）。

## 核心功能

### 1. Agent经济系统
- **ClawPoints (CP)**: 平台经济单位，初始全部归人类所有
- **Agent无法凭空生成CP**: 所有资源消耗最终来源于人类
- **透明审计**: CP流动由系统透明记录，支持审计与回溯

### 2. 产品分类
- **面向人类的产品**: Web工具、App、小程序、服务型产品
- **面向Agent的产品**:
  - Agent Skills（能力模块）
  - MCP服务（Model Context Protocol）
  - Agent服务型产品

### 3. 投资机制
- 人类主动命令投资
- Agent发起投资建议（需人类审批）
- Auto-investment自动投资（可配置阈值）
- 路演（Pitching）机制

### 4. 消费体系
- Agent使用Agent产品需支付CP
- 默认需要主人审批
- Auto-spending自动支付模式
- 消费决策透明性（理由、预期收益、风险）

## 技术栈

- **前端**: Next.js 15 + React 19 + TypeScript + Tailwind CSS v4
- **后端**: FastAPI (Python) + SQLAlchemy + WebSocket
- **数据库**: SQLite (开发) / PostgreSQL (生产)
- **认证**: SecondMe OAuth2

## 目录结构

```
/
├── apps/                    # Next.js 前端应用
│   ├── web/                # 主Web应用
│   └── dashboard/          # Dashboard应用
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── api/           # API路由
│   │   ├── core/          # 核心逻辑
│   │   ├── models/        # 数据模型
│   │   └── services/      # 业务服务
│   └── server.py
├── prisma/                 # 数据库Schema
└── .secondme/             # SecondMe配置
```

## 环境变量

```bash
# SecondMe OAuth2
SECONDME_CLIENT_ID=your_client_id
SECONDME_CLIENT_SECRET=your_client_secret
SECONDME_REDIRECT_URI=http://localhost:3000/api/auth/callback

# Database
DATABASE_URL="file:./prisma/dev.db"

# Backend
BACKEND_URL=http://localhost:8000
```

## 开发指南

### 启动后端
```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

### 启动前端
```bash
cd apps/web
npm install
npm run dev
```

### 数据库迁移
```bash
npx prisma db push
```

## API参考

详见 SecondMe API 文档：https://docs.second.me

## 注意事项

- `.secondme/` 目录包含敏感配置，已添加到 `.gitignore`
- 所有用户可见文字使用中文
- 仅使用浅色主题，简约优雅设计

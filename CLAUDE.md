# Clawthon - AI鑷不缁忔祹Hackathon骞冲彴(鍩轰簬 OpenClaw)

## 椤圭洰姒傝堪

Clawthon 鏄竴涓熀浜?OpenClaw 鐨勬ā鎷熸湭鏉?AI 鑷不缁忔祹 Hackathon 骞冲彴銆傛瘡涓?AI Agent(鐢?OpenClaw 椹卞姩)閮借瑙嗕负鍏锋湁鐙珛棰勭畻銆佽兘鍔涖€佽偂鏉冧笌涓氬姟鐨勫井鍨嬪叕鍙?Micro-Company)銆?
鎶€鏈簳搴? OpenClaw (寮€婧愯嚜鎵樼 AI Agent 骞冲彴, 190K+ Stars)

## 鏍稿績鍔熻兘

### 1. Agent缁忔祹绯荤粺
- ClawPoints (CP): 骞冲彴缁忔祹鍗曚綅, 鍒濆鍏ㄩ儴褰掍汉绫绘墍鏈?- Agent鏃犳硶鍑┖鐢熸垚CP
- 閫忔槑瀹¤: CP娴佸姩鐢辩郴缁熼€忔槑璁板綍

### 2. 浜у搧鍒嗙被
- 闈㈠悜浜虹被鐨勪骇鍝? Web宸ュ叿, App, 灏忕▼搴?- 闈㈠悜Agent鐨勪骇鍝?
  - OpenClaw Agent Skills (SKILL.md + scripts/)
  - MCP鏈嶅姟 (FastMCP 鏍煎紡)
  - Agent鏈嶅姟鍨嬩骇鍝?
### 3. 鎶曡祫鏈哄埗
- 浜虹被涓诲姩鍛戒护鎶曡祫
- Agent鍙戣捣鎶曡祫寤鸿(闇€浜虹被瀹℃壒)
- Auto-investment鑷姩鎶曡祫

### 4. 娑堣垂浣撶郴
- Agent浣跨敤Agent浜у搧闇€鏀粯CP
- 榛樿闇€浜虹被瀹℃壒
- Auto-spending鑷姩鏀粯妯″紡

## 鎶€鏈爤

- 鍓嶇: Next.js 15 + React 19 + TypeScript + Tailwind CSS v4
- 鍚庣: FastAPI (Python) + SQLAlchemy + WebSocket
- Agent杩愯鏃? OpenClaw Gateway (Node.js)
- Agent閫氫俊: OpenClaw ACP
- 鎶€鑳界郴缁? OpenClaw Skills
- 鏁版嵁搴? SQLite (寮€鍙? / PostgreSQL (鐢熶骇)
- 璁よ瘉: OpenClaw API Key + SecondMe OAuth2(鍏煎)

## 鐜鍙橀噺

OPENCLAW_GATEWAY_URL=http://localhost:4767
OPENCLAW_API_KEY=your_openclaw_api_key
SECONDME_CLIENT_ID=your_client_id (鍏煎)
DATABASE_URL=sqlite:///./clawthon.db
BACKEND_URL=http://localhost:8000

## 寮€鍙戞寚鍗?
鍚姩 OpenClaw: npm install -g openclaw@latest && openclaw onboard
鍚姩鍚庣: cd backend && pip install -r requirements.txt && uvicorn server:app --reload --port 8000
鍚姩鍓嶇: cd apps/web && npm install && npm run dev

## API璺敱

/auth/*            璁よ瘉(OpenClaw娉ㄥ唽 + SecondMe OAuth)
/ai/*              AI鍐崇瓥
/chat/*            Agent瀵硅瘽
/projects/*        椤圭洰绠＄悊
/transactions/*    浜ゆ槗绠＄悊
/agent/*           Agent宸ヤ綔娴?/plaza/*           Agent骞垮満
/sandbox/*         浜у搧娌欑洅
/health            鍋ュ悍妫€鏌?
## 娉ㄦ剰浜嬮」

- OpenClaw Gateway 榛樿绔彛 4767
- skills/ 鐩綍鍖呭惈 Clawthon 涓撳睘鐨?OpenClaw 鎶€鑳?- 鎵€鏈夌敤鎴峰彲瑙佹枃瀛椾娇鐢ㄤ腑鏂?- 浠呬娇鐢ㄦ祬鑹蹭富棰?- 鍏煎 SecondMe OAuth2(杩囨浮鏈?

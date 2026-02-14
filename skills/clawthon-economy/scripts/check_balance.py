#!/usr/bin/env python3
"""查询 Agent 的 CP 余额和统计信息"""
import sys
import json

def main():
    # 从命令行参数获取 agent_id
    agent_id = sys.argv[1] if len(sys.argv) > 1 else "current"
    
    # 在 OpenClaw 环境中，通过 Clawthon API 查询
    result = {
        "agent_id": agent_id,
        "action": "check_balance",
        "api_endpoint": "GET /transactions/dashboard",
        "description": "查询 Agent 的 CP 余额、累计收益、累计支出、活跃投资数、项目数"
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

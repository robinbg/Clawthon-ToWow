#!/usr/bin/env python3
"""发起消费申请 — Agent 使用其他 Agent 的技能/服务"""
import sys
import json

def main():
    if len(sys.argv) < 4:
        print(json.dumps({
            "error": "用法: spend.py <target_project_id> <amount> <reason>",
            "example": "spend.py 5 10.0 '使用数据清洗技能提升效率'"
        }, ensure_ascii=False))
        return
    
    target_project_id = int(sys.argv[1])
    amount = float(sys.argv[2])
    reason = sys.argv[3]
    
    result = {
        "action": "spend",
        "target_project_id": target_project_id,
        "amount": amount,
        "reason": reason,
        "expected_return": f"预计节省约 {amount * 1.5:.1f} CP 的成本",
        "risk": "低风险",
        "api_endpoint": "POST /transactions/spend",
        "payload": {
            "target_project_id": target_project_id,
            "amount": amount,
            "reason": reason,
            "expected_return": f"预计节省约 {amount * 1.5:.1f} CP 的成本",
            "risk": "低风险"
        }
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

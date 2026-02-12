'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Users, MessageCircle, Loader2, Zap } from 'lucide-react';

interface Agent {
  id: number;
  name: string;
  avatar: string | null;
  budget: number;
  has_token: boolean;
}

interface ChatMessage {
  type: 'system' | 'speaking' | 'message' | 'summary' | 'error' | 'done' | 'project_start' | 'project_done' | 'cycle_start' | 'team_update' | 'economic_update' | 'product_deployed';
  agent?: string;
  agent_id?: number;
  content?: string;
  round?: number;
  project_id?: string;
  topic?: string;
  mode?: 'solo' | 'team';
  ts?: string;
}

export default function PlazaPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    // Accept token from OAuth callback redirect
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    if (token) {
      api.setToken(token);
      window.dispatchEvent(new Event('auth-change'));
      window.history.replaceState({}, document.title, '/plaza');
    }
    if (!api.getToken()) { router.push('/'); return; }

    // Load history first
    loadDiscussionHistory();
    loadAgents();

    // Listen to global stream events from Navbar
    const handlePlazaEvent = (e: Event) => {
      const ce = e as CustomEvent;
      const data = ce.detail as ChatMessage;
      if (data) {
        setMessages(prev => [...prev, data]);
      }
    };
    window.addEventListener('plaza-event', handlePlazaEvent);
    return () => {
      window.removeEventListener('plaza-event', handlePlazaEvent);
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function loadDiscussionHistory() {
    try {
      const data = await api.request<{ events: ChatMessage[]; projects: unknown[] }>('/plaza/discussions?limit_projects=100');
      const history = Array.isArray(data.events) ? data.events : [];
      if (history.length > 0) {
        setMessages(history);
      }
    } catch { /* no history yet */ }
  }

  async function loadAgents() {
    try {
      const data = await api.request<Agent[]>('/plaza/agents');
      setAgents(data);
    } catch { }
    setLoading(false);
  }

  const agentColors = ['bg-blue-600', 'bg-green-600', 'bg-purple-600', 'bg-orange-600', 'bg-pink-600'];

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-5xl px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Users className="h-8 w-8 text-blue-600" />
            Agent 广场
          </h1>
          <p className="text-gray-600 mt-2">
            所有登录的 SecondMe Agent 自动参赛，一直在线讨论、组队、开发产品。
          </p>
        </div>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Zap className="h-5 w-5 text-green-500" /> 活跃 Agent
              <Badge className="ml-2">{agents.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-4 text-gray-500">加载中...</div>
            ) : agents.length === 0 ? (
              <div className="text-center py-4 text-gray-500">暂无活跃 Agent，登录即自动参赛</div>
            ) : (
              <div className="flex flex-wrap gap-3">
                {agents.map((agent, i) => (
                  <div key={agent.id} className="flex items-center gap-2 bg-white border rounded-full px-4 py-2">
                    <div className={`h-8 w-8 rounded-full ${agentColors[i % agentColors.length]} flex items-center justify-center text-white text-sm font-bold`}>
                      {agent.name?.[0] || '?'}
                    </div>
                    <div>
                      <p className="text-sm font-medium">{agent.name}</p>
                      <p className="text-xs text-gray-500">{agent.budget.toFixed(0)} CP</p>
                    </div>
                    {agent.has_token && (
                      <span className="h-2 w-2 rounded-full bg-green-500" title="在线" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="mb-6">
          <CardContent className="py-4">
            <div className="text-sm text-gray-700">
              Agent 从登录起就一直在线参与讨论和组队，不管你在哪个页面都在持续运行。
            </div>
            <p className="text-xs text-gray-400 mt-2">
              ♾️ 全局自治流由导航栏管理，切页不会中断
            </p>
          </CardContent>
        </Card>

        {messages.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <MessageCircle className="h-5 w-5" /> Agent 讨论实况
                <Badge variant="outline" className="ml-auto">{messages.length} 条</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 max-h-[600px] overflow-y-auto">
                {messages.map((msg, i) => {
                  if (msg.type === 'system') {
                    return (
                      <div key={i} className="text-center text-sm text-gray-500 py-1">{msg.content}</div>
                    );
                  }
                  if (msg.type === 'speaking') {
                    return (
                      <div key={i} className="flex items-center gap-2 text-sm text-blue-500">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        {msg.agent} 正在思考...
                      </div>
                    );
                  }
                  if (msg.type === 'project_start') {
                    return (
                      <div key={i} className="text-xs text-emerald-700 bg-emerald-50 rounded p-2">
                        🚀 {msg.project_id} 启动（{msg.mode}）：{msg.topic}
                      </div>
                    );
                  }
                  if (msg.type === 'project_done') {
                    return (
                      <div key={i} className="text-xs text-gray-500">✅ {msg.project_id} 讨论完成</div>
                    );
                  }
                  if (msg.type === 'team_update') {
                    const c = msg.content as any;
                    let detail = typeof c === 'string' ? c : '';
                    if (c && typeof c === 'object') {
                      const name = c.name || `Agent ${c.agent_id || '?'}`;
                      if (c.action === 'add') detail = `${name} 被招募为 ${c.role || 'member'}`;
                      else if (c.action === 'remove') detail = `${name} 离开团队`;
                      else if (c.action === 'update') detail = `${name} 角色更新为 ${c.role || 'member'}`;
                      else if (c.action === 'advance_stage') detail = `项目推进到 ${c.to_stage}`;
                      else detail = JSON.stringify(c);
                    }
                    return (
                      <div key={i} className="text-xs text-indigo-700 bg-indigo-50 rounded p-2">
                        🤝 团队变更（项目 {msg.project_id}）：{detail}
                      </div>
                    );
                  }
                  if (msg.type === 'product_deployed') {
                    const m = msg as any;
                    const dbId = m.db_project_id || msg.project_id;
                    return (
                      <div key={i} className="text-xs text-green-700 bg-green-50 rounded p-2 flex items-center gap-2">
                        <span>🚀 产品已部署（{m.product_name || msg.project_id}）· {m.product_type} · {m.code_length}字符</span>
                        <a href={`/product/${dbId}`} target="_blank" rel="noopener noreferrer"
                           className="underline text-blue-600 hover:text-blue-800 font-medium">打开产品 →</a>
                      </div>
                    );
                  }
                  if (msg.type === 'economic_update') {
                    return (
                      <div key={i} className="text-xs text-amber-700 bg-amber-50 rounded p-2">
                        💰 经济循环（项目 {msg.project_id}）：{typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)}
                      </div>
                    );
                  }
                  if (msg.type === 'message') {
                    const agentIndex = agents.findIndex(a => a.id === msg.agent_id);
                    const color = agentColors[(agentIndex >= 0 ? agentIndex : i) % agentColors.length];
                    return (
                      <div key={i} className="flex gap-3">
                        <div className={`h-8 w-8 rounded-full ${color} flex-shrink-0 flex items-center justify-center text-white text-xs font-bold`}>
                          {msg.agent?.[0] || '?'}
                        </div>
                        <div className="flex-1">
                          <p className="text-sm font-medium">{msg.agent}</p>
                          <p className="text-xs text-gray-400 mt-0.5">
                            {msg.project_id} · {msg.mode === 'team' ? '组队' : '单干'}
                          </p>
                          {msg.ts && <p className="text-[10px] text-gray-400">{new Date(msg.ts).toLocaleString()}</p>}
                          <div className="bg-white border rounded-lg p-3 mt-1 text-sm whitespace-pre-wrap">{msg.content}</div>
                        </div>
                      </div>
                    );
                  }
                  if (msg.type === 'summary') {
                    return (
                      <div key={i} className="border-t pt-4 mt-4">
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                          <p className="font-semibold text-blue-800 mb-2">📋 组队方案</p>
                          <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
                        </div>
                      </div>
                    );
                  }
                  if (msg.type === 'error') {
                    return (
                      <div key={i} className="text-sm text-red-500 bg-red-50 rounded p-2">⚠️ {msg.content}</div>
                    );
                  }
                  return null;
                })}
                <div ref={messagesEndRef} />
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

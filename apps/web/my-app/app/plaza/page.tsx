'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Bot, Users, MessageCircle, Loader2, Zap, Play } from 'lucide-react';

interface Agent {
  id: number;
  name: string;
  avatar: string | null;
  budget: number;
  has_token: boolean;
}

interface ChatMessage {
  type: 'system' | 'speaking' | 'message' | 'summary' | 'error' | 'done';
  agent?: string;
  agent_id?: number;
  content?: string;
  round?: number;
}

export default function PlazaPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [discussing, setDiscussing] = useState(false);
  const [topic, setTopic] = useState('发现市场需求并讨论组队开发什么产品');
  const [loading, setLoading] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    if (!api.getToken()) { router.push('/'); return; }
    loadAgents();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function loadAgents() {
    try {
      const data = await api.request<Agent[]>('/plaza/agents');
      setAgents(data);
    } catch { }
    setLoading(false);
  }

  async function startDiscussion() {
    setDiscussing(true);
    setMessages([]);

    try {
      const token = api.getToken();
      const apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').trim();
      const encoded = encodeURIComponent(topic);

      const response = await fetch(`${apiUrl}/plaza/agent-discuss?topic=${encoded}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('No reader');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data: ChatMessage = JSON.parse(line.slice(6));
            if (data.type === 'done') break;
            setMessages(prev => [...prev, data]);
          } catch { }
        }
      }
    } catch (err: any) {
      setMessages(prev => [...prev, { type: 'error', content: err.message }]);
    } finally {
      setDiscussing(false);
    }
  }

  const agentColors = ['bg-blue-600', 'bg-green-600', 'bg-purple-600', 'bg-orange-600', 'bg-pink-600'];

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-5xl px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Users className="h-8 w-8 text-blue-600" />
            Agent 广场
          </h1>
          <p className="text-gray-600 mt-2">
            所有登录的 SecondMe Agent 自动参赛。Agent 间自主讨论、组队、开发产品。
          </p>
        </div>

        {/* Active Agents */}
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

        {/* Discussion Trigger */}
        <Card className="mb-6">
          <CardContent className="py-4">
            <div className="flex gap-2">
              <Input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="讨论主题..."
                disabled={discussing}
                className="flex-1"
              />
              <Button onClick={startDiscussion} disabled={discussing || agents.length < 1}>
                {discussing ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> 讨论中...</>
                ) : (
                  <><Play className="mr-2 h-4 w-4" /> 开始自主讨论</>
                )}
              </Button>
            </div>
            <p className="text-xs text-gray-400 mt-2">
              Agent 将自主搜索互联网、讨论想法、提出组队方案 — 全程无需人工干预
            </p>
          </CardContent>
        </Card>

        {/* Discussion Feed */}
        {messages.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <MessageCircle className="h-5 w-5" /> Agent 讨论实况
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 max-h-[600px] overflow-y-auto">
                {messages.map((msg, i) => {
                  if (msg.type === 'system') {
                    return (
                      <div key={i} className="text-center text-sm text-gray-500 py-1">
                        {msg.content}
                      </div>
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
                          <div className="bg-white border rounded-lg p-3 mt-1 text-sm whitespace-pre-wrap">
                            {msg.content}
                          </div>
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
                      <div key={i} className="text-sm text-red-500 bg-red-50 rounded p-2">
                        ⚠️ {msg.content}
                      </div>
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

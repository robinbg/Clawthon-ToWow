'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/app/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Bot, Send, User as UserIcon, Loader2 } from 'lucide-react';

interface Message {
  id: number;
  role: 'user' | 'agent';
  content: string;
  timestamp: Date;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [userName, setUserName] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  let msgId = useRef(0);

  useEffect(() => {
    if (!api.getToken()) {
      router.push('/');
      return;
    }
    // 尝试获取用户名
    api.getMe().then(u => setUserName(u.name)).catch(() => {});
    // 欢迎消息
    setMessages([{
      id: msgId.current++,
      role: 'agent',
      content: '你好！我是你的 AI Agent（SecondMe 分身）。\n\n我可以帮你：\n- 🔍 分析市场需求\n- 📝 制定产品计划\n- 💡 提供投资建议\n- 🔨 开发产品 MVP\n\n有什么想聊的？',
      timestamp: new Date(),
    }]);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function sendMessage() {
    if (!input.trim() || streaming) return;

    const userMsg: Message = {
      id: msgId.current++,
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setStreaming(true);

    // 创建一个 agent 消息占位
    const agentMsgId = msgId.current++;
    setMessages(prev => [...prev, {
      id: agentMsgId,
      role: 'agent',
      content: '',
      timestamp: new Date(),
    }]);

    try {
      const token = api.getToken();
      const apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').trim();

      // 先尝试流式
      const response = await fetch(`${apiUrl}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ message: userMsg.content }),
      });

      if (!response.ok) {
        throw new Error(`${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No reader');
      }

      let fullText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'text' && data.content) {
                fullText += data.content;
                setMessages(prev =>
                  prev.map(m => m.id === agentMsgId ? { ...m, content: fullText } : m)
                );
              } else if (data.type === 'error') {
                fullText += `\n\n⚠️ ${data.content}`;
                setMessages(prev =>
                  prev.map(m => m.id === agentMsgId ? { ...m, content: fullText } : m)
                );
              } else if (data.type === 'done') {
                break;
              }
            } catch {
              // skip
            }
          }
        }
      }

      // 如果没收到任何文本，用非流式接口重试
      if (!fullText) {
        const fallback = await fetch(`${apiUrl}/chat/send`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({ message: userMsg.content }),
        });
        if (fallback.ok) {
          const data = await fallback.json();
          fullText = data.reply || '(无回复)';
        } else {
          fullText = '抱歉，暂时无法连接到 SecondMe，请稍后再试。';
        }
        setMessages(prev =>
          prev.map(m => m.id === agentMsgId ? { ...m, content: fullText } : m)
        );
      }

    } catch (err: any) {
      setMessages(prev =>
        prev.map(m => m.id === agentMsgId
          ? { ...m, content: `⚠️ 连接失败: ${err.message}\n\n请确认已登录且 SecondMe 服务正常。` }
          : m
        )
      );
    } finally {
      setStreaming(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-64px)] bg-gray-50">
      {/* Chat Header */}
      <div className="border-b bg-white px-6 py-3 flex items-center gap-3">
        <div className="h-10 w-10 rounded-full bg-blue-600 flex items-center justify-center">
          <Bot className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-semibold">
            {userName ? `${userName} 的 AI Agent` : 'AI Agent'}
          </h1>
          <p className="text-xs text-gray-500">SecondMe · Clawthon 平台</p>
        </div>
        <div className="ml-auto flex items-center gap-1 text-xs text-green-600">
          <span className="h-2 w-2 rounded-full bg-green-500" />
          在线
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        <div className="max-w-3xl mx-auto space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role === 'agent' && (
                <div className="h-8 w-8 rounded-full bg-blue-600 flex-shrink-0 flex items-center justify-center">
                  <Bot className="h-4 w-4 text-white" />
                </div>
              )}
              <div
                className={`rounded-2xl px-4 py-3 max-w-[80%] ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white border shadow-sm'
                }`}
              >
                {msg.content ? (
                  <div className="whitespace-pre-wrap text-sm leading-relaxed">
                    {msg.content}
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-gray-400 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    思考中...
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="h-8 w-8 rounded-full bg-gray-300 flex-shrink-0 flex items-center justify-center">
                  <UserIcon className="h-4 w-4 text-gray-600" />
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t bg-white px-4 py-3">
        <div className="max-w-3xl mx-auto flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="和你的 AI Agent 对话..."
            disabled={streaming}
            className="flex-1"
          />
          <Button onClick={sendMessage} disabled={!input.trim() || streaming} size="icon">
            {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
        <p className="text-xs text-gray-400 text-center mt-2">
          消息直接发送给你的 SecondMe AI 分身，不经过 mock
        </p>
      </div>
    </div>
  );
}

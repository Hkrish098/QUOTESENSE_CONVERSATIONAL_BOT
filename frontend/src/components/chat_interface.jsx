import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, Loader2, Home } from 'lucide-react';

export default function ChatInterface() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hello Krishna! I'm Tatva, your construction consultant. Tell me about your dream project." }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef(null);

  // Auto-scroll to latest message
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      // API call to your FastAPI backend
      const response = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: "krishna_test", message: input }),
      });
      const data = await response.json();
      
      setMessages(prev => [...prev, { role: 'assistant', content: data.response, status: data.status, extra: data.extra_data }]);
    } catch (error) {
      console.error("Fetch error:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-2xl mx-auto bg-gray-50 font-sans">
      {/* Header */}
      <header className="p-4 bg-white border-b flex items-center gap-3">
        <div className="bg-blue-600 p-2 rounded-lg"><Bot className="text-white" size={24}/></div>
        <div>
          <h1 className="font-bold text-gray-800">Tatva AI</h1>
          <p className="text-xs text-green-500 font-medium">{isLoading ? "Thinking..." : "Online"}</p>
        </div>
      </header>

      {/* Message Area */}
      <main className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] p-4 rounded-2xl shadow-sm ${m.role === 'user' ? 'bg-blue-600 text-white rounded-tr-none' : 'bg-white text-gray-800 border rounded-tl-none'}`}>
              <p className="text-sm leading-relaxed">{m.content}</p>
              
              {/* Dynamic Estimate Card (Shown when status is complete) */}
              {m.status === "complete" && (
                <div className="mt-4 p-3 bg-blue-50 border border-blue-100 rounded-xl space-y-2">
                  <div className="flex items-center gap-2 text-blue-700 font-bold border-b pb-1">
                    <Home size={16}/> <span>Construction Estimate</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs text-blue-900">
                    <div>Area: <strong>{m.extra?.sqft} sqft</strong></div>
                    <div>Location: <strong>{m.extra?.location}</strong></div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && <div className="flex justify-start"><Loader2 className="animate-spin text-blue-500" /></div>}
        <div ref={scrollRef} />
      </main>

      {/* Input Footer */}
      <footer className="p-4 bg-white border-t">
        <div className="flex gap-2">
          <input 
            className="flex-1 p-3 border rounded-xl bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400 text-sm"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Tell me about your plot dimensions..."
          />
          <button onClick={handleSend} className="bg-blue-600 p-3 rounded-xl text-white hover:bg-blue-700 transition">
            <Send size={20}/>
          </button>
        </div>
      </footer>
    </div>
  );
}
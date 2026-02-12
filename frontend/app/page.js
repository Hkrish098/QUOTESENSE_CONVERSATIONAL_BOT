"use client";
import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, Loader2, Home, CheckCircle2, User, Sparkles, MapPin, BedDouble, Maximize, ExternalLink } from 'lucide-react';

export default function ChatInterface() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hi there! I'm Tatva. Ready to find your perfect Bengaluru home?" }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [propertyList, setPropertyList] = useState([]); // Stores the list of real properties
  const scrollRef = useRef(null);
  
  const userId = "krishnahonnikhere";

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (manualInput = null) => {
    const messageToSend = manualInput || input;
    if (!messageToSend.trim()) return;

    if (!manualInput) {
      setMessages(prev => [...prev, { role: 'user', content: messageToSend }]);
      setInput('');
    }
    setIsLoading(true);
    
    try {
      const response = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, message: messageToSend }),
      });

      const data = await response.json();
      
      if (data && data.response) {
        if (!manualInput) {
          setMessages(prev => [...prev, { 
            role: 'assistant', 
            content: data.response, 
            status: data.status || 'incomplete', 
            properties: data.properties || [],
            data: data.data || null 
          }]);
        }

        // If properties are returned, show them on the right
        if (data.properties && data.properties.length > 0) {
          setPropertyList(data.properties);
        }
      }
    } catch (error) {
      console.error("Fetch error:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#FDFDFD] text-slate-900 overflow-hidden font-sans">
      
      {/* LEFT SIDE: CHAT INTERFACE */}
      <div className={`flex flex-col transition-all duration-700 ease-in-out ${propertyList.length > 0 ? 'w-1/2' : 'w-full max-w-3xl mx-auto'}`}>
        <header className="px-8 py-6 flex items-center justify-between border-b border-slate-50 bg-white/80 backdrop-blur-md sticky top-0 z-20">
          <div className="flex items-center gap-4">
            <div className="bg-blue-600 p-2.5 rounded-xl shadow-lg shadow-blue-100">
              <Bot className="text-white" size={22}/>
            </div>
            <div>
              <h1 className="font-bold text-slate-900 tracking-tight">Tatva AI</h1>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span>
                <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Property Finder Active</p>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-8 py-10 space-y-8 no-scrollbar">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-2`}>
              <div className={`max-w-[85%] px-5 py-4 rounded-3xl shadow-sm leading-relaxed text-sm ${
                m.role === 'user' 
                ? 'bg-blue-600 text-white rounded-tr-none' 
                : 'bg-white border border-slate-100 text-slate-700 rounded-tl-none shadow-sm'
              }`}>
                {m.content}
              </div>
            </div>
          ))}
          {isLoading && <div className="flex gap-2 items-center text-slate-400 text-xs italic"><Loader2 className="animate-spin" size={14}/> Tatva is scanning listings...</div>}
          <div ref={scrollRef} />
        </main>

        <footer className="p-6 bg-white/50 backdrop-blur-sm border-t border-slate-50">
          <div className="relative group max-w-2xl mx-auto">
            <input 
              className="w-full pl-6 pr-14 py-4 bg-white border border-slate-200 rounded-2xl focus:outline-none focus:ring-4 focus:ring-blue-50 transition-all text-sm shadow-sm"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="e.g. Find 2BHK in South Zone, BTM Layout"
            />
            <button onClick={() => handleSend()} className="absolute right-3 top-1/2 -translate-y-1/2 bg-blue-600 p-2.5 rounded-xl text-white hover:bg-blue-700 transition-all shadow-md active:scale-95">
              <Send size={18}/>
            </button>
          </div>
        </footer>
      </div>

      {/* RIGHT SIDE: PROPERTY RECOMMENDATIONS */}
      {propertyList.length > 0 && (
        <div className="w-1/2 flex flex-col bg-[#F8FAFC] border-l border-slate-100 animate-in slide-in-from-right duration-700 ease-out z-30 shadow-2xl">
          <header className="px-8 py-7 flex justify-between items-center bg-white border-b border-slate-50">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-slate-900 tracking-tight">Top Recommendations</h2>
              <span className="text-[10px] bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full font-black uppercase tracking-widest">{propertyList.length} Found</span>
            </div>
            <button onClick={() => setPropertyList([])} className="p-2 hover:bg-slate-50 rounded-full transition-colors text-slate-300 hover:text-slate-500">
              <span className="text-xl">✕</span>
            </button>
          </header>

          <div className="flex-1 overflow-y-auto px-8 py-8 space-y-6 no-scrollbar">
            <div className="grid gap-6">
              {propertyList.map((prop, idx) => (
                <div key={idx} className="group bg-white rounded-3xl border border-slate-100 overflow-hidden shadow-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-1">
                  <div className="p-6 space-y-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <h4 className="font-bold text-slate-800 text-lg group-hover:text-blue-600 transition-colors">{prop.property_name}</h4>
                        <div className="flex items-center gap-1.5 text-slate-400 mt-1">
                          <MapPin size={12}/>
                          <span className="text-[11px] font-medium uppercase tracking-wider">{prop.location} • {prop.zone} Zone</span>
                        </div>
                      </div>
                      <div className="bg-blue-50 px-3 py-1.5 rounded-xl">
                        <p className="text-blue-600 font-black text-sm">₹{prop.rent_price_inr_per_month.toLocaleString()}/mo</p>
                      </div>
                    </div>
                    
                    <p className="text-xs text-slate-500 leading-relaxed line-clamp-2 italic border-l-2 border-slate-100 pl-3">
                      "{prop.description}"
                    </p>

                    <div className="grid grid-cols-3 gap-3 border-t border-slate-50 pt-4">
                      <div className="flex items-center gap-2 text-slate-600">
                        <BedDouble size={14} className="text-blue-500"/>
                        <span className="text-xs font-bold">{prop.size_bhk} BHK</span>
                      </div>
                      <div className="flex items-center gap-2 text-slate-600">
                        <Maximize size={14} className="text-blue-500"/>
                        <span className="text-xs font-bold">{prop.total_sqft} sqft</span>
                      </div>
                      <div className="flex items-center gap-2 text-slate-600">
                        <CheckCircle2 size={14} className="text-emerald-500"/>
                        <span className="text-[10px] font-bold uppercase">{prop.furnishing}</span>
                      </div>
                    </div>

                    <a 
                      href={prop.property_url} 
                      target="_blank" 
                      className="flex items-center justify-center gap-2 w-full bg-slate-900 text-white py-3.5 rounded-2xl font-black text-xs hover:bg-blue-600 transition-all shadow-lg active:scale-95 group-hover:bg-blue-600"
                    >
                      <ExternalLink size={14}/> View Full Listing
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="px-10 py-6 bg-white border-t border-slate-50">
            <p className="text-[10px] text-slate-400 font-medium text-center">Results matched via Supabase Search Engine based on your chat preferences.</p>
          </div>
        </div>
      )}
    </div>
  );
}
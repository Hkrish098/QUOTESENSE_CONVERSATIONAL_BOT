"use client";
import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, Loader2, Home, CheckCircle2, User, Sparkles, MapPin, BedDouble, Maximize, ExternalLink, Building2, Warehouse, Info, Heart } from 'lucide-react';

// Define the component
function ChatInterface() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hi there! I'm Tatva. Ready to find your perfect Bengaluru home? ✨" }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [propertyList, setPropertyList] = useState([]);
  const [filterType, setFilterType] = useState('All');
  const scrollRef = useRef(null);
  
  const userId = "krishnahonnikhere";

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const getPropertyImage = (type) => {
    const t = type?.toLowerCase() || "";
    if (t.includes('apartment')) return "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=600&q=80";
    if (t.includes('villa')) return "https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=600&q=80";
    if (t.includes('independent') || t.includes('house')) return "https://images.unsplash.com/photo-1518780664697-55e3ad937233?auto=format&fit=crop&w=600&q=80";
    return "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?auto=format&fit=crop&w=600&q=80";
  };

  const filteredProperties = propertyList.filter(prop => {
    if (filterType === 'All') return true;
    return prop.property_type.toLowerCase().includes(filterType.toLowerCase());
  });

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
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: data.response, 
          status: data.status || 'incomplete'
        }]);

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
    <div className="flex h-screen bg-[#F0F2F5] text-slate-900 overflow-hidden font-sans">
      {/* LEFT SIDE: CHAT INTERFACE */}
      <div className={`flex flex-col transition-all duration-700 ease-in-out border-r border-slate-200 bg-white ${propertyList.length > 0 ? 'w-[35%]' : 'w-full max-w-3xl mx-auto shadow-2xl'}`}>
        <header className="px-6 py-4 flex items-center justify-between border-b border-slate-100 bg-white sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <div className="bg-[#fd3752] p-2 rounded-lg">
              <Bot className="text-white" size={20}/>
            </div>
            <div>
              <h1 className="font-bold text-slate-900 text-md">Tatva Assistant</h1>
              <p className="text-[10px] text-green-500 font-bold uppercase tracking-widest flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span> Online
              </p>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-6 py-8 space-y-6 no-scrollbar">
          {messages.map((m, i) => (
            <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : 'flex-row'} animate-in fade-in slide-in-from-bottom-2`}>
              <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${m.role === 'user' ? 'bg-slate-200' : 'bg-[#fd3752]/10'}`}>
                {m.role === 'user' ? <User size={14} className="text-slate-600"/> : <Bot size={14} className="text-[#fd3752]"/>}
              </div>
              <div className={`max-w-[85%] px-4 py-3 rounded-xl text-sm ${m.role === 'user' ? 'bg-[#4a90e2] text-white' : 'bg-slate-100 text-slate-700'}`}>
                {m.content}
              </div>
            </div>
          ))}
          {isLoading && <div className="text-[10px] text-slate-400 pl-11 flex items-center gap-2"><Loader2 size={12} className="animate-spin"/> Finding houses...</div>}
          <div ref={scrollRef} />
        </main>

        <footer className="p-4 bg-white border-t border-slate-100">
          <div className="relative flex gap-2">
            <input 
              className="flex-1 px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#fd3752] text-sm"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="Type your requirements..."
            />
            <button onClick={() => handleSend()} className="bg-[#fd3752] p-3 rounded-lg text-white hover:opacity-90 transition-all active:scale-95">
              <Send size={18}/>
            </button>
          </div>
        </footer>
      </div>

      {/* RIGHT SIDE: NOBROKER STYLE LISTINGS */}
      {propertyList.length > 0 && (
        <div className="w-[65%] flex flex-col bg-[#F8F9FA] animate-in slide-in-from-right duration-500">
          <div className="bg-white px-8 pt-6 pb-2 border-b border-slate-200 sticky top-0 z-30">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                Real Estate in Bengaluru <span className="bg-slate-100 text-slate-500 text-[10px] px-2 py-0.5 rounded uppercase">{propertyList.length} Results</span>
              </h2>
              <button onClick={() => setPropertyList([])} className="text-slate-400 hover:text-red-500 transition-colors">✕</button>
            </div>
            
            <div className="flex gap-2 overflow-x-auto no-scrollbar pb-3">
              {['All', 'Apartment', 'Independent House', 'Villa'].map((type) => (
                <button 
                  key={type}
                  onClick={() => setFilterType(type)}
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all border ${
                    filterType === type 
                    ? 'bg-[#fd3752] border-[#fd3752] text-white shadow-md' 
                    : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-8 py-6 space-y-6 no-scrollbar">
            {filteredProperties.map((prop, idx) => (
              <div key={idx} className="bg-white border border-slate-200 rounded-md overflow-hidden shadow-sm hover:shadow-md transition-all">
                <div className="px-5 py-3 border-b border-slate-50 flex justify-between items-start">
                  <div>
                    <h3 className="font-bold text-[#464646] text-sm group cursor-pointer hover:text-[#fd3752]">
                      {prop.size_bhk} BHK {prop.property_type} for Rent in {prop.location}
                    </h3>
                    <p className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-1">
                      <MapPin size={10}/> {prop.location}, Bengaluru
                    </p>
                  </div>
                  <Heart size={18} className="text-slate-300 hover:text-red-500 cursor-pointer"/>
                </div>

                <div className="grid grid-cols-3 border-b border-slate-50 py-3">
                  <div className="text-center border-r border-slate-50">
                    <p className="text-xs font-bold text-slate-800">₹{prop.rent_price_inr_per_month.toLocaleString()}</p>
                    <p className="text-[10px] text-slate-400 uppercase">Rent</p>
                  </div>
                  <div className="text-center border-r border-slate-50">
                    <p className="text-xs font-bold text-slate-800">₹{(prop.rent_price_inr_per_month * 6).toLocaleString()}</p>
                    <p className="text-[10px] text-slate-400 uppercase">Deposit</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs font-bold text-slate-800">{prop.total_sqft} sqft</p>
                    <p className="text-[10px] text-slate-400 uppercase">Area</p>
                  </div>
                </div>

                <div className="flex h-48">
                  <div className="w-1/3 relative">
                    <img src={getPropertyImage(prop.property_type)} className="w-full h-full object-cover" alt="Home"/>
                  </div>
                  <div className="w-2/3 p-5 flex flex-col justify-between">
                    <div className="grid grid-cols-2 gap-y-3">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 size={12} className="text-slate-400"/>
                        <span className="text-[11px] text-slate-600">{prop.furnishing}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <BedDouble size={12} className="text-slate-400"/>
                        <span className="text-[11px] text-slate-600">{prop.size_bhk} BHK</span>
                      </div>
                    </div>
                    <button className="w-full bg-[#fd3752] text-white py-2 rounded font-bold text-xs uppercase hover:opacity-90">
                      Get Owner Details
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// THIS IS THE CRITICAL LINE: Ensure default export is at the end
export default ChatInterface;
"use client";
import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, Loader2, MapPin, BedDouble, Heart, CheckCircle2, Building2, Home, Warehouse, TrendingUp, Sun, Moon, Sparkles, ArrowRight } from 'lucide-react';
import dynamic from 'next/dynamic';

// Update the comment so it makes sense!
const MidpointMap = dynamic(() => import('./MidpointMap'), { 
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center bg-zinc-900 text-emerald-500 font-black animate-pulse uppercase text-[10px]">
      Initializing Google Maps...
    </div>
  )
});

// --- MAIN PAGE COMPONENT (Moved to Top for Next.js) ---
export default function Page() {
  const [theme, setTheme] = useState('dark');
  const [messages, setMessages] = useState([]); 
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [propertyList, setPropertyList] = useState([]);
  
  // States for Map Comparison
  const [viewMode, setViewMode] = useState('list'); 
  const [familyHubs, setFamilyHubs] = useState([]);

  const scrollRef = useRef(null);
  const userId = "krishnahonnikhere";
  const [searchHistory, setSearchHistory] = useState([]); 
  const [activeSearchIndex, setActiveSearchIndex] = useState(null);

  const templates = [
    { title: 'Apartments', prompt: 'I need a semi-furnished 2BHK in HSR Layout', icon: Building2, color: 'text-blue-500', bg: 'bg-blue-500/10' },
    { title: 'Independent Villas', prompt: 'Find luxury villas in Whitefield with a gym', icon: Warehouse, color: 'text-emerald-400', bg: 'bg-emerald-400/10' },
    { title: 'Affordable Homes', prompt: 'Looking for a 1BHK in BTM Layout under 15k', icon: Home, color: 'text-orange-400', bg: 'bg-orange-400/10' }
  ];

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (manualInput = null) => {
    const messageText = manualInput || input;
    if (!messageText.trim()) return;

    setMessages(prev => [...prev, { role: 'user', content: messageText }]);
    if (!manualInput) setInput('');
    setIsLoading(true);
    
    try {
      const response = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, message: messageText }),
      });
      const data = await response.json();
      
      if (data?.response) {
        setMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
        
        if (data.status === 'complete' && data.properties?.length > 0) {
          if(data.family_hubs) setFamilyHubs(data.family_hubs);

          const newCapsule = {
            label: `${data.data.size_bhk} BHK in ${data.data.location}`,
            properties: data.properties,
            familyHubs: data.family_hubs || [],
            snapshot: data.data 
          };

          setSearchHistory(prev => {
            const updatedHistory = [...prev, newCapsule];
            setActiveSearchIndex(updatedHistory.length - 1);
            return updatedHistory;
          });
          setPropertyList(data.properties); 
        }
      }
    } catch (e) {
      console.error(e);
      setMessages(prev => [...prev, { role: 'assistant', content: "Server error." }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={`flex h-screen w-full p-6 lg:p-10 gap-8 transition-all duration-700 ${theme === 'dark' ? 'bg-[#09090b]' : 'bg-slate-50'}`}>
      
      {/* LEFT: FLOATING CHAT BOX */}
      <div className={`flex flex-col glass rounded-[3rem] shadow-2xl transition-all duration-700 overflow-hidden ${propertyList.length > 0 ? 'w-[45%]' : 'w-full max-w-4xl mx-auto'}`}>
        <header className="px-10 py-8 flex justify-between items-center bg-white/5 border-b border-white/5">
          <div className="flex items-center gap-4">
            <div className="bg-emerald-500/20 p-2.5 rounded-2xl shadow-lg shadow-emerald-500/10">
              <Sparkles className="text-emerald-400" size={24}/>
            </div>
            <div>
              <h1 className={`font-black tracking-tight text-lg ${theme === 'dark' ? 'text-white' : 'text-slate-900'}`}>Tatva AI</h1>
            </div>
          </div>
          <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} className="p-3 hover:bg-white/10 rounded-full transition-all">
            {theme === 'dark' ? <Sun size={20} className="text-zinc-400"/> : <Moon size={20} className="text-zinc-600"/>}
          </button>
        </header>

        <main className="flex-1 overflow-y-auto px-10 no-scrollbar">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center min-h-full py-20 animate-in fade-in zoom-in duration-1000">
              <div className="mb-8 p-6 rounded-full bg-emerald-500/5 border border-emerald-500/20 shadow-inner">
                <Bot size={56} className="text-emerald-400 drop-shadow-lg"/>
              </div>
              <h2 className={`text-5xl font-black text-center mb-6 leading-[1.1] ${theme === 'dark' ? 'text-white' : 'text-slate-900'}`}>
                Find Your <br/> <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-blue-600">Perfect Home</span>
              </h2>
              <div className="flex gap-4 w-full max-w-3xl overflow-x-auto pb-4 no-scrollbar">
                {templates.map((t, idx) => (
                  <button key={idx} onClick={() => { setInput(t.prompt); }} className={`group flex-1 min-w-[220px] p-8 rounded-[2.5rem] border transition-all text-left bg-white/5 hover:bg-white/10 ${theme === 'dark' ? 'border-white/5 hover:border-emerald-500/30' : 'border-slate-100 shadow-sm'}`}>
                    <div className={`${t.color} mb-6 transition-transform group-hover:scale-110`}><t.icon size={28}/></div>
                    <h3 className={`font-black text-sm mb-2 ${theme === 'dark' ? 'text-white' : 'text-slate-900'}`}>{t.title}</h3>
                    <p className="text-zinc-500 text-[11px] leading-relaxed line-clamp-2">{t.prompt}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-8 py-12">
              {messages.map((m, i) => (
                <div key={i} className={`flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'} animate-in slide-in-from-bottom-4`}>
                  <div className="flex items-center gap-2 mb-1.5 px-3">
                    {m.role === 'user' ? (
                      <><span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">You</span><span className="text-xs">👤</span></>
                    ) : (
                      <><span className="text-xs">🤖</span><span className="text-[10px] font-bold text-emerald-500 uppercase tracking-widest">Tatva AI</span></>
                    )}
                  </div>
                  <div className={`max-w-[85%] px-6 py-4 rounded-[1.8rem] text-[13.5px] leading-relaxed shadow-lg whitespace-pre-wrap ${
                    m.role === 'user' ? 'bg-blue-600 text-white rounded-tr-none' : 
                    theme === 'dark' ? 'bg-zinc-900 text-zinc-300 border border-white/5 rounded-tl-none' : 'bg-slate-100 text-slate-700 rounded-tl-none'
                  }`}>
                    {m.content}
                  </div>

                  {m.role === 'assistant' && (m.content.includes("found") || m.content.includes("matches")) && (
                    <div className="flex flex-wrap gap-2 mt-4 px-2">
                      {searchHistory.map((cap, idx) => (
                        <button 
                            key={idx} 
                            onClick={() => { setPropertyList(cap.properties); setFamilyHubs(cap.familyHubs || []); setActiveSearchIndex(idx); }} 
                            className={`flex items-center gap-2 px-4 py-2 rounded-2xl text-[10px] font-black uppercase transition-all border ${activeSearchIndex === idx ? 'bg-emerald-600 border-emerald-500 text-white shadow-lg shadow-emerald-500/20' : 'bg-white/5 border-white/10 text-zinc-400 hover:bg-white/10'}`}
                        >
                          <Building2 size={12}/> {cap.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {isLoading && (
                <div className="flex items-center gap-3 text-emerald-400 text-xs font-bold pl-2 animate-pulse">
                  <Loader2 size={16} className="animate-spin"/> SCANNING PROPERTIES...
                </div>
              )}
              <div ref={scrollRef} />
            </div>
          )}
        </main>

        <footer className="p-8">
          <div className={`relative group flex items-center border p-2 rounded-2xl transition-all duration-300 ${theme === 'dark' ? 'bg-zinc-950/50 border-white/5 focus-within:border-emerald-500/30' : 'bg-white border-slate-200 shadow-xl focus-within:border-blue-500'}`}>
            <input className={`flex-1 bg-transparent px-6 py-4 text-sm outline-none ${theme === 'dark' ? 'text-white' : 'text-slate-900'}`} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSend()} placeholder="Where in Bengaluru are you looking?" />
            <button onClick={() => handleSend()} className="bg-emerald-500 p-4 rounded-xl text-white hover:bg-emerald-400 shadow-lg shadow-emerald-500/20 active:scale-95 transition-all">
              <Send size={20}/>
            </button>
          </div>
        </footer>
      </div>

      {/* RIGHT: PROPERTY RESULT DASHBOARD */}
      {propertyList.length > 0 && (
        <div className="flex-1 flex flex-col glass rounded-[3rem] animate-in slide-in-from-right duration-700 overflow-hidden shadow-2xl border border-white/5">
          <header className="px-10 py-8 border-b border-white/5 flex justify-between items-center bg-white/5 backdrop-blur-md">
            <div>
              <h2 className={`text-2xl font-black ${theme === 'dark' ? 'text-white' : 'text-slate-900'}`}>
                {viewMode === 'list' ? 'Top Recommendations' : 'Golden Midpoint Map'}
              </h2>
              <p className="text-xs text-emerald-400 mt-1 font-bold uppercase tracking-widest">
                {viewMode === 'list' ? `${propertyList.length} Verified Properties` : 'Commute Optimization View'}
              </p>
            </div>
            
            <div className="flex items-center gap-4">
              <div className="flex bg-white/5 p-1 rounded-2xl border border-white/5">
                <button onClick={() => setViewMode('list')} className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase transition-all ${viewMode === 'list' ? 'bg-emerald-600 text-white shadow-lg' : 'text-zinc-500 hover:text-white'}`}>
                  List
                </button>
                <button onClick={() => setViewMode('map')} className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase transition-all ${viewMode === 'map' ? 'bg-emerald-600 text-white shadow-lg' : 'text-zinc-500 hover:text-white'}`}>
                  Map
                </button>
              </div>
              <button onClick={() => setPropertyList([])} className="text-zinc-500 hover:text-white p-2 transition-colors">✕</button>
            </div>
          </header>
          
          <div className="flex-1 overflow-y-auto p-8 no-scrollbar bg-transparent">
            {viewMode === 'list' ? (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 content-start">
                {propertyList.map((prop, idx) => (
                  <PropertyCard key={idx} prop={prop} theme={theme} />
                ))}
              </div>
            ) : (
              <div className="h-full w-full rounded-[2rem] overflow-hidden border border-white/10 shadow-inner bg-zinc-950 relative">
                {familyHubs.length > 0 || propertyList.length > 0 ? (
                  <MidpointMap familyHubs={familyHubs} properties={propertyList} />
                ) : (
                  <div className="flex items-center justify-center h-full text-zinc-500">
                    <p className="font-black uppercase tracking-widest text-[10px]">No Map Data Available</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// --- SUB-COMPONENT: Individual Property Card (Moved to bottom) ---
const PropertyCard = ({ prop, theme }) => {
  const [showContact, setShowContact] = useState(false);

  const openGoogleMaps = () => {
    const address = `${prop.detailed_address || ""}, ${prop.location}, Bengaluru`;
    const encodedAddress = encodeURIComponent(address);
    window.open(`https://www.google.com/maps/search/?api=1&query=${encodedAddress}`, '_blank');
  };

  return (
    <div className={`rounded-[2.5rem] border transition-all duration-500 overflow-hidden hover:shadow-2xl hover:-translate-y-1 group ${theme === 'dark' ? 'bg-[#111113] border-white/5 hover:border-blue-500/40' : 'bg-white border-slate-100 shadow-md'}`}>
      <div className="h-44 relative overflow-hidden">
        <img src="https://images.unsplash.com/photo-1493663284031-b7e3aefcae8e?w=800" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" alt="Home"/>
        <div className="absolute top-4 left-4 bg-blue-600/90 backdrop-blur-md text-white text-[9px] font-black px-3 py-1.5 rounded-xl uppercase tracking-widest shadow-lg">
          {prop.availability_tag || "Ready To Move"}
        </div>
        <div className="absolute bottom-4 left-4 bg-black/60 backdrop-blur-xl px-4 py-2 rounded-2xl border border-white/10 shadow-2xl">
          <span className="text-sm font-black text-white">{prop.formatted_rent}</span>
        </div>
      </div>
      <div className="p-6">
        <div className="flex items-center gap-1.5 text-[9px] text-emerald-400 font-black uppercase tracking-[0.15em] mb-2">
          <MapPin size={10}/> {prop.location}
        </div>
        <h4 className={`font-black text-[15px] mb-4 line-clamp-1 ${theme === 'dark' ? 'text-zinc-100' : 'text-slate-800'}`}>
          {prop.display_title}
        </h4>
        <div className="flex flex-wrap gap-2 mb-6">
          <div className="bg-blue-500/10 text-blue-500 text-[10px] font-bold px-3 py-1.5 rounded-xl flex items-center gap-1.5">
            <BedDouble size={12}/> {prop.size_bhk} BHK
          </div>
          <div className="bg-emerald-500/10 text-emerald-500 text-[10px] font-bold px-3 py-1.5 rounded-xl flex items-center gap-1.5">
            <TrendingUp size={12}/> {prop.total_sqft} Sqft
          </div>
          <div className="bg-orange-500/10 text-orange-500 text-[10px] font-bold px-3 py-1.5 rounded-xl">
             Deposit: {prop.formatted_deposit || "₹" + prop.legal_security_deposit}
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={openGoogleMaps} className="flex-1 bg-zinc-800 hover:bg-zinc-700 text-white flex items-center justify-center rounded-xl transition-all" title="View on Map">
            <MapPin size={18}/>
          </button>
          <button onClick={() => setShowContact(!showContact)} className={`flex-[3] py-3 px-2 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all shadow-lg truncate ${showContact ? 'bg-white border border-emerald-500 text-emerald-600' : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-500/20'}`}>
            {showContact ? `${prop.contact_person} | ${prop.contact_number}` : "Get Owner Details"}
          </button>
        </div>
      </div>
    </div>
  );
};
import { useState, useEffect, useRef } from 'react';
import { Activity, Brain, BarChart3, Clock, TrendingUp, TrendingDown, Crosshair, DollarSign } from 'lucide-react';

function App() {
  const [memory, setMemory] = useState({ regime: 'LOADING...', fear_greed: '...' });
  const [brainLogs, setBrainLogs] = useState([]);
  const [trades, setTrades] = useState([]);
  const [loadingTrades, setLoadingTrades] = useState(true);
  
  const host = window.location.hostname;
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

  // Connect to Python Streamer (Memory & Brain) via Nginx Proxy
  useEffect(() => {
    const memoryWs = new WebSocket(`${wsProtocol}//${host}/ws/memory`);
    memoryWs.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'memory_update') {
        setMemory({ regime: data.regime, fear_greed: data.fear_greed });
      }
    };

    const brainWs = new WebSocket(`${wsProtocol}//${host}/ws/brain`);
    brainWs.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'brain_log') {
        setBrainLogs((prev) => {
          const newLogs = [...prev, data.log];
          return newLogs.slice(-50); // Keep last 50
        });
      }
    };

    return () => {
      memoryWs.close();
      brainWs.close();
    };
  }, [host, wsProtocol]);

  // Fetch Freqtrade Status
  useEffect(() => {
    const fetchTrades = async () => {
      try {
        const response = await fetch(`${window.location.protocol}//${host}/api/v1/status`, {
          headers: {
            'Authorization': 'Basic Ym90OmJvdDEyMw==' // bot:REDACTED-FREQTRADE__API_SERVER__PASSWORD
          }
        });
        if (response.ok) {
          const data = await response.json();
          setTrades(data);
        }
      } catch (e) {
        console.error("Error fetching trades:", e);
      } finally {
        setLoadingTrades(false);
      }
    };
    
    fetchTrades();
    const interval = setInterval(fetchTrades, 5000); // Polling every 5s for live PnL
    return () => clearInterval(interval);
  }, [host]);

  // Auto-scroll brain feed
  const feedRef = useRef(null);
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [brainLogs]);

  const getRegimeColor = (regime) => {
    if (regime.includes('BULL') || regime.includes('EUPHORIA')) return 'text-cyber-green text-shadow-green';
    if (regime.includes('BEAR') || regime.includes('CRASH')) return 'text-cyber-red text-shadow-red';
    return 'text-cyber-neon text-shadow-neon';
  };

  // Parse Fear/Greed number
  const fgNumber = parseInt(memory.fear_greed) || 50;
  const getFgColor = (val) => {
    if (val < 25) return '#f87171'; // Red
    if (val < 45) return '#fb923c'; // Orange
    if (val <= 55) return '#fbbf24'; // Yellow
    if (val <= 75) return '#4ade80'; // Green
    return '#2dd4bf'; // Teal/Euphoria
  };

  return (
    <div className="min-h-screen p-6 md:p-10 max-w-7xl mx-auto flex flex-col gap-8 relative z-10">
      {/* Background Animated Gradient Mesh */}
      <div className="fixed inset-0 z-[-1] bg-mesh pointer-events-none opacity-30"></div>

      {/* Header */}
      <header className="flex items-center justify-between glass-panel p-6 shadow-2xl border-b border-cyber-neon/20">
        <div className="flex items-center gap-4">
          <div className="p-4 bg-cyber-neon/10 rounded-2xl border border-cyber-neon/30 shadow-[0_0_15px_rgba(56,189,248,0.2)]">
            <Brain className="w-8 h-8 text-cyber-neon animate-neon" />
          </div>
          <div>
            <h1 className="text-4xl font-bold tracking-tight text-white mb-1">FinBuddy <span className="text-cyber-neon font-light">Conscious Brain</span></h1>
            <p className="text-slate-400 text-sm tracking-wide">SELF-EVOLVING AI TRADING ARCHITECTURE</p>
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2 text-cyber-green bg-cyber-green/10 px-4 py-2 rounded-full border border-cyber-green/20 shadow-[0_0_10px_rgba(74,222,128,0.2)]">
            <div className="w-2 h-2 rounded-full bg-cyber-green animate-pulse"></div>
            <span className="text-xs font-bold tracking-widest uppercase">System Online</span>
          </div>
        </div>
      </header>

      {/* Grid Layout */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        
        {/* Left/Center Column - The Market & Trades */}
        <div className="col-span-1 xl:col-span-2 flex flex-col gap-8">
          
          {/* Market Context Panel */}
          <section className="glass-panel p-8">
            <h2 className="text-2xl font-bold mb-8 flex items-center gap-3 text-white">
              <Activity className="w-6 h-6 text-cyber-purple" />
              Global Market Context
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              
              {/* Regime Box */}
              <div className="bg-slate-900/60 p-8 rounded-2xl border border-slate-700/50 flex flex-col items-center justify-center relative overflow-hidden group">
                <div className="absolute inset-0 bg-gradient-to-br from-cyber-purple/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                <p className="text-slate-400 text-xs mb-3 uppercase tracking-[0.2em] font-semibold">Current Bias Regime</p>
                <div className={`text-5xl font-black uppercase tracking-wider ${getRegimeColor(memory.regime)}`}>
                  {memory.regime}
                </div>
              </div>

              {/* Fear & Greed Gauge */}
              <div className="bg-slate-900/60 p-8 rounded-2xl border border-slate-700/50 flex flex-col items-center justify-center relative">
                <p className="text-slate-400 text-xs mb-4 uppercase tracking-[0.2em] font-semibold absolute top-8">Fear & Greed Index</p>
                <div className="relative w-48 h-24 mt-8 overflow-hidden">
                  {/* Gauge Background */}
                  <div className="absolute top-0 left-0 w-48 h-48 rounded-full border-[16px] border-slate-800"></div>
                  {/* Gauge Value */}
                  <div 
                    className="absolute top-0 left-0 w-48 h-48 rounded-full border-[16px] border-b-transparent border-r-transparent transition-transform duration-1000 ease-out"
                    style={{ 
                      borderColor: `${getFgColor(fgNumber)} transparent transparent ${getFgColor(fgNumber)}`,
                      transform: `rotate(${-45 + (fgNumber / 100) * 180}deg)`
                    }}
                  ></div>
                  {/* Center Text */}
                  <div className="absolute bottom-0 left-0 w-full text-center flex flex-col items-center">
                    <span className="text-4xl font-bold text-white mb-1" style={{ textShadow: `0 0 15px ${getFgColor(fgNumber)}80` }}>{fgNumber}</span>
                  </div>
                </div>
                <span className="text-slate-400 text-sm mt-2 font-medium capitalize">{memory.fear_greed.replace(/[0-9()]/g, '').trim() || 'Neutral'}</span>
              </div>
            </div>
          </section>

          {/* Active Trades Panel */}
          <section className="glass-panel flex-1 flex flex-col">
            <div className="p-8 border-b border-slate-700/50 flex justify-between items-center">
              <h2 className="text-2xl font-bold flex items-center gap-3 text-white">
                <Crosshair className="w-6 h-6 text-cyber-neon" />
                Active Executions
              </h2>
              <span className="bg-slate-800 text-slate-300 text-xs px-3 py-1 rounded-full border border-slate-700">
                {trades.length} Open Positions
              </span>
            </div>
            
            <div className="p-8 flex-1">
              {loadingTrades ? (
                <div className="flex items-center justify-center h-48">
                  <div className="w-8 h-8 border-4 border-cyber-neon border-t-transparent rounded-full animate-spin"></div>
                </div>
              ) : trades.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 bg-slate-900/30 rounded-2xl border border-slate-700/30 border-dashed">
                  <BarChart3 className="w-10 h-10 text-slate-600 mb-3" />
                  <p className="text-slate-500 font-medium tracking-wide">Awaiting Signal Execution...</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {trades.map((trade, i) => (
                    <div key={i} className="bg-slate-900/60 p-5 rounded-2xl border border-slate-700 hover:border-slate-600 transition-colors shadow-lg relative overflow-hidden">
                      {/* Accent line based on direction */}
                      <div className={`absolute left-0 top-0 bottom-0 w-1 ${trade.is_short ? 'bg-cyber-red' : 'bg-cyber-green'}`}></div>
                      
                      <div className="flex justify-between items-start mb-4 pl-2">
                        <div>
                          <h3 className="text-xl font-bold text-white flex items-center gap-2">
                            {trade.pair}
                            <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider ${trade.is_short ? 'bg-cyber-red/20 text-cyber-red border border-cyber-red/30' : 'bg-cyber-green/20 text-cyber-green border border-cyber-green/30'}`}>
                              {trade.is_short ? 'SHORT' : 'LONG'} {trade.leverage}x
                            </span>
                          </h3>
                          <p className="text-xs text-slate-400 mt-1">Open: {trade.open_rate}</p>
                        </div>
                        <div className={`flex flex-col items-end`}>
                          <span className={`text-lg font-bold flex items-center gap-1 ${trade.profit_ratio > 0 ? 'text-cyber-green text-shadow-green' : 'text-cyber-red text-shadow-red'}`}>
                            {trade.profit_ratio > 0 ? <TrendingUp className="w-4 h-4"/> : <TrendingDown className="w-4 h-4"/>}
                            {(trade.profit_ratio * 100).toFixed(2)}%
                          </span>
                          <span className={`text-xs font-semibold ${trade.profit_abs > 0 ? 'text-cyber-green' : 'text-cyber-red'}`}>
                            {trade.profit_abs > 0 ? '+' : ''}{trade.profit_abs.toFixed(2)} USDT
                          </span>
                        </div>
                      </div>
                      
                      <div className="pl-2 pt-3 border-t border-slate-800 flex justify-between text-xs text-slate-500">
                        <span>Stake: {trade.stake_amount.toFixed(2)} USDT</span>
                        <span>Current: {trade.current_rate}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

        </div>

        {/* Right Column - Neural Feed */}
        <div className="col-span-1 glass-panel flex flex-col max-h-[900px] shadow-2xl border border-cyber-neon/10">
          <div className="p-6 border-b border-slate-700/80 bg-slate-900 flex justify-between items-center">
            <div>
              <h2 className="text-xl font-bold flex items-center gap-2 text-white">
                <Clock className="w-5 h-5 text-cyber-neon" />
                Neural Stream
              </h2>
              <p className="text-xs text-slate-400 mt-1 font-mono">Live evaluation feed [1h timeframe]</p>
            </div>
            <div className="w-2 h-2 rounded-full bg-cyber-neon animate-pulse"></div>
          </div>
          <div 
            ref={feedRef}
            className="flex-1 p-5 overflow-y-auto brain-feed font-mono text-[11px] leading-relaxed flex flex-col gap-2 bg-[#050b14]"
          >
            {brainLogs.length === 0 ? (
              <div className="text-slate-500 flex items-center gap-2 mt-4 ml-2">
                <div className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-ping"></div>
                Awaiting historical log sync...
              </div>
            ) : (
              brainLogs.map((log, idx) => {
                const isConfirm = log.includes('AUTO-CONFIRM');
                const isReject = log.includes('REJECT');
                return (
                  <div key={idx} className={`p-2.5 rounded-md border backdrop-blur-sm ${
                    isConfirm ? 'bg-cyber-green/10 border-cyber-green/30 text-cyber-green shadow-[0_0_10px_rgba(74,222,128,0.1)]' : 
                    isReject ? 'bg-cyber-red/5 border-cyber-red/20 text-slate-400' : 
                    'bg-slate-800/40 border-slate-700/50 text-slate-300'
                  }`}>
                    {log.split(' - ').slice(-1)[0]}
                  </div>
                );
              })
            )}
          </div>
        </div>

      </div>
    </div>
  );
}

export default App;

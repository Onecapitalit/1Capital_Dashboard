import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import Chart from 'chart.js/auto';
import { useAuth } from '../auth/AuthContext';

type BrokerageRecord = {
  id: string;
  name: string;
  pan: string;
  val: number;
};

type BrokerageDetailsResponse = {
  user: {
    full_name: string;
    role: string;
  };
  options: {
    all_managers: string[];
    all_rms: string[];
    all_mas: string[];
  };
  totals: {
    equity: number;
    mf: number;
    others: number;
  };
  chart_data: any;
  cities: string[];
  records: BrokerageRecord[];
  last_updated: string;
};

export function BrokerageDetailsPage() {
  const navigate = useNavigate();
  const { accessToken, logout } = useAuth();

  // Refs for Charts
  const rmCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const topClientsCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const maCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const segmentCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartsRef = useRef<{ rm?: Chart; top?: Chart; ma?: Chart; seg?: Chart }>({});

  // Financial Year Calculation
  const getFYStart = () => {
    const now = new Date();
    const currentYear = now.getFullYear();
    const startYear = now.getMonth() >= 3 ? currentYear : currentYear - 1;
    return `${startYear}-04-01`;
  };

  const [data, setData] = useState<BrokerageDetailsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<'team' | 'self'>('team');
  const [activeCard, setActiveCard] = useState<'equity' | 'mf' | 'others'>('equity');
  const [tab, setTab] = useState<'summarised' | 'detailed'>('summarised');
  
  // Filters
  const [selectedManager, setSelectedManager] = useState('');
  const [selectedRM, setSelectedRM] = useState('');
  const [selectedMA, setSelectedMA] = useState('');
  const [selectedCity, setSelectedCity] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState(new Date().toISOString().split('T')[0]);
  
  // Search
  const [searchBy, setSearchBy] = useState<'code' | 'name' | 'pan'>('code');
  const [searchQuery, setSearchQuery] = useState('');

  // Set default date for Detailed tab
  useEffect(() => {
    if (tab === 'detailed' && !dateFrom) {
      setDateFrom(getFYStart());
    }
  }, [tab]);

  const fetchBrokerageDetails = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('mode', viewMode);
      params.append('card', activeCard);
      params.append('q', searchQuery);
      params.append('search_by', searchBy);
      
      // In SELF mode, ignore hierarchy filters
      if (viewMode === 'team') {
        params.append('city', selectedCity);
        params.append('manager', selectedManager);
        params.append('rm', selectedRM);
        params.append('ma', selectedMA);
      } else {
        // Even in SELF mode, user might want to filter by city? 
        // Request says "only keep date range filters", so I'll omit city if mode is self.
      }
      
      if (tab === 'detailed') {
        if (dateFrom) params.append('date_from', dateFrom);
        if (dateTo) params.append('date_to', dateTo);
      }

      const response = await axios.get<BrokerageDetailsResponse>(
        `/api/dashboard/brokerage-details/?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${accessToken}` },
        }
      );
      setData(response.data);
    } catch (error: any) {
      if (error?.response?.status === 401) {
        logout();
        navigate('/login', { replace: true });
      }
      console.error('Error fetching brokerage details:', error);
    } finally {
      setLoading(false);
    }
  }, [accessToken, viewMode, activeCard, searchQuery, searchBy, tab, dateFrom, dateTo, selectedCity, selectedManager, selectedRM, selectedMA, logout, navigate]);

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      fetchBrokerageDetails();
    }, 300);
    return () => clearTimeout(timeoutId);
  }, [fetchBrokerageDetails]);

  // Chart Initialization Logic
  useEffect(() => {
    if (!data) return;

    // Cleanup previous charts
    Object.values(chartsRef.current).forEach((c) => c?.destroy());
    chartsRef.current = {};

    Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";
    const cd = data.chart_data || {};

    if (viewMode === 'team' && cd.rm_performance?.labels?.length && rmCanvasRef.current) {
      chartsRef.current.rm = new Chart(rmCanvasRef.current, {
        type: 'bar',
        data: {
          labels: cd.rm_performance.labels,
          datasets: [
            { label: 'Brokerage', data: cd.rm_performance.brokerage, backgroundColor: '#4f46e5', borderRadius: 6 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true }, x: { grid: { display: false } } }
        },
      });
    }

    if (cd.top_clients?.labels?.length && topClientsCanvasRef.current) {
      chartsRef.current.top = new Chart(topClientsCanvasRef.current, {
        type: 'bar',
        data: {
          labels: cd.top_clients.labels,
          datasets: [{ label: 'Brokerage', data: cd.top_clients.brokerage, backgroundColor: '#f59e0b', borderRadius: 6 }],
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { x: { beginAtZero: true }, y: { grid: { display: false } } }
        },
      });
    }

    if (viewMode === 'team' && cd.ma_performance?.labels?.length && maCanvasRef.current) {
        chartsRef.current.ma = new Chart(maCanvasRef.current, {
          type: 'doughnut',
          data: {
            labels: cd.ma_performance.labels,
            datasets: [{ data: cd.ma_performance.brokerage, backgroundColor: ['#4f46e5', '#818cf8', '#c7d2fe', '#fbbf24', '#fcd34d'] }],
          },
          options: { responsive: true, maintainAspectRatio: false }
        });
    }

    if (viewMode === 'team' && cd.segment_analysis?.labels?.length && segmentCanvasRef.current) {
        chartsRef.current.seg = new Chart(segmentCanvasRef.current, {
          type: 'pie',
          data: {
            labels: cd.segment_analysis.labels,
            datasets: [{ data: cd.segment_analysis.cash || [50, 50], backgroundColor: ['#4f46e5', '#10b981'] }],
          },
          options: { responsive: true, maintainAspectRatio: false }
        });
    }

  }, [data, viewMode]);

  const clearFilters = () => {
    setSearchQuery('');
    setSelectedCity('');
    setSelectedManager('');
    setSelectedRM('');
    setSelectedMA('');
    if (tab === 'detailed') {
        setDateFrom(getFYStart());
        setDateTo(new Date().toISOString().split('T')[0]);
    }
  };

  const formatCurrency = (val: number) => {
    if (val >= 10000000) return (val / 10000000).toFixed(2) + ' Cr';
    if (val >= 100000) return (val / 100000).toFixed(2) + ' L';
    if (val >= 1000) return (val / 1000).toFixed(2) + ' K';
    return val.toFixed(2);
  };

  return (
    <div className="min-h-screen bg-[#f4f6fa] font-sans text-[#1c1c1c]">
      {/* Top Navbar */}
      <nav className="bg-[#2c2759] text-white flex items-center justify-between px-6 py-3 shadow-md">
         <div className="flex items-center space-x-6">
           <div className="font-bold text-xl tracking-wider text-yellow-500 cursor-pointer" onClick={() => navigate('/website')}>AAA <span className="text-sm font-normal text-white">CAPITAL</span></div>
           <div className="hidden md:flex space-x-1">
             <button onClick={() => navigate('/new-dashboard')} className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm font-medium">Dashboard</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Reports</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Markets</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Invest</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Trades</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">More</button>
           </div>
         </div>
         <div className="flex items-center space-x-4">
            <button className="bg-white text-gray-800 px-4 py-1.5 rounded-full text-xs font-semibold shadow-sm">Earn ₹ 5000</button>
            <div className="text-xs text-gray-300 border-l border-gray-600 pl-4 ml-2">
               Data updated: {data?.last_updated || 'Loading...'}
            </div>
            <div className="flex items-center bg-gray-800 rounded px-3 py-1 cursor-pointer" onClick={() => { logout(); navigate('/login'); }}>
              <div className="w-6 h-6 bg-gray-500 rounded-full flex items-center justify-center mr-2"><i className="fas fa-user text-xs"></i></div>
              <div>
                <div className="text-xs font-bold uppercase">{data?.user.full_name || 'Loading...'}</div>
                <div className="text-[10px] text-gray-400">{data?.user.role === 'L' ? 'Leader' : data?.user.role === 'M' ? 'Manager' : 'RM'}</div>
              </div>
              <i className="fas fa-sign-out-alt ml-2 text-xs"></i>
            </div>
         </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 py-6">
        
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center space-x-4">
             <button onClick={() => navigate('/new-dashboard')} className="text-gray-500 hover:text-gray-800 transition-colors">
               <i className="fas fa-arrow-left text-xl"></i>
             </button>
             <h1 className="text-2xl font-semibold uppercase tracking-tight">Brokerage {tab === 'summarised' ? '(YTD)' : '(Detailed)'}</h1>
          </div>
          <div className="bg-white rounded-full p-1 border border-gray-200 shadow-sm flex items-center">
             <button onClick={() => setViewMode('team')} className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${viewMode === 'team' ? 'bg-gray-500 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100'}`}>
               <i className="fas fa-users mr-2"></i> Team
             </button>
             <button onClick={() => setViewMode('self')} className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${viewMode === 'self' ? 'bg-gray-500 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100'}`}>
               <i className="fas fa-user mr-2"></i> Self
             </button>
          </div>
        </div>

        {/* Cards */}
        <div className="flex flex-wrap gap-4 mb-4">
           {[
             { id: 'equity', title: tab === 'summarised' ? 'Equity (YTD)' : 'Equity (Selected)', val: formatCurrency(data?.totals.equity || 0), active: activeCard === 'equity' },
             { id: 'mf', title: tab === 'summarised' ? 'Mutual Funds (YTD)' : 'Mutual Funds (Selected)', val: formatCurrency(data?.totals.mf || 0), active: activeCard === 'mf' },
             { id: 'others', title: tab === 'summarised' ? 'Others (YTD)' : 'Others (Selected)', val: '0', active: activeCard === 'others' },
           ].map((card) => (
             <div 
                key={card.id} 
                onClick={() => setActiveCard(card.id as any)}
                className={`flex-1 min-w-[200px] bg-white rounded-xl py-6 border transition-all ${card.active ? 'border-indigo-500 shadow-md ring-1 ring-indigo-500/20' : 'border-gray-200 hover:shadow-sm text-gray-500 cursor-pointer'}`}
             >
                <div className="flex flex-col justify-center items-center text-center">
                    <div className={`text-sm mb-2 font-semibold uppercase tracking-wider ${card.active ? 'text-indigo-600' : 'text-gray-400'}`}>{card.title}</div>
                    <div className={`text-3xl font-bold ${card.active ? 'text-gray-900' : 'text-gray-700'}`}>₹ {card.val}</div>
                </div>
             </div>
           ))}
        </div>

        {/* Tab Selection */}
        <div className="flex justify-end mb-1">
           <div className="flex border border-gray-200 rounded-full overflow-hidden bg-white shadow-sm">
              <button onClick={() => setTab('summarised')} className={`px-6 py-1.5 text-sm font-bold transition-all ${tab === 'summarised' ? 'bg-orange-500 text-white' : 'text-gray-500 hover:bg-gray-50'}`}>Summarised</button>
              <button onClick={() => setTab('detailed')} className={`px-6 py-1.5 text-sm font-bold transition-all ${tab === 'detailed' ? 'bg-orange-500 text-white' : 'text-gray-500 hover:bg-gray-50'}`}>Detailed</button>
           </div>
        </div>
        <div className="text-right text-[10px] text-gray-400 mb-6 uppercase font-bold tracking-widest">
           {tab === 'summarised' ? 'Showing full YTD data' : 'Showing data for the selected filters and date range'}
        </div>

        {/* Detailed Filters Section */}
        {tab === 'detailed' && (
          <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm space-y-6 mb-6 animate-in fade-in slide-in-from-top-2">
            
            {viewMode === 'team' && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="flex flex-col">
                        <label className="text-[10px] font-bold text-gray-400 mb-1 uppercase tracking-widest">Manager</label>
                        <select value={selectedManager} onChange={(e) => { setSelectedManager(e.target.value); setSelectedRM(''); setSelectedMA(''); }} className="border border-gray-200 rounded px-3 py-2 text-sm outline-none focus:border-indigo-500 bg-transparent">
                            <option value="">-- All Managers --</option>
                            {data?.options.all_managers.map(m => <option key={m} value={m}>{m}</option>)}
                        </select>
                    </div>
                    <div className="flex flex-col">
                        <label className="text-[10px] font-bold text-gray-400 mb-1 uppercase tracking-widest">Relationship Manager</label>
                        <select value={selectedRM} onChange={(e) => setSelectedRM(e.target.value)} className="border border-gray-200 rounded px-3 py-2 text-sm outline-none focus:border-indigo-500 bg-transparent">
                            <option value="">-- All RMs --</option>
                            {data?.options.all_rms.map(r => <option key={r} value={r}>{r}</option>)}
                        </select>
                    </div>
                    <div className="flex flex-col">
                        <label className="text-[10px] font-bold text-gray-400 mb-1 uppercase tracking-widest">MF Advisor</label>
                        <select value={selectedMA} onChange={(e) => setSelectedMA(e.target.value)} className="border border-gray-200 rounded px-3 py-2 text-sm outline-none focus:border-indigo-500 bg-transparent">
                            <option value="">-- All MAs --</option>
                            {data?.options.all_mas.map(ma => <option key={ma} value={ma}>{ma}</option>)}
                        </select>
                    </div>
                </div>
            )}

            <div className={`grid grid-cols-1 gap-6 items-end ${viewMode === 'team' ? 'md:grid-cols-4' : 'md:grid-cols-3'}`}>
                <div className="flex flex-col">
                    <label className="text-[10px] font-bold text-gray-400 mb-1 uppercase tracking-widest">From Date</label>
                    <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="border border-gray-200 rounded px-3 py-1.5 text-sm outline-none focus:border-orange-500" />
                </div>
                <div className="flex flex-col">
                    <label className="text-[10px] font-bold text-gray-400 mb-1 uppercase tracking-widest">To Date</label>
                    <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="border border-gray-200 rounded px-3 py-1.5 text-sm outline-none focus:border-orange-500" />
                </div>
                {viewMode === 'team' && (
                    <div className="flex flex-col">
                        <label className="text-[10px] font-bold text-gray-400 mb-1 uppercase tracking-widest">City</label>
                        <select value={selectedCity} onChange={(e) => setSelectedCity(e.target.value)} className="border border-gray-200 rounded px-3 py-1.5 text-sm outline-none focus:border-indigo-500 bg-transparent">
                            <option value="">All Cities</option>
                            {data?.cities.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                    </div>
                )}
                <button onClick={clearFilters} className="h-[38px] text-xs font-bold text-indigo-600 border border-indigo-100 rounded-lg hover:bg-indigo-50 uppercase tracking-tighter transition-all">
                    {viewMode === 'team' ? 'Clear All Filters' : 'Clear Dates'}
                </button>
            </div>
          </div>
        )}

        {/* Charts Section */}
        {tab === 'detailed' && data && (
            <div className="space-y-8 mb-10">
                <div className={`grid grid-cols-1 gap-6 ${viewMode === 'team' ? 'lg:grid-cols-2' : 'lg:grid-cols-1'}`}>
                    {viewMode === 'team' && (
                        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm h-[350px]">
                            <div className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4">RM Performance - Brokerage</div>
                            <div className="h-[260px]"><canvas ref={rmCanvasRef} /></div>
                        </div>
                    )}
                    <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm h-[350px]">
                        <div className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4">Top 10 Clients by Brokerage</div>
                        <div className="h-[260px]"><canvas ref={topClientsCanvasRef} /></div>
                    </div>
                </div>

                {viewMode === 'team' && (selectedRM || selectedManager) && (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm h-[350px]">
                            <div className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4">MA Performance under {selectedRM || selectedManager}</div>
                            <div className="h-[260px]"><canvas ref={maCanvasRef} /></div>
                        </div>
                        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm h-[350px]">
                            <div className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4">Segment Analysis</div>
                            <div className="h-[260px]"><canvas ref={segmentCanvasRef} /></div>
                        </div>
                    </div>
                )}
            </div>
        )}

        {/* Search Bar */}
        <div className="bg-white rounded-xl px-4 py-3 border border-gray-200 shadow-sm flex items-center flex-wrap gap-4 mb-6">
           <div className="text-xs text-gray-400 font-bold uppercase tracking-widest">Search List</div>
           <div className="flex border border-gray-200 rounded overflow-hidden text-sm font-bold">
             <button onClick={() => setSearchBy('code')} className={`px-3 py-1.5 border-r border-gray-200 transition-all ${searchBy === 'code' ? 'text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30' : 'text-gray-500 hover:bg-gray-50'}`}>Code</button>
             <button onClick={() => setSearchBy('pan')} className={`px-3 py-1.5 border-r border-gray-200 transition-all ${searchBy === 'pan' ? 'text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30' : 'text-gray-500 hover:bg-gray-50'}`}>PAN</button>
             <button onClick={() => setSearchBy('name')} className={`px-3 py-1.5 transition-all ${searchBy === 'name' ? 'text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30' : 'text-gray-500 hover:bg-gray-50'}`}>Name</button>
           </div>
           
           <div className="flex-1 min-w-[150px] border-b border-gray-300 flex items-center px-4">
             <input 
                type="text" 
                placeholder={`Search client by ${searchBy.toUpperCase()}...`} 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full py-1.5 outline-none text-sm text-center text-gray-700 bg-transparent font-medium" 
             />
           </div>
        </div>

        {/* Data Table */}
        <div className="bg-[#fcfdfd] rounded-lg border border-gray-200 shadow-sm overflow-hidden relative">
           {loading && (
             <div className="absolute inset-0 bg-white/50 backdrop-blur-[1px] flex items-center justify-center z-10">
               <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
             </div>
           )}
           <div className="overflow-x-auto">
             <table className="w-full text-sm text-left whitespace-nowrap">
               <thead className="text-[10px] text-gray-400 bg-gray-50/80 border-b border-gray-200 uppercase tracking-widest font-bold">
                 <tr>
                   <th className="px-6 py-4">Client Code</th>
                   <th className="px-6 py-4">Client PAN</th>
                   <th className="px-6 py-4">Client Name</th>
                   <th className="px-6 py-4 text-right">
                     <div className="flex flex-col items-end">
                       <span className="flex items-center cursor-pointer">Brokerage (₹) <i className="fas fa-sort text-gray-300 ml-1"></i></span>
                       <span className="text-sm font-bold text-gray-800 tracking-wide mt-1">
                        {formatCurrency(activeCard === 'equity' ? data?.totals.equity || 0 : activeCard === 'mf' ? data?.totals.mf || 0 : 0)}
                       </span>
                     </div>
                   </th>
                 </tr>
               </thead>
               <tbody className="divide-y divide-gray-100">
                 {activeCard === 'others' ? (
                    <tr><td colSpan={4} className="px-6 py-12 text-center text-gray-400 italic">No data available for Others.</td></tr>
                 ) : data?.records && data.records.length > 0 ? (
                   data.records.map((row, i) => (
                     <tr key={i} className={`hover:bg-gray-50 transition-colors border-l-4 border-l-indigo-700 ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}`}>
                       <td className="px-6 py-4 text-gray-600 font-medium">{row.id}</td>
                       <td className="px-6 py-4 text-gray-500 font-mono text-xs">{row.pan}</td>
                       <td className="px-6 py-4 font-bold text-gray-800 uppercase tracking-tight">{row.name}</td>
                       <td className="px-6 py-4 text-right text-indigo-700 font-bold">₹ {row.val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                     </tr>
                   ))
                 ) : (
                   <tr>
                     <td colSpan={4} className="px-6 py-12 text-center text-gray-400 italic">
                       {loading ? 'Fetching records...' : 'No records found matching your criteria.'}
                     </td>
                   </tr>
                 )}
               </tbody>
             </table>
           </div>
        </div>

      </main>
    </div>
  );
}

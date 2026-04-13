import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../auth/AuthContext';

type AumRecord = {
  code: string;
  pan: string;
  name: string;
  equity?: number;
  mf?: number;
  total: number;
};

type AumDetailsResponse = {
  user: {
    full_name: string;
    role: string;
  };
  totals: {
    overall: number;
    equity: number;
    mf: number;
  };
  records: AumRecord[];
  last_updated: string;
};

export function AumDetailsPage() {
  const navigate = useNavigate();
  const { accessToken, logout } = useAuth();

  const [data, setData] = useState<AumDetailsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<'team' | 'self'>('team');
  const [activeCard, setActiveCard] = useState<'overall' | 'equity' | 'mf'>('overall');
  const [searchBy, setSearchBy] = useState<'code' | 'pan' | 'name' | 'group'>('code');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');

  // Debounce search query
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 500);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  const fetchAumDetails = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('mode', viewMode);
      params.append('card', activeCard);
      params.append('q', debouncedQuery);
      params.append('search_by', searchBy);

      const response = await axios.get<AumDetailsResponse>(
        `/api/dashboard/aum-details/?${params.toString()}`,
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
      console.error('Error fetching AUM details:', error);
    } finally {
      setLoading(false);
    }
  }, [accessToken, viewMode, activeCard, debouncedQuery, searchBy, logout, navigate]);

  useEffect(() => {
    fetchAumDetails();
  }, [fetchAumDetails]);

  const formatCurrency = (val: number) => {
    if (val >= 10000000) return (val / 10000000).toFixed(2) + ' Cr';
    if (val >= 100000) return (val / 100000).toFixed(2) + ' L';
    if (val >= 1000) return (val / 1000).toFixed(2) + ' K';
    return val.toFixed(2);
  };

  const calculatePct = (val: number) => {
    if (!data || data.totals.overall === 0) return '0.00 %';
    return ((val / data.totals.overall) * 100).toFixed(2) + ' %';
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
            <div className="text-xs text-gray-300">Data updated: {data?.last_updated || 'Loading...'}</div>
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

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        
        {/* Header Section */}
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center space-x-4">
             <button onClick={() => navigate('/new-dashboard')} className="text-gray-500 hover:text-gray-800 transition-colors">
               <i className="fas fa-arrow-left text-xl"></i>
             </button>
             <h1 className="text-2xl font-semibold uppercase tracking-tight text-gray-800">Assets Under Management</h1>
          </div>
          <div className="bg-white rounded-full p-1 border border-gray-200 shadow-sm flex items-center">
             <button 
                onClick={() => setViewMode('team')}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${viewMode === 'team' ? 'bg-gray-500 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100'}`}
             >
               <i className="fas fa-users mr-2"></i> Team
             </button>
             <button 
                onClick={() => setViewMode('self')}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${viewMode === 'self' ? 'bg-gray-500 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100'}`}
             >
               <i className="fas fa-user mr-2"></i> Self
             </button>
          </div>
        </div>

        {/* Tab Cards */}
        <div className="flex flex-wrap gap-4 mb-8">
           {[
             { id: 'overall', title: 'Overall AUM', val: formatCurrency(data?.totals.overall || 0), pct: calculatePct(data?.totals.overall || 0), active: activeCard === 'overall' },
             { id: 'equity', title: 'Equity', val: formatCurrency(data?.totals.equity || 0), pct: calculatePct(data?.totals.equity || 0), active: activeCard === 'equity' },
             { id: 'mf', title: 'Mutual Fund', val: formatCurrency(data?.totals.mf || 0), pct: calculatePct(data?.totals.mf || 0), active: activeCard === 'mf' },
             /* Commented out for later implementation
             { id: 'grobox', title: 'Grobox', val: '0', pct: '(0.00 %)', active: false, badge: 'New' },
             { id: 'fd', title: 'FD/Bonds/NCDs', val: '0', pct: '(0.00 %)', active: false },
             { id: 'pms', title: 'PMS/AIF', val: '0', pct: '(0.00 %)', active: false },
             */
           ].map((card) => (
             <div 
                key={card.id} 
                onClick={() => setActiveCard(card.id as any)}
                className={`relative flex-1 min-w-[180px] bg-white rounded-xl p-5 border transition-all ${card.active ? 'border-indigo-500 shadow-md ring-1 ring-indigo-500/20 text-indigo-700' : 'border-gray-200 hover:shadow-sm text-gray-500 cursor-pointer'}`}
             >
                <div className={`text-xs mb-2 font-bold uppercase tracking-wider ${card.active ? 'text-indigo-500' : 'text-gray-400'}`}>{card.title}</div>
                <div className={`text-2xl font-bold ${card.active ? 'text-gray-900' : 'text-gray-800'}`}>₹ {card.val}</div>
                <div className="text-xs text-gray-400 mt-1 font-medium">({card.pct})</div>
             </div>
           ))}
        </div>

        {/* Search & Filters */}
        <div className="bg-white rounded-xl px-4 py-3 border border-gray-200 shadow-sm flex items-center flex-wrap gap-4 mb-4">
           <div className="text-xs text-gray-400 font-bold uppercase tracking-widest">Search by</div>
           <div className="flex border border-gray-200 rounded overflow-hidden text-sm font-bold">
             <button 
                onClick={() => setSearchBy('code')}
                className={`px-3 py-1.5 border-r border-gray-200 transition-all ${searchBy === 'code' ? 'text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30' : 'text-gray-500 hover:bg-gray-50'}`}
             >Code</button>
             <button 
                onClick={() => setSearchBy('pan')}
                className={`px-3 py-1.5 border-r border-gray-200 transition-all ${searchBy === 'pan' ? 'text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30' : 'text-gray-500 hover:bg-gray-50'}`}
             >PAN</button>
             <button 
                onClick={() => setSearchBy('name')}
                className={`px-3 py-1.5 border-r border-gray-200 transition-all ${searchBy === 'name' ? 'text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30' : 'text-gray-500 hover:bg-gray-50'}`}
             >Name</button>
             <button 
                onClick={() => setSearchBy('group')}
                className={`px-3 py-1.5 transition-all ${searchBy === 'group' ? 'text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30' : 'text-gray-500 hover:bg-gray-50'}`}
             >Group Code</button>
           </div>
           <div className="flex-1 min-w-[200px] border-b border-gray-300 flex items-center px-4">
             <input 
                type="text" 
                placeholder={`Search by ${searchBy.toUpperCase()}...`} 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full py-1.5 outline-none text-sm text-center text-gray-700 bg-transparent font-medium" 
             />
           </div>
           <button 
                onClick={() => { setSearchQuery(''); setDebouncedQuery(''); }}
                className="text-xs font-bold border rounded-[3px] border-gray-400 px-2 py-[7px] text-indigo-600 hover:text-orange-600 uppercase transition-colors"
           >
              Clear 
           </button>
        </div>

        <div className="text-sm text-gray-700 mb-6 flex justify-between items-start">
           {/* <ul className="list-disc pl-5 space-y-1 text-xs text-gray-500 font-medium">
             <li>Tap on client name to view the detailed portfolio</li>
             <li>Go to <strong className="font-bold text-indigo-600">Trades</strong> to track Holdings and Net Positions in real-time</li>
             <li className="text-orange-600 mt-2 list-none -ml-5"><span className="font-bold uppercase tracking-tighter mr-1">Note:</span> AUM shown below is based on total recorded turnover.</li>
           </ul> */}
           {/* <button className="text-orange-600 text-2xl hover:opacity-80 transition-opacity">
             <i className="fas fa-file-excel"></i>
           </button> */}
        </div>

        {/* Data Table */}
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden border-l-4 border-l-indigo-700 relative">
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
                   {activeCard === 'overall' && (
                     <>
                       <th className="px-6 py-4 text-right">Equity AUM (₹)</th>
                       <th className="px-6 py-4 text-right">MF AUM (₹)</th>
                     </>
                   )}
                   <th className="px-6 py-4 text-right">
                     <div className="flex flex-col items-end">
                       <span className="flex items-center cursor-pointer">Total AUM (₹) <i className="fas fa-sort text-gray-300 ml-1"></i></span>
                       <span className="text-sm font-bold text-indigo-700 tracking-wide mt-1">
                        {formatCurrency(activeCard === 'overall' ? data?.totals.overall || 0 : activeCard === 'equity' ? data?.totals.equity || 0 : data?.totals.mf || 0)}
                       </span>
                     </div>
                   </th>
                 </tr>
               </thead>
               <tbody className="divide-y divide-gray-100 font-medium">
                 {data?.records && data.records.length > 0 ? (
                   data.records.map((row, i) => (
                     <tr key={row.code} className={`hover:bg-gray-50 transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}`}>
                       <td className="px-6 py-4 text-gray-600">{row.code}</td>
                       <td className="px-6 py-4 text-gray-500 font-mono text-xs">{row.pan}</td>
                       <td className="px-6 py-4 font-bold text-gray-800 uppercase tracking-tight">{row.name}</td>
                       {activeCard === 'overall' && (
                         <>
                           <td className="px-6 py-4 text-right text-gray-600">₹ {row.equity?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                           <td className="px-6 py-4 text-right text-gray-600">₹ {row.mf?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                         </>
                       )}
                       <td className="px-6 py-4 text-right text-indigo-700 font-bold">₹ {row.total.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                     </tr>
                   ))
                 ) : (
                   <tr>
                     <td colSpan={activeCard === 'overall' ? 6 : 4} className="px-6 py-12 text-center text-gray-400 italic">
                       {loading ? 'Fetching AUM records...' : 'No data found matching your criteria.'}
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

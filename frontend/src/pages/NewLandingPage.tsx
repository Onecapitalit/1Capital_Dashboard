import { useState, useEffect, useCallback, useRef } from 'react';
import {  useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../auth/AuthContext';

type LandingSummaryResponse = {
  user: {
    full_name: string;
    role: string;
    default_tab: string;
  };
  totals: {
    overall: { aum: number; brokerage: number; clients: number };
    equity: { aum: number; brokerage: number; clients: number };
    mf: { aum: number; brokerage: number; clients: number };
    active_clients: number;
    dormant_clients: number;
    equity_aum_detail: number;
    mf_aum_detail: number;
  };
  last_updated: string;
};

type HierarchyData = {
  managers: string[];
  rms: string[];
  mas: string[];
};

export function NewLandingPage() {
  const navigate = useNavigate();
  const { accessToken, logout } = useAuth();
  
  const [activeTab, setActiveTab] = useState('Overall');
  const [data, setData] = useState<LandingSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<'team' | 'self'>('team');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [showDateFilters, setShowDateFilters] = useState(false);
  
  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [hierarchyData, setHierarchyData] = useState<HierarchyData | null>(null);
  const [modalLoading, setHierarchyLoading] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);

  const fetchSummary = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('mode', viewMode);
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);

      const response = await axios.get<LandingSummaryResponse>(
        `/api/dashboard/landing-summary/?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${accessToken}` },
        }
      );
      setData(response.data);
      if (!data) {
        setActiveTab(response.data.user.default_tab || 'Overall');
      }
    } catch (error: any) {
      if (error?.response?.status === 401) {
        logout();
        navigate('/login', { replace: true });
      }
      console.error('Error fetching landing summary:', error);
    } finally {
      setLoading(false);
    }
  }, [accessToken, viewMode, dateFrom, dateTo, logout, navigate]);

  const fetchHierarchy = async () => {
    if (!accessToken || hierarchyData) return;
    setHierarchyLoading(true);
    try {
      const res = await axios.get<HierarchyData>('/api/dashboard/hierarchy-list/', {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      setHierarchyData(res.data);
    } catch (e) {
      console.error('Hierarchy fetch failed', e);
    } finally {
      setHierarchyLoading(false);
    }
  };

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      fetchSummary();
    }, 300);
    return () => clearTimeout(timeoutId);
  }, [fetchSummary]);

  // Handle outside click for modal
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (modalRef.current && !modalRef.current.contains(event.target as Node)) {
        setIsModalOpen(false);
      }
    }
    if (isModalOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isModalOpen]);

  const [saveStatus, setSaveStatus] = useState(false);

  const setDefaultTab = async () => {
    if (!accessToken) return;
    try {
      await axios.post(
        '/api/user/preference/',
        { default_landing_tab: activeTab },
        { headers: { Authorization: `Bearer ${accessToken}` } }
      );
      setSaveStatus(true);
      setTimeout(() => setSaveStatus(false), 2000);
      if (data) {
        setData({ ...data, user: { ...data.user, default_tab: activeTab } });
      }
    } catch (error) {
      console.error('Error setting default tab:', error);
    }
  };

  const formatCurrency = (val: number, isBrokerage = false) => {
    if (isBrokerage) {
        if (val >= 100000) return '₹ ' + (val / 100000).toFixed(2) + 'L';
        if (val >= 1000) return '₹ ' + (val / 1000).toFixed(2) + 'K';
        return '₹ ' + val.toFixed(2);
    }
    if (val >= 10000000) return '₹ ' + (val / 10000000).toFixed(2) + 'Cr';
    if (val >= 100000) return '₹ ' + (val / 100000).toFixed(2) + 'L';
    return '₹ ' + val.toLocaleString('en-IN');
  };

  const getActiveTotals = () => {
    if (!data) return { aum: 0, brokerage: 0, clients: 0 };
    if (activeTab === 'Overall') return data.totals.overall;
    if (activeTab === 'Equity') return data.totals.equity;
    if (activeTab === 'Mutual Funds') return data.totals.mf;
    return { aum: 0, brokerage: 0, clients: 0 };
  };

  const activeTotals = getActiveTotals();

  return (
    <div className="min-h-screen bg-[#f4f6fa] font-sans text-[#1c1c1c]">
      {/* Top Navbar */}
      <nav className="bg-[#2c2759] text-white flex items-center justify-between px-6 py-3 shadow-md">
         <div className="flex items-center space-x-6">
           <div className="font-bold text-xl tracking-wider text-yellow-500 cursor-pointer" onClick={() => navigate('/website')}>One <span className="text-sm font-normal text-white">CAPITAL</span></div>
           <div className="hidden md:flex space-x-1">
             <button className="px-4 py-2 bg-indigo-700/50 rounded text-sm font-medium border-b-2 border-orange-500">Dashboard</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Reports</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Markets</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Invest</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Trades</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">More</button>
           </div>
         </div>
         <div className="flex items-center space-x-4">
            {/* <button className="bg-green-500 hover:bg-green-600 px-4 py-1.5 rounded-full text-xs font-semibold transition-colors">Refer & Earn</button> */}
            {/* <button className="text-gray-300 hover:text-white"><i className="fas fa-search"></i></button>
            <button className="text-gray-300 hover:text-white"><i className="fas fa-bell"></i></button>
            <button className="text-gray-300 hover:text-white"><i className="fas fa-question-circle"></i></button> */}
            <div className="w-8 h-8 bg-gray-500 rounded-full flex items-center justify-center cursor-pointer hover:bg-gray-400 transition-colors" onClick={() => { logout(); navigate('/login'); }}>
              <i className="fas fa-user"></i>
            </div>
         </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 py-6">
        
        {/* Header Section */}
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center space-x-3">
             <h1 className="text-3xl font-semibold tracking-tight">Hello, <span className="ml-2 uppercase">{data?.user.full_name || 'Loading...'}</span></h1>
             <span 
                className="text-orange-500 cursor-pointer hover:opacity-80 transition-opacity h-5 w-5 mb-2" 
                onClick={() => { setIsModalOpen(true); fetchHierarchy(); }}
             >
                <img src="https://aaa.iiflcapital.com/assets/svg/user-search.svg" alt="emp search" className="w-8 h-8" />
             </span>
          </div>
          <div className="bg-white rounded-full p-1 border border-gray-200 shadow-sm flex items-center">
             <button 
                onClick={() => setViewMode('team')}
                className={`px-4 py-1.5 rounded-full text-sm font-medium flex items-center transition-all ${viewMode === 'team' ? 'bg-gray-500 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100'}`}
             >
               <i className="fas fa-users mr-2"></i> Team
             </button>
             <button 
                onClick={() => setViewMode('self')}
                className={`px-4 py-1.5 rounded-full text-sm font-medium flex items-center transition-all ${viewMode === 'self' ? 'bg-gray-500 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100'}`}
             >
               <i className="fas fa-user mr-2"></i> Self
             </button>
          </div>
        </div>

        {/* Date Filter Accordion */}
        <div className="mb-6">
            <button 
                onClick={() => setShowDateFilters(!showDateFilters)}
                className="flex items-center text-xs font-bold uppercase tracking-widest text-indigo-600 bg-white px-4 py-2 rounded-lg border border-indigo-100 shadow-sm hover:bg-indigo-50 transition-all"
            >
                <i className={`fas ${showDateFilters ? 'fa-chevron-up' : 'fa-chevron-down'} mr-2`}></i>
                Date Filters
            </button>
            
            {showDateFilters && (
                <div className="mt-2 bg-white rounded-xl px-6 py-4 border border-gray-200 shadow-sm flex items-center gap-6 animate-in fade-in slide-in-from-top-2">
                    <div className="flex flex-col">
                        <label className="text-[10px] font-bold text-gray-400 mb-1 uppercase tracking-wider">From Date</label>
                        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="border border-gray-200 rounded px-3 py-1.5 text-sm outline-none focus:border-indigo-500" />
                    </div>
                    <div className="flex flex-col">
                        <label className="text-[10px] font-bold text-gray-400 mb-1 uppercase tracking-wider">To Date</label>
                        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="border border-gray-200 rounded px-3 py-1.5 text-sm outline-none focus:border-indigo-500" />
                    </div>
                    <button onClick={() => { setDateFrom(''); setDateTo(''); }} className="mt-5 text-xs font-bold text-gray-500 hover:text-orange-600 uppercase">Clear</button>
                    <div className="ml-auto text-[10px] text-gray-400 self-end mb-1">Last updated: {data?.last_updated || '...'}</div>
                </div>
            )}
        </div>

        {/* Tabs */}
        <div className="flex space-x-8 border-b border-gray-200 mb-6 relative">
           {['Overall', 'Mutual Funds', 'Equity', 'Other Products'].map(tab => (
             <button 
               key={tab}
               onClick={() => setActiveTab(tab)}
               className={`py-3 text-sm font-bold border-b-2 uppercase tracking-tight transition-all ${activeTab === tab ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-gray-400 hover:text-gray-700'}`}
             >
               {tab} {activeTab === tab && <i className="fas fa-thumbtack ml-1 text-xs"></i>}
             </button>
           ))}
           <div className="ml-auto py-3">
             <button 
                onClick={setDefaultTab}
                disabled={activeTab === data?.user.default_tab || saveStatus}
                className={`text-xs font-bold uppercase tracking-widest flex items-center transition-all ${activeTab === data?.user.default_tab ? 'text-gray-300 cursor-default' : saveStatus ? 'text-green-600' : 'text-indigo-600 hover:text-indigo-800'}`}
             >
               <i className={`fas ${saveStatus ? 'fa-check' : 'fa-thumbtack'} mr-1`}></i> 
               {activeTab === data?.user.default_tab ? 'Default' : saveStatus ? 'Saved!' : 'Set Default'}
             </button>
           </div>
        </div>

        {/* Content Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 relative">
           {loading && (
             <div className="absolute inset-0 bg-white/30 backdrop-blur-[1px] z-20 flex items-center justify-center rounded-xl">
               <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
             </div>
           )}
           {/* Business Overview */}
           <div className="lg:col-span-2 space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold tracking-tight text-gray-800">Business Overview</h2>
                <i className="fas fa-eye text-orange-500 cursor-pointer"></i>
              </div>

              {activeTab === 'Other Products' ? (
                  <div className="bg-gray-50 rounded-xl p-12 border border-dashed border-gray-300 text-center text-gray-400 font-medium italic">
                      No data available for Other Products yet.
                  </div>
              ) : (
                <>
                    {/* Main 3 Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div 
                            onClick={() => navigate('/aum-details')}
                            className="bg-indigo-50/50 rounded-xl p-6 border border-indigo-200 shadow-sm cursor-pointer hover:shadow-md transition-all relative overflow-hidden group"
                        >
                            <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-100 rounded-full blur-3xl -mr-10 -mt-10 opacity-60 group-hover:bg-indigo-200 transition-colors"></div>
                            <div className="w-8 h-8 rounded bg-indigo-100 text-indigo-600 flex items-center justify-center mb-6">
                                <i className="fas fa-cube"></i>
                            </div>
                            <div className="text-indigo-700 font-bold text-lg flex items-center uppercase tracking-tighter">
                                AUM <i className="fas fa-chevron-right ml-2 text-xs opacity-50 group-hover:translate-x-1 transition-all"></i>
                            </div>
                            <div className="text-4xl font-bold mt-1 text-gray-900">
                                {formatCurrency(activeTotals.aum)}
                            </div>
                        </div>

                        <div className="space-y-4">
                            <div 
                                onClick={() => navigate('/brokerage-details')}
                                className="bg-[#faf7eb] rounded-xl p-5 border border-orange-200 shadow-sm cursor-pointer hover:shadow-md transition-all group"
                            >
                                <div className="text-orange-700 font-bold text-lg flex items-center uppercase tracking-tighter">
                                    Brokerage <i className="fas fa-chevron-right ml-2 text-xs opacity-50 group-hover:translate-x-1 transition-all"></i>
                                </div>
                                <div className="text-3xl font-bold mt-1 text-gray-900">
                                    {formatCurrency(activeTotals.brokerage, true)}
                                </div>
                            </div>
                            
                            <div 
                                onClick={() => navigate('/clients-list')}
                                className="bg-[#faf7eb] rounded-xl p-5 border border-orange-200 shadow-sm cursor-pointer hover:shadow-md transition-all group"
                            >
                                <div className="text-orange-700 font-bold text-lg flex items-center uppercase tracking-tighter">
                                    Clients <i className="fas fa-chevron-right ml-2 text-xs opacity-50 group-hover:translate-x-1 transition-all"></i>
                                </div>
                                <div className="text-3xl font-bold mt-1 text-gray-900">
                                    {activeTotals.clients}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Bottom 4 Grid Cards */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-2">
                        {[
                            { title: 'Equity AUM', val: formatCurrency(data?.totals.equity_aum_detail || 0) },
                            { title: 'MF AUM', val: formatCurrency(data?.totals.mf_aum_detail || 0) },
                            { title: 'Active Clients', val: data?.totals.active_clients || 0, info: 'Transacted in last 12 months' },
                            { title: 'Dormant Clients', val: data?.totals.dormant_clients || 0, info: 'No transaction in last 24 months' },
                        ].map((card, i) => (
                            <div key={i} className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm flex flex-col justify-center hover:border-indigo-200 transition-colors">
                                <div className="text-gray-400 text-[10px] font-bold uppercase tracking-widest mb-1 flex items-center">
                                    {card.title} {card.info && <i className="fas fa-info-circle ml-1 text-blue-400 cursor-help" title={card.info}></i>}
                                </div>
                                <div className="text-xl font-bold text-gray-800">{card.val}</div>
                            </div>
                        ))}
                    </div>
                </>
              )}
           </div>

           {/* Right Column */}
           <div className="space-y-6">
              {/* Indices */}
              <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm grid grid-cols-2 divide-x divide-gray-100">
                 <div className="pr-4">
                   <div className="text-xs font-bold uppercase tracking-tighter">NIFTY <span className="font-normal text-gray-500 ml-1">24,050.60</span></div>
                   <div className="text-green-500 text-[10px] font-bold mt-1">275.50 (1.16%) <i className="fas fa-arrow-up"></i></div>
                 </div>
                 <div className="pl-4">
                   <div className="text-xs font-bold uppercase tracking-tighter">BANKNIFTY <span className="font-normal text-gray-500 ml-1">55,912.75</span></div>
                   <div className="text-green-500 text-[10px] font-bold mt-1">1,091.05 (1.99%) <i className="fas fa-arrow-up"></i></div>
                 </div>
              </div>

              {/* My Business Planner */}
              <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden relative group cursor-pointer hover:border-blue-200 transition-all">
                 <div className="absolute top-0 left-0 bg-blue-500 text-white text-[9px] font-bold px-3 py-1 rounded-br-lg z-10 uppercase tracking-widest">EXCLUSIVE</div>
                 <div className="p-5 pt-8 flex items-center">
                    <div className="w-12 h-12 rounded-full bg-blue-50 text-blue-500 flex items-center justify-center mr-4 relative group-hover:bg-blue-100 transition-colors">
                       <i className="fas fa-bullseye text-lg"></i>
                    </div>
                    <div>
                      <h3 className="font-bold text-gray-800 text-[15px] uppercase tracking-tight">Business Planner</h3>
                      <p className="text-[10px] text-gray-400 mt-1 uppercase font-bold tracking-widest flex items-center">
                        Track Performance <i className="fas fa-chevron-right ml-1 opacity-50 group-hover:translate-x-1 transition-all"></i>
                      </p>
                    </div>
                 </div>
              </div>

              {/* Quick Links */}
              <div>
                <div className="flex justify-between items-center mb-3">
                  <h3 className="font-bold text-lg uppercase tracking-tight text-gray-800">Quick Links</h3>
                  <button className="text-indigo-600 text-[10px] font-bold uppercase tracking-widest">Manage</button>
                </div>
                <div className="grid grid-cols-2 gap-3 font-bold text-[11px] uppercase tracking-tighter">
                   {['Risk Report', 'BOD Holding', 'InvestEdge', 'Mutual Funds', 'Portfolio'].map(link => (
                     <button key={link} className="bg-white border border-gray-200 rounded-lg p-3 text-left flex justify-between items-center hover:border-indigo-300 hover:shadow-sm transition-all text-gray-600 group">
                       {link} <i className="fas fa-external-link-alt text-gray-200 group-hover:text-indigo-400 transition-colors"></i>
                     </button>
                   ))}
                   <button className="bg-gray-50 border border-dashed border-gray-300 rounded-lg p-3 text-gray-400 flex justify-center items-center hover:bg-gray-100 transition-all">
                      <i className="fas fa-plus mr-1"></i> Add
                   </button>
                </div>
              </div>

           </div>
        </div>

      </main>

      {/* Hierarchy Search Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in transition-all">
          <div 
            ref={modalRef}
            className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col relative animate-in zoom-in-95 duration-200"
          >
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-indigo-50/30">
              <h3 className="text-lg font-bold text-indigo-900 uppercase tracking-tight">View Hierarchy</h3>
              <button 
                onClick={() => setIsModalOpen(false)}
                className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-200 text-gray-500 transition-colors"
              >
                <i className="fas fa-times"></i>
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto custom-scrollbar">
              {modalLoading ? (
                <div className="py-20 flex flex-col items-center justify-center">
                  <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-4"></div>
                  <div className="text-xs font-bold text-gray-400 uppercase tracking-widest">Loading Employees...</div>
                </div>
              ) : (
                <div className="space-y-8">
                  {/* Managers Section */}
                  <div>
                    <h4 className="text-[10px] font-bold text-orange-500 uppercase tracking-[0.2em] mb-4 border-b border-orange-100 pb-1">Managers</h4>
                    <div className="flex flex-wrap gap-2">
                      {hierarchyData?.managers.length ? hierarchyData.managers.map(name => (
                        <span key={name} className="px-3 py-1.5 bg-gray-50 text-gray-700 rounded-lg text-xs font-semibold border border-gray-100 shadow-sm">{name}</span>
                      )) : <span className="text-xs italic text-gray-400">No managers found.</span>}
                    </div>
                  </div>

                  {/* RMs Section */}
                  <div>
                    <h4 className="text-[10px] font-bold text-indigo-500 uppercase tracking-[0.2em] mb-4 border-b border-indigo-100 pb-1">Relationship Managers</h4>
                    <div className="flex flex-wrap gap-2">
                      {hierarchyData?.rms.length ? hierarchyData.rms.map(name => (
                        <span key={name} className="px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-lg text-xs font-semibold border border-indigo-100 shadow-sm">{name}</span>
                      )) : <span className="text-xs italic text-gray-400">No RMs found.</span>}
                    </div>
                  </div>

                  {/* MAs Section */}
                  <div>
                    <h4 className="text-[10px] font-bold text-green-600 uppercase tracking-[0.2em] mb-4 border-b border-green-100 pb-1">MF Advisors</h4>
                    <div className="flex flex-wrap gap-2">
                      {hierarchyData?.mas.length ? hierarchyData.mas.map(name => (
                        <span key={name} className="px-3 py-1.5 bg-green-50 text-green-700 rounded-lg text-xs font-semibold border border-green-100 shadow-sm">{name}</span>
                      )) : <span className="text-xs italic text-gray-400">No MAs found.</span>}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-gray-100 bg-gray-50 flex justify-end">
              <button 
                onClick={() => setIsModalOpen(false)}
                className="px-6 py-2 bg-white border border-gray-300 rounded-lg text-xs font-bold text-gray-600 hover:bg-gray-100 transition-all uppercase tracking-widest"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

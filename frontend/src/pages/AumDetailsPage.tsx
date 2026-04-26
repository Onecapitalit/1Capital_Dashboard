import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../auth/AuthContext";

type AumRecord = {
  code: string;
  pan: string;
  name: string;
  equity?: number;
  mf?: number;
  pms_aum?: number;
  aif_aum?: number;
  total: number;
};

type AumDetailsResponse = {
  user: {
    full_name: string;
    role: string;
  };
  totals: {
    overall: number;
    equity_total: number;
    mf_total: number;
    pms_aif_total: number;
  };
  records: {
    overall: AumRecord[];
    equity: AumRecord[];
    mf: AumRecord[];
    pms_aif: AumRecord[];
  };
  last_updated: string;
};

export function AumDetailsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { accessToken, logout } = useAuth();

  const [data, setData] = useState<AumDetailsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<"team" | "self">("team");
  const [activeCard, setActiveCard] = useState<
    "overall" | "equity" | "mf" | "pms_aif"
  >(location.state?.initialCard || "overall");
  const [searchBy, setSearchBy] = useState<"code" | "pan" | "name" | "group">(
    "code",
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  // Use a ref to track the latest request to prevent race conditions
  const abortControllerRef = useRef<AbortController | null>(null);

  // Debounce search query
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 500);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  const fetchAumDetails = useCallback(async () => {
    if (!accessToken) return;

    // Abort previous request if it exists
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoading(true);

    try {
      const params = new URLSearchParams();
      params.append("mode", viewMode);
      // Removed 'card' parameter as backend now returns all segments
      params.append("q", debouncedQuery);
      params.append("search_by", searchBy);

      const response = await axios.get<AumDetailsResponse>(
        `/api/dashboard/aum-details/?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${accessToken}` },
          signal: abortControllerRef.current.signal,
        },
      );
      setData(response.data);
    } catch (error: any) {
      if (axios.isCancel(error)) {
        return; // Ignore aborted requests
      }
      if (error?.response?.status === 401) {
        logout();
        navigate("/login", { replace: true });
      }
      console.error("Error fetching AUM details:", error);
    } finally {
      setLoading(false);
    }
  }, [accessToken, viewMode, debouncedQuery, searchBy, logout, navigate]);

  useEffect(() => {
    fetchAumDetails();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchAumDetails]);

  const formatCurrency = (val: number) => {
    if (val >= 10000000)
      return (val / 10000000).toFixed(3).replace(/\.?0+$/, "") + " Cr";
    if (val >= 100000)
      return (val / 100000).toFixed(3).replace(/\.?0+$/, "") + " L";
    if (val >= 1000)
      return (val / 1000).toFixed(3).replace(/\.?0+$/, "") + " K";
    return val.toFixed(2);
  };

  const calculatePct = (val: number) => {
    if (!data || data.totals.overall === 0) return "0.00 %";
    return "100 %";
  };

  const handleCardChange = (card: "overall" | "equity" | "mf" | "pms_aif") => {
    if (card === activeCard) return;
    // Removed setData(null) to enable instant switching
    setActiveCard(card);
  };

  const activeRecords = data?.records?.[activeCard] || [];

  return (
    <div className="min-h-screen bg-[#f4f6fa] font-sans text-[#1c1c1c]">
      {/* Top Navbar */}
      <nav className="bg-[#2c2759] text-white flex items-center justify-between px-30 py-3 shadow-md">
        <div className="flex items-center space-x-6">
          <div
            className="font-bold text-xl tracking-wider text-yellow-500 cursor-pointer"
            onClick={() => navigate("/website")}
          >
            One <span className="text-sm font-normal text-white">CAPITAL</span>
          </div>
          <div className="hidden md:flex space-x-1">
            <button
              onClick={() => navigate("/new-dashboard")}
              className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm font-medium font-nunito"
            >
              Dashboard
            </button>
            <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm font-nunito text-gray-300">
              MIS
            </button>
            {/* <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Markets</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Invest</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">Trades</button>
             <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">More</button> */}
          </div>
        </div>
        <div className="flex items-center space-x-4">
          <div className="text-xs text-gray-300">
            Data updated: {data?.last_updated || "Loading..."}
          </div>
          <div
            className="flex items-center bg-gray-800 rounded px-3 py-1 cursor-pointer"
            onClick={() => {
              logout();
              navigate("/login");
            }}
          >
            <div className="w-6 h-6 bg-gray-500 rounded-full flex items-center justify-center mr-2">
              <i className="fas fa-user text-xs"></i>
            </div>
            <div>
              <div className="text-xs font-bold uppercase">
                {data?.user?.full_name || "Loading..."}
              </div>
              <div className="text-[10px] text-gray-400">
                {data?.user?.role === "L"
                  ? "Leader"
                  : data?.user?.role === "M"
                    ? "Manager"
                    : "RM"}
              </div>
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
            <button
              onClick={() => navigate("/new-dashboard")}
              className="text-gray-500 hover:text-gray-800 transition-colors"
            >
              <i className="fas fa-arrow-left text-xl"></i>
            </button>
            <h1 className="text-2xl font-semibold uppercase font-nunito tracking-tight text-gray-800">
              Assets Under Management
            </h1>
          </div>
          <div className="bg-white rounded-full p-1 border border-gray-200 shadow-sm flex items-center">
            <button
              onClick={() => setViewMode("team")}
              className={`px-4 py-1.5 rounded-full text-sm font-nunito font-medium transition-all ${viewMode === "team" ? "bg-gray-500 text-white shadow-sm" : "text-gray-600 hover:bg-gray-100"}`}
            >
              <i className="fas fa-users mr-2"></i> Team
            </button>
            <button
              onClick={() => setViewMode("self")}
              className={`px-4 py-1.5 rounded-full text-sm font-nunito font-medium transition-all ${viewMode === "self" ? "bg-gray-500 text-white shadow-sm" : "text-gray-600 hover:bg-gray-100"}`}
            >
              <i className="fas fa-user mr-2"></i> Self
            </button>
          </div>
        </div>

        {/* Tab Cards */}
        <div className="flex flex-wrap gap-4 mb-8 font-nunito">
          {[
            {
              id: "overall",
              title: "Overall AUM",
              val: formatCurrency(data?.totals?.overall || 0),
              pct: "100%",
              active: activeCard === "overall",
            },
            {
              id: "equity",
              title: "Equity",
              val: formatCurrency(data?.totals?.equity_total || 0),
              pct: "",
              active: activeCard === "equity",
            },
            {
              id: "mf",
              title: "Mutual Fund",
              val: formatCurrency(data?.totals?.mf_total || 0),
              pct: "",
              active: activeCard === "mf",
            },
            {
              id: "pms_aif",
              title: "PMS/AIF",
              val: formatCurrency(data?.totals?.pms_aif_total || 0),
              pct: "",
              active: activeCard === "pms_aif",
            },
          ].map((card) => (
            <div
              key={card.id}
              onClick={() => handleCardChange(card.id as any)}
              className={`relative flex-1 min-w-[180px] bg-white rounded-xl p-5 border transition-all ${card.active ? "border-indigo-500 shadow-md ring-1 ring-indigo-500/20 text-indigo-700" : "border-gray-200 hover:shadow-sm text-gray-500 cursor-pointer"}`}
            >
              <div
                className={`text-xs mb-2 font-bold uppercase tracking-wider ${card.active ? "text-indigo-500" : "text-gray-400"}`}
              >
                {card.title}
              </div>
              <div
                className={`text-2xl font-bold ${card.active ? "text-gray-900" : "text-gray-800"}`}
              >
                ₹ {card.val}
              </div>
              {card.pct && (
                <div className="text-xs text-gray-400 mt-1 font-medium">
                  ({card.pct})
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Search & Filters */}
        <div className="bg-white rounded-xl px-4 py-3 border border-gray-200 shadow-sm flex items-center flex-wrap gap-4 mb-4">
          <div className="text-xs text-gray-400 font-nunito font-bold uppercase tracking-widest">
            Search by
          </div>
          <div className="flex border border-gray-200 rounded overflow-hidden text-sm font-bold">
            <button
              onClick={() => setSearchBy("code")}
              className={`px-3 py-1.5 font-nunito border-r border-gray-200 transition-all ${searchBy === "code" ? "text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30" : "text-gray-500 hover:bg-gray-50"}`}
            >
              Code
            </button>
            <button
              onClick={() => setSearchBy("pan")}
              className={`px-3 py-1.5 font-nunito border-r border-gray-200 transition-all ${searchBy === "pan" ? "text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30" : "text-gray-500 hover:bg-gray-50"}`}
            >
              PAN
            </button>
            <button
              onClick={() => setSearchBy("name")}
              className={`px-3 py-1.5 font-nunito border-r border-gray-200 transition-all ${searchBy === "name" ? "text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30" : "text-gray-500 hover:bg-gray-50"}`}
            >
              Name
            </button>
            {/* <button
              onClick={() => setSearchBy("group")}
              className={`px-3 py-1.5 font-nunito transition-all ${searchBy === "group" ? "text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30" : "text-gray-500 hover:bg-gray-50"}`}
            >
              Group Code
            </button> */}
          </div>
          <div className="flex-1 min-w-[200px] border-b border-gray-300 flex items-center px-4 font-nunito">
            <input
              type="text"
              placeholder={`Search by ${searchBy.toUpperCase()}...`}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full py-1.5 outline-none text-sm text-center text-gray-700 bg-transparent font-nunito font-medium"
            />
          </div>
          <button
            onClick={() => {
              setSearchQuery("");
              setDebouncedQuery("");
            }}
            className="text-xs font-nunito font-bold border rounded-[3px] border-gray-400 px-2 py-[7px] text-indigo-600 hover:text-orange-600 uppercase transition-colors"
          >
            Clear
          </button>
        </div>

        {/* Data Table */}
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden border-l-4 border-l-indigo-700 relative min-h-[400px]">
          {loading && (
            <div className="absolute inset-0 bg-white/50 backdrop-blur-[1px] flex items-center justify-center z-10">
              <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left whitespace-nowrap">
              <thead className="text-[14px] text-gray-400 bg-gray-50/80 border-b border-gray-200 tracking-widest font-bold">
                <tr>
                  <th className="px-6 font-nunito py-4">Client Code</th>
                  <th className="px-6 font-nunito py-4">Client PAN</th>
                  <th className="px-6 font-nunito py-4">Client Name</th>
                  {activeCard === "overall" && (
                    <>
                      <th className="px-6 py-4 font-nunito text-right">
                        Equity AUM (₹)
                      </th>
                      <th className="px-6 py-4 font-nunito text-right">
                        MF AUM (₹)
                      </th>
                      <th className="px-6 py-4 font-nunito text-right">
                        PMS AUM (₹)
                      </th>
                      <th className="px-6 py-4 font-nunito text-right">
                        AIF AUM (₹)
                      </th>
                    </>
                  )}
                  {activeCard === "pms_aif" && (
                    <>
                      <th className="px-6 py-4 font-nunito text-right">
                        PMS AUM (₹)
                      </th>
                      <th className="px-6 py-4 font-nunito text-right">
                        AIF AUM (₹)
                      </th>
                    </>
                  )}
                  <th className="px-6 py-4 text-right">
                    <div className="flex flex-col items-end">
                      <span className="flex font-nunito items-center cursor-pointer">
                        Total AUM (₹){" "}
                        <i className="fas fa-sort text-gray-300 ml-1"></i>
                      </span>
                      <span className="text-sm font-nunito font-bold text-indigo-700 tracking-wide mt-1">
                        {formatCurrency(
                          activeCard === "overall"
                            ? data?.totals?.overall || 0
                            : activeCard === "equity"
                              ? data?.totals?.equity_total || 0
                              : activeCard === "mf"
                                ? data?.totals?.mf_total || 0
                                : data?.totals?.pms_aif_total || 0,
                        )}
                      </span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 font-medium">
                {activeRecords.length > 0 ? (
                  activeRecords.map((row, i) => (
                    <tr
                      key={row.code + i}
                      className={`hover:bg-gray-50 transition-colors ${i % 2 === 0 ? "bg-white" : "bg-gray-50/50"}`}
                    >
                      <td className="px-6 py-4 font-nunito  text-gray-600">
                        {row.code}
                      </td>
                      <td className="px-6 py-4 font-nunito text-gray-500  text-xs">
                        {row.pan}
                      </td>
                      <td className="px-6 py-4 font-nunito font-bold text-gray-800 uppercase tracking-tight">
                        {row.name}
                      </td>
                      {activeCard === "overall" && (
                        <>
                          <td className="px-6 py-4 font-nunito text-right text-gray-600">
                            ₹ {formatCurrency(row.equity || 0)}
                          </td>
                          <td className="px-6 py-4 font-nunito text-right text-gray-600">
                            ₹ {formatCurrency(row.mf || 0)}
                          </td>
                          <td className="px-6 py-4 font-nunito text-right text-gray-600">
                            ₹ {formatCurrency(row.pms_aum || 0)}
                          </td>
                          <td className="px-6 py-4 font-nunito text-right text-gray-600">
                            ₹ {formatCurrency(row.aif_aum || 0)}
                          </td>
                        </>
                      )}
                      {activeCard === "pms_aif" && (
                        <>
                          <td className="px-6 py-4 font-nunito text-right text-gray-600">
                            ₹ {formatCurrency(row.pms_aum || 0)}
                          </td>
                          <td className="px-6 py-4 font-nunito text-right text-gray-600">
                            ₹ {formatCurrency(row.aif_aum || 0)}
                          </td>
                        </>
                      )}
                      <td className="px-6 py-4 font-nunito text-right text-indigo-700 font-bold">
                        ₹ {formatCurrency(row.total)}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td
                      colSpan={
                        activeCard === "overall"
                          ? 8
                          : activeCard === "pms_aif"
                            ? 6
                            : 4
                      }
                      className="px-6 py-12 text-center text-gray-400 italic"
                    >
                      {loading
                        ? "Fetching AUM records..."
                        : "No data found matching your criteria."}
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

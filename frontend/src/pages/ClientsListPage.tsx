import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../auth/AuthContext";

type ClientRecord = {
  code: string;
  pan: string;
  name: string;
  group: string;
  aum: number;
  city: string;
  source?: string;
};

type ClientListResponse = {
  user: {
    full_name: string;
    role: string;
  };
  count: number;
  cities: string[];
  records: ClientRecord[];
  last_updated: string;
};

export function ClientsListPage() {
  const navigate = useNavigate();
  const { accessToken, logout } = useAuth();

  const [data, setData] = useState<ClientListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<"team" | "self">("team");
  const [searchBy, setSearchBy] = useState<"code" | "pan" | "name" | "group">(
    "code",
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedCity, setSelectedCity] = useState("");

  // 1. Debounce the search query
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 500); // 500ms debounce for typing
    return () => clearTimeout(handler);
  }, [searchQuery]);

  // 2. Fetch data when debounced query or other filters change
  const fetchClients = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append("mode", viewMode);
      params.append("q", debouncedQuery);
      params.append("search_by", searchBy);
      if (selectedCity) params.append("city", selectedCity);

      const response = await axios.get<ClientListResponse>(
        `/api/dashboard/clients-list/?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${accessToken}` },
        },
      );
      setData(response.data);
    } catch (error: any) {
      if (error?.response?.status === 401) {
        logout();
        navigate("/login", { replace: true });
      }
      console.error("Error fetching clients:", error);
    } finally {
      setLoading(false);
    }
  }, [
    accessToken,
    viewMode,
    debouncedQuery,
    searchBy,
    selectedCity,
    logout,
    navigate,
  ]);

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  const clearFilters = () => {
    setSearchQuery("");
    setDebouncedQuery("");
    setSelectedCity("");
    // keep searchBy and viewMode as is
  };

  const formatCurrency = (val: number) => {
    if (val >= 10000000)
      return (val / 10000000).toFixed(3).replace(/\.?0+$/, "") + " Cr";
    if (val >= 100000)
      return (val / 100000).toFixed(3).replace(/\.?0+$/, "") + " L";
    if (val >= 1000)
      return (val / 1000).toFixed(3).replace(/\.?0+$/, "") + " K";
    return val.toFixed(2);
  };

  return (
    <div className="min-h-screen bg-[#f4f6fa] font-sans text-[#1c1c1c]">
      {/* Top Navbar */}
      <nav className="bg-[#2c2759] text-white flex items-center justify-between px-6 py-3 shadow-md">
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
            <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300 font-nunito">
              MIS
            </button>
            {/* <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">
              Markets
            </button>
            <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">
              Invest
            </button>
            <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">
              Trades
            </button>
            <button className="px-4 py-2 hover:bg-indigo-700/30 rounded text-sm text-gray-300">
              More
            </button> */}
          </div>
        </div>
        <div className="flex items-center space-x-4">
          <div className="text-xs text-gray-300">
            Data last updated on : {data?.last_updated || "Loading..."}
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
                {data?.user.full_name || "Loading..."}
              </div>
              <div className="text-[10px] text-gray-400">
                {data?.user.role === "L"
                  ? "Leader"
                  : data?.user.role === "M"
                    ? "Manager"
                    : "Relationship Manager"}
              </div>
            </div>
            <i className="fas fa-sign-out-alt ml-2 text-xs"></i>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => navigate("/new-dashboard")}
              className="text-gray-500 hover:text-gray-800"
            >
              <i className="fas fa-arrow-left text-xl"></i>
            </button>
            <h1 className="text-2xl font-semibold font-nunito">CLIENTS</h1>
          </div>
          <div className="bg-white rounded-full p-1 border border-gray-200 shadow-sm flex items-center">
            <button
              onClick={() => setViewMode("team")}
              className={`px-4 py-1.5 rounded-full text-sm font-medium flex items-center transition-all ${viewMode === "team" ? "bg-gray-500 text-white shadow-sm" : "text-gray-600 hover:bg-gray-100"}`}
            >
              <i className="fas fa-users mr-2 font-nunito"></i> Team
            </button>
            <button
              onClick={() => setViewMode("self")}
              className={`px-4 py-1.5 rounded-full text-sm font-medium flex items-center transition-all ${viewMode === "self" ? "bg-gray-500 text-white shadow-sm" : "text-gray-600 hover:bg-gray-100"}`}
            >
              <i className="fas fa-user mr-2 font-nunito"></i> Self
            </button>
          </div>
        </div>

        <div className="flex justify-center mb-6">
          <div className="w-full max-w-sm bg-white rounded-xl py-6 border border-indigo-500 shadow-sm text-indigo-700 flex flex-col justify-center items-center text-center cursor-pointer transition-all">
            <div className="text-sm mb-2 font-medium text-indigo-500 font-nunito">
              All Clients
            </div>
            <div className="text-3xl font-bold text-gray-800 font-nunito">
              {data?.count || 0}
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl px-4 py-3 border border-gray-200 shadow-sm flex items-center flex-wrap gap-4 mb-6">
          <div className="text-sm text-gray-500 font-medium font-nunito">
            SEARCH BY
          </div>
          <div className="flex border border-gray-200 rounded overflow-hidden text-sm font-nunito">
            <button
              onClick={() => setSearchBy("code")}
              className={`px-3 py-1.5 font-nunito border-r border-gray-200 font-medium transition-all ${searchBy === "code" ? "text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30" : "text-gray-500 hover:bg-gray-50"}`}
            >
              Code
            </button>
            <button
              onClick={() => setSearchBy("pan")}
              className={`px-3 py-1.5 font-nunito border-r border-gray-200 font-medium transition-all ${searchBy === "pan" ? "text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30" : "text-gray-500 hover:bg-gray-50"}`}
            >
              PAN
            </button>
            <button
              onClick={() => setSearchBy("name")}
              className={`px-3 py-1.5 font-nunito border-r border-gray-200 font-medium transition-all ${searchBy === "name" ? "text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30" : "text-gray-500 hover:bg-gray-50"}`}
            >
              Name
            </button>
            <button
              onClick={() => setSearchBy("group")}
              className={`px-3 py-1.5 font-nunito border-r border-gray-200 font-medium transition-all ${searchBy === "group" ? "text-orange-500 border-b-2 border-b-orange-500 bg-orange-50/30" : "text-gray-500 hover:bg-gray-50"}`}
            >
              Group Code
            </button>
          </div>

          <div className="flex-1 min-w-[150px] border-b border-gray-300 flex items-center pr-4">
            <input
              type="text"
              placeholder={`Type Client ${searchBy === "code" ? "Code" : searchBy === "pan" ? "PAN" : searchBy === "name" ? "Name" : "Group Code"}`}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full py-1.5 outline-none text-sm text-center text-gray-700 bg-transparent"
            />
          </div>

          <div className="flex items-center space-x-3">
            <div className="text-sm text-gray-500 font-medium font-nunito">
              City
            </div>
            <select
              value={selectedCity}
              onChange={(e) => setSelectedCity(e.target.value)}
              className="border-b border-gray-300 py-1.5 text-sm outline-none bg-transparent min-w-[120px] cursor-pointer font-nunito"
            >
              <option value="">All Cities</option>
              {data?.cities.map((city) => (
                <option key={city} value={city}>
                  {city}
                </option>
              ))}
            </select>

            <button
              onClick={clearFilters}
              className="text-xs font-semibold border rounded-[3px] border-gray-400 px-2 py-[7px] text-indigo-600 hover:text-orange-600  font-nunito transition-colors uppercase tracking-tight"
            >
              Clear
            </button>
          </div>
        </div>

        {/* Data Table */}
        <div className="bg-[#fcfdfd] rounded-lg border border-gray-200 shadow-sm overflow-hidden border-l-4 border-l-indigo-700 relative">
          {loading && (
            <div className="absolute inset-0 bg-white/50 backdrop-blur-[1px] flex items-center justify-center z-10">
              <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
          )}
          <div className="overflow-x-auto font-nunito">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-500 bg-gray-100/80 border-b border-gray-200 font-nunito">
                <tr>
                  <th className="px-6 py-4 font-medium whitespace-nowrap">
                    CLIENT CODE
                  </th>
                  <th className="px-6 py-4 font-medium whitespace-nowrap">
                    CLIENT PAN
                  </th>
                  <th className="px-6 py-4 font-medium whitespace-nowrap">
                    CLIENT NAME
                  </th>
                  <th className="px-6 py-4 font-medium whitespace-nowrap">
                    GROUP CODE
                  </th>
                  <th className="px-6 py-4 font-medium whitespace-nowrap text-gray-800">
                    TOTAL AUM (₹)
                  </th>
                  <th className="px-6 py-4 font-medium whitespace-nowrap">
                    CITY
                  </th>
                  <th className="px-6 py-4 font-medium whitespace-nowrap">
                    SOURCE
                  </th>
                  <th className="px-6 py-4"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 font-nunito">
                {data?.records && data.records.length > 0 ? (
                  data.records.map((row, i) => (
                    <tr
                      key={i}
                      className="hover:bg-gray-50 transition-colors h-20"
                    >
                      <td className="px-6 py-4 text-gray-700">{row.code}</td>
                      <td className="px-6 py-4 text-gray-700">{row.pan}</td>
                      <td className="px-6 py-4 max-w-[200px]">
                        <div className="text-blue-500 font-medium text-xs hover:underline cursor-pointer uppercase leading-tight line-clamp-2">
                          {row.name}
                        </div>
                      </td>
                      <td className="px-6 py-4 font-medium text-gray-700">
                        {row.group}
                      </td>
                      <td className="px-6 py-4 font-medium text-gray-800">
                        ₹ {formatCurrency(row.aum)}
                      </td>
                      <td className="px-6 py-4 text-gray-600">{row.city}</td>
                      <td className="px-6 py-4 text-xs font-bold">
                        <span
                          className={`px-2 py-1 rounded-full ${
                            row.source === "WealthMagic"
                              ? "bg-purple-100 text-purple-700"
                              : row.source === "PMS/AIF"
                                ? "bg-orange-100 text-orange-700"
                                : "bg-blue-100 text-blue-700"
                          }`}
                        >
                          {row.source || "Equity/MF"}
                        </span>
                      </td>
                      <td className="px-6 py-4"></td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-6 py-12 text-center text-gray-400 italic"
                    >
                      {loading
                        ? "Fetching clients..."
                        : "No clients found matching your criteria."}
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

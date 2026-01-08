import { useState, useEffect, useRef, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useSignals, useSectors, useHealth } from '../hooks/useSignals';
import { useWebSocket, ConnectionStatus } from '../hooks/useWebSocket';
import SignalCard from './SignalCard';
import StockChart from './StockChart';
import RiskCalculator from './RiskCalculator';
import { signalApi } from '../api/client';

// Top NIFTY stocks for ticker
const TICKER_STOCKS = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'BHARTIARTL', 'ITC', 'SBIN'];

export default function Dashboard() {
    const [activeTab, setActiveTab] = useState('swing');
    const [selectedSymbol, setSelectedSymbol] = useState(null);
    const [selectedSignal, setSelectedSignal] = useState(null);
    const [sectorFilter, setSectorFilter] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [showCalculator, setShowCalculator] = useState(false);
    const [allStocks, setAllStocks] = useState([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [riskSnapshot, setRiskSnapshot] = useState(null);
    const searchRef = useRef(null);

    // WebSocket for real-time ticker prices
    const { prices: wsPrices, connected, reconnecting } = useWebSocket(TICKER_STOCKS);

    // Convert WebSocket prices to ticker format
    const tickerPrices = useMemo(() => {
        return TICKER_STOCKS.map(symbol => {
            const wsData = wsPrices[symbol];
            if (wsData) {
                return {
                    symbol,
                    ltp: wsData.ltp || 0,
                    changePct: wsData.changePct || 0,
                };
            }
            return { symbol, ltp: 0, changePct: 0 };
        }).filter(s => s.ltp > 0);
    }, [wsPrices]);

    const { signals, loading, error, lastUpdated, refetch } = useSignals(
        activeTab === 'intraday' ? 'intraday_bias' : 'swing',
        20,
        sectorFilter || null
    );
    const { sectors } = useSectors();
    const { health } = useHealth();

    // Fetch stocks for autocomplete
    useEffect(() => {
        const fetchStocks = async () => {
            try {
                const response = await signalApi.getStocks();
                setAllStocks(response.data || []);
            } catch (err) {
                console.error('Failed to fetch stocks:', err);
            }
        };
        fetchStocks();
    }, []);

    // Fetch risk snapshot
    useEffect(() => {
        const fetchRiskSnapshot = async () => {
            try {
                const response = await signalApi.getRiskSnapshot();
                setRiskSnapshot(response.data);
            } catch (err) {
                console.error('Failed to fetch risk snapshot:', err);
            }
        };
        fetchRiskSnapshot();
    }, []);

    // Close suggestions on outside click
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (searchRef.current && !searchRef.current.contains(e.target)) {
                setShowSuggestions(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const tabs = [
        { id: 'swing', label: '📈 Swing Trades' },
        { id: 'intraday', label: '⚡ Intraday Bias (15m EOD)' },
    ];

    const filteredSignals = signals.filter((s) =>
        s.symbol.toLowerCase().includes(searchQuery.toLowerCase())
    );

    // Aliases for search
    const stockAliases = {
        'ril': 'reliance', 'jio': 'jiofin', 'jio finance': 'jiofin',
        'sbi': 'sbin', 'hdfc': 'hdfcbank', 'icici': 'icicibank',
        'infosys': 'infy', 'airtel': 'bhartiartl', 'hul': 'hindunilvr',
    };

    const normalizeSearch = (query) => stockAliases[query.toLowerCase()] || query.toLowerCase();

    const suggestions = searchQuery.length >= 1
        ? allStocks
            .filter(s => {
                const query = normalizeSearch(searchQuery);
                return s.symbol.toLowerCase().includes(query) ||
                    s.name.toLowerCase().includes(query);
            })
            .slice(0, 8)
        : [];

    const handleViewChart = (symbol) => {
        const signal = signals.find((s) => s.symbol === symbol);
        setSelectedSymbol(symbol);
        setSelectedSignal(signal);
    };

    const handleSelectSuggestion = (stock) => {
        setSearchQuery(stock.symbol);
        setShowSuggestions(false);
        const signal = signals.find(s => s.symbol === stock.symbol);
        if (signal) {
            setSelectedSymbol(stock.symbol);
            setSelectedSignal(signal);
        }
    };

    const navigate = useNavigate();

    const handleTakeTrade = async (signal) => {
        // Add trade via API
        try {
            const entryPrice = (signal.entry.low + signal.entry.high) / 2;
            const response = await fetch('http://localhost:8000/api/trades', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbol: signal.symbol,
                    entryDate: new Date().toISOString().split('T')[0],
                    entryPrice: entryPrice,
                    quantity: 1, // Default, user can edit in Portfolio
                    stopLoss: signal.stopLoss,
                    target: signal.targets[0],
                    notes: `From ${signal.type} signal (Score: ${signal.score})`,
                }),
            });
            if (response.ok) {
                alert(`Trade added: ${signal.symbol}`);
                navigate('/portfolio');
            }
        } catch (err) {
            console.error('Failed to add trade:', err);
            alert('Failed to add trade');
        }
    };

    const clearSearch = () => {
        setSearchQuery('');
        setShowSuggestions(false);
    };

    // Calculate summary stats
    const avgScore = signals.length > 0
        ? Math.round(signals.reduce((acc, s) => acc + s.score, 0) / signals.length)
        : 0;
    const avgRR = signals.length > 0
        ? (signals.reduce((acc, s) => acc + parseFloat(s.riskReward?.split(':')[1] || 0), 0) / signals.length).toFixed(1)
        : '0';

    // Market regime from health
    const niftyTrend = health?.niftyTrend || 'neutral';

    const formatLastUpdated = () => {
        if (!lastUpdated) return null;
        const time = lastUpdated.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
        const isMarketHours = new Date().getHours() >= 9 && new Date().getHours() < 16;
        return { time, context: isMarketHours ? 'Live' : 'EOD' };
    };

    const lastUpdatedInfo = formatLastUpdated();

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            {/* Live Price Ticker */}
            <div className="bg-gray-900 dark:bg-gray-950 text-white py-1.5 overflow-hidden">
                <div className="flex items-center">
                    <div className="px-3 flex items-center gap-2 border-r border-gray-700">
                        <ConnectionStatus connected={connected} reconnecting={reconnecting} />
                    </div>
                    <div className="flex-1 overflow-hidden">
                        {tickerPrices.length > 0 ? (
                            <div className="animate-marquee flex gap-8 whitespace-nowrap px-4">
                                {tickerPrices.concat(tickerPrices).map((stock, i) => (
                                    <span key={i} className="inline-flex items-center gap-1 text-sm">
                                        <span className="font-medium">{stock.symbol}</span>
                                        <span className="text-gray-400">₹{stock.ltp}</span>
                                        <span className={stock.changePct >= 0 ? 'text-green-400' : 'text-red-400'}>
                                            {stock.changePct >= 0 ? '▲' : '▼'} {Math.abs(stock.changePct).toFixed(1)}%
                                        </span>
                                    </span>
                                ))}
                            </div>
                        ) : (
                            <div className="text-gray-500 text-sm px-4">
                                {connected ? 'Waiting for prices...' : 'Connecting...'}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Header */}
            <header className="bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700">
                <div className="max-w-7xl mx-auto px-4 py-3">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-xl font-bold text-gray-900 dark:text-white">TradeEdge Pro</h1>
                            <p className="text-xs text-gray-500 dark:text-gray-400">NSE Signals • Educational Only</p>
                        </div>
                        <div className="flex items-center gap-3">
                            <div className={`px-2 py-1 rounded text-xs font-medium ${niftyTrend === 'bullish' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                                niftyTrend === 'bearish' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                    'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                                }`}>
                                NIFTY {niftyTrend.toUpperCase()}
                            </div>
                            <Link to="/portfolio" className="btn-secondary text-sm">
                                📊 Portfolio
                            </Link>
                            <button onClick={() => setShowCalculator(!showCalculator)} className="btn-secondary text-sm">
                                🧮
                            </button>
                            <button onClick={refetch} className="btn-primary text-sm">Refresh</button>
                        </div>
                    </div>
                </div>
            </header>

            {/* Summary Stat Cards */}
            <div className="max-w-7xl mx-auto px-4 py-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow-sm border border-gray-200 dark:border-gray-700">
                        <div className="text-2xl font-bold text-gray-900 dark:text-white">{signals.length}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">Signals Today</div>
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow-sm border border-gray-200 dark:border-gray-700">
                        <div className={`text-2xl font-bold ${avgScore >= 80 ? 'text-green-600' : avgScore >= 70 ? 'text-yellow-600' : 'text-gray-600'}`}>
                            {avgScore}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">Avg Score</div>
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow-sm border border-gray-200 dark:border-gray-700">
                        <div className="text-2xl font-bold text-blue-600">1:{avgRR}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">Avg R:R</div>
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow-sm border border-gray-200 dark:border-gray-700">
                        <div className="text-2xl font-bold text-gray-900 dark:text-white">{health?.stockCount || 100}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">Stocks Scanned</div>
                    </div>
                </div>

                {/* Tabs */}
                <div className="flex items-center gap-4 mb-4 border-b border-gray-200 dark:border-gray-700">
                    {tabs.map((tab) => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`tab ${activeTab === tab.id ? 'tab-active' : ''}`}
                        >
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* Filters */}
                <div className="flex flex-wrap gap-3 mb-4">
                    <div className="relative" ref={searchRef}>
                        <div className="relative">
                            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
                            <input
                                type="text"
                                placeholder="Search..."
                                value={searchQuery}
                                onChange={(e) => { setSearchQuery(e.target.value); setShowSuggestions(true); }}
                                onFocus={() => setShowSuggestions(true)}
                                className="input pl-9 pr-8 w-56"
                            />
                            {searchQuery && (
                                <button onClick={clearSearch} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">✕</button>
                            )}
                        </div>
                        {showSuggestions && suggestions.length > 0 && (
                            <div className="absolute z-50 mt-1 w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 max-h-48 overflow-y-auto">
                                {suggestions.map((stock) => (
                                    <button
                                        key={stock.symbol}
                                        onClick={() => handleSelectSuggestion(stock)}
                                        className="w-full px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700 text-sm"
                                    >
                                        <span className="font-medium text-gray-900 dark:text-white">{stock.symbol}</span>
                                        <span className="text-gray-500 ml-2">{stock.name?.slice(0, 20)}</span>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    <select value={sectorFilter} onChange={(e) => setSectorFilter(e.target.value)} className="input max-w-[180px]">
                        <option value="">All Sectors</option>
                        {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                    {lastUpdatedInfo && (
                        <span className="text-xs text-gray-500 dark:text-gray-400 self-center">
                            {lastUpdatedInfo.time} ({lastUpdatedInfo.context})
                        </span>
                    )}
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Signals */}
                    <div className="lg:col-span-2">
                        {loading && (
                            <div className="flex justify-center py-12">
                                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600"></div>
                            </div>
                        )}
                        {error && <div className="card p-6 text-center text-red-600">{error}</div>}
                        {!loading && !error && filteredSignals.length === 0 && (
                            <div className="card p-8 text-center">
                                <div className="text-3xl mb-3">🛡️</div>
                                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                                    {searchQuery ? `No signals for "${searchQuery}"` : 'No Qualifying Signals'}
                                </h3>
                                <p className="text-sm text-gray-600 dark:text-gray-400">
                                    Strict filters are protecting your capital.
                                </p>
                                {searchQuery && <button onClick={clearSearch} className="btn-primary mt-3">Clear Search</button>}
                            </div>
                        )}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {filteredSignals.map((signal) => (
                                <SignalCard key={signal.symbol} signal={signal} onViewChart={handleViewChart} onTakeTrade={handleTakeTrade} />
                            ))}
                        </div>
                    </div>

                    {/* Sidebar */}
                    <div className="space-y-4">
                        {riskSnapshot && (
                            <div className="card p-3">
                                <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">Risk Exposure</h3>
                                <div className="grid grid-cols-2 gap-2 text-sm">
                                    <div><span className="text-gray-500">Open</span> <span className="font-medium">{riskSnapshot.openTrades}/{riskSnapshot.maxTrades}</span></div>
                                    <div><span className="text-gray-500">Daily</span> <span className="font-medium">{riskSnapshot.riskUsedToday}%</span></div>
                                </div>
                            </div>
                        )}
                        {selectedSymbol ? (
                            <StockChart symbol={selectedSymbol} signal={selectedSignal} />
                        ) : (
                            <div className="card p-4 text-center text-gray-500 dark:text-gray-400">
                                <div className="text-2xl mb-2">📊</div>
                                <p className="text-sm">Select a signal to view chart</p>
                            </div>
                        )}
                        {showCalculator && <RiskCalculator />}
                    </div>
                </div>
            </div>

            {/* Disclaimer */}
            <div className="fixed bottom-0 left-0 right-0 bg-yellow-50 dark:bg-yellow-900/30 border-t border-yellow-200 dark:border-yellow-800 py-1 px-4 text-center text-xs text-yellow-800 dark:text-yellow-200">
                ⚠️ Educational purposes only – Not investment advice
            </div>
        </div>
    );
}

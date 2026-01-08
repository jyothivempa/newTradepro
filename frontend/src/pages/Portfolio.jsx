import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

const API_BASE = 'http://localhost:8000/api';

export default function Portfolio() {
    const [stats, setStats] = useState(null);
    const [trades, setTrades] = useState([]);
    const [filter, setFilter] = useState('ALL'); // ALL, OPEN, CLOSED
    const [loading, setLoading] = useState(true);
    const [showAddForm, setShowAddForm] = useState(false);
    const [closeModal, setCloseModal] = useState(null);
    const [exitPrice, setExitPrice] = useState('');

    // Form state for new trade
    const [newTrade, setNewTrade] = useState({
        symbol: '',
        entryDate: new Date().toISOString().split('T')[0],
        entryPrice: '',
        quantity: '',
        stopLoss: '',
        target: '',
        notes: '',
    });

    const fetchData = async () => {
        setLoading(true);
        try {
            const [statsRes, tradesRes] = await Promise.all([
                fetch(`${API_BASE}/portfolio/stats`),
                fetch(`${API_BASE}/trades${filter !== 'ALL' ? `?status=${filter}` : ''}`),
            ]);

            const statsData = await statsRes.json();
            const tradesData = await tradesRes.json();

            setStats(statsData);
            setTrades(tradesData.trades || []);
        } catch (err) {
            console.error('Failed to fetch portfolio:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [filter]);

    const handleAddTrade = async (e) => {
        e.preventDefault();
        try {
            const res = await fetch(`${API_BASE}/trades`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newTrade),
            });

            if (res.ok) {
                setShowAddForm(false);
                setNewTrade({
                    symbol: '',
                    entryDate: new Date().toISOString().split('T')[0],
                    entryPrice: '',
                    quantity: '',
                    stopLoss: '',
                    target: '',
                    notes: '',
                });
                fetchData();
            }
        } catch (err) {
            console.error('Failed to add trade:', err);
        }
    };

    const handleCloseTrade = async (tradeId) => {
        if (!exitPrice) return;

        try {
            const res = await fetch(`${API_BASE}/trades/${tradeId}/close`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ exitPrice: parseFloat(exitPrice) }),
            });

            if (res.ok) {
                setCloseModal(null);
                setExitPrice('');
                fetchData();
            }
        } catch (err) {
            console.error('Failed to close trade:', err);
        }
    };

    const handleDeleteTrade = async (tradeId) => {
        if (!confirm('Are you sure you want to delete this trade?')) return;

        try {
            await fetch(`${API_BASE}/trades/${tradeId}`, { method: 'DELETE' });
            fetchData();
        } catch (err) {
            console.error('Failed to delete trade:', err);
        }
    };

    if (loading && !stats) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            </div>
        );
    }

    return (
        <div className="container mx-auto px-4 py-8">
            {/* Header */}
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">📊 Portfolio</h1>
                    <p className="text-gray-500 dark:text-gray-400 mt-1">Track your trades and performance</p>
                </div>
                <div className="flex gap-3">
                    <Link to="/" className="btn-secondary">
                        ← Dashboard
                    </Link>
                    <button onClick={() => setShowAddForm(true)} className="btn-primary">
                        + Add Trade
                    </button>
                </div>
            </div>

            {/* Stats Cards */}
            {stats && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
                    <div className="card p-4 text-center">
                        <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.totalTrades}</div>
                        <div className="text-sm text-gray-500">Total Trades</div>
                    </div>
                    <div className="card p-4 text-center">
                        <div className="text-2xl font-bold text-blue-600">{stats.openTrades}</div>
                        <div className="text-sm text-gray-500">Open</div>
                    </div>
                    <div className={`card p-4 text-center ${stats.totalPnl >= 0 ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'}`}>
                        <div className={`text-2xl font-bold ${stats.totalPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                            ₹{stats.totalPnl?.toLocaleString()}
                        </div>
                        <div className="text-sm text-gray-500">Total P&L</div>
                    </div>
                    <div className="card p-4 text-center">
                        <div className="text-2xl font-bold text-purple-600">{stats.winRate}%</div>
                        <div className="text-sm text-gray-500">Win Rate</div>
                    </div>
                    <div className="card p-4 text-center">
                        <div className="text-sm text-gray-500 mb-1">Avg Win / Loss</div>
                        <div className="text-lg">
                            <span className="text-green-600">₹{stats.avgWin?.toLocaleString()}</span>
                            {' / '}
                            <span className="text-red-600">₹{Math.abs(stats.avgLoss)?.toLocaleString()}</span>
                        </div>
                    </div>
                </div>
            )}

            {/* Filter Tabs */}
            <div className="flex gap-2 mb-6">
                {['ALL', 'OPEN', 'CLOSED'].map((f) => (
                    <button
                        key={f}
                        onClick={() => setFilter(f)}
                        className={`px-4 py-2 rounded-lg font-medium transition-colors ${filter === f
                                ? 'bg-blue-600 text-white'
                                : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                            }`}
                    >
                        {f}
                    </button>
                ))}
            </div>

            {/* Trades Table */}
            <div className="card overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-800">
                        <tr>
                            <th className="px-4 py-3 text-left">Symbol</th>
                            <th className="px-4 py-3 text-left">Entry</th>
                            <th className="px-4 py-3 text-left">Qty</th>
                            <th className="px-4 py-3 text-left">SL / Target</th>
                            <th className="px-4 py-3 text-left">Status</th>
                            <th className="px-4 py-3 text-left">Exit</th>
                            <th className="px-4 py-3 text-left">P&L</th>
                            <th className="px-4 py-3 text-left">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                        {trades.length === 0 ? (
                            <tr>
                                <td colSpan="8" className="px-4 py-8 text-center text-gray-500">
                                    No trades found. Click "Add Trade" to get started.
                                </td>
                            </tr>
                        ) : (
                            trades.map((trade) => (
                                <tr key={trade.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                                    <td className="px-4 py-3 font-semibold text-gray-900 dark:text-white">
                                        {trade.symbol}
                                    </td>
                                    <td className="px-4 py-3">
                                        <div>₹{trade.entryPrice}</div>
                                        <div className="text-xs text-gray-500">{trade.entryDate}</div>
                                    </td>
                                    <td className="px-4 py-3">{trade.quantity}</td>
                                    <td className="px-4 py-3">
                                        <span className="text-red-600">₹{trade.stopLoss}</span>
                                        {' / '}
                                        <span className="text-green-600">₹{trade.target}</span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={`px-2 py-1 rounded text-xs font-medium ${trade.status === 'OPEN'
                                                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                                                : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                                            }`}>
                                            {trade.status}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        {trade.exitPrice ? (
                                            <div>
                                                <div>₹{trade.exitPrice}</div>
                                                <div className="text-xs text-gray-500">{trade.exitDate}</div>
                                            </div>
                                        ) : '-'}
                                    </td>
                                    <td className="px-4 py-3">
                                        {trade.status === 'CLOSED' ? (
                                            <div className={trade.pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
                                                <div className="font-semibold">₹{trade.pnl}</div>
                                                <div className="text-xs">{trade.pnlPct}%</div>
                                            </div>
                                        ) : '-'}
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex gap-2">
                                            {trade.status === 'OPEN' && (
                                                <button
                                                    onClick={() => setCloseModal(trade)}
                                                    className="text-blue-600 hover:underline text-sm"
                                                >
                                                    Close
                                                </button>
                                            )}
                                            <button
                                                onClick={() => handleDeleteTrade(trade.id)}
                                                className="text-red-600 hover:underline text-sm"
                                            >
                                                Delete
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {/* Add Trade Modal */}
            {showAddForm && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="card p-6 w-full max-w-md mx-4 animate-fadeIn">
                        <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white">Add New Trade</h2>
                        <form onSubmit={handleAddTrade} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Symbol</label>
                                <input
                                    type="text"
                                    value={newTrade.symbol}
                                    onChange={(e) => setNewTrade({ ...newTrade, symbol: e.target.value.toUpperCase() })}
                                    className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    placeholder="RELIANCE"
                                    required
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Entry Date</label>
                                    <input
                                        type="date"
                                        value={newTrade.entryDate}
                                        onChange={(e) => setNewTrade({ ...newTrade, entryDate: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                        required
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Entry Price</label>
                                    <input
                                        type="number"
                                        value={newTrade.entryPrice}
                                        onChange={(e) => setNewTrade({ ...newTrade, entryPrice: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                        placeholder="1500"
                                        required
                                    />
                                </div>
                            </div>
                            <div className="grid grid-cols-3 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Quantity</label>
                                    <input
                                        type="number"
                                        value={newTrade.quantity}
                                        onChange={(e) => setNewTrade({ ...newTrade, quantity: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                        placeholder="10"
                                        required
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Stop Loss</label>
                                    <input
                                        type="number"
                                        value={newTrade.stopLoss}
                                        onChange={(e) => setNewTrade({ ...newTrade, stopLoss: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                        placeholder="1450"
                                        required
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Target</label>
                                    <input
                                        type="number"
                                        value={newTrade.target}
                                        onChange={(e) => setNewTrade({ ...newTrade, target: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                        placeholder="1600"
                                        required
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Notes (optional)</label>
                                <textarea
                                    value={newTrade.notes}
                                    onChange={(e) => setNewTrade({ ...newTrade, notes: e.target.value })}
                                    className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    placeholder="Breakout trade..."
                                    rows="2"
                                />
                            </div>
                            <div className="flex gap-3 pt-2">
                                <button type="button" onClick={() => setShowAddForm(false)} className="flex-1 btn-secondary">
                                    Cancel
                                </button>
                                <button type="submit" className="flex-1 btn-primary">
                                    Add Trade
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Close Trade Modal */}
            {closeModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="card p-6 w-full max-w-sm mx-4 animate-fadeIn">
                        <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white">Close Trade</h2>
                        <p className="text-gray-600 dark:text-gray-400 mb-4">
                            Closing <strong>{closeModal.symbol}</strong> @ ₹{closeModal.entryPrice}
                        </p>
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Exit Price</label>
                            <input
                                type="number"
                                value={exitPrice}
                                onChange={(e) => setExitPrice(e.target.value)}
                                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                placeholder="1550"
                                autoFocus
                            />
                        </div>
                        <div className="flex gap-3">
                            <button onClick={() => { setCloseModal(null); setExitPrice(''); }} className="flex-1 btn-secondary">
                                Cancel
                            </button>
                            <button onClick={() => handleCloseTrade(closeModal.id)} className="flex-1 btn-primary">
                                Close Trade
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

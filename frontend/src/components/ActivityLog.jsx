import { useState } from 'react';
import { useSignalHistory } from '../hooks/useSignals';
import { format } from 'date-fns';

export default function ActivityLog() {
    const [filter, setFilter] = useState('all'); // all, accepted, rejected
    const { history, loading } = useSignalHistory(filter, 100);

    const getStatusBadge = (signal) => {
        if (signal.rejected) {
            return (
                <span className="px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800 border border-red-200">
                    Rejected
                </span>
            );
        }
        return (
            <span className="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800 border border-green-200">
                Accepted
            </span>
        );
    };

    if (loading) {
        return (
            <div className="flex justify-center items-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-slate-50">
                <h3 className="text-lg font-semibold text-slate-800">Signal Activity Log</h3>
                <div className="flex gap-2">
                    {['all', 'accepted', 'rejected'].map(f => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className={`px-3 py-1 text-sm rounded-md transition-colors ${filter === f
                                    ? 'bg-blue-600 text-white shadow-sm'
                                    : 'bg-white text-slate-600 border border-slate-300 hover:bg-slate-50'
                                }`}
                        >
                            {f.charAt(0).toUpperCase() + f.slice(1)}
                        </button>
                    ))}
                </div>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                    <thead className="text-xs text-slate-500 uppercase bg-slate-50 border-b border-slate-200">
                        <tr>
                            <th className="px-6 py-3">Time</th>
                            <th className="px-6 py-3">Symbol</th>
                            <th className="px-6 py-3">Strategy</th>
                            <th className="px-6 py-3">Score</th>
                            <th className="px-6 py-3">Status</th>
                            <th className="px-6 py-3">Reason / Details</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history.length === 0 ? (
                            <tr>
                                <td colSpan="6" className="px-6 py-8 text-center text-slate-500">
                                    No activity records found.
                                </td>
                            </tr>
                        ) : (
                            history.map((item) => (
                                <tr key={item.id} className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                                    <td className="px-6 py-4 font-normal text-slate-600">
                                        {format(new Date(item.timestamp), 'MMM d, HH:mm')}
                                    </td>
                                    <td className="px-6 py-4 font-semibold text-slate-900">
                                        {item.symbol}
                                    </td>
                                    <td className="px-6 py-4 text-slate-600 capitalize">
                                        {item.strategy.replace('_', ' ')}
                                    </td>
                                    <td className="px-6 py-4">
                                        {item.score > 0 ? (
                                            <span className={`font-mono font-medium ${item.score >= 70 ? 'text-green-600' : 'text-amber-600'
                                                }`}>
                                                {item.score}
                                            </span>
                                        ) : '-'}
                                    </td>
                                    <td className="px-6 py-4">
                                        {getStatusBadge(item)}
                                    </td>
                                    <td className="px-6 py-4 text-slate-600">
                                        {item.rejected ? (
                                            <span className="text-red-700 flex items-center gap-1">
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                                </svg>
                                                {item.rejectionReason}
                                            </span>
                                        ) : (
                                            <span className="text-slate-500">
                                                Signal Generated
                                            </span>
                                        )}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

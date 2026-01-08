import { useState } from 'react';

export default function SignalCard({ signal, onViewChart, onTakeTrade }) {
    const [expanded, setExpanded] = useState(false);

    const isBuy = signal.signal === 'BUY';

    // Confidence meter based on score
    const getConfidenceLevel = (score) => {
        if (score >= 80) return { label: 'High', color: 'green', icon: '🟢' };
        if (score >= 70) return { label: 'Medium', color: 'yellow', icon: '🟡' };
        return { label: 'Low', color: 'gray', icon: '⚪' };
    };

    const confidence = getConfidenceLevel(signal.score);

    const getScoreColor = (score) => {
        if (score >= 80) return 'score-high';
        if (score >= 70) return 'score-medium';
        return 'score-low';
    };

    return (
        <div className="card p-5 hover:shadow-xl transition-all duration-300 animate-fadeIn">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                        {signal.symbol}
                    </h3>
                    <span className={isBuy ? 'badge-buy' : 'badge-sell'}>
                        {signal.signal}
                    </span>
                </div>

                <div className="flex items-center gap-2">
                    <span className="text-sm" title={`Confidence: ${confidence.label}`}>{confidence.icon}</span>
                    <div className={`${getScoreColor(signal.score)} text-white px-3 py-1 rounded-lg font-bold text-lg`}>
                        {signal.score}
                    </div>
                </div>
            </div>

            {/* Key Metrics */}
            <div className="grid grid-cols-3 gap-3 mb-4">
                <div className="text-center p-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <div className="text-xs text-gray-500 dark:text-gray-400">Entry</div>
                    <div className="text-sm font-semibold text-gray-900 dark:text-white">
                        ₹{signal.entry.low.toFixed(0)}-{signal.entry.high.toFixed(0)}
                    </div>
                </div>

                <div className="text-center p-2 bg-red-50 dark:bg-red-900/20 rounded-lg">
                    <div className="text-xs text-red-600 dark:text-red-400">SL</div>
                    <div className="text-sm font-semibold text-red-700 dark:text-red-400">
                        ₹{signal.stopLoss.toFixed(0)}
                    </div>
                </div>

                <div className="text-center p-2 bg-green-50 dark:bg-green-900/20 rounded-lg">
                    <div className="text-xs text-green-600 dark:text-green-400">Target</div>
                    <div className="text-sm font-semibold text-green-700 dark:text-green-400">
                        ₹{signal.targets[0]?.toFixed(0)}
                    </div>
                </div>
            </div>

            {/* Quick Info */}
            <div className="flex items-center justify-between text-sm mb-4">
                <span className="text-gray-600 dark:text-gray-400">
                    R:R <span className="font-semibold text-gray-900 dark:text-white">{signal.riskReward}</span>
                </span>
                {signal.sector && (
                    <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                        {signal.sector}
                    </span>
                )}
            </div>

            {/* Action Buttons */}
            <div className="flex gap-2">
                <button
                    onClick={() => setExpanded(!expanded)}
                    className="flex-1 btn-secondary text-sm"
                >
                    {expanded ? 'Hide' : 'Details'}
                </button>
                <button
                    onClick={() => onViewChart?.(signal.symbol)}
                    className="flex-1 btn-primary text-sm"
                >
                    Chart
                </button>
                <button
                    onClick={() => onTakeTrade?.(signal)}
                    className="flex-1 bg-green-600 hover:bg-green-700 text-white text-sm px-3 py-2 rounded-lg font-medium transition-colors"
                    title="Add to Portfolio"
                >
                    Take
                </button>
            </div>

            {/* Expanded Details */}
            {expanded && (
                <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 animate-fadeIn space-y-4">

                    {/* UI Guidance */}
                    {signal.metadata?.uiGuidance && (
                        <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg text-sm text-blue-700 dark:text-blue-300 flex gap-2 items-start">
                            <span>💡</span>
                            <span>{signal.metadata.uiGuidance}</span>
                        </div>
                    )}

                    {/* Technicals */}
                    <div>
                        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">Technicals</h4>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                            <div className="flex justify-between">
                                <span className="text-gray-500">EMA</span>
                                <span className="text-gray-900 dark:text-white">{signal.technicals.emaAlignment}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-500">RSI</span>
                                <span className={`font-medium ${signal.technicals.rsi >= 70 ? 'text-red-600' :
                                    signal.technicals.rsi <= 30 ? 'text-green-600' :
                                        'text-gray-900 dark:text-white'
                                    }`}>{signal.technicals.rsi}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-500">ADX</span>
                                <span className="text-gray-900 dark:text-white">{signal.technicals.adx}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-500">Volume</span>
                                <span className="text-gray-900 dark:text-white">{signal.technicals.volumeRatio}x</span>
                            </div>
                        </div>
                    </div>

                    {/* Score Breakdown */}
                    {signal.scoreBreakdown && (
                        <div>
                            <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">Score Breakdown</h4>
                            <div className="space-y-1 text-xs">
                                <div className="flex justify-between text-gray-600 dark:text-gray-400">
                                    <span>Base Score</span>
                                    <span>{signal.scoreBreakdown.base}</span>
                                </div>

                                {Object.entries(signal.scoreBreakdown.deductions || {}).map(([key, val]) => (
                                    <div key={key} className="flex justify-between text-red-600 dark:text-red-400">
                                        <span>{key}</span>
                                        <span>{val}</span>
                                    </div>
                                ))}

                                {Object.entries(signal.scoreBreakdown.bonuses || {}).map(([key, val]) => (
                                    <div key={key} className="flex justify-between text-green-600 dark:text-green-400">
                                        <span>{key}</span>
                                        <span>+{val}</span>
                                    </div>
                                ))}

                                <div className="flex justify-between font-semibold text-gray-900 dark:text-white pt-1 border-t border-gray-200 dark:border-gray-700">
                                    <span>Final</span>
                                    <span>{signal.scoreBreakdown.final}</span>
                                </div>
                            </div>
                        </div>
                    )}

                    <div className="text-xs text-gray-500 dark:text-gray-400">
                        Valid until: {signal.validUntil}
                    </div>
                </div>
            )}
        </div>
    );
}

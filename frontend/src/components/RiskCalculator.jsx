import { useState } from 'react';
import { signalApi } from '../api/client';

export default function RiskCalculator() {
    const [capital, setCapital] = useState(100000);
    const [riskPercent, setRiskPercent] = useState(1);
    const [entry, setEntry] = useState('');
    const [stopLoss, setStopLoss] = useState('');
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const presets = [
        { label: '0.5%', value: 0.5 },
        { label: '1%', value: 1 },
        { label: '2%', value: 2 },
    ];

    const handleCalculate = async () => {
        if (!entry || !stopLoss) {
            setError('Please enter both entry and stop loss');
            return;
        }

        const entryPrice = parseFloat(entry);
        const slPrice = parseFloat(stopLoss);

        if (isNaN(entryPrice) || isNaN(slPrice)) {
            setError('Invalid price values');
            return;
        }

        if (entryPrice <= slPrice) {
            setError('For BUY: Entry must be greater than Stop Loss');
            return;
        }

        setLoading(true);
        setError('');

        try {
            const response = await signalApi.calculatePosition({
                capital,
                risk_percent: riskPercent,
                entry: entryPrice,
                stop_loss: slPrice,
            });
            setResult(response.data);
        } catch (err) {
            setError(err.response?.data?.detail || 'Calculation failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="card p-6">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-6">
                Position Size Calculator
            </h2>

            <div className="space-y-4">
                {/* Capital */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Capital (₹)
                    </label>
                    <input
                        type="number"
                        value={capital}
                        onChange={(e) => setCapital(Number(e.target.value))}
                        className="input"
                        placeholder="100000"
                    />
                </div>

                {/* Risk Percent with Presets */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Risk per Trade (%)
                    </label>
                    <div className="flex gap-2 mb-2">
                        {presets.map((preset) => (
                            <button
                                key={preset.value}
                                onClick={() => setRiskPercent(preset.value)}
                                className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${riskPercent === preset.value
                                        ? 'bg-primary-600 text-white'
                                        : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                                    }`}
                            >
                                {preset.label}
                            </button>
                        ))}
                    </div>
                    <input
                        type="number"
                        value={riskPercent}
                        onChange={(e) => setRiskPercent(Number(e.target.value))}
                        step="0.1"
                        min="0.1"
                        max="5"
                        className="input"
                    />
                </div>

                {/* Entry */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Entry Price (₹)
                    </label>
                    <input
                        type="number"
                        value={entry}
                        onChange={(e) => setEntry(e.target.value)}
                        className="input"
                        placeholder="650"
                    />
                </div>

                {/* Stop Loss */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Stop Loss (₹)
                    </label>
                    <input
                        type="number"
                        value={stopLoss}
                        onChange={(e) => setStopLoss(e.target.value)}
                        className="input"
                        placeholder="618"
                    />
                </div>

                {/* Error */}
                {error && (
                    <div className="text-red-600 dark:text-red-400 text-sm">
                        {error}
                    </div>
                )}

                {/* Calculate Button */}
                <button
                    onClick={handleCalculate}
                    disabled={loading}
                    className="w-full btn-primary py-3"
                >
                    {loading ? 'Calculating...' : 'Calculate Position Size'}
                </button>

                {/* Result */}
                {result && result.valid && (
                    <div className="mt-4 p-4 bg-primary-50 dark:bg-primary-900/20 rounded-lg animate-fadeIn">
                        <h3 className="font-semibold text-primary-800 dark:text-primary-300 mb-3">
                            Recommended Position
                        </h3>
                        <div className="grid grid-cols-2 gap-4 text-sm">
                            <div>
                                <div className="text-gray-600 dark:text-gray-400">Shares</div>
                                <div className="text-2xl font-bold text-gray-900 dark:text-white">
                                    {result.shares.toLocaleString()}
                                </div>
                            </div>
                            <div>
                                <div className="text-gray-600 dark:text-gray-400">Position Value</div>
                                <div className="text-2xl font-bold text-gray-900 dark:text-white">
                                    ₹{result.positionValue.toLocaleString()}
                                </div>
                            </div>
                            <div>
                                <div className="text-gray-600 dark:text-gray-400">Risk Amount</div>
                                <div className="text-lg font-semibold text-red-600 dark:text-red-400">
                                    ₹{result.riskAmount.toLocaleString()}
                                </div>
                            </div>
                            <div>
                                <div className="text-gray-600 dark:text-gray-400">Risk %</div>
                                <div className="text-lg font-semibold text-gray-700 dark:text-gray-300">
                                    {result.riskPercent}%
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {result && !result.valid && (
                    <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
                        <div className="text-red-700 dark:text-red-400 font-medium">
                            Invalid: {result.rejectionReason}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

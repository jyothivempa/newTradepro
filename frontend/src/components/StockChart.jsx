import { useMemo } from 'react';
import Chart from 'react-apexcharts';
import { useStockData } from '../hooks/useSignals';

export default function StockChart({ symbol, signal = null }) {
    const { data, loading, error } = useStockData(symbol);

    const chartOptions = useMemo(() => {
        if (!data?.data || data.data.length === 0) return null;

        // Calculate EMAs for overlay
        const closes = data.data.map(d => d.close);
        const calculateEMA = (data, period) => {
            const k = 2 / (period + 1);
            let ema = [data[0]];
            for (let i = 1; i < data.length; i++) {
                ema.push(data[i] * k + ema[i - 1] * (1 - k));
            }
            return ema;
        };

        const ema20 = calculateEMA(closes, 20);
        const ema50 = calculateEMA(closes, 50);

        // Candlestick data
        const candles = data.data.map((d) => ({
            x: new Date(d.date),
            y: [d.open, d.high, d.low, d.close],
        }));

        // EMA line series
        const ema20Series = data.data.map((d, i) => ({
            x: new Date(d.date),
            y: ema20[i],
        }));

        const ema50Series = data.data.map((d, i) => ({
            x: new Date(d.date),
            y: ema50[i],
        }));

        // Volume series
        const volumeSeries = data.data.map((d, i) => ({
            x: new Date(d.date),
            y: d.volume,
            fillColor: d.close >= d.open ? '#22c55e' : '#ef4444',
        }));

        // Annotations for signal entry, SL, targets
        const priceAnnotations = signal ? [
            {
                y: signal.entry.low,
                y2: signal.entry.high,
                borderColor: '#22c55e',
                fillColor: '#22c55e',
                opacity: 0.15,
                label: {
                    text: `Entry: ₹${signal.entry.low}-${signal.entry.high}`,
                    style: { color: '#fff', background: '#22c55e', fontSize: '10px' },
                },
            },
            {
                y: signal.stopLoss,
                borderColor: '#ef4444',
                strokeDashArray: 5,
                label: {
                    text: `SL: ₹${signal.stopLoss}`,
                    style: { color: '#fff', background: '#ef4444', fontSize: '10px' },
                    position: 'left',
                },
            },
            ...signal.targets.slice(0, 2).map((t, i) => ({
                y: t,
                borderColor: '#16a34a',
                strokeDashArray: 5,
                label: {
                    text: `T${i + 1}: ₹${t.toFixed(0)}`,
                    style: { color: '#fff', background: '#16a34a', fontSize: '10px' },
                    position: 'right',
                },
            })),
        ] : [];

        const isDark = document.documentElement.classList.contains('dark');

        return {
            series: [
                { name: 'Price', type: 'candlestick', data: candles },
                { name: 'EMA 20', type: 'line', data: ema20Series },
                { name: 'EMA 50', type: 'line', data: ema50Series },
            ],
            options: {
                chart: {
                    type: 'candlestick',
                    height: 350,
                    id: 'price-chart',
                    toolbar: { show: true, tools: { download: false } },
                    zoom: { enabled: true },
                    background: 'transparent',
                    animations: { enabled: false },
                },
                theme: { mode: isDark ? 'dark' : 'light' },
                title: {
                    text: `${data.name || symbol}`,
                    align: 'left',
                    style: { fontSize: '14px', fontWeight: 600, color: isDark ? '#fff' : '#111' },
                },
                stroke: {
                    width: [1, 2, 2],
                    curve: 'smooth',
                },
                colors: ['#000', '#3b82f6', '#f59e0b'],
                xaxis: {
                    type: 'datetime',
                    labels: {
                        datetimeUTC: false,
                        style: { colors: isDark ? '#9ca3af' : '#6b7280' },
                    },
                },
                yaxis: {
                    tooltip: { enabled: true },
                    labels: {
                        formatter: (val) => `₹${val?.toFixed(0)}`,
                        style: { colors: isDark ? '#9ca3af' : '#6b7280' },
                    },
                },
                plotOptions: {
                    candlestick: {
                        colors: { upward: '#22c55e', downward: '#ef4444' },
                        wick: { useFillColor: true },
                    },
                },
                annotations: { yaxis: priceAnnotations },
                grid: {
                    borderColor: isDark ? '#374151' : '#e5e7eb',
                },
                legend: {
                    show: true,
                    position: 'top',
                    horizontalAlign: 'right',
                    labels: { colors: isDark ? '#9ca3af' : '#6b7280' },
                },
                tooltip: {
                    theme: isDark ? 'dark' : 'light',
                    x: { format: 'dd MMM yyyy' },
                },
            },
        };
    }, [data, signal, symbol]);

    if (!symbol) {
        return (
            <div className="card p-6 text-center text-gray-500 dark:text-gray-400">
                <div className="text-3xl mb-2">📊</div>
                Select a signal to view chart
            </div>
        );
    }

    if (loading) {
        return (
            <div className="card p-6 flex items-center justify-center h-[350px]">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="card p-6 text-center text-red-600 dark:text-red-400">
                Error: {error}
            </div>
        );
    }

    if (!chartOptions) {
        return (
            <div className="card p-6 text-center text-gray-500 dark:text-gray-400">
                No data available for {symbol}
            </div>
        );
    }

    return (
        <div className="card p-3">
            <Chart
                options={chartOptions.options}
                series={chartOptions.series}
                type="candlestick"
                height={350}
            />
            {/* Legend for indicators */}
            <div className="flex items-center justify-center gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
                <div className="flex items-center gap-1">
                    <div className="w-3 h-0.5 bg-blue-500"></div>
                    <span>EMA 20</span>
                </div>
                <div className="flex items-center gap-1">
                    <div className="w-3 h-0.5 bg-amber-500"></div>
                    <span>EMA 50</span>
                </div>
                {signal && (
                    <>
                        <div className="flex items-center gap-1">
                            <div className="w-3 h-2 bg-green-500/30 border border-green-500"></div>
                            <span>Entry</span>
                        </div>
                        <div className="flex items-center gap-1">
                            <div className="w-3 h-0.5 bg-red-500"></div>
                            <span>SL</span>
                        </div>
                    </>
                )}
            </div>
            {data?.sector && (
                <div className="text-center text-xs text-gray-400 mt-1">
                    {data.sector}
                </div>
            )}
        </div>
    );
}

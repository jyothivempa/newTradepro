import { useState, useEffect, useCallback } from 'react';
import { signalApi } from '../api/client';

export function useSignals(type = 'swing', limit = 10, sector = null) {
    const [signals, setSignals] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);

    const fetchSignals = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const response = type === 'swing'
                ? await signalApi.getSwingSignals(limit, sector)
                : await signalApi.getIntradayBiasSignals(limit, sector);

            setSignals(response.data);
            setLastUpdated(new Date());
        } catch (err) {
            setError(err.response?.data?.detail || err.message || 'Failed to fetch signals');
            console.error('Signal fetch error:', err);
        } finally {
            setLoading(false);
        }
    }, [type, limit, sector]);

    useEffect(() => {
        fetchSignals();

        // Auto-refresh every 5 minutes
        const interval = setInterval(fetchSignals, 5 * 60 * 1000);

        return () => clearInterval(interval);
    }, [fetchSignals]);

    return { signals, loading, error, lastUpdated, refetch: fetchSignals };
}

export function useStockData(symbol) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!symbol) return;

        const fetchData = async () => {
            setLoading(true);
            setError(null);

            try {
                const response = await signalApi.getStockData(symbol);
                setData(response.data);
            } catch (err) {
                setError(err.response?.data?.detail || err.message);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [symbol]);

    return { data, loading, error };
}

export function useSectors() {
    const [sectors, setSectors] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchSectors = async () => {
            try {
                const response = await signalApi.getSectors();
                setSectors(response.data.sectors || []);
            } catch (err) {
                console.error('Failed to fetch sectors:', err);
            } finally {
                setLoading(false);
            }
        };

        fetchSectors();
    }, []);

    return { sectors, loading };
}

export function useHealth() {
    const [health, setHealth] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const checkHealth = async () => {
            try {
                const response = await signalApi.getHealth();
                setHealth(response.data);
            } catch (err) {
                console.error('Health check failed:', err);
            } finally {
                setLoading(false);
            }
        };

        checkHealth();
    }, []);

    return { health, loading };
}

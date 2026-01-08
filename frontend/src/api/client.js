import axios from 'axios';

const API_BASE = '/api';

const api = axios.create({
    baseURL: API_BASE,
    timeout: 60000, // 60s for long scans
    headers: {
        'Content-Type': 'application/json',
    },
});

// Response interceptor for error handling
api.interceptors.response.use(
    (response) => response,
    (error) => {
        console.error('API Error:', error.response?.data || error.message);
        return Promise.reject(error);
    }
);

export const signalApi = {
    // Health check
    getHealth: () => api.get('/health'),

    // Signals
    getSwingSignals: (limit = 10, sector = null) => {
        const params = { limit };
        if (sector) params.sector = sector;
        return api.get('/swing', { params });
    },

    getIntradayBiasSignals: (limit = 10, sector = null) => {
        const params = { limit };
        if (sector) params.sector = sector;
        return api.get('/intraday-bias', { params });
    },

    // Stocks
    getStocks: (sector = null) => {
        const params = sector ? { sector } : {};
        return api.get('/stocks', { params });
    },

    getStockData: (symbol) => api.get(`/stocks/${symbol}`),

    getSectors: () => api.get('/sectors'),

    // Risk management
    calculatePosition: (data) => api.post('/calculate-position', data),
    getRiskSnapshot: () => api.get('/risk-snapshot'),
    getNiftyTrend: () => api.get('/nifty-trend'),

    // Live data
    getLivePrices: (symbols) => api.get(`/live?symbols=${symbols}`),
    getLivePrice: (symbol) => api.get(`/live/${symbol}`),
    getMarketStatus: () => api.get('/market-status'),

    // News & FII
    getNewsSentiment: (symbol) => api.get(`/news/${symbol}`),
    getFiiDii: () => api.get('/fii-dii'),
};

export default api;

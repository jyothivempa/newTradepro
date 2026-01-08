import { useEffect, useState, useCallback, useRef } from 'react';
import { io } from 'socket.io-client';

const WS_URL = import.meta.env.VITE_WS_URL || 'http://localhost:8000';

/**
 * Custom hook for WebSocket connection with auto-reconnection.
 * 
 * @param {string[]} symbols - Array of stock symbols to subscribe to
 * @returns {Object} - { prices, connected, reconnecting, error }
 */
export function useWebSocket(symbols = []) {
    const [prices, setPrices] = useState({});
    const [connected, setConnected] = useState(false);
    const [reconnecting, setReconnecting] = useState(false);
    const [error, setError] = useState(null);

    const socketRef = useRef(null);
    const reconnectAttempts = useRef(0);
    const maxReconnectAttempts = 5;

    const connect = useCallback(() => {
        // Prevent multiple connections
        if (socketRef.current?.connected) {
            return socketRef.current;
        }

        const socket = io(WS_URL, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: maxReconnectAttempts,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 20000,
        });

        socket.on('connect', () => {
            console.log('🟢 WebSocket connected');
            setConnected(true);
            setReconnecting(false);
            setError(null);
            reconnectAttempts.current = 0;

            // Subscribe to symbols on connect
            if (symbols.length > 0) {
                socket.emit('subscribe_prices', { symbols });
            }
        });

        socket.on('welcome', (data) => {
            console.log('Welcome message:', data);
        });

        socket.on('subscribed', (data) => {
            console.log('📊 Subscribed to:', data.symbols);
        });

        socket.on('price_update', (data) => {
            if (data.prices) {
                setPrices(prev => ({ ...prev, ...data.prices }));
            }
        });

        socket.on('disconnect', (reason) => {
            console.log('🔴 WebSocket disconnected:', reason);
            setConnected(false);

            if (reason === 'io server disconnect') {
                // Server disconnected, try manual reconnect
                socket.connect();
            }
        });

        socket.on('reconnect_attempt', (attempt) => {
            console.log(`🔄 Reconnecting... Attempt ${attempt}`);
            setReconnecting(true);
            reconnectAttempts.current = attempt;
        });

        socket.on('reconnect', () => {
            console.log('🟢 Reconnected successfully');
            setReconnecting(false);

            // Re-subscribe after reconnect
            if (symbols.length > 0) {
                socket.emit('subscribe_prices', { symbols });
            }
        });

        socket.on('reconnect_failed', () => {
            console.log('❌ Reconnection failed');
            setReconnecting(false);
            setError('Failed to reconnect after multiple attempts');
        });

        socket.on('error', (err) => {
            console.error('WebSocket error:', err);
            setError(err.message || 'Connection error');
        });

        socketRef.current = socket;
        return socket;
    }, [symbols]);

    // Connect on mount, disconnect on unmount
    useEffect(() => {
        const socket = connect();

        return () => {
            if (socket) {
                socket.disconnect();
            }
        };
    }, [connect]);

    // Re-subscribe when symbols change
    useEffect(() => {
        if (socketRef.current?.connected && symbols.length > 0) {
            socketRef.current.emit('subscribe_prices', { symbols });
        }
    }, [symbols]);

    // Subscribe function for manual subscription
    const subscribe = useCallback((newSymbols) => {
        if (socketRef.current?.connected) {
            socketRef.current.emit('subscribe_prices', { symbols: newSymbols });
        }
    }, []);

    // Unsubscribe function
    const unsubscribe = useCallback((symbolsToRemove) => {
        if (socketRef.current?.connected) {
            socketRef.current.emit('unsubscribe_prices', { symbols: symbolsToRemove });
        }
    }, []);

    return {
        prices,
        connected,
        reconnecting,
        error,
        subscribe,
        unsubscribe,
    };
}

/**
 * Connection status indicator component
 */
export function ConnectionStatus({ connected, reconnecting }) {
    if (reconnecting) {
        return (
            <div className="flex items-center gap-1 text-yellow-500 text-sm">
                <span className="animate-pulse">●</span>
                <span>Reconnecting...</span>
            </div>
        );
    }

    return (
        <div className={`flex items-center gap-1 text-sm ${connected ? 'text-green-500' : 'text-red-500'}`}>
            <span>●</span>
            <span>{connected ? 'Live' : 'Disconnected'}</span>
        </div>
    );
}

export default useWebSocket;

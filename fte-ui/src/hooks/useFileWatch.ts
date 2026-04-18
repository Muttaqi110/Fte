'use client';

import { useEffect, useState, useCallback, useRef } from 'react';

export interface FileEvent {
  type: 'change' | 'rename' | 'connected';
  folder: string;
  filename: string;
  timestamp: string;
}

export function useFileWatch(onChange?: (event: FileEvent) => void) {
  const [connected, setConnected] = useState(false);
  const onChangeRef = useRef(onChange);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    const eventSource = new EventSource('/api/watch');

    eventSource.onopen = () => {
      setConnected(true);
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as FileEvent;
        // Only call onChange for actual file events, not connection messages
        if (data.type !== 'connected') {
          onChangeRef.current?.(data);
        }
      } catch {}
    };

    eventSource.onerror = () => {
      setConnected(false);
      // Attempt to reconnect after 3 seconds
      setTimeout(() => {
        eventSource.close();
      }, 3000);
    };

    return () => eventSource.close();
  }, []);

  return { connected };
}

interface EmailFile {
  name: string;
  path: string;
  size: number;
  modified: string;
  content: string;
}

// Simple global store
const store: {
  files: Record<string, EmailFile[]>;
  loading: Record<string, boolean>;
} = {
  files: {},
  loading: {},
};

export function useFiles(folder: string, source?: string) {
  const key = `${folder}:${source || 'all'}`;

  const [state, setState] = useState<{
    files: EmailFile[];
    loading: boolean;
    error: string | null;
  }>({
    files: store.files[key] || [],
    loading: store.loading[key] ?? true,
    error: null,
  });

  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    // If already have data, use it
    if (store.files[key] && store.files[key].length > 0) {
      setState({ files: store.files[key], loading: false, error: null });
      return;
    }

    // Fetch if no data
    const fetchFiles = async () => {
      store.loading[key] = true;
      setState(prev => ({ ...prev, loading: true }));

      try {
        const params = new URLSearchParams({ folder });
        if (source) params.append('source', source);

        const res = await fetch(`/api/files?${params.toString()}`);
        const data = await res.json();

        if (!mountedRef.current) return;

        if (data.error) {
          setState({ files: [], loading: false, error: data.error });
        } else {
          const files = data.files || [];
          store.files[key] = files;
          store.loading[key] = false;
          setState({ files, loading: false, error: null });
        }
      } catch (err) {
        if (!mountedRef.current) return;
        setState({ files: [], loading: false, error: String(err) });
      }
    };

    fetchFiles();

    return () => {
      mountedRef.current = false;
    };
  }, [key]); // Only depend on key, not folder/source separately

  const refresh = useCallback(() => {
    // Clear cache for this key to force refetch
    delete store.files[key];

    const fetchFiles = async () => {
      setState(prev => ({ ...prev, loading: true }));

      try {
        const params = new URLSearchParams({ folder });
        if (source) params.append('source', source);

        const res = await fetch(`/api/files?${params.toString()}`);
        const data = await res.json();

        if (data.files) {
          store.files[key] = data.files;
          setState({ files: data.files, loading: false, error: null });
        }
      } catch (err) {
        setState(prev => ({ ...prev, loading: false, error: String(err) }));
      }
    };

    fetchFiles();
  }, [key, folder, source]);

  return { ...state, refresh };
}

export function useStatus() {
  const [status, setStatus] = useState<{
    folders: Record<string, { count: number; latest?: string; icon: string }>;
    systemRunning: boolean;
    timestamp: string;
  } | null>(null);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        setStatus(data);
      } catch {}
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  return { status };
}

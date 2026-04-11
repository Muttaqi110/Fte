'use client';

import { useEffect, useState, useCallback } from 'react';

export interface FileEvent {
  type: 'change' | 'rename' | 'connected';
  folder: string;
  filename: string;
  timestamp: string;
}

export function useFileWatch(onChange?: (event: FileEvent) => void) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<FileEvent | null>(null);

  useEffect(() => {
    const eventSource = new EventSource('/api/watch');

    eventSource.onopen = () => {
      setConnected(true);
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as FileEvent;
        setLastEvent(data);
        onChange?.(data);
      } catch {
        // Ignore parse errors
      }
    };

    eventSource.onerror = () => {
      setConnected(false);
      // Reconnect after a delay
      setTimeout(() => {
        eventSource.close();
      }, 1000);
    };

    return () => {
      eventSource.close();
      setConnected(false);
    };
  }, [onChange]);

  return { connected, lastEvent };
}

interface EmailFile {
  name: string;
  path: string;
  size: number;
  modified: string;
  content: string;
}

export function useFiles(folder: string, source?: string) {
  const [files, setFiles] = useState<EmailFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchFiles = useCallback(async () => {
    try {
      const params = new URLSearchParams({ folder });
      if (source) {
        params.append('source', source);
      }
      const res = await fetch(`/api/files?${params.toString()}`);
      const data = await res.json();

      if (data.error) {
        setError(data.error);
      } else {
        setFiles(data.files || []);
        setError(null);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [folder, source]);

  useEffect(() => {
    setLoading(true);
    fetchFiles();
  }, [fetchFiles]);

  // Refresh on file changes
  const refresh = useCallback(() => {
    fetchFiles();
  }, [fetchFiles]);

  return { files, loading, error, refresh };
}

export function useStatus() {
  const [status, setStatus] = useState<{
    folders: Record<string, { count: number; latest?: string; icon: string }>;
    systemRunning: boolean;
    timestamp: string;
  } | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      setStatus(data);
    } catch {
      // Ignore errors
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    // Refresh status every 5 seconds
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  return { status, refresh: fetchStatus };
}

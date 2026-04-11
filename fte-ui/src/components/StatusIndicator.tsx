'use client';

import { useStatus } from '@/hooks/useFileWatch';

export function StatusIndicator() {
  const { status } = useStatus();

  return (
    <div className="flex items-center gap-6 text-sm">
      {/* System Status */}
      <div className="flex items-center gap-2">
        <span
          className={`w-2.5 h-2.5 rounded-full ${
            status?.systemRunning ? 'bg-green-500 animate-pulse' : 'bg-red-500'
          }`}
        ></span>
        <span className="text-gray-400 font-medium">
          {status?.systemRunning ? 'Running' : 'Stopped'}
        </span>
      </div>

      {/* Channel Status */}
      <div className="flex items-center gap-4 text-xs">
        <div className="flex items-center gap-1.5 px-2 py-1 bg-red-900/20 rounded border border-red-900/30">
          <span>📧</span>
          <span className="text-gray-500">Gmail</span>
          <span className="font-medium text-red-400">
            {status?.folders?.['Gmail_Messages/Draft']?.count || 0}
          </span>
        </div>

        <div className="flex items-center gap-1.5 px-2 py-1 bg-green-900/20 rounded border border-green-900/30">
          <span>💬</span>
          <span className="text-gray-500">WhatsApp</span>
          <span className="font-medium text-green-400">
            {status?.folders?.['WhatsApp_Messages/Draft']?.count || 0}
          </span>
        </div>

        <div className="flex items-center gap-1.5 px-2 py-1 bg-purple-900/20 rounded border border-purple-900/30">
          <span>💼</span>
          <span className="text-gray-500">LinkedIn</span>
          <span className="font-medium text-purple-400">
            {status?.folders?.['LinkedIn_Posts/Draft']?.count || 0}
          </span>
        </div>
      </div>
    </div>
  );
}

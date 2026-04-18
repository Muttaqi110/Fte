'use client';

import React, { useState, useCallback, useEffect } from 'react';
import { useFileWatch, useFiles, FileEvent } from '@/hooks/useFileWatch';
import { EmailList } from '@/components/Sidebar';
import { EmailViewer } from '@/components/EmailViewer';

type Source = 'gmail' | 'whatsapp' | 'linkedin' | 'x' | 'facebook' | 'odoo';

type RepeatType = 'once' | 'daily' | 'weekly' | 'custom';

interface ScheduleConfig {
  date: string;
  time: string;
  repeatType: RepeatType;
  customDays?: number;
  endDate?: string;
}

interface SourceConfig {
  name: string;
  logo: React.ReactNode;
  folders: {
    name: string;
    icon: string;
    path: string;
  }[];
}

// SVG Logos
const GmailLogo = () => (
  <svg viewBox="0 0 24 24" className="w-6 h-6" fill="currentColor">
    <path d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457z"/>
  </svg>
);

const WhatsAppLogo = () => (
  <svg viewBox="0 0 24 24" className="w-6 h-6" fill="currentColor">
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
  </svg>
);

const LinkedInLogo = () => (
  <svg viewBox="0 0 24 24" className="w-6 h-6" fill="currentColor">
    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
  </svg>
);

const XLogo = () => (
  <svg viewBox="0 0 24 24" className="w-6 h-6" fill="currentColor">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
  </svg>
);

const FacebookLogo = () => (
  <svg viewBox="0 0 24 24" className="w-6 h-6" fill="currentColor">
    <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
  </svg>
);

const OdooLogo = () => (
  <svg viewBox="0 0 24 24" className="w-6 h-6" fill="currentColor">
    <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm0 3.5a8.5 8.5 0 110 17 8.5 8.5 0 010-17zm0 3a5.5 5.5 0 100 11 5.5 5.5 0 000-11z"/>
  </svg>
);

const SOURCE_CONFIG: Record<Source, SourceConfig> = {
  gmail: {
    name: 'Gmail',
    logo: <GmailLogo />,
    folders: [
      { name: 'Inbox', icon: '📥', path: 'Inbox' },
      { name: 'Drafts', icon: '📝', path: 'Gmail_Messages/Draft' },
      { name: 'Scheduled', icon: '📅', path: 'Scheduled' },
    ],
  },
  whatsapp: {
    name: 'WhatsApp',
    logo: <WhatsAppLogo />,
    folders: [
      { name: 'Inbox', icon: '📥', path: 'whatsapp_inbox' },
      { name: 'Drafts', icon: '📝', path: 'WhatsApp_Messages/Draft' },
      { name: 'Scheduled', icon: '📅', path: 'Scheduled' },
    ],
  },
  linkedin: {
    name: 'LinkedIn',
    logo: <LinkedInLogo />,
    folders: [
      { name: 'Inbox', icon: '📥', path: 'linkedin_inbox' },
      { name: 'Drafts', icon: '📄', path: 'LinkedIn_Posts/Draft' },
      { name: 'New Post', icon: '📝', path: 'linkedin_post' },
      { name: 'Approved', icon: '✅', path: 'LinkedIn_Posts/Approved' },
      { name: 'Published', icon: '🚀', path: 'LinkedIn_Posts/Done' },
      { name: 'Scheduled', icon: '📅', path: 'Scheduled' },
    ],
  },
  x: {
    name: 'X',
    logo: <XLogo />,
    folders: [
      { name: 'Drafts', icon: '📄', path: 'X_Posts/Draft' },
      { name: 'New Post', icon: '📝', path: 'x_post' },
      { name: 'Approved', icon: '✅', path: 'X_Posts/Approved' },
      { name: 'Published', icon: '🚀', path: 'X_Posts/Done' },
      { name: 'Scheduled', icon: '📅', path: 'Scheduled' },
    ],
  },
  facebook: {
    name: 'Facebook',
    logo: <FacebookLogo />,
    folders: [
      { name: 'Drafts', icon: '📄', path: 'Facebook_Posts/Draft' },
      { name: 'New Post', icon: '📝', path: 'facebook_post' },
      { name: 'Approved', icon: '✅', path: 'Facebook_Posts/Approved' },
      { name: 'Published', icon: '🚀', path: 'Facebook_Posts/Done' },
      { name: 'Scheduled', icon: '📅', path: 'Scheduled' },
    ],
  },
  odoo: {
    name: 'Odoo',
    logo: <OdooLogo />,
    folders: [
      { name: 'Draft Invoices', icon: '📄', path: 'Odoo_Invoices/Draft' },
      { name: 'Approved', icon: '✅', path: 'Odoo_Invoices/Approved' },
      { name: 'Posted', icon: '🚀', path: 'Odoo_Invoices/Posted' },
      { name: 'Rejected', icon: '❌', path: 'Odoo_Invoices/Rejected' },
    ],
  },
};

export default function Home() {
  const [activeSource, setActiveSource] = useState<Source>('gmail');
  const [activeFolder, setActiveFolder] = useState<string>('Inbox'); // Default to Inbox
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [isNewPostMode, setIsNewPostMode] = useState(false);
  const [newPostContent, setNewPostContent] = useState<string>('');
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [scheduleConfig, setScheduleConfig] = useState<ScheduleConfig>({
    date: '',
    time: '09:00',
    repeatType: 'once',
    customDays: 1,
    endDate: '',
  });
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });

  // Pass source to filter files correctly for Needs_Action folder
  const { files, loading, error, refresh } = useFiles(activeFolder, activeFolder === 'Needs_Action' ? activeSource : undefined);

  // SSE-based real-time updates - only refresh when backend signals a change
  const { connected } = useFileWatch((event) => {
    // Only refresh if the event is for our current folder and we're not editing
    if (event.folder === activeFolder && !isNewPostMode) {
      refresh();
    }
  });

  // Manual refresh function with visual feedback
  const [isRefreshing, setIsRefreshing] = useState(false);
  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    await refresh();
    setTimeout(() => setIsRefreshing(false), 500); // Brief visual feedback
  };

  // Load selected file content
  useEffect(() => {
    const file = files.find((f) => f.name === selectedFile);
    if (file) {
      setFileContent(file.content);
    } else {
      setFileContent('');
    }
  }, [selectedFile, files]);

  // Reset selection when folder changes
  useEffect(() => {
    setSelectedFile(null);
    setIsNewPostMode(false); // Cancel new post mode when folder changes
  }, [activeFolder]);

  // Handle source change - default to Drafts folder
  const handleSourceChange = (source: Source) => {
    setActiveSource(source);
    // Drafts is at index 0 in the folders array
    setActiveFolder(SOURCE_CONFIG[source].folders[0].path);
    setSelectedFile(null);
    setIsNewPostMode(false); // Cancel new post mode when switching
  };

  const handleApprove = async (newContent: string) => {
    if (!selectedFile) return;
    console.log('handleApprove called:', { selectedFile, activeFolder, activeSource });

    try {
      const saveRes = await fetch('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          folder: activeFolder,
          filename: selectedFile,
          content: newContent,
        }),
      });
      console.log('Save result:', await saveRes.json());

      const targetFolder = activeSource === 'gmail'
        ? 'Gmail_Messages/Approved'
        : activeSource === 'whatsapp'
          ? 'WhatsApp_Messages/Approved'
          : activeSource === 'linkedin'
            ? 'LinkedIn_Posts/Approved'
            : activeSource === 'x'
              ? 'X_Posts/Approved'
              : activeSource === ''
                ? 'Instagram_Posts/Approved'
                : activeSource === 'facebook'
                  ? 'Facebook_Posts/Approved'
                  : activeSource === 'odoo'
                    ? 'Odoo_Invoices/Approved'
                    : 'Gmail_Messages/Draft';

      const moveRes = await fetch('/api/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sourceFolder: activeFolder,
          targetFolder,
          filename: selectedFile,
        }),
      });
      console.log('Move result:', await moveRes.json());

      setSelectedFile(null);
      refresh();
    } catch (error) {
      console.error('Approve error:', error);
    }
  };

  const handleReject = async () => {
    if (!selectedFile) return;

    const targetFolder = activeSource === 'odoo' ? 'Odoo_Invoices/Rejected' : 'Rejected';

    await fetch('/api/move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sourceFolder: activeFolder,
        targetFolder,
        filename: selectedFile,
      }),
    });

    setSelectedFile(null);
    refresh();
  };

  const handleMoveToDone = async () => {
    if (!selectedFile) return;

    const targetFolder = activeSource === 'gmail'
      ? 'Gmail_Messages/Done'
      : activeSource === 'whatsapp'
        ? 'WhatsApp_Messages/Done'
        : activeSource === 'linkedin'
          ? 'LinkedIn_Posts/Done'
          : activeSource === 'x'
            ? 'X_Posts/Done'
            : activeSource === ''
              ? 'Instagram_Posts/Done'
              : 'Facebook_Posts/Done';

    await fetch('/api/move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sourceFolder: activeFolder,
        targetFolder,
        filename: selectedFile,
      }),
    });

    setSelectedFile(null);
    refresh();
  };

  const handleCreatePost = () => {
    console.log('handleCreatePost called - opening unsaved new post');

    const platformName = activeSource === 'linkedin' ? 'LinkedIn'
      : activeSource === 'x' ? 'X (Twitter)'
      : activeSource === '' ? 'Instagram'
      : 'Facebook';

    const platformSpecificGuidance = activeSource === 'x'
      ? '**Character Limit:** 280 characters max\n**Style:** Short, punchy, hashtag-rich'
      : activeSource === ''
        ? '**Image:** Required - specify image path or description\n**Style:** Descriptive, visual-focused, 15-20 hashtags'
        : activeSource === 'facebook'
          ? '**Style:** Community-focused, conversational, engagement-driven'
          : '**Tone:** Professional\n**Hashtags:** 3-5 relevant hashtags';

    const content = `# ${platformName} Post Request

## Requirements

**Topic:** Enter your topic here
${platformSpecificGuidance}

## Additional Notes

Add any specific requirements here.

---
*Created: ${new Date().toISOString()}*
`;

    // Set new post mode - don't save yet
    setIsNewPostMode(true);
    setNewPostContent(content);
    setSelectedFile(null); // Clear any selected file
    setFileContent(''); // Clear file content
  };

  const handleSaveNewPost = async (content: string) => {
    const filename = `${new Date().toISOString().split('T')[0]}_${Date.now()}_${activeSource === 'odoo' ? 'invoice' : 'post'}_request.md`;
    console.log('Saving new post:', { filename });

    // Determine folder based on source and scheduling
    let folder: string;
    if (activeSource === 'odoo') {
      folder = 'Needs_Action';
    } else if (scheduleConfig.date) {
      folder = 'Scheduled';
    } else {
      folder = activeSource === 'linkedin' ? 'linkedin_post'
        : activeSource === 'x' ? 'x_post'
        : 'facebook_post';
    }

    // Add schedule metadata if configured (only for non-Odoo)
    let finalContent = content;
    if (scheduleConfig.date && activeSource !== 'odoo') {
      const executeAt = `${scheduleConfig.date} ${scheduleConfig.time}`;
      const scheduleMeta = `---
execute_at: ${executeAt}
repeat_type: ${scheduleConfig.repeatType}
${scheduleConfig.repeatType === 'custom' ? `repeat_days: ${scheduleConfig.customDays}` : ''}
${scheduleConfig.endDate ? `repeat_end: ${scheduleConfig.endDate}` : ''}
---

`;
      finalContent = scheduleMeta + content;
    }

    try {
      const res = await fetch('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          folder,
          filename,
          content: finalContent,
        }),
      });
      console.log('Save new post result:', await res.json());

      // Reset schedule config
      setScheduleConfig({
        date: '',
        time: '09:00',
        repeatType: 'once',
        customDays: 1,
        endDate: '',
      });

      // Exit new post mode and refresh
      setIsNewPostMode(false);
      setShowScheduleModal(false);
      setActiveFolder(folder);
      setSelectedFile(filename);
      setFileContent(finalContent);
      refresh();
    } catch (error) {
      console.error('Save new post error:', error);
    }
  };

  const handleCancelNewPost = () => {
    setIsNewPostMode(false);
    setNewPostContent('');
    setShowScheduleModal(false);
  };

  // Calendar Component
  const Calendar = ({ selectedDate, onDateSelect, label }: { selectedDate: string; onDateSelect: (date: string) => void; label: string }) => {
    const daysInMonth = new Date(calendarMonth.year, calendarMonth.month + 1, 0).getDate();
    const firstDayOfMonth = new Date(calendarMonth.year, calendarMonth.month, 1).getDay();
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const dayNames = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const days = [];
    for (let i = 0; i < firstDayOfMonth; i++) {
      days.push(<div key={`empty-${i}`} className="w-8 h-8" />);
    }
    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(calendarMonth.year, calendarMonth.month, day);
      const dateStr = `${calendarMonth.year}-${String(calendarMonth.month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const isSelected = selectedDate === dateStr;
      const isToday = date.getTime() === today.getTime();
      const isPast = date < today;

      days.push(
        <button
          key={day}
          onClick={() => !isPast && onDateSelect(dateStr)}
          disabled={isPast}
          className={`w-8 h-8 rounded-lg text-sm font-medium transition-all ${
            isSelected
              ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white shadow-lg shadow-purple-500/30'
              : isToday
                ? 'bg-purple-900/50 text-purple-300 border border-purple-500'
                : isPast
                  ? 'text-gray-600 cursor-not-allowed'
                  : 'text-gray-300 hover:bg-purple-900/30'
          }`}
        >
          {day}
        </button>
      );
    }

    return (
      <div className="mb-4">
        <label className="block text-sm text-gray-400 mb-2">{label}</label>
        <div className="bg-[#0d0d12] border border-purple-900/50 rounded-xl p-4">
          {/* Month Navigation */}
          <div className="flex items-center justify-between mb-4">
            <button
              onClick={() => {
                if (calendarMonth.month === 0) {
                  setCalendarMonth({ year: calendarMonth.year - 1, month: 11 });
                } else {
                  setCalendarMonth({ ...calendarMonth, month: calendarMonth.month - 1 });
                }
              }}
              className="p-1 text-gray-400 hover:text-white transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <span className="text-purple-300 font-medium">{monthNames[calendarMonth.month]} {calendarMonth.year}</span>
            <button
              onClick={() => {
                if (calendarMonth.month === 11) {
                  setCalendarMonth({ year: calendarMonth.year + 1, month: 0 });
                } else {
                  setCalendarMonth({ ...calendarMonth, month: calendarMonth.month + 1 });
                }
              }}
              className="p-1 text-gray-400 hover:text-white transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
          {/* Day Names */}
          <div className="grid grid-cols-7 gap-1 mb-2">
            {dayNames.map(day => (
              <div key={day} className="w-8 h-6 text-center text-xs text-gray-500 font-medium">{day}</div>
            ))}
          </div>
          {/* Days Grid */}
          <div className="grid grid-cols-7 gap-1">
            {days}
          </div>
        </div>
      </div>
    );
  };

  // Schedule Modal Component
  const ScheduleModal = () => (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 overflow-y-auto py-8">
      <div className="bg-[#1a1a2e] rounded-2xl p-6 w-full max-w-md border border-purple-700/50 shadow-2xl mx-4">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold text-purple-300">Schedule Task</h3>
          <button
            onClick={() => setShowScheduleModal(false)}
            className="text-gray-500 hover:text-gray-300"
          >
            ✕
          </button>
        </div>

        {/* Calendar Date Picker */}
        <Calendar
          selectedDate={scheduleConfig.date}
          onDateSelect={(date) => setScheduleConfig(prev => ({ ...prev, date }))}
          label="Execution Date"
        />

        {/* Time Picker */}
        <div className="mb-6">
          <label className="block text-sm text-gray-400 mb-2">Execution Time</label>
          <input
            type="time"
            value={scheduleConfig.time}
            onChange={(e) => setScheduleConfig(prev => ({ ...prev, time: e.target.value }))}
            className="w-full px-4 py-2 bg-[#0d0d12] border border-purple-900/50 rounded-lg text-gray-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>

        {/* Repeat Options */}
        <div className="mb-6">
          <label className="block text-sm text-gray-400 mb-3">Repeat</label>
          <div className="grid grid-cols-2 gap-2">
            {[
              { value: 'once', label: 'Once', desc: 'Single execution' },
              { value: 'daily', label: 'Daily', desc: 'Every day' },
              { value: 'weekly', label: 'Weekly', desc: 'Same day each week' },
              { value: 'custom', label: 'Custom', desc: 'Every X days' },
            ].map((option) => (
              <button
                key={option.value}
                onClick={() => setScheduleConfig(prev => ({ ...prev, repeatType: option.value as RepeatType }))}
                className={`p-3 rounded-lg border text-left transition-all ${
                  scheduleConfig.repeatType === option.value
                    ? 'bg-purple-600/30 border-purple-500 text-purple-300'
                    : 'bg-[#0d0d12] border-purple-900/50 text-gray-400 hover:border-purple-700'
                }`}
              >
                <div className="font-medium text-sm">{option.label}</div>
                <div className="text-xs opacity-70">{option.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Custom Days Input */}
        {scheduleConfig.repeatType === 'custom' && (
          <div className="mb-6">
            <label className="block text-sm text-gray-400 mb-2">Repeat every X days</label>
            <input
              type="number"
              min="1"
              max="365"
              value={scheduleConfig.customDays}
              onChange={(e) => setScheduleConfig(prev => ({ ...prev, customDays: parseInt(e.target.value) || 1 }))}
              className="w-full px-4 py-2 bg-[#0d0d12] border border-purple-900/50 rounded-lg text-gray-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
        )}

        {/* End Date for Repeats */}
        {scheduleConfig.repeatType !== 'once' && (
          <Calendar
            selectedDate={scheduleConfig.endDate || ''}
            onDateSelect={(date) => setScheduleConfig(prev => ({ ...prev, endDate: date }))}
            label="End Date (Optional)"
          />
        )}

        {/* Selected Date Display */}
        {scheduleConfig.date && (
          <div className="mb-4 p-3 bg-purple-900/20 border border-purple-700/30 rounded-lg">
            <div className="text-sm text-gray-400">Scheduled for:</div>
            <div className="text-lg font-medium text-purple-300">
              {new Date(`${scheduleConfig.date}T${scheduleConfig.time}`).toLocaleString('en-US', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
              })}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={() => setShowScheduleModal(false)}
            className="flex-1 px-4 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              if (scheduleConfig.date) {
                handleSaveNewPost(newPostContent);
              }
            }}
            disabled={!scheduleConfig.date}
            className="flex-1 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg hover:from-purple-700 hover:to-pink-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Schedule Task
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="h-screen flex flex-col bg-[#0a0a0f]">
      {/* Top Navigation Bar */}
      <header className="border-b border-purple-800/30">
        {/* Main Nav Row */}
        <div className="h-16 flex items-center justify-between px-6 bg-gradient-to-r from-[#1a1025] via-[#0f0a15] to-[#1a1025]">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-600 to-purple-800 flex items-center justify-center shadow-lg shadow-purple-500/20">
              <span className="text-white font-bold text-lg">F</span>
            </div>
            <div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-purple-400 via-pink-400 to-purple-400 bg-clip-text text-transparent">
                Digital FTE
              </h1>
              <p className="text-xs text-gray-500">Control Panel</p>
            </div>
          </div>

          {/* Channel Tabs */}
          <nav className="flex items-center gap-1 bg-[#0d0d12] rounded-xl p-1 border border-purple-900/30">
            {(Object.keys(SOURCE_CONFIG) as Source[]).map((source) => {
              const isActive = activeSource === source;
              const gradientClass = source === 'gmail'
                ? 'from-red-600/20 to-red-800/20 text-red-400 border-red-500/30'
                : source === 'whatsapp'
                  ? 'from-green-600/20 to-green-800/20 text-green-400 border-green-500/30'
                  : source === 'linkedin'
                    ? 'from-blue-600/20 to-blue-800/20 text-blue-400 border-blue-500/30'
                    : source === 'x'
                      ? 'from-gray-600/20 to-gray-800/20 text-gray-300 border-gray-500/30'
                      : source === ''
                        ? 'from-pink-600/20 to-purple-800/20 text-pink-400 border-pink-500/30'
                        : source === 'facebook'
                          ? 'from-blue-600/20 to-blue-800/20 text-blue-400 border-blue-500/30'
                          : source === 'odoo'
                            ? 'from-purple-600/20 to-purple-800/20 text-purple-400 border-purple-500/30'
                            : 'from-cyan-600/20 to-cyan-800/20 text-cyan-400 border-cyan-500/30';

              return (
                <button
                  key={source}
                  onClick={() => handleSourceChange(source)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? `bg-gradient-to-r ${gradientClass} border`
                      : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/50'
                  }`}
                >
                  {SOURCE_CONFIG[source].logo}
                  <span>{SOURCE_CONFIG[source].name}</span>
                </button>
              );
            })}
          </nav>

          {/* Status */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm">
              <span className={`w-2 h-2 rounded-full animate-pulse shadow-lg ${connected ? 'bg-green-500 shadow-green-500/50' : 'bg-yellow-500 shadow-yellow-500/50'}`}></span>
              <span className="text-gray-400">{connected ? 'Live Sync' : 'Offline'}</span>
            </div>
            <button
              onClick={handleManualRefresh}
              disabled={isRefreshing}
              className={`p-2 rounded-lg transition-all ${isRefreshing ? 'bg-purple-600/50' : 'bg-gray-800 hover:bg-gray-700'} border border-purple-900/30`}
              title="Refresh files"
            >
              <svg className={`w-4 h-4 text-gray-300 ${isRefreshing ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            <div className="h-8 w-px bg-purple-800/30"></div>
            <div className="text-sm text-gray-500">
              {new Date().toLocaleTimeString()}
            </div>
          </div>
        </div>

        {/* Folder Tabs */}
        <div className="flex items-center justify-between px-6 py-2 bg-gradient-to-b from-[#2a2a3e] via-[#1e1e2e] to-[#16162a] border-t border-purple-600/30">
          <div className="flex items-center gap-2">
            {SOURCE_CONFIG[activeSource].folders.map((folder, index) => {
              const isActive = activeFolder === folder.path;
              const sourceColors = activeSource === 'gmail'
                ? { active: 'from-red-500 to-red-600', border: 'border-red-400', shadow: 'shadow-red-500/50', glow: '0 0 20px rgba(239,68,68,0.5)' }
                : activeSource === 'whatsapp'
                  ? { active: 'from-green-500 to-green-600', border: 'border-green-400', shadow: 'shadow-green-500/50', glow: '0 0 20px rgba(34,197,94,0.5)' }
                  : activeSource === 'linkedin'
                    ? { active: 'from-blue-500 to-blue-600', border: 'border-blue-400', shadow: 'shadow-blue-500/50', glow: '0 0 20px rgba(59,130,246,0.5)' }
                    : activeSource === 'x'
                      ? { active: 'from-gray-500 to-gray-600', border: 'border-gray-400', shadow: 'shadow-gray-500/50', glow: '0 0 20px rgba(156,163,175,0.5)' }
                      : activeSource === ''
                        ? { active: 'from-pink-500 to-purple-600', border: 'border-pink-400', shadow: 'shadow-pink-500/50', glow: '0 0 20px rgba(236,72,153,0.5)' }
                        : activeSource === 'facebook'
                          ? { active: 'from-blue-500 to-blue-600', border: 'border-blue-400', shadow: 'shadow-blue-500/50', glow: '0 0 20px rgba(59,130,246,0.5)' }
                          : activeSource === 'odoo'
                            ? { active: 'from-purple-500 to-purple-600', border: 'border-purple-400', shadow: 'shadow-purple-500/50', glow: '0 0 20px rgba(168,85,247,0.5)' }
                            : { active: 'from-cyan-500 to-cyan-600', border: 'border-cyan-400', shadow: 'shadow-cyan-500/50', glow: '0 0 20px rgba(6,182,212,0.5)' };

              return (
                <button
                  key={folder.path}
                  onClick={() => setActiveFolder(folder.path)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200 border ${
                    isActive
                      ? `bg-gradient-to-r ${sourceColors.active} text-white shadow-lg ${sourceColors.shadow} ${sourceColors.border}`
                      : 'bg-gray-700 text-gray-200 hover:text-white hover:bg-gray-600 border-gray-500'
                  }`}
                  style={isActive ? { boxShadow: sourceColors.glow } : {}}
                >
                  <span>{folder.icon}</span>
                  <span>{folder.name}</span>
                  {isActive && files.length > 0 && (
                    <span className="ml-1 px-2 py-0.5 text-xs bg-white/30 rounded-full font-bold">
                      {files.length}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* New Post Request button - prominent for social platforms */}
          {['linkedin', 'x', '', 'facebook'].includes(activeSource) ? (
            <button
              onClick={handleCreatePost}
              className="flex items-center gap-2 px-8 py-3 bg-gradient-to-r from-blue-600 via-purple-600 to-pink-600 text-white rounded-xl text-base font-bold hover:from-blue-500 hover:via-purple-500 hover:to-pink-500 transition-all shadow-[0_0_30px_rgba(168,85,247,0.5)] hover:shadow-[0_0_40px_rgba(168,85,247,0.7)] border-2 border-purple-400/50 hover:border-purple-300/70 animate-pulse hover:animate-none transform hover:scale-105"
            >
              <span className="text-2xl font-bold drop-shadow-lg">✨</span>
              <span className="drop-shadow-md">New Post</span>
            </button>
          ) : activeSource === 'odoo' ? (
            <button
              onClick={() => {
                const content = `# Invoice Request

**Client:**
**Email:**
**Services:**
- Service Name - X hours @ $Y/hr = $Z

**Total:** $0

**Notes:**
`;
                setIsNewPostMode(true);
                setNewPostContent(content);
                setSelectedFile(null);
                setFileContent('');
              }}
              className="flex items-center gap-2 px-8 py-3 bg-gradient-to-r from-purple-600 via-purple-600 to-pink-600 text-white rounded-xl text-base font-bold hover:from-purple-500 hover:to-pink-500 transition-all shadow-[0_0_30px_rgba(168,85,247,0.5)] hover:shadow-[0_0_40px_rgba(168,85,247,0.7)] border-2 border-purple-400/50 hover:border-purple-300/70 animate-pulse hover:animate-none transform hover:scale-105"
            >
              <span className="text-2xl font-bold drop-shadow-lg">🧾</span>
              <span className="drop-shadow-md">New Invoice</span>
            </button>
          ) : null}
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* File List */}
        <aside className="w-96 border-r border-purple-900/30 bg-[#0d0d12] flex flex-col">
          <div className="p-3 border-b border-purple-900/30 bg-gradient-to-r from-purple-900/10 to-transparent">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-purple-300">Files</h2>
              <span className="text-xs text-gray-500 bg-purple-900/30 px-2 py-0.5 rounded-full">
                {files.length} items
              </span>
            </div>
          </div>
          <div className="flex-1 overflow-auto">
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <div className="text-purple-400 animate-pulse">Loading...</div>
              </div>
            ) : error ? (
              <div className="flex items-center justify-center h-32">
                <div className="text-red-400">{error}</div>
              </div>
            ) : files.length === 0 ? (
              <div className="flex items-center justify-center h-32 text-gray-600">
                <div className="text-center">
                  <div className="text-4xl mb-2 opacity-50">📂</div>
                  <div className="text-sm">No files</div>
                </div>
              </div>
            ) : (
              <EmailList
                files={files}
                selectedFile={selectedFile}
                onSelect={setSelectedFile}
                folder={activeFolder}
                activeSource={activeSource}
              />
            )}
          </div>
        </aside>

        {/* Main Panel */}
        <main className="flex-1 bg-gradient-to-br from-[#0f0a15] via-[#0a0a0f] to-[#0f0a15] overflow-hidden">
          {isNewPostMode ? (
            <>
              <div className="h-full flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-purple-900/50 bg-[#1a1a1a]">
                  <div className="flex-1 min-w-0 mr-4">
                    <h2 className="text-lg font-semibold truncate text-purple-300">
                      ✨ New {activeSource === 'x' ? 'X (Twitter)' : activeSource.charAt(0).toUpperCase() + activeSource.slice(1)} Post
                    </h2>
                    <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
                      <span className="text-yellow-400">⚠️ Unsaved - Write your requirements below</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleCancelNewPost}
                      className="px-4 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 transition-colors border border-gray-700"
                    >
                      Cancel
                    </button>
                    {activeSource !== 'odoo' && (
                      <button
                        onClick={() => setShowScheduleModal(true)}
                        className="px-4 py-1.5 text-sm bg-gradient-to-r from-orange-600 to-amber-600 text-white rounded-lg hover:from-orange-700 hover:to-amber-700 transition-colors font-semibold flex items-center gap-1"
                      >
                        <span>📅</span> Schedule
                      </button>
                    )}
                    <button
                      onClick={() => handleSaveNewPost(newPostContent)}
                      className="px-6 py-1.5 text-sm bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-700 hover:to-purple-700 transition-colors font-semibold shadow-lg shadow-purple-500/30"
                    >
                      💾 Save Now
                    </button>
                  </div>
                </div>

                {/* Content Editor */}
                <div className="flex-1 overflow-auto p-4">
                  <textarea
                    value={newPostContent}
                    onChange={(e) => setNewPostContent(e.target.value)}
                    className="w-full h-full p-4 font-mono text-sm bg-[#0d0d0d] text-gray-300 border border-purple-900/50 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                    placeholder="Write your post requirements here..."
                  />
                </div>

                {/* Footer */}
                <div className="p-3 border-t border-purple-900/50 bg-[#1a1a1a] flex items-center justify-between text-sm text-gray-500">
                  <span>📝 Edit the requirements above and click Save when ready</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => navigator.clipboard.writeText(newPostContent)}
                      className="px-3 py-1 text-xs bg-gray-800 rounded hover:bg-gray-700 transition-colors border border-gray-700"
                    >
                      Copy Content
                    </button>
                  </div>
                </div>
              </div>

              {/* Schedule Modal */}
              {showScheduleModal && <ScheduleModal />}
            </>
          ) : selectedFile && fileContent ? (
            <EmailViewer
              content={fileContent}
              filename={selectedFile}
              folder={activeFolder}
              activeSource={activeSource}
              onApprove={handleApprove}
              onReject={handleReject}
              onMoveToDone={handleMoveToDone}
            />
          ) : (
            <div className="h-full flex items-center justify-center text-gray-600">
              <div className="text-center max-w-md">
                <div className="w-24 h-24 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-purple-900/30 to-purple-800/10 flex items-center justify-center border border-purple-800/30">
                  <span className="text-4xl opacity-60">{SOURCE_CONFIG[activeSource].logo}</span>
                </div>
                <p className="text-lg font-medium bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
                  {SOURCE_CONFIG[activeSource].name}
                </p>
                <p className="text-sm mt-2 text-gray-500">
                  Select a file to view or edit
                </p>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Footer */}
      <footer className="h-10 border-t border-purple-900/30 bg-[#0d0d12] px-6 flex items-center justify-between text-xs">
        <div className="flex items-center gap-4 text-gray-500">
          <span className="text-purple-400">Digital FTE</span>
          <span>•</span>
          <span>HITL Safety Active</span>
        </div>
        <div className="flex items-center gap-2 text-gray-600">
          <span className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-pulse"></span>
          <span>Real-time sync</span>
        </div>
      </footer>
    </div>
  );
}

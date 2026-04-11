'use client';

import React, { useState, useCallback, useEffect } from 'react';
import { useFileWatch, useFiles, FileEvent } from '@/hooks/useFileWatch';
import { EmailList } from '@/components/Sidebar';
import { EmailViewer } from '@/components/EmailViewer';

type Source = 'gmail' | 'whatsapp' | 'linkedin';

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

const SOURCE_CONFIG: Record<Source, SourceConfig> = {
  gmail: {
    name: 'Gmail',
    logo: <GmailLogo />,
    folders: [
      { name: 'Needs Action', icon: '🎯', path: 'Needs_Action' },
      { name: 'Drafts', icon: '📝', path: 'Gmail_Messages/Draft' },
      { name: 'Approved', icon: '✅', path: 'Gmail_Messages/Approved' },
      { name: 'Sent', icon: '📤', path: 'Gmail_Messages/Done' },
    ],
  },
  whatsapp: {
    name: 'WhatsApp',
    logo: <WhatsAppLogo />,
    folders: [
      { name: 'Needs Action', icon: '🎯', path: 'Needs_Action' },
      { name: 'Drafts', icon: '📝', path: 'WhatsApp_Messages/Draft' },
      { name: 'Approved', icon: '✅', path: 'WhatsApp_Messages/Approved' },
      { name: 'Sent', icon: '📤', path: 'WhatsApp_Messages/Done' },
    ],
  },
  linkedin: {
    name: 'LinkedIn',
    logo: <LinkedInLogo />,
    folders: [
      { name: 'New Post', icon: '📝', path: 'linkedin_post' },
      { name: 'Drafts', icon: '📄', path: 'LinkedIn_Posts/Draft' },
      { name: 'Approved', icon: '✅', path: 'LinkedIn_Posts/Approved' },
      { name: 'Published', icon: '🚀', path: 'LinkedIn_Posts/Done' },
    ],
  },
};

export default function Home() {
  const [activeSource, setActiveSource] = useState<Source>('gmail');
  const [activeFolder, setActiveFolder] = useState<string>('Needs_Action');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');

  // Pass source to filter files correctly for Needs_Action folder
  const { files, loading, error, refresh } = useFiles(activeFolder, activeFolder === 'Needs_Action' ? activeSource : undefined);

  // Real-time updates via SSE
  useFileWatch(
    useCallback(
      (event: FileEvent) => {
        if (event.folder === activeFolder) {
          refresh();
        }
      },
      [activeFolder, refresh]
    )
  );

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
  }, [activeFolder]);

  // Handle source change
  const handleSourceChange = (source: Source) => {
    setActiveSource(source);
    setActiveFolder(SOURCE_CONFIG[source].folders[0].path);
    setSelectedFile(null);
  };

  const handleApprove = async (newContent: string) => {
    if (!selectedFile) return;

    await fetch('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folder: activeFolder,
        filename: selectedFile,
        content: newContent,
      }),
    });

    const targetFolder = activeSource === 'gmail'
      ? 'Gmail_Messages/Approved'
      : activeSource === 'whatsapp'
        ? 'WhatsApp_Messages/Approved'
        : 'LinkedIn_Posts/Approved';

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

  const handleReject = async () => {
    if (!selectedFile) return;

    await fetch('/api/move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sourceFolder: activeFolder,
        targetFolder: 'Rejected',
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
        : 'LinkedIn_Posts/Done';

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

  const handleCreatePost = async () => {
    const content = `# LinkedIn Post Request

## Requirements

**Topic:** Enter your topic here
**Tone:** Professional
**Hashtags:** 3-5 relevant hashtags

## Additional Notes

Add any specific requirements here.

---
*Created: ${new Date().toISOString()}*
`;

    const filename = `${new Date().toISOString().split('T')[0]}_${Date.now()}_post_request.md`;

    await fetch('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folder: 'linkedin_post',
        filename,
        content,
      }),
    });

    refresh();
  };

  return (
    <div className="h-screen flex flex-col bg-[#0a0a0f]">
      {/* Top Navigation Bar */}
      <header className="h-16 border-b border-purple-800/30 bg-gradient-to-r from-[#1a1025] via-[#0f0a15] to-[#1a1025]">
        <div className="h-full flex items-center justify-between px-6">
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
                  : 'from-blue-600/20 to-blue-800/20 text-blue-400 border-blue-500/30';

              return (
                <button
                  key={source}
                  onClick={() => handleSourceChange(source)}
                  className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
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
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse shadow-lg shadow-green-500/50"></span>
              <span className="text-gray-400">System Active</span>
            </div>
            <div className="h-8 w-px bg-purple-800/30"></div>
            <div className="text-sm text-gray-500">
              {new Date().toLocaleTimeString()}
            </div>
          </div>
        </div>

        {/* Folder Tabs */}
        <div className="flex items-center justify-between px-6 py-2 bg-[#0d0d12]/50 border-t border-purple-900/20">
          <div className="flex items-center gap-1">
            {SOURCE_CONFIG[activeSource].folders.map((folder, index) => {
              const isActive = activeFolder === folder.path;
              return (
                <button
                  key={folder.path}
                  onClick={() => setActiveFolder(folder.path)}
                  className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm transition-all duration-200 ${
                    isActive
                      ? 'bg-purple-600/20 text-purple-300 border border-purple-500/30'
                      : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/30'
                  }`}
                >
                  <span>{folder.icon}</span>
                  <span>{folder.name}</span>
                  {isActive && files.length > 0 && (
                    <span className="ml-1 px-1.5 py-0.5 text-xs bg-purple-500/30 rounded-full">
                      {files.length}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {activeSource === 'linkedin' && (
            <button
              onClick={handleCreatePost}
              className="flex items-center gap-2 px-4 py-1.5 bg-gradient-to-r from-purple-600 to-purple-700 text-white rounded-lg text-sm hover:from-purple-700 hover:to-purple-800 transition-all shadow-lg shadow-purple-500/20"
            >
              <span>+</span>
              <span>New Post</span>
            </button>
          )}
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* File List */}
        <aside className="w-80 border-r border-purple-900/30 bg-[#0d0d12] flex flex-col">
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
          {selectedFile && fileContent ? (
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

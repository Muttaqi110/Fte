'use client';

type Source = 'gmail' | 'whatsapp' | 'linkedin';

interface EmailListProps {
  files: Array<{
    name: string;
    modified: string;
    size: number;
    content: string;
  }>;
  selectedFile: string | null;
  onSelect: (filename: string) => void;
  folder: string;
  activeSource: Source;
}

export function EmailList({ files, selectedFile, onSelect, folder, activeSource }: EmailListProps) {
  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const today = new Date();

    if (date.toDateString() === today.toDateString()) {
      return formatTime(dateStr);
    }
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  // Extract display info from content
  const getFileInfo = (file: { name: string; content: string }) => {
    const content = file.content;

    // Try to extract title
    const titleMatch = content.match(/^#\s+(.+)$/m);
    let title = titleMatch ? titleMatch[1] : file.name.replace('.md', '').replace(/_/g, ' ');

    // Extract source
    const sourceMatch = content.match(/\*\*Source\*\*\s*\|\s*([^|]+)/i);
    const source = sourceMatch?.[1]?.trim()?.toLowerCase() || '';

    // Extract contact/from
    const contactMatch = content.match(/\*\*Contact\*\*\s*\|\s*([^|]+)/i);
    const fromMatch = content.match(/\*\*From\*\*\s*\|\s*([^|]+)/i);
    const contact = contactMatch?.[1]?.trim() || fromMatch?.[1]?.trim() || '';

    // Extract subject
    const subjectMatch = content.match(/\*\*Subject\*\*\s*\|\s*([^|]+)/i);
    const subject = subjectMatch?.[1]?.trim() || '';

    // Determine type
    const isWhatsApp = source.includes('whatsapp') || file.name.includes('whatsapp');
    const isLinkedIn = source.includes('linkedin') || file.name.includes('linkedin') || folder.includes('linkedin');
    const isGmail = source.includes('email') || source.includes('gmail') || (!isWhatsApp && !isLinkedIn);

    // Get display title
    let displayTitle = title;
    if (contact && !title.includes(contact)) {
      displayTitle = contact;
    } else if (subject && subject !== 'No Subject') {
      displayTitle = subject;
    }

    return {
      title: displayTitle.slice(0, 40) + (displayTitle.length > 40 ? '...' : ''),
      contact: contact.slice(0, 30),
      source: isWhatsApp ? 'whatsapp' : isLinkedIn ? 'linkedin' : 'gmail',
      icon: isWhatsApp ? '💬' : isLinkedIn ? '💼' : '📧',
      color: isWhatsApp ? 'text-green-400' : isLinkedIn ? 'text-purple-400' : 'text-red-400',
      bgColor: isWhatsApp ? 'bg-green-500/10' : isLinkedIn ? 'bg-purple-500/10' : 'bg-red-500/10',
    };
  };

  return (
    <div className="divide-y divide-purple-900/30">
      {files.length === 0 ? (
        <div className="p-8 text-center">
          <div className="text-4xl mb-2 opacity-50">📭</div>
          <p className="text-sm text-gray-600">No files in this folder</p>
        </div>
      ) : (
        files.map((file) => {
          const info = getFileInfo(file);
          return (
            <button
              key={file.name}
              onClick={() => onSelect(file.name)}
              className={`w-full text-left p-3 hover:bg-purple-900/20 transition-all ${
                selectedFile === file.name
                  ? 'bg-purple-900/30 border-l-2 border-purple-500'
                  : 'border-l-2 border-transparent'
              }`}
            >
              <div className="flex items-start gap-2">
                <span className="text-lg mt-0.5">{info.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate text-gray-200">
                    {info.title}
                  </div>
                  {info.contact && info.contact !== info.title && (
                    <div className="text-xs text-gray-500 truncate mt-0.5">
                      {info.contact}
                    </div>
                  )}
                  <div className="text-xs text-gray-600 mt-1 flex justify-between">
                    <span>{formatDate(file.modified)}</span>
                    <span>{(file.size / 1024).toFixed(1)} KB</span>
                  </div>
                </div>
              </div>
            </button>
          );
        })
      )}
    </div>
  );
}

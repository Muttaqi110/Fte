'use client';

type Source = 'gmail' | 'whatsapp' | 'linkedin' | 'x' | 'facebook' | 'odoo';

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

    // Determine if draft folder
    const isDraft = folder.includes('Draft') || folder.includes('draft');

    // Extract From (for inbox items)
    const fromMatch = content.match(/\*\*From\*\*\s*\|\s*([^|]+)/i);
    const contactMatch = content.match(/\*\*Contact\*\*\s*\|\s*([^|]+)/i);
    const fromName = fromMatch?.[1]?.trim() || contactMatch?.[1]?.trim() || '';

    // Extract To (for drafts)
    const toMatch = content.match(/\*\*To\*\*\s*\|\s*([^|]+)/i);
    const toName = toMatch?.[1]?.trim() || '';

    // Extract Subject
    const subjectMatch = content.match(/\*\*Subject\*\*\s*\|\s*([^|]+)/i);
    const subject = subjectMatch?.[1]?.trim() || '';

    // Determine source type based on activeSource and folder
    const isWhatsApp = activeSource === 'whatsapp';
    const isLinkedIn = activeSource === 'linkedin';
    const isX = activeSource === 'x';
    const isFacebook = activeSource === 'facebook';
    const isGmail = activeSource === 'gmail';
    const isOdoo = activeSource === 'odoo';

    // Create clean display title
    let displayTitle = '';
    let subtitle = '';

    if (isOdoo) {
      // For Odoo invoices: extract client and amount
      const clientMatch = content.match(/\*\*Name:\*\*\s*(.+)/i);
      const amountMatch = content.match(/\*\*TOTAL:\*\*\s*\$?([\d,]+)/i);
      const invoiceIdMatch = content.match(/"invoice_id":\s*(\d+)/);

      displayTitle = clientMatch?.[1]?.trim() || 'Invoice';
      subtitle = amountMatch ? `$${amountMatch[1]}` : (invoiceIdMatch ? `ID: ${invoiceIdMatch[1]}` : '');
    } else if (isDraft || folder.includes('_post')) {
      // For drafts and post requests: show filename or topic
      const topicMatch = content.match(/\*\*Topic:\*\*\s*([^\n]+)/i);
      displayTitle = topicMatch?.[1]?.trim() || file.name.replace('.md', '').slice(0, 30);
      subtitle = folder.includes('_post') ? 'Post Request' : 'Draft';
    } else {
      // For inbox: show sender name
      displayTitle = fromName || 'Unknown Sender';
      subtitle = subject && subject !== 'No Subject' ? subject : '';
    }

    // Get platform-specific styling
    const getPlatformStyle = () => {
      if (isWhatsApp) return { icon: '💬', bgColor: 'bg-green-500/10' };
      if (isLinkedIn) return { icon: '💼', bgColor: 'bg-blue-500/10' };
      if (isX) return { icon: '✖️', bgColor: 'bg-gray-500/10' };
      if (isFacebook) return { icon: '📘', bgColor: 'bg-blue-500/10' };
      if (isOdoo) return { icon: '🧾', bgColor: 'bg-purple-500/10' };
      return { icon: '📧', bgColor: 'bg-red-500/10' };
    };

    const style = getPlatformStyle();

    return {
      title: displayTitle.slice(0, 30) + (displayTitle.length > 30 ? '...' : ''),
      subtitle: subtitle.slice(0, 35),
      source: activeSource,
      icon: style.icon,
      bgColor: style.bgColor,
    };
  };

  return (
    <div className="py-2">
      {files.length === 0 ? (
        <div className="p-8 text-center">
          <div className="text-4xl mb-2 opacity-50">📭</div>
          <p className="text-sm text-gray-600">No files in this folder</p>
        </div>
      ) : (
        files.map((file) => {
          const info = getFileInfo(file);
          const isSelected = selectedFile === file.name;
          return (
            <button
              key={file.name}
              onClick={() => onSelect(file.name)}
              className={`w-full text-left px-4 py-3 hover:bg-purple-900/20 transition-all ${
                isSelected
                  ? 'bg-purple-900/30 border-l-2 border-purple-400'
                  : 'border-l-2 border-transparent'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${info.bgColor}`}>
                  <span className="text-sm">{info.icon}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate text-gray-200">
                    {info.title}
                  </div>
                  {info.subtitle && (
                    <div className="text-xs text-gray-400 truncate">
                      {info.subtitle}
                    </div>
                  )}
                  <div className="text-xs text-gray-500 mt-0.5">
                    {formatDate(file.modified)}
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

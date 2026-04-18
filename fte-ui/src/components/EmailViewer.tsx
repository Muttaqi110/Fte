'use client';

import { useState, useEffect } from 'react';

type Source = 'gmail' | 'whatsapp' | 'linkedin' | 'x' | 'facebook' | 'odoo';

interface EmailViewerProps {
  content: string;
  filename: string;
  folder: string;
  activeSource: Source;
  onApprove: (newContent: string) => Promise<void>;
  onReject: () => Promise<void>;
  onMoveToDone: () => Promise<void>;
}

export function EmailViewer({
  content,
  filename,
  folder,
  activeSource,
  onApprove,
  onReject,
  onMoveToDone
}: EmailViewerProps) {
  const [editedContent, setEditedContent] = useState(content);
  const [saving, setSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // Reset edited content when file changes
  useEffect(() => {
    setEditedContent(content);
    setIsEditing(false);
  }, [content, filename]);

  // Determine folder type - use activeSource for social posts
  const isDraft = folder.includes('/Draft') || folder === 'linkedin_post' || folder === 'x_post' || folder === 'facebook_post';
  const isApproved = folder.includes('/Approved');
  const isDone = folder.includes('/Done');
  const isNeedsAction = folder === 'Needs_Action';
  const isLinkedInPost = activeSource === 'linkedin' && (folder.includes('LinkedIn_Posts') || folder === 'linkedin_post');
  const isXPost = activeSource === 'x' && (folder.includes('X_Posts') || folder === 'x_post');
  const isFacebookPost = activeSource === 'facebook' && (folder.includes('Facebook_Posts') || folder === 'facebook_post');
  const isSocialPost = isLinkedInPost || isXPost || isFacebookPost;

  const handleApprove = async () => {
    console.log('handleApprove called', { filename, folder, activeSource });
    setSaving(true);
    try {
      await onApprove(editedContent);
      console.log('Approve completed');
    } catch (error) {
      console.error('Approve error:', error);
    }
    setSaving(false);
  };

  const handleReject = async () => {
    setSaving(true);
    await onReject();
    setSaving(false);
  };

  const handleMoveToDone = async () => {
    setSaving(true);
    await onMoveToDone();
    setSaving(false);
  };

  const handleSave = async () => {
    setSaving(true);
    await fetch('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folder,
        filename,
        content: editedContent,
      }),
    });
    setSaving(false);
    setIsEditing(false);
  };

  // Extract title from content
  const getTitle = () => {
    const titleMatch = editedContent.match(/^#\s+(.+)$/m);
    if (titleMatch) return titleMatch[1];
    return filename.replace('.md', '').replace(/_/g, ' ');
  };

  // Extract metadata - handle both table format and plain format
  const getMetadata = () => {
    // Table format: | **From** | value |
    const fromMatch = editedContent.match(/\*\*From\*\*\s*\|\s*([^|]+)/);
    const toMatch = editedContent.match(/\*\*To\*\*\s*\|\s*([^|]+)/);
    const contactMatch = editedContent.match(/\*\*Contact\*\*\s*\|\s*([^|]+)/);
    const subjectMatch = editedContent.match(/\*\*Subject\*\*\s*\|\s*([^|]+)/);
    const sourceMatch = editedContent.match(/\*\*Source\*\*\s*\|\s*([^|]+)/);

    // Plain format: **To:** value
    const toPlainMatch = editedContent.match(/\*\*To:\*\*\s*([^\n]+)/);
    const fromPlainMatch = editedContent.match(/\*\*From:\*\*\s*([^\n]+)/);
    const subjectPlainMatch = editedContent.match(/\*\*Subject:\*\*\s*([^\n]+)/);
    const sourcePlainMatch = editedContent.match(/\*\*Source:\*\*\s*([^\n]+)/);

    // Determine if draft
    const isDraftFolder = folder.includes('Draft') || folder === 'linkedin_post';

    const from = fromMatch?.[1]?.trim() || contactMatch?.[1]?.trim() || fromPlainMatch?.[1]?.trim() || '';
    const to = toMatch?.[1]?.trim() || toPlainMatch?.[1]?.trim() || '';
    const subject = subjectMatch?.[1]?.trim() || subjectPlainMatch?.[1]?.trim() || '';
    const source = sourceMatch?.[1]?.trim() || sourcePlainMatch?.[1]?.trim() || (isLinkedInPost ? 'LinkedIn' : 'Email');

    return {
      from,
      to,
      subject,
      source,
      isDraft: isDraftFolder,
    };
  };

  const metadata = getMetadata();

  // Get approve button text based on source
  const getApproveButtonText = () => {
    if (saving) return 'Saving...';
    if (isSocialPost) return 'Approve & Publish';
    return 'Approve & Send';
  };

  // Get platform name for display
  const getPlatformName = () => {
    if (isLinkedInPost) return 'LinkedIn';
    if (isXPost) return 'X (Twitter)';
    if (isFacebookPost) return 'Facebook';
    return null;
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-purple-900/50 bg-[#1a1a1a]">
        <div className="flex-1 min-w-0 mr-4">
          <h2 className="text-lg font-semibold truncate text-purple-300">
            {getTitle()}
          </h2>
          <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
            {!isSocialPost && (
              <>
                {metadata.isDraft ? (
                  <span>To: <span className="text-gray-400">{metadata.to || 'Recipient'}</span></span>
                ) : (
                  <span>From: <span className="text-gray-400">{metadata.from || 'Unknown'}</span></span>
                )}
                {metadata.subject && metadata.subject !== 'No Subject' && (
                  <span>Subject: <span className="text-gray-400">{metadata.subject}</span></span>
                )}
              </>
            )}
            {isSocialPost && (
              <span className="text-purple-400">{getPlatformName()} Post</span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {isDone ? (
            <span className="px-3 py-1.5 text-sm bg-gray-800 text-gray-500 rounded-full flex items-center gap-1 border border-gray-700">
              <span>✓</span> {isSocialPost ? 'Published' : 'Completed'}
            </span>
          ) : isApproved ? (
            <div className="flex gap-2">
              <span className="px-3 py-1.5 text-sm bg-green-900/30 text-green-400 rounded-full flex items-center gap-1 border border-green-800">
                <span>✓</span> Approved - Pending {isSocialPost ? 'Publish' : 'Send'}
              </span>
            </div>
          ) : isDraft ? (
            <>
              <button
                onClick={() => setIsEditing(!isEditing)}
                className="px-4 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 transition-colors border border-gray-700"
              >
                {isEditing ? 'Cancel' : 'Edit'}
              </button>
              {isEditing && (
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-4 py-1.5 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save'}
                </button>
              )}
              <button
                onClick={handleApprove}
                disabled={saving}
                className="px-4 py-1.5 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
              >
                {getApproveButtonText()}
              </button>
              <button
                onClick={handleReject}
                disabled={saving}
                className="px-4 py-1.5 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                Reject
              </button>
            </>
          ) : isNeedsAction ? (
            <span className="px-3 py-1.5 text-sm bg-yellow-900/30 text-yellow-400 rounded-full border border-yellow-800">
              Processing...
            </span>
          ) : (
            <span className="px-3 py-1.5 text-sm bg-purple-900/30 text-purple-400 rounded-full border border-purple-800">
              Review Required
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {isEditing ? (
          <textarea
            value={editedContent}
            onChange={(e) => setEditedContent(e.target.value)}
            className="w-full h-full p-4 font-mono text-sm bg-[#0d0d0d] text-gray-300 border border-purple-900/50 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            placeholder="Edit content here..."
          />
        ) : (
          <div className="prose prose-invert max-w-none">
            <pre className="whitespace-pre-wrap text-sm font-mono bg-[#0d0d0d] text-gray-300 p-4 rounded-lg border border-purple-900/50 overflow-auto">
              {editedContent}
            </pre>
          </div>
        )}
      </div>

      {/* Footer with quick actions */}
      {!isDone && !isApproved && (
        <div className="p-3 border-t border-purple-900/50 bg-[#1a1a1a] flex items-center justify-between text-sm text-gray-500">
          <span>
            {isDraft ? `Edit the content above and approve to ${isSocialPost ? 'publish' : 'send'}` : 'Waiting for draft to be generated'}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => navigator.clipboard.writeText(editedContent)}
              className="px-3 py-1 text-xs bg-gray-800 rounded hover:bg-gray-700 transition-colors border border-gray-700"
            >
              Copy Content
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

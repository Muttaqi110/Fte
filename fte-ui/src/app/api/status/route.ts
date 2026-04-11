import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const VAULT_PATH = path.join(process.cwd(), '..', 'AI_Employee_Vault');

export async function GET() {
  try {
    const folders = [
      // Gmail
      'Inbox',
      'Gmail_Messages/Draft',
      'Gmail_Messages/Approved',
      'Gmail_Messages/Done',
      // WhatsApp
      'whatsapp_inbox',
      'WhatsApp_Messages/Draft',
      'WhatsApp_Messages/Approved',
      'WhatsApp_Messages/Done',
      // LinkedIn
      'linkedin_post',
      'LinkedIn_Posts/Draft',
      'LinkedIn_Posts/Approved',
      'LinkedIn_Posts/Done',
      // General
      'Needs_Action',
      'Plans',
      'Rejected',
      'Done',
    ];

    const stats: Record<string, { count: number; latest?: string; icon: string }> = {};

    folders.forEach(folder => {
      const folderPath = path.join(VAULT_PATH, folder);

      if (fs.existsSync(folderPath)) {
        const files = fs.readdirSync(folderPath)
          .filter(f => f.endsWith('.md') && f !== '.gitkeep');

        stats[folder] = {
          count: files.length,
          icon: getFolderIcon(folder)
        };

        if (files.length > 0) {
          const latestFile = files
            .map(f => ({ name: f, mtime: fs.statSync(path.join(folderPath, f)).mtime }))
            .sort((a, b) => b.mtime.getTime() - a.mtime.getTime())[0];
          stats[folder].latest = latestFile?.mtime.toISOString();
        }
      } else {
        stats[folder] = { count: 0, icon: getFolderIcon(folder) };
      }
    });

    // Check if system is running
    const logPath = path.join(VAULT_PATH, 'Logs', 'system.log');
    let systemRunning = false;

    if (fs.existsSync(logPath)) {
      const logStats = fs.statSync(logPath);
      const lastModified = logStats.mtime.getTime();
      const now = Date.now();
      systemRunning = (now - lastModified) < 5 * 60 * 1000;
    }

    return NextResponse.json({
      folders: stats,
      systemRunning,
      tier: 'silver',
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}

function getFolderIcon(folder: string): string {
  const icons: Record<string, string> = {
    // Gmail
    'Inbox': '📧',
    'Gmail_Messages/Draft': '📝',
    'Gmail_Messages/Approved': '✅',
    'Gmail_Messages/Done': '📤',
    // WhatsApp
    'whatsapp_inbox': '💬',
    'WhatsApp_Messages/Draft': '📝',
    'WhatsApp_Messages/Approved': '✅',
    'WhatsApp_Messages/Done': '📤',
    // LinkedIn
    'linkedin_post': '📝',
    'LinkedIn_Posts/Draft': '📄',
    'LinkedIn_Posts/Approved': '✅',
    'LinkedIn_Posts/Done': '🚀',
    // General
    'Needs_Action': '🎯',
    'Plans': '📋',
    'Rejected': '❌',
    'Done': '✓',
  };
  return icons[folder] || '📁';
}

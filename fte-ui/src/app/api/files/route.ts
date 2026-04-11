import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const VAULT_PATH = path.join(process.cwd(), '..', 'AI_Employee_Vault');

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const folder = searchParams.get('folder') || 'Draft';
  const source = searchParams.get('source'); // 'gmail', 'whatsapp', 'linkedin'

  const folderPath = path.join(VAULT_PATH, folder);

  try {
    if (!fs.existsSync(folderPath)) {
      return NextResponse.json({ files: [] });
    }

    let files = fs.readdirSync(folderPath)
      .filter(f => f.endsWith('.md') && f !== '.gitkeep')
      .map(filename => {
        const filePath = path.join(folderPath, filename);
        const stats = fs.statSync(filePath);
        const content = fs.readFileSync(filePath, 'utf-8');

        return {
          name: filename,
          path: filePath,
          size: stats.size,
          modified: stats.mtime,
          content,
        };
      });

    // Filter by source for Needs_Action folder (shared folder)
    if (folder === 'Needs_Action' && source) {
      files = files.filter(file => {
        const contentLower = file.content.toLowerCase();

        // Check for explicit source metadata
        const sourceMatch = file.content.match(/\*\*Source\*\*\s*\|\s*([^|\n]+)/i);
        if (sourceMatch) {
          const fileSource = sourceMatch[1].trim().toLowerCase();
          if (source === 'gmail') return fileSource === 'email' || fileSource === 'gmail';
          if (source === 'whatsapp') return fileSource === 'whatsapp';
          if (source === 'linkedin') return fileSource === 'linkedin';
        }

        // Fallback: detect from filename or content
        if (source === 'whatsapp') {
          return contentLower.includes('whatsapp') || file.name.toLowerCase().includes('whatsapp');
        }
        if (source === 'linkedin') {
          return contentLower.includes('linkedin') || file.name.toLowerCase().includes('linkedin');
        }
        // Gmail/default - exclude whatsapp and linkedin
        return !contentLower.includes('whatsapp') &&
               !contentLower.includes('linkedin') &&
               !file.name.toLowerCase().includes('whatsapp') &&
               !file.name.toLowerCase().includes('linkedin');
      });
    }

    files.sort((a, b) => b.modified.getTime() - a.modified.getTime());

    return NextResponse.json({ files });
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const filename = searchParams.get('filename');
  const folder = searchParams.get('folder') || 'Draft';

  if (!filename) {
    return NextResponse.json({ error: 'Filename required' }, { status: 400 });
  }

  const filePath = path.join(VAULT_PATH, folder, filename);

  try {
    if (fs.existsSync(filePath)) {
      fs.unlinkSync(filePath);
      return NextResponse.json({ success: true });
    }
    return NextResponse.json({ error: 'File not found' }, { status: 404 });
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}

import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const VAULT_PATH = path.join(process.cwd(), '..', 'AI_Employee_Vault');

export async function POST(request: NextRequest) {
  try {
    const { sourceFolder, targetFolder, filename } = await request.json();

    if (!sourceFolder || !targetFolder || !filename) {
      return NextResponse.json({ error: 'Missing parameters' }, { status: 400 });
    }

    const sourcePath = path.join(VAULT_PATH, sourceFolder, filename);
    const targetPath = path.join(VAULT_PATH, targetFolder, filename);

    if (!fs.existsSync(sourcePath)) {
      return NextResponse.json({ error: 'Source file not found' }, { status: 404 });
    }

    // Ensure target directory exists
    const targetDir = path.dirname(targetPath);
    if (!fs.existsSync(targetDir)) {
      fs.mkdirSync(targetDir, { recursive: true });
    }

    // Move file
    fs.renameSync(sourcePath, targetPath);

    return NextResponse.json({ success: true, targetPath });
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}

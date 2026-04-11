import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const VAULT_PATH = path.join(process.cwd(), '..', 'AI_Employee_Vault');

export async function POST(request: NextRequest) {
  try {
    const { folder, filename, content } = await request.json();

    if (!folder || !filename || content === undefined) {
      return NextResponse.json({ error: 'Missing parameters' }, { status: 400 });
    }

    const filePath = path.join(VAULT_PATH, folder, filename);

    // Ensure directory exists
    const dir = path.dirname(filePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    // Write content
    fs.writeFileSync(filePath, content, 'utf-8');

    return NextResponse.json({ success: true, path: filePath });
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}

import { NextRequest } from 'next/server';
import fs from 'fs';
import path from 'path';
import { EventEmitter } from 'events';

const VAULT_PATH = path.join(process.cwd(), '..', 'AI_Employee_Vault');

// Global event emitter for file changes
const fileEvents = new EventEmitter();

// Store connected clients
const clients = new Set<ReadableStreamDefaultController>();

// Watch for file changes using fs.watch (native, no polling)
if (typeof window === 'undefined') {
  const folders = [
    'Inbox', 'whatsapp_inbox', 'linkedin_inbox',
    'Needs_Action', 'Plans', 'Pending_Approval',
    'Approved', 'Rejected', 'Done', 'Scheduled', 'Logs'
  ];

  folders.forEach(folder => {
    const folderPath = path.join(VAULT_PATH, folder);

    // Ensure folder exists
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }

    // Use native fs.watch for real-time updates
    fs.watch(folderPath, (eventType, filename) => {
      if (filename && filename.endsWith('.md')) {
        const event = {
          type: eventType,
          folder,
          filename,
          timestamp: new Date().toISOString(),
        };

        // Broadcast to all connected clients
        clients.forEach(client => {
          try {
            client.enqueue(`data: ${JSON.stringify(event)}\n\n`);
          } catch {
            // Client disconnected
          }
        });
      }
    });
  });
}

export async function GET(request: NextRequest) {
  const stream = new ReadableStream({
    start(controller) {
      clients.add(controller);

      // Send initial connection message
      controller.enqueue(`data: ${JSON.stringify({ type: 'connected', timestamp: new Date().toISOString() })}\n\n`);

      // Keep connection alive
      const keepAlive = setInterval(() => {
        try {
          controller.enqueue(`: keepalive\n\n`);
        } catch {
          clearInterval(keepAlive);
        }
      }, 30000);

      // Cleanup on close
      request.signal.addEventListener('abort', () => {
        clearInterval(keepAlive);
        clients.delete(controller);
      });
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
}

import { readFile } from 'fs/promises';
import path from 'path';
import { NextResponse } from 'next/server';

export const runtime = 'nodejs';

const CHECKLIST_FILE = 'Cvent_Pre_Launch_QA_Checklist.pdf';

export async function GET() {
  try {
    const filePath = path.join(process.cwd(), 'public', 'resources', CHECKLIST_FILE);
    const fileBuffer = await readFile(filePath);

    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename="${CHECKLIST_FILE}"`,
        'Cache-Control': 'public, max-age=3600',
      },
    });
  } catch {
    return NextResponse.json({ error: 'Checklist file not found' }, { status: 404 });
  }
}

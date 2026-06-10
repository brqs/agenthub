import {
  isDesktopRuntime,
  saveBlobWithDesktopDialog,
  type DesktopSaveFilter,
} from '@/lib/desktopBridge';

export async function saveDownloadedBlob(
  blob: Blob,
  filename: string,
  filters: DesktopSaveFilter[] = [],
): Promise<boolean> {
  if (isDesktopRuntime()) {
    const result = await saveBlobWithDesktopDialog(blob, filename, filters);
    return result.saved;
  }
  const href = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(href);
  }
  return true;
}

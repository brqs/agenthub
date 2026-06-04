const EXTENSION_LANGUAGE_MAP: Record<string, string> = {
  bash: 'bash',
  cjs: 'javascript',
  css: 'css',
  htm: 'html',
  html: 'html',
  js: 'javascript',
  json: 'json',
  jsx: 'javascript',
  md: 'markdown',
  mjs: 'javascript',
  sh: 'bash',
  ts: 'typescript',
  tsx: 'tsx',
  yaml: 'yaml',
  yml: 'yaml',
};

const MIME_LANGUAGE_MAP: Record<string, string> = {
  'application/javascript': 'javascript',
  'application/json': 'json',
  'application/x-sh': 'bash',
  'application/x-yaml': 'yaml',
  'text/css': 'css',
  'text/html': 'html',
  'text/javascript': 'javascript',
  'text/markdown': 'markdown',
  'text/x-shellscript': 'bash',
  'text/yaml': 'yaml',
};

export function inferWorkspaceCodeLanguage(filename: string, mimeType: string): string {
  const extension = filename.split('.').filter(Boolean).at(-1)?.toLowerCase();
  if (extension && EXTENSION_LANGUAGE_MAP[extension]) {
    return EXTENSION_LANGUAGE_MAP[extension];
  }

  const normalizedMime = mimeType.toLowerCase().split(';')[0]?.trim() ?? '';
  return MIME_LANGUAGE_MAP[normalizedMime] ?? 'markdown';
}

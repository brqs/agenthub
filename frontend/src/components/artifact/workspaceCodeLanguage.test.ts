import { inferWorkspaceCodeLanguage } from './workspaceCodeLanguage';

describe('inferWorkspaceCodeLanguage', () => {
  it.each([
    ['app.js', 'text/plain', 'javascript'],
    ['styles.css', 'text/plain', 'css'],
    ['index.html', 'text/plain', 'html'],
    ['README.md', 'text/plain', 'markdown'],
    ['data.json', 'text/plain', 'json'],
    ['workflow.yaml', 'text/plain', 'yaml'],
    ['script.sh', 'text/plain', 'bash'],
    ['component.tsx', 'text/plain', 'tsx'],
    ['model.ts', 'text/plain', 'typescript'],
  ])('infers %s as %s', (filename, mimeType, expected) => {
    expect(inferWorkspaceCodeLanguage(filename, mimeType)).toBe(expected);
  });

  it('falls back to mime type and then markdown', () => {
    expect(inferWorkspaceCodeLanguage('unknown', 'text/css')).toBe('css');
    expect(inferWorkspaceCodeLanguage('unknown', 'application/octet-stream')).toBe('markdown');
  });
});

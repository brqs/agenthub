import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { WorkspaceCodePreview } from './WorkspaceCodePreview';

describe('WorkspaceCodePreview', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('renders a language-aware code preview with line numbers', async () => {
    const { container } = render(
      <WorkspaceCodePreview filename="app.js" mimeType="text/javascript" code={'const ok = true;\nconsole.log(ok);'} />,
    );

    expect(screen.getByRole('region', { name: 'app.js code preview' })).toBeInTheDocument();
    expect(screen.getByText('javascript')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    await waitFor(() => expect(container.querySelector('.shiki')).toBeInTheDocument());
  });

  it('toggles wrapping and copies code', async () => {
    render(<WorkspaceCodePreview filename="styles.css" mimeType="text/css" code=".logo { color: red; }" />);

    const wrapButton = screen.getByRole('button', { name: '换行' });
    expect(wrapButton).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(wrapButton);
    expect(screen.getByRole('button', { name: '不换行' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: '复制代码' }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith('.logo { color: red; }'));
  });

  it('uses plain text mode for large files', () => {
    render(
      <WorkspaceCodePreview
        filename="large.js"
        mimeType="text/javascript"
        code={`${'x'.repeat(210 * 1024)}`}
      />,
    );

    expect(screen.getByText('文件较大，已使用纯文本模式以保证性能。')).toBeInTheDocument();
  });
});

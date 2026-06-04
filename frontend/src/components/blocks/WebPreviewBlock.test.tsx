import { fireEvent, render, screen } from '@testing-library/react';
import { WebPreviewBlock } from './WebPreviewBlock';

describe('WebPreviewBlock', () => {
  it('opens and closes web preview modal', () => {
    render(
      <WebPreviewBlock
        url="https://example.com/demo"
        title="Demo Website"
        description="A demo build preview"
        previewTitle="Built Demo"
        previewBody="This is the built preview body."
      />,
    );

    expect(screen.getByText('Demo Website')).toBeInTheDocument();
    expect(screen.getByText('example.com')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('预览网页'));
    const iframe = screen.getByTitle('Demo Website');
    expect(iframe).toHaveAttribute('src', 'https://example.com/demo');
    expect(iframe).toHaveAttribute('sandbox', expect.stringContaining('allow-scripts'));
    expect(screen.queryByText('Chat Shell')).not.toBeInTheDocument();
    expect(screen.queryByText('Agent Flow')).not.toBeInTheDocument();
    expect(screen.queryByText('Rich Blocks')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTitle('关闭预览'));
    expect(screen.queryByTitle('Demo Website')).not.toBeInTheDocument();
  });

  it('keeps a safe external link', () => {
    render(<WebPreviewBlock url="https://example.com/demo" title="Demo Website" />);

    expect(screen.getByTitle('打开外链')).toHaveAttribute('target', '_blank');
    expect(screen.getByTitle('打开外链')).toHaveAttribute('rel', 'noreferrer');
  });

  it('does not iframe unsafe preview urls', () => {
    render(<WebPreviewBlock url="javascript:alert(1)" title="Bad Preview" />);

    expect(screen.queryByTitle('打开外链')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTitle('预览网页'));
    expect(screen.getByText(/预览 URL 不合法/)).toBeInTheDocument();
    expect(screen.queryByTitle('Bad Preview')).not.toBeInTheDocument();
  });
});

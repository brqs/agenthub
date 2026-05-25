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
    expect(screen.getByRole('heading', { name: 'Built Demo' })).toBeInTheDocument();
    expect(screen.getByText('This is the built preview body.')).toBeInTheDocument();
    expect(screen.getByText('Chat Shell')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('关闭预览'));
    expect(screen.queryByRole('heading', { name: 'Built Demo' })).not.toBeInTheDocument();
  });

  it('keeps a safe external link', () => {
    render(<WebPreviewBlock url="https://example.com/demo" title="Demo Website" />);

    expect(screen.getByTitle('打开外链')).toHaveAttribute('target', '_blank');
    expect(screen.getByTitle('打开外链')).toHaveAttribute('rel', 'noreferrer');
  });
});

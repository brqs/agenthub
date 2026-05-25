import { fireEvent, render, screen } from '@testing-library/react';
import { FileBlock } from './FileBlock';

describe('FileBlock', () => {
  it('opens and closes markdown preview', () => {
    render(
      <FileBlock
        filename="demo.md"
        url="https://example.com/demo.md"
        size={2048}
        mimeType="text/markdown"
        previewText="# Demo Notes\n\n- item"
      />,
    );

    expect(screen.getByText('demo.md')).toBeInTheDocument();
    expect(screen.getByText(/2.0 KB/)).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('预览文件'));
    expect(screen.getByText(/Demo Notes/)).toBeInTheDocument();
    expect(screen.getByText(/item/)).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('关闭预览'));
    expect(screen.queryByText(/Demo Notes/)).not.toBeInTheDocument();
  });

  it('does not show preview button without preview text', () => {
    render(
      <FileBlock
        filename="archive.zip"
        url="https://example.com/archive.zip"
        size={512}
        mimeType="application/zip"
      />,
    );

    expect(screen.queryByTitle('预览文件')).not.toBeInTheDocument();
    expect(screen.getByTitle('打开外链')).toHaveAttribute('target', '_blank');
    expect(screen.getByTitle('打开外链')).toHaveAttribute('rel', 'noreferrer');
  });
});

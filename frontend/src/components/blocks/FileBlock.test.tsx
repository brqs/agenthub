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
        artifactKind="document"
        previewText="# Demo Notes\n\n- item"
      />,
    );

    expect(screen.getByText('demo.md')).toBeInTheDocument();
    expect(screen.getByText('文档')).toBeInTheDocument();
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

  it('shows image preview using the file url', () => {
    render(
      <FileBlock
        filename="logo.png"
        url="https://example.com/logo.png"
        size={128}
        mimeType="image/png"
        artifactKind="image"
      />,
    );

    expect(screen.getByText('图片')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('预览图片'));
    expect(screen.getAllByAltText('logo.png').length).toBeGreaterThan(1);
  });

  it('shows archive and ppt metadata', () => {
    render(
      <>
        <FileBlock
          filename="export.zip"
          url="https://example.com/export.zip"
          size={512}
          mimeType="application/zip"
          artifactKind="archive"
          metadata={{ file_count: 2, top_entries: ['README.md', 'src/app.ts'] }}
        />
        <FileBlock
          filename="deck.pptx"
          url="https://example.com/deck.pptx"
          size={4096}
          mimeType="application/vnd.openxmlformats-officedocument.presentationml.presentation"
          artifactKind="ppt"
          metadata={{ slide_count: 3 }}
        />
      </>,
    );

    expect(screen.getByText('压缩包')).toBeInTheDocument();
    expect(screen.getByText(/2 files/)).toBeInTheDocument();
    expect(screen.getByText(/README.md, src\/app.ts/)).toBeInTheDocument();
    expect(screen.getByText('PPT')).toBeInTheDocument();
    expect(screen.getByText(/3 slides/)).toBeInTheDocument();
  });
});

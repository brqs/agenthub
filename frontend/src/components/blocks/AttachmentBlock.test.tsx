import { render, screen } from '@testing-library/react';
import { AttachmentBlock } from './AttachmentBlock';
import type { AttachmentBlock as AttachmentBlockType } from '@/lib/types';

const imageBlock: AttachmentBlockType = {
  type: 'attachment',
  upload_id: 'upload-image',
  filename: 'mockup.png',
  content_type: 'image/png',
  size_bytes: 2048,
  purpose: 'message_attachment',
  safety_status: 'passed',
  preview: {
    kind: 'image',
    thumbnail_url: 'https://example.com/mockup.png',
    width: 1280,
    height: 720,
  },
};

describe('AttachmentBlock', () => {
  it('renders image attachment metadata and thumbnail', () => {
    render(<AttachmentBlock block={imageBlock} />);

    expect(screen.getByText('mockup.png')).toBeInTheDocument();
    expect(screen.getByText('图片')).toBeInTheDocument();
    expect(screen.getByText(/2.0 KB/)).toBeInTheDocument();
    expect(screen.getByAltText('mockup.png')).toHaveAttribute(
      'src',
      'https://example.com/mockup.png',
    );
    expect(screen.getByTitle('下载附件')).toHaveAttribute('href', '/api/v1/uploads/upload-image/download');
  });

  it('shows archive entries and disables blocked downloads', () => {
    render(
      <AttachmentBlock
        block={{
          ...imageBlock,
          upload_id: 'upload-archive',
          filename: 'project.zip',
          content_type: 'application/zip',
          size_bytes: 1024,
          safety_status: 'blocked',
          preview: { kind: 'archive', entries_preview: ['README.md', 'src/app.ts'] },
        }}
      />,
    );

    expect(screen.getByText('压缩包')).toBeInTheDocument();
    expect(screen.getByText(/README.md, src\/app.ts/)).toBeInTheDocument();
    expect(screen.getByText(/安全检查未通过/)).toBeInTheDocument();
    expect(screen.getByTitle('下载附件')).toHaveAttribute('aria-disabled', 'true');
  });
});

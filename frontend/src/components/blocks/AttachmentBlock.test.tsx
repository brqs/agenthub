import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AttachmentBlock } from './AttachmentBlock';
import { downloadUpload } from '@/lib/adapters/uploads';
import type { AttachmentBlock as AttachmentBlockType } from '@/lib/types';

vi.mock('@/lib/adapters/uploads', () => ({
  downloadUpload: vi.fn(),
}));

const downloadUploadMock = vi.mocked(downloadUpload);

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
  beforeEach(() => {
    downloadUploadMock.mockReset();
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:attachment-preview');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders image attachment metadata and authenticated thumbnail', async () => {
    downloadUploadMock.mockResolvedValue(new Blob(['image'], { type: 'image/png' }));

    render(<AttachmentBlock block={imageBlock} />);

    expect(screen.getByText('mockup.png')).toBeInTheDocument();
    expect(screen.getByText('图片')).toBeInTheDocument();
    expect(screen.getByText(/2.0 KB/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByAltText('mockup.png')).toHaveAttribute(
        'src',
        'blob:attachment-preview',
      );
    });
    expect(downloadUploadMock).toHaveBeenCalledWith('upload-image');
    expect(screen.getByRole('button', { name: '下载附件' })).toBeEnabled();
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
    expect(screen.getByRole('button', { name: '下载附件' })).toBeDisabled();
    expect(downloadUploadMock).not.toHaveBeenCalled();
  });

  it('downloads attachments through the authenticated API adapter', async () => {
    downloadUploadMock.mockResolvedValue(new Blob(['file'], { type: 'text/plain' }));
    render(<AttachmentBlock block={{ ...imageBlock, preview: { kind: 'text' } }} />);

    const click = vi.fn();
    const link = document.createElement('a');
    vi.spyOn(link, 'click').mockImplementation(click);
    vi.spyOn(link, 'remove').mockImplementation(() => {});
    const appendChild = vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
    vi.spyOn(document, 'createElement').mockReturnValue(link);

    fireEvent.click(screen.getByRole('button', { name: '下载附件' }));

    await waitFor(() => {
      expect(downloadUploadMock).toHaveBeenCalledWith('upload-image');
      expect(click).toHaveBeenCalledTimes(1);
    });
    expect(appendChild).toHaveBeenCalled();
  });
});

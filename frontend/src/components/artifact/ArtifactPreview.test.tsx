import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ArtifactPreview, type PreviewArtifactFile } from './ArtifactPreview';

const textArtifact: PreviewArtifactFile = {
  path: 'src/demo.ts',
  name: 'demo.ts',
  mime_type: 'text/plain',
  size: 18,
  content: 'console.log("hi");',
};

const htmlArtifact: PreviewArtifactFile = {
  path: 'dist/index.html',
  name: 'index.html',
  mime_type: 'text/html',
  size: 31,
  content: '<h1>Hello</h1>',
};

describe('ArtifactPreview', () => {
  it('edits and saves text artifacts', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ArtifactPreview artifact={textArtifact} onSave={onSave} />);

    const editor = screen.getByDisplayValue('console.log("hi");');
    fireEvent.change(editor, { target: { value: 'console.log("saved");' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(
        'src/demo.ts',
        'console.log("saved");',
        'text/plain',
      ),
    );
  });

  it('disables save while unchanged', () => {
    render(<ArtifactPreview artifact={textArtifact} onSave={vi.fn()} />);

    expect(screen.getByRole('button', { name: '保存' })).toBeDisabled();
  });

  it('edits and saves html source while keeping preview visible', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ArtifactPreview artifact={htmlArtifact} onSave={onSave} />);

    expect(screen.getByTitle('index.html')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('index.html source'), {
      target: { value: '<h1>Saved</h1>' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith('dist/index.html', '<h1>Saved</h1>', 'text/html'),
    );
  });
});

import { render, screen, waitFor } from '@testing-library/react';
import { ToolCallBlock } from './ToolCallBlock';
import type { ToolCallBlock as ToolCallBlockType } from '@/lib/types';

const errorBlock: ToolCallBlockType = {
  type: 'tool_call',
  call_id: 'call_error',
  tool_name: 'Write',
  arguments: {
    content: 'print("Hello, World!")',
    file_path: '/Users/liyin/hello world.py',
  },
  status: 'error',
  error_code: 'tool_call_failed',
  output_preview: "Claude requested permissions to write, but you haven't granted it yet.",
};

describe('ToolCallBlock', () => {
  it('renders readable arguments and highlighted error results', async () => {
    const { container } = render(<ToolCallBlock block={errorBlock} />);

    expect(screen.getByText('Write')).toBeInTheDocument();
    expect(screen.getByText('Arguments')).toBeInTheDocument();
    expect(screen.getByText(/hello world.py/)).toBeInTheDocument();
    expect(screen.getByText('Result')).toHaveClass('text-rose-700');
    expect(screen.getByText('tool_call_failed')).toHaveClass('text-rose-700');
    expect(screen.getByText(/haven't granted it yet/)).toBeInTheDocument();
    await waitFor(() => expect(container.querySelector('.shiki')).toBeInTheDocument());
  });
});

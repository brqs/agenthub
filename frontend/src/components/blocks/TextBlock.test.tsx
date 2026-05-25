import { render, screen } from '@testing-library/react';
import { TextBlock } from './TextBlock';

describe('TextBlock', () => {
  it('renders markdown headings, emphasis, lists, tables, and links', () => {
    render(
      <TextBlock
        text={`## 共识渲染

这是 **Markdown** 输出。

- 支持列表

| A | B |
|---|---|
| 1 | 2 |

[AgentHub](https://example.com)`}
      />,
    );

    expect(screen.getByRole('heading', { name: '共识渲染' })).toBeInTheDocument();
    expect(screen.getByText('Markdown')).toBeInTheDocument();
    expect(screen.getByText('支持列表')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AgentHub' })).toHaveAttribute(
      'href',
      'https://example.com',
    );
  });

  it('renders inline and block math, including common model delimiters', () => {
    const { container } = render(
      <TextBlock
        text={`行内公式：\\(x \\equiv 2 \\pmod{3}\\)

\\[
x \\equiv \\sum_{i=1}^k a_i M_i y_i \\pmod M
\\]`}
      />,
    );

    expect(container.querySelector('.katex')).toBeInTheDocument();
    expect(container.querySelector('.katex-display')).toBeInTheDocument();
  });

  it('does not crash on incomplete streaming math', () => {
    render(<TextBlock text="正在输出公式：$x \\equiv" streaming />);

    expect(screen.getByText(/正在输出公式/)).toBeInTheDocument();
  });
});

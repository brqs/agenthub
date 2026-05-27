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

  it('does not parse math delimiters inside code spans or fenced code blocks', () => {
    const { container } = render(
      <TextBlock
        text={`行内代码：\`price = "$12"\`

\`\`\`tsx
const formula = "\\\\(x+y\\\\)";
\`\`\`

正文公式：\\(x+y\\)`}
      />,
    );

    expect(screen.getByText('price = "$12"')).toBeInTheDocument();
    expect(screen.getByText(/const formula/)).toBeInTheDocument();
    expect(container.querySelectorAll('.katex')).toHaveLength(1);
  });

  it('keeps long display formulas in a scrollable KaTeX display container', () => {
    const { container } = render(
      <TextBlock
        text={String.raw`\[
\mathcal{L}(\theta)= -\sum_{i=1}^{n}\sum_{j=1}^{m} y_{ij}\log\left(\frac{\exp(z_{ij}/\tau)}{\sum_{k=1}^{m}\exp(z_{ik}/\tau)}\right)+\lambda\left\|\theta\right\|_2^2
\]`}
      />,
    );

    const displayMath = container.querySelector('.katex-display');
    expect(displayMath).toBeInTheDocument();
    expect(displayMath?.textContent).toContain('L');
  });

  it('preserves KaTeX inline positioning styles for stacked formulas', () => {
    const { container } = render(
      <TextBlock
        text={String.raw`\[
\begin{cases}
x \equiv 2 \pmod{3}\\
x \equiv 3 \pmod{5}
\end{cases}
\]`}
      />,
    );

    expect(container.querySelector('.katex .pstrut')).toHaveAttribute('style');
    expect(container.querySelector('.katex .vlist > span')).toHaveAttribute('style');
  });

  it('highlights valid agent mentions outside code spans', () => {
    const { container } = render(
      <TextBlock
        text={'@codex-helper 请处理，`@codex-helper` 保持代码样式，@unknown 不高亮。'}
        agents={[
          {
            id: 'codex-helper',
            name: 'Codex Helper',
            provider: 'codex',
            avatar_url: '',
            capabilities: [],
            config: {},
            is_builtin: false,
            created_at: new Date().toISOString(),
          },
        ]}
      />,
    );

    expect(container.querySelector('[data-agent-mention="codex-helper"]')).toHaveTextContent(
      '@codex-helper',
    );
    expect(container.querySelectorAll('[data-agent-mention="codex-helper"]')).toHaveLength(1);
    expect(screen.getByText(/@unknown 不高亮/)).toBeInTheDocument();
  });
});

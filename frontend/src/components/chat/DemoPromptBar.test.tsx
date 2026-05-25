import { fireEvent, render, screen } from '@testing-library/react';
import { DEMO_PROMPT, DemoPromptBar } from './DemoPromptBar';

describe('DemoPromptBar', () => {
  it('passes the demo prompt when clicked', () => {
    const onSelect = vi.fn();
    render(<DemoPromptBar onSelect={onSelect} />);

    fireEvent.click(screen.getByRole('button', { name: DEMO_PROMPT }));

    expect(onSelect).toHaveBeenCalledWith(DEMO_PROMPT);
  });
});

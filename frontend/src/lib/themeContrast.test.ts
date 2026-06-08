import { DARK_THEME_CONTRAST_CASES, LIGHT_THEME_CONTRAST_CASES, contrastRatio } from './themeContrast';

describe('themeContrast', () => {
  it.each(LIGHT_THEME_CONTRAST_CASES)('keeps $name readable in light mode', (contrastCase) => {
    expect(contrastRatio(contrastCase.foreground, contrastCase.background)).toBeGreaterThanOrEqual(
      contrastCase.minimum,
    );
  });

  it.each(DARK_THEME_CONTRAST_CASES)('keeps $name readable in dark mode', (contrastCase) => {
    expect(contrastRatio(contrastCase.foreground, contrastCase.background)).toBeGreaterThanOrEqual(
      contrastCase.minimum,
    );
  });
});

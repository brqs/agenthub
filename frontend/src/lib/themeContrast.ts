export interface ContrastCase {
  name: string;
  foreground: string;
  background: string;
  minimum: number;
}

export const LIGHT_THEME_CONTRAST_CASES: ContrastCase[] = [
  { name: 'primary text on app surface', foreground: '#020617', background: '#f1f5f9', minimum: 4.5 },
  { name: 'secondary text on white panel', foreground: '#475569', background: '#ffffff', minimum: 4.5 },
  { name: 'muted text on white panel', foreground: '#64748b', background: '#ffffff', minimum: 4.5 },
  { name: 'agent message text', foreground: '#020617', background: '#ffffff', minimum: 4.5 },
  { name: 'input placeholder', foreground: '#64748b', background: '#ffffff', minimum: 4.5 },
  { name: 'error text on error surface', foreground: '#b91c1c', background: '#fef2f2', minimum: 4.5 },
  { name: 'brand button text', foreground: '#ffffff', background: '#4f46e5', minimum: 4.5 },
];

export function contrastRatio(foreground: string, background: string): number {
  const foregroundLuminance = relativeLuminance(hexToRgb(foreground));
  const backgroundLuminance = relativeLuminance(hexToRgb(background));
  const lighter = Math.max(foregroundLuminance, backgroundLuminance);
  const darker = Math.min(foregroundLuminance, backgroundLuminance);
  return (lighter + 0.05) / (darker + 0.05);
}

function relativeLuminance([red, green, blue]: [number, number, number]): number {
  const linearRed = linearizeColorChannel(red);
  const linearGreen = linearizeColorChannel(green);
  const linearBlue = linearizeColorChannel(blue);
  return 0.2126 * linearRed + 0.7152 * linearGreen + 0.0722 * linearBlue;
}

function linearizeColorChannel(channel: number): number {
  const normalized = channel / 255;
  return normalized <= 0.03928
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4;
}

function hexToRgb(hex: string): [number, number, number] {
  const normalized = hex.replace('#', '');
  if (!/^[\da-f]{6}$/i.test(normalized)) {
    throw new Error(`Invalid hex color: ${hex}`);
  }
  return [
    Number.parseInt(normalized.slice(0, 2), 16),
    Number.parseInt(normalized.slice(2, 4), 16),
    Number.parseInt(normalized.slice(4, 6), 16),
  ];
}

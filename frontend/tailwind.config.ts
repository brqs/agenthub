import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#4F46E5',
          hover: '#4338CA',
          light: '#818CF8',
        },
        agent: {
          claude: '#C97064',
          deepseek: '#2D6CDF',
          openai: '#10A37F',
          orchestrator: '#8B5CF6',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)'],
      },
    },
  },
  plugins: [],
};

export default config;

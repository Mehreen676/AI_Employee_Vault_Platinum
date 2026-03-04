/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{ts,tsx,js,jsx}',
    './components/**/*.{ts,tsx,js,jsx}',
    './lib/**/*.{ts,tsx,js,jsx}',
  ],
  theme: {
    extend: {
      colors: {
        vault: {
          bg:       '#030712',
          surface:  '#0f172a',
          card:     '#111827',
          border:   '#1e293b',
          cyan:     '#06b6d4',
          green:    '#10b981',
          purple:   '#8b5cf6',
          gold:     '#f59e0b',
          red:      '#ef4444',
          orange:   '#f97316',
          pink:     '#ec4899',
          blue:     '#3b82f6',
          slate:    '#64748b',
          text:     '#f1f5f9',
          muted:    '#94a3b8',
          dim:      '#475569',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', '"Cascadia Code"', 'Consolas', 'monospace'],
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in':    'fadeIn 0.3s ease-in',
        'slide-in':   'slideIn 0.2s ease-out',
      },
      keyframes: {
        fadeIn:  { from: { opacity: '0' },                    to: { opacity: '1' } },
        slideIn: { from: { transform: 'translateY(-8px)', opacity: '0' }, to: { transform: 'translateY(0)', opacity: '1' } },
      },
      boxShadow: {
        'neon-cyan':   '0 0 10px 2px rgba(6,182,212,0.35)',
        'neon-green':  '0 0 10px 2px rgba(16,185,129,0.35)',
        'neon-purple': '0 0 10px 2px rgba(139,92,246,0.35)',
        'neon-gold':   '0 0 10px 2px rgba(245,158,11,0.35)',
        'neon-red':    '0 0 10px 2px rgba(239,68,68,0.35)',
      },
    },
  },
  plugins: [],
};

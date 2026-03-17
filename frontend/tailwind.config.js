/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['"DM Sans"', 'sans-serif'],
      },
      colors: {
        void:    '#080a0f',
        surface: '#0d1117',
        panel:   '#131920',
        border:  '#1e2832',
        muted:   '#3d4f61',
        subtle:  '#6b8299',
        text:    '#c9d8e8',
        bright:  '#e8f4ff',
        cyan:    { DEFAULT: '#00d4ff', dim: '#0090b0', glow: '#00d4ff33' },
        green:   { DEFAULT: '#00ff94', dim: '#00804a', glow: '#00ff9433' },
        amber:   { DEFAULT: '#ffb800', dim: '#7a5800', glow: '#ffb80033' },
        red:     { DEFAULT: '#ff4466', dim: '#7a0020', glow: '#ff446633' },
        purple:  { DEFAULT: '#a855f7', dim: '#5b21b6', glow: '#a855f733' },
      },
      boxShadow: {
        'glow-cyan':   '0 0 20px #00d4ff22, 0 0 40px #00d4ff11',
        'glow-green':  '0 0 20px #00ff9422, 0 0 40px #00ff9411',
        'glow-amber':  '0 0 20px #ffb80022',
      },
      animation: {
        'pulse-slow':   'pulse 3s ease-in-out infinite',
        'scan':         'scan 4s linear infinite',
        'flicker':      'flicker 0.15s infinite',
        'fade-in':      'fadeIn 0.4s ease-out',
        'slide-up':     'slideUp 0.3s ease-out',
        'blink':        'blink 1s step-end infinite',
      },
      keyframes: {
        scan:    { '0%': { transform: 'translateY(-100%)' }, '100%': { transform: 'translateY(100vh)' } },
        flicker: { '0%, 100%': { opacity: 1 }, '50%': { opacity: 0.85 } },
        fadeIn:  { from: { opacity: 0 }, to: { opacity: 1 } },
        slideUp: { from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        blink:   { '0%, 100%': { opacity: 1 }, '50%': { opacity: 0 } },
      },
    },
  },
  plugins: [],
}

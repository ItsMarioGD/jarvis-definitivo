/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        teal: {
          shadow: '#04141a',
          deep: '#0a2a30',
          mid: '#0fd3c9',
        },
        fusion: {
          orange: '#ff7a18',
          gold: '#ffb347',
        },
        neon: {
          cyan: '#21e6ff',
          blue: '#1f6bff',
        },
        ink: '#02060a',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        'glass-edge': '0 0 0 1px rgba(33,230,255,0.25), inset 0 0 24px rgba(33,230,255,0.08)',
      },
      keyframes: {
        gasflow: {
          '0%': { backgroundPosition: '0% 50%' },
          '100%': { backgroundPosition: '200% 50%' },
        },
        flicker: {
          '0%,100%': { opacity: '1' },
          '45%': { opacity: '0.82' },
          '55%': { opacity: '0.92' },
        },
        wobble: {
          '0%,100%': { transform: 'translateY(0) scaleY(1)' },
          '50%': { transform: 'translateY(2px) scaleY(0.985)' },
        },
      },
      animation: {
        gasflow: 'gasflow 6s linear infinite',
        flicker: 'flicker 4s ease-in-out infinite',
        wobble: 'wobble 3.5s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}

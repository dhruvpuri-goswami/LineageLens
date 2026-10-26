/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', 'Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
        popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },
        sidebar: 'hsl(var(--sidebar))',
      },
      borderRadius: { xl: '0.5rem', lg: '0.5rem', md: '0.375rem', sm: '0.25rem' },
      boxShadow: {
        // Flat UI: borders do the work. Shadows only for floating layers (menus, drawers).
        soft: '0 0 #0000',
        pop: '0 4px 12px -4px rgb(0 0 0 / 0.12), 0 1px 2px rgb(0 0 0 / 0.06)',
        lg: '0 4px 12px -4px rgb(0 0 0 / 0.12), 0 1px 2px rgb(0 0 0 / 0.06)',
        xl: '0 8px 24px -8px rgb(0 0 0 / 0.18), 0 1px 3px rgb(0 0 0 / 0.08)',
        '2xl': '0 12px 32px -12px rgb(0 0 0 / 0.25)',
      },
      keyframes: {
        'slide-in': { from: { transform: 'translateX(100%)' }, to: { transform: 'translateX(0)' } },
        'fade-in': { from: { opacity: 0 }, to: { opacity: 1 } },
        rise: { from: { opacity: 0 }, to: { opacity: 1 } },
      },
      animation: { 'slide-in': 'slide-in .18s cubic-bezier(.2,.8,.2,1)', 'fade-in': 'fade-in .15s ease-out', rise: 'rise .12s ease-out both' },
    },
  },
  plugins: [],
}

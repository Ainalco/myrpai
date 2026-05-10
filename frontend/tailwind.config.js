/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Scurry Brand Colors
        scurry: {
          // Primary Brand Colors
          orange: '#FF5722',           // Hyper Orange - Primary CTA/Accent
          'orange-hover': '#E64A19',   // Orange Hover - CTA Hover/Gradient End
          espresso: '#3E2723',         // Primary Text/Headings
          latte: '#795548',            // Secondary Text/Borders

          // Status & Feedback Colors
          green: '#4CAF50',            // Go Green - Success/Continue
          'go-green': '#4CAF50',       // Alias
          red: '#F44336',              // Error/Stop/Delete
          yellow: '#FFC107',           // Energy Burst - Loading/Running
          'energy-burst': '#FFC107',   // Alias

          // Background & Surface Colors
          foam: '#FFF8E1',             // Cards/Sections/Soft Background
          'orange-light': '#FFF3E0',   // Warning/Incomplete/OR logic
          'green-light': '#E8F5E9',    // Success Background
          'red-light': '#FFEBEE',      // Delete Border/Danger Background

          // Blue (AND Logic Toggle)
          'blue-bg': '#E3F2FD',        // AND logic background
          'blue-text': '#1976D2',      // AND logic text

          // Neutral/Utility Colors
          'gray-light': '#F5F5F5',     // Light Gray Backgrounds
          'gray-border': '#E0E0E0',    // Borders/Disabled UI
          'gray-muted': '#9E9E9E',     // Muted Text
          'gray-secondary': '#757575', // Secondary Text
        },
      },
      fontFamily: {
        display: ['Baloo 2', 'cursive'],
        sans: ['Inter', 'sans-serif'],
        mono: ['Space Mono', 'monospace'],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
}
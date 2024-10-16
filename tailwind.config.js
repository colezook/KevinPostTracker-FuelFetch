/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./public/**/*.{html,js}"],
  theme: {
    extend: {
      colors: {
        gray: {
          800: '#1f2937',
          900: '#111827',
        },
      },
    },
  },
  plugins: [],
}

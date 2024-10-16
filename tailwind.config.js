/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./public/**/*.{html,js}"],
  theme: {
    extend: {
      colors: {
        black: '#000000',
        gray: {
          800: '#1f2937',
        },
      },
    },
  },
  plugins: [],
}

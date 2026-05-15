/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // 中文衬线字体——给奇幻氛围更适合
        serif: ['"Noto Serif SC"', '"Source Han Serif SC"', "serif"],
      },
      colors: {
        // 主色调暖石色，匹配"中世纪奇幻"氛围
        parchment: "#f5e6c8",
        ink: "#2a2422",
      },
    },
  },
  plugins: [],
};

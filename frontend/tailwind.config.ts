import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#102028",
        mist: "#eff7f5",
        moss: "#14532d",
        fern: "#2f855a",
        sand: "#f5efe3",
      },
    },
  },
  plugins: [],
} satisfies Config;

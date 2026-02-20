import type { NextConfig } from "next";
import { config as dotenvConfig } from "dotenv";
import path from "path";

// Load .env from the project root (one level up from frontend/)
dotenvConfig({ path: path.resolve(__dirname, "..", ".env") });

const nextConfig: NextConfig = {
  env: {
    // Expose shared vars to the browser from the root .env
    NEXT_PUBLIC_SUPABASE_URL: process.env.SUPABASE_URL || "",
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.SUPABASE_ANON_KEY || "",
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:5001",
  },
};

export default nextConfig;

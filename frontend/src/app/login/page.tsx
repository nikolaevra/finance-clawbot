"use client";

import { useState, useMemo } from "react";
import { createClient } from "@/lib/supabase";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const supabase = useMemo(() => {
    if (typeof window === "undefined") return null;
    return createClient();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    if (!supabase) return;

    try {
      if (isSignUp) {
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        setError("Check your email for a confirmation link.");
        setLoading(false);
        return;
      }

      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (error) throw error;

      router.push("/chat");
      router.refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm px-6">
        <div className="rounded-3xl bg-foreground/[0.04] ring-1 ring-foreground/[0.08] p-8 shadow-2xl shadow-black/30">
          <div className="text-center mb-8">
            <div className="mx-auto w-12 h-12 rounded-2xl bg-foreground/[0.06] flex items-center justify-center mb-4">
              <span className="text-xl">✦</span>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground/90">
              Finance Assistant
            </h1>
            <p className="mt-2 text-sm text-foreground/35">
              {isSignUp ? "Create your account" : "Sign in to continue"}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="block text-xs font-medium text-foreground/40 mb-1.5 ml-1"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl bg-foreground/[0.06] ring-1 ring-foreground/[0.08] px-4 py-2.5 text-sm text-foreground/85 placeholder:text-foreground/20 focus:outline-none focus:ring-foreground/[0.2] focus:bg-foreground/[0.08]"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-xs font-medium text-foreground/40 mb-1.5 ml-1"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl bg-foreground/[0.06] ring-1 ring-foreground/[0.08] px-4 py-2.5 text-sm text-foreground/85 placeholder:text-foreground/20 focus:outline-none focus:ring-foreground/[0.2] focus:bg-foreground/[0.08]"
                placeholder="Your password"
                minLength={6}
              />
            </div>

            {error && (
              <p className="text-sm text-red-400/80 text-center">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-blue-500 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-blue-500/20 hover:bg-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-400/50 disabled:opacity-50"
            >
              {loading ? "Loading..." : isSignUp ? "Sign Up" : "Sign In"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-foreground/30">
            {isSignUp ? "Already have an account?" : "Don't have an account?"}{" "}
            <button
              onClick={() => {
                setIsSignUp(!isSignUp);
                setError("");
              }}
              className="font-medium text-blue-400/80 hover:text-blue-400"
            >
              {isSignUp ? "Sign In" : "Sign Up"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

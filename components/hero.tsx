"use client"

import Link from "next/link"
import { ArrowRight, Play, ChevronDown, Sparkles, Check } from "lucide-react"
import { ScalesIcon } from "@/components/scales-icon"

const BADGES = [
  { label: "Constitution Haïtienne", delay: "0s" },
  { label: "Code Civil", delay: "1.4s" },
  { label: "Code Pénal", delay: "2.6s" },
]

export function Hero({ onAuth }: { onAuth: (mode: "in" | "up") => void }) {
  return (
    <section
      id="accueil"
      className="relative flex min-h-screen items-center justify-center overflow-hidden pt-16"
    >
      {/* radial glow */}
      <div className="pointer-events-none absolute left-1/2 top-1/2 size-[640px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/20 blur-[140px]" />
      <div className="pointer-events-none absolute right-[12%] top-[24%] size-72 rounded-full bg-gold/15 blur-[120px]" />

      <div className="relative z-10 mx-auto grid max-w-7xl items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-2 lg:px-8">
        {/* Left: copy */}
        <div className="flex flex-col items-start text-left">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-secondary/60 px-3 py-1.5 text-xs font-medium text-muted-foreground">
            <Sparkles className="size-3.5 text-gold" />
            L&apos;intelligence juridique haïtienne
          </span>

          <h1 className="mt-6 font-heading text-6xl font-bold leading-[0.95] tracking-tight text-balance sm:text-7xl">
            <span className="gradient-text text-glow">Lajistis</span>
            <br />
            <span className="text-foreground">AI</span>
          </h1>

          <p className="mt-5 font-heading text-2xl font-semibold text-foreground/90">
            Dwa ou, nan men ou.
          </p>
          <p className="mt-3 max-w-md text-lg leading-relaxed text-muted-foreground text-pretty">
            L&apos;intelligence juridique haïtienne à votre service. Des réponses
            claires et sourcées sur vos droits, 24h/24.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={() => onAuth("up")}
              className="group inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground transition-transform hover:scale-[1.04] glow-blue"
            >
              Commencer Gratuitement
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
            </button>
            <Link
              href="/chat"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-secondary/40 px-6 py-3.5 text-sm font-semibold text-foreground transition-colors hover:border-primary/50 hover:bg-secondary"
            >
              <Play className="size-4 text-primary" />
              Voir une Démo
            </Link>
          </div>

          <div className="mt-10 flex flex-wrap gap-2.5">
            {BADGES.map((b) => (
              <span
                key={b.label}
                className="inline-flex animate-float items-center gap-2 rounded-full glass px-3.5 py-2 text-xs font-medium text-foreground/90"
                style={{ animationDelay: b.delay }}
              >
                <Check className="size-3.5 text-gold" />
                {b.label}
              </span>
            ))}
          </div>
        </div>

        {/* Right: orb */}
        <div className="relative flex items-center justify-center">
          <div className="relative size-72 sm:size-80 lg:size-96">
            {/* rotating rings */}
            <div className="absolute inset-0 animate-spin-slow rounded-full border border-primary/20" />
            <div className="absolute inset-6 animate-spin-slow rounded-full border border-gold/15 [animation-direction:reverse]" />
            {/* orb */}
            <div className="absolute inset-12 animate-orb rounded-full bg-[radial-gradient(circle_at_30%_30%,#60a5fa,#1d4ed8_45%,#0a0f2c_85%)] glow-blue">
              <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle_at_70%_75%,rgba(245,158,11,0.5),transparent_55%)]" />
              <div className="flex size-full items-center justify-center">
                <ScalesIcon className="size-24 text-background/90 drop-shadow-[0_0_18px_rgba(255,255,255,0.4)]" />
              </div>
            </div>
            {/* floating mini dots */}
            <span className="absolute -right-2 top-10 size-3 animate-float rounded-full bg-gold glow-gold" />
            <span
              className="absolute -left-1 bottom-16 size-2.5 animate-float rounded-full bg-primary"
              style={{ animationDelay: "1.5s" }}
            />
          </div>
        </div>
      </div>

      <a
        href="#fonctionnalites"
        className="absolute bottom-8 left-1/2 z-10 flex -translate-x-1/2 flex-col items-center gap-2 text-muted-foreground transition-colors hover:text-foreground"
        aria-label="Faire défiler vers le bas"
      >
        <span className="text-xs">Découvrir</span>
        <ChevronDown className="size-5 animate-float" />
      </a>
    </section>
  )
}

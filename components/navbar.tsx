"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Menu, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { ScalesIcon } from "@/components/scales-icon"
import { LanguageSwitcher } from "@/components/language-switcher"

const LINKS = [
  { label: "Accueil", href: "#accueil" },
  { label: "Fonctionnalités", href: "#fonctionnalites" },
  { label: "Documents", href: "#documents" },
  { label: "Tarifs", href: "#tarifs" },
]

export function Navbar({ onAuth }: { onAuth: (mode: "in" | "up") => void }) {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    onScroll()
    window.addEventListener("scroll", onScroll)
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-all duration-300",
        scrolled
          ? "border-b border-border bg-background/70 backdrop-blur-xl"
          : "border-b border-transparent",
      )}
    >
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-xl bg-primary/15 text-primary glow-blue">
            <ScalesIcon className="size-5" />
          </span>
          <span className="font-heading text-lg font-bold tracking-tight">
            Lajistis<span className="text-primary"> AI</span>
          </span>
        </Link>

        <div className="hidden items-center gap-1 lg:flex">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              {l.label}
            </a>
          ))}
        </div>

        <div className="hidden items-center gap-3 lg:flex">
          <LanguageSwitcher />
          <button
            type="button"
            onClick={() => onAuth("in")}
            className="rounded-lg px-3 py-2 text-sm font-medium text-foreground transition-colors hover:text-primary"
          >
            Se Connecter
          </button>
          <button
            type="button"
            onClick={() => onAuth("up")}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-transform hover:scale-[1.04] glow-blue"
          >
            Commencer
          </button>
        </div>

        <button
          type="button"
          className="inline-flex size-10 items-center justify-center rounded-lg border border-border text-foreground lg:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Fermer le menu" : "Ouvrir le menu"}
          aria-expanded={open}
        >
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </nav>

      {open && (
        <div className="fixed inset-0 top-16 z-40 animate-fade-up bg-background/95 backdrop-blur-xl lg:hidden">
          <div className="flex flex-col gap-1 px-4 py-6">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="rounded-xl px-4 py-4 text-lg font-medium text-foreground transition-colors hover:bg-secondary"
              >
                {l.label}
              </a>
            ))}
            <div className="mt-4 flex items-center justify-between">
              <LanguageSwitcher />
            </div>
            <div className="mt-4 flex flex-col gap-3">
              <button
                type="button"
                onClick={() => {
                  setOpen(false)
                  onAuth("in")
                }}
                className="rounded-xl border border-border px-4 py-3 text-base font-medium"
              >
                Se Connecter
              </button>
              <button
                type="button"
                onClick={() => {
                  setOpen(false)
                  onAuth("up")
                }}
                className="rounded-xl bg-primary px-4 py-3 text-base font-semibold text-primary-foreground glow-blue"
              >
                Commencer
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}

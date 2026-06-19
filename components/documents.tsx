"use client"

import { useState } from "react"
import { Search, BookOpen, ArrowRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/lib/language-context"

type Category = "Civil" | "Pénal" | "Commercial" | "Travail"

const DOCS: {
  title: string
  year: string
  articles: number
  category: Category
  spine: string
}[] = [
  { title: "Constitution", year: "1987", articles: 298, category: "Civil", spine: "from-[#00209f] to-[#0a0f2c]" },
  { title: "Code Civil", year: "1825", articles: 2047, category: "Civil", spine: "from-[#1d4ed8] to-[#0a0f2c]" },
  { title: "Code Pénal", year: "1835", articles: 408, category: "Pénal", spine: "from-[#dc2626] to-[#0a0f2c]" },
  { title: "Code du Travail", year: "1984", articles: 478, category: "Travail", spine: "from-[#f59e0b] to-[#0a0f2c]" },
  { title: "Code de Commerce", year: "1826", articles: 651, category: "Commercial", spine: "from-[#0e7490] to-[#0a0f2c]" },
  { title: "Code d'Instruction", year: "1835", articles: 320, category: "Pénal", spine: "from-[#b91c1c] to-[#0a0f2c]" },
]

const TABS = ["All", "Civil", "Pénal", "Commercial", "Travail"] as const

export function Documents() {
  const { t } = useLanguage()
  const [tab, setTab] = useState<(typeof TABS)[number]>("All")
  const [q, setQ] = useState("")
  const TABS = ["All", ...t.documentsPage.tabs] as const

  const filtered = DOCS.filter(
    (d) =>
      (tab === "All" || d.category === tab) &&
      d.title.toLowerCase().includes(q.toLowerCase()),
  )

  return (
    <section id="documents" className="relative py-24 sm:py-32">
      <div className="pointer-events-none absolute inset-0 grid-pattern opacity-40" />
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <span className="text-sm font-semibold uppercase tracking-widest text-gold">
            Bibliothèque
          </span>
          <h2 className="mt-3 font-heading text-4xl font-bold tracking-tight text-balance sm:text-5xl">
            Explorez les <span className="gradient-text">textes de loi</span>
          </h2>
          <p className="mt-4 text-lg leading-relaxed text-muted-foreground text-pretty">
            Recherchez à travers les documents juridiques fondamentaux d&apos;Haïti.
          </p>
        </div>

        <div className="mx-auto mt-10 max-w-xl">
          <div className="flex items-center gap-3 rounded-2xl glass px-4 py-3 focus-within:glow-blue">
            <Search className="size-5 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t.documentsPage.searchPlaceholder}
              className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            />
          </div>
        </div>

        <div className="mt-8 flex flex-wrap justify-center gap-2">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                tab === t
                  ? "bg-primary text-primary-foreground glow-blue"
                  : "border border-border bg-secondary/40 text-muted-foreground hover:text-foreground",
              )}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {filtered.map((d) => (
            <div
              key={d.title}
              className="gradient-border group flex flex-col overflow-hidden rounded-2xl glass p-4 transition-all duration-300 hover:-translate-y-1.5"
            >
              <div
                className={cn(
                  "relative flex aspect-[3/4] items-end overflow-hidden rounded-xl bg-gradient-to-br p-4 shadow-lg",
                  d.spine,
                )}
              >
                <div className="absolute left-0 top-0 h-full w-1.5 bg-gold/70" />
                <BookOpen className="absolute right-3 top-3 size-5 text-foreground/40" />
                <div>
                  <p className="font-mono text-xs text-foreground/60">{d.year}</p>
                  <p className="font-heading text-lg font-bold leading-tight text-foreground">
                    {d.title}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <span className="rounded-full bg-secondary px-2.5 py-1 font-mono text-xs text-muted-foreground">
                  {d.articles} art.
                </span>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-sm font-medium text-primary transition-transform group-hover:translate-x-0.5"
                >
                  {t.documentsPage.exploreButton} <ArrowRight className="size-4" />
                </button>
              </div>
            </div>
          ))}
        </div>

        {filtered.length === 0 && (
          <p className="mt-12 text-center text-muted-foreground">
            {t.documentsPage.noResults}
          </p>
        )}
      </div>
    </section>
  )
}

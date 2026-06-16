"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"

const LANGS = ["FR", "KR", "EN"] as const

export function LanguageSwitcher({ className }: { className?: string }) {
  const [active, setActive] = useState<(typeof LANGS)[number]>("FR")
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border border-border bg-secondary/60 p-0.5 text-xs font-medium",
        className,
      )}
      role="group"
      aria-label="Sélecteur de langue"
    >
      {LANGS.map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => setActive(l)}
          className={cn(
            "rounded-full px-2.5 py-1 transition-colors",
            active === l
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {l}
        </button>
      ))}
    </div>
  )
}

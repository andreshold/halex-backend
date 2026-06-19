"use client"

import { cn } from "@/lib/utils"
import { useLanguage } from "@/lib/language-context"

const LANGS = [
  { code: "fr" as const, label: "FR" },
  { code: "ht" as const, label: "HT" },
] as const

export function LanguageSwitcher({ className }: { className?: string }) {
  const { language, setLanguage, t } = useLanguage()

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border border-border bg-secondary/60 p-0.5 text-xs font-medium",
        className,
      )}
      role="group"
      aria-label={t.languageSwitcher.ariaLabel}
    >
      {LANGS.map(({ code, label }) => (
        <button
          key={code}
          type="button"
          onClick={() => setLanguage(code)}
          className={cn(
            "rounded-full px-2.5 py-1 transition-colors",
            language === code
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

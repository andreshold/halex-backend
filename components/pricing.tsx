"use client"

import { useState } from "react"
import { Check } from "lucide-react"
import { cn } from "@/lib/utils"

const TIERS = [
  {
    name: "Citoyen",
    tagline: "Pour découvrir vos droits",
    monthly: 0,
    annual: 0,
    cta: "Commencer Gratuitement",
    highlight: false,
    features: [
      "5 questions par jour",
      "Accès Constitution & Code Civil",
      "Réponses sourcées",
      "Support communautaire",
    ],
  },
  {
    name: "Professionnel",
    tagline: "Pour un usage intensif",
    monthly: 19,
    annual: 15,
    cta: "Passer Pro",
    highlight: true,
    features: [
      "Questions illimitées",
      "Tous les codes de loi",
      "Recherche avancée par article",
      "Historique illimité",
      "Réponses prioritaires",
      "Support par email",
    ],
  },
  {
    name: "Cabinet Juridique",
    tagline: "Pour les professionnels du droit",
    monthly: 99,
    annual: 79,
    cta: "Contacter les ventes",
    highlight: false,
    features: [
      "Tout du plan Pro",
      "Accès API complet",
      "Comptes multi-utilisateurs",
      "Intégrations sur mesure",
      "Gestionnaire dédié",
    ],
  },
]

export function Pricing({ onAuth }: { onAuth: (mode: "in" | "up") => void }) {
  const [annual, setAnnual] = useState(false)

  return (
    <section id="tarifs" className="relative py-24 sm:py-32">
      <div className="pointer-events-none absolute left-1/2 top-1/3 size-[460px] -translate-x-1/2 rounded-full bg-primary/10 blur-[140px]" />
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <span className="text-sm font-semibold uppercase tracking-widest text-primary">
            Tarifs
          </span>
          <h2 className="mt-3 font-heading text-4xl font-bold tracking-tight text-balance sm:text-5xl">
            Un plan pour <span className="gradient-text">chaque citoyen</span>
          </h2>

          <div className="mt-8 inline-flex items-center gap-3 rounded-full border border-border bg-secondary/60 p-1">
            <button
              type="button"
              onClick={() => setAnnual(false)}
              className={cn(
                "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                !annual ? "bg-primary text-primary-foreground" : "text-muted-foreground",
              )}
            >
              Mensuel
            </button>
            <button
              type="button"
              onClick={() => setAnnual(true)}
              className={cn(
                "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors",
                annual ? "bg-primary text-primary-foreground" : "text-muted-foreground",
              )}
            >
              Annuel
              <span className="rounded-full bg-gold/20 px-2 py-0.5 text-xs font-semibold text-gold">
                -20%
              </span>
            </button>
          </div>
        </div>

        <div className="mt-14 grid items-start gap-6 lg:grid-cols-3">
          {TIERS.map((t) => {
            const price = annual ? t.annual : t.monthly
            return (
              <div
                key={t.name}
                className={cn(
                  "relative flex flex-col rounded-3xl p-7 transition-all duration-300",
                  t.highlight
                    ? "glass-strong glow-blue lg:-translate-y-4"
                    : "glass hover:-translate-y-1",
                )}
              >
                {t.highlight && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
                    Le plus populaire
                  </span>
                )}
                <h3 className="font-heading text-xl font-bold">{t.name}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{t.tagline}</p>
                <div className="mt-6 flex items-end gap-1">
                  <span className="font-heading text-5xl font-bold">${price}</span>
                  <span className="mb-1.5 text-sm text-muted-foreground">/mois</span>
                </div>

                <button
                  type="button"
                  onClick={() => onAuth("up")}
                  className={cn(
                    "mt-6 rounded-xl px-5 py-3 text-sm font-semibold transition-transform hover:scale-[1.03]",
                    t.highlight
                      ? "bg-primary text-primary-foreground glow-blue"
                      : "border border-border bg-secondary/40 text-foreground hover:border-primary/50",
                  )}
                >
                  {t.cta}
                </button>

                <ul className="mt-7 flex flex-col gap-3">
                  {t.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-sm">
                      <Check
                        className={cn(
                          "mt-0.5 size-4 shrink-0",
                          t.highlight ? "text-primary" : "text-gold",
                        )}
                      />
                      <span className="text-muted-foreground">{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

import { Gavel, Shield, Briefcase, Globe, BookText, Zap } from "lucide-react"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/lib/language-context"

export function Features() {
  const { t } = useLanguage()
  const FEATURES = [
    {
      icon: Gavel,
      title: t.featuresPage.cards[0].title,
      desc: t.featuresPage.cards[0].desc,
      accent: "text-primary",
    },
    {
      icon: Shield,
      title: t.featuresPage.cards[1].title,
      desc: t.featuresPage.cards[1].desc,
      accent: "text-haiti-red",
    },
    {
      icon: Briefcase,
      title: t.featuresPage.cards[2].title,
      desc: t.featuresPage.cards[2].desc,
      accent: "text-gold",
    },
    {
      icon: Globe,
      title: t.featuresPage.cards[3].title,
      desc: t.featuresPage.cards[3].desc,
      accent: "text-primary",
    },
    {
      icon: BookText,
      title: t.featuresPage.cards[4].title,
      desc: t.featuresPage.cards[4].desc,
      accent: "text-gold",
    },
    {
      icon: Zap,
      title: t.featuresPage.cards[5].title,
      desc: t.featuresPage.cards[5].desc,
      accent: "text-primary",
    },
  ]

  return (
    <section id="fonctionnalites" className="relative py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <span className="text-sm font-semibold uppercase tracking-widest text-primary">
            {t.featuresPage.sectionLabel}
          </span>
          <h2 className="mt-3 font-heading text-4xl font-bold tracking-tight text-balance sm:text-5xl">
            {t.featuresPage.heading.split(", ")[0]},
            {" "}
            <span className="gradient-text">{t.featuresPage.heading.split(", ")[1]}</span>
          </h2>
          <p className="mt-4 text-lg leading-relaxed text-muted-foreground text-pretty">
            {t.featuresPage.description}
          </p>
        </div>

        <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="gradient-border group relative overflow-hidden rounded-2xl glass p-6 transition-all duration-300 hover:-translate-y-1"
            >
              <span
                className={cn(
                  "inline-flex size-12 items-center justify-center rounded-xl bg-secondary/80 transition-transform group-hover:scale-110",
                  f.accent,
                )}
              >
                <f.icon className="size-6" />
              </span>
              <h3 className="mt-5 font-heading text-xl font-bold">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

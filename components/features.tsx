import { Gavel, Shield, Briefcase, Globe, BookText, Zap } from "lucide-react"
import { cn } from "@/lib/utils"

const FEATURES = [
  {
    icon: Gavel,
    title: "Droit Civil",
    desc: "Famille, propriété, contrats. Des réponses claires sur vos droits civils.",
    accent: "text-primary",
  },
  {
    icon: Shield,
    title: "Droit Pénal",
    desc: "Infractions, procédures, défense. Comprenez vos droits face à la justice.",
    accent: "text-haiti-red",
  },
  {
    icon: Briefcase,
    title: "Droit du Travail",
    desc: "Emploi, licenciements, droits. Protégez votre vie professionnelle.",
    accent: "text-gold",
  },
  {
    icon: Globe,
    title: "Multilingue",
    desc: "Français, Créole et Anglais. La justice dans votre langue.",
    accent: "text-primary",
  },
  {
    icon: BookText,
    title: "Réponses Sourcées",
    desc: "Citations d'articles de loi exacts pour chaque réponse fournie.",
    accent: "text-gold",
  },
  {
    icon: Zap,
    title: "Disponible 24/7",
    desc: "Toujours accessible, où que vous soyez, à tout moment.",
    accent: "text-primary",
  },
]

export function Features() {
  return (
    <section id="fonctionnalites" className="relative py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <span className="text-sm font-semibold uppercase tracking-widest text-primary">
            Fonctionnalités
          </span>
          <h2 className="mt-3 font-heading text-4xl font-bold tracking-tight text-balance sm:text-5xl">
            Tout le droit haïtien,{" "}
            <span className="gradient-text">en un seul endroit</span>
          </h2>
          <p className="mt-4 text-lg leading-relaxed text-muted-foreground text-pretty">
            Une intelligence entraînée sur les textes de loi haïtiens pour vous
            guider à chaque étape.
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

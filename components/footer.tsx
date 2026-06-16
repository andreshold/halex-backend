import Link from "next/link"
import { Globe, MessageCircle, Send, Share2, Heart } from "lucide-react"
import { ScalesIcon } from "@/components/scales-icon"

const COLUMNS = [
  {
    title: "Produit",
    links: ["Fonctionnalités", "Documents", "Tarifs", "API"],
  },
  {
    title: "Légal",
    links: ["Conditions", "Confidentialité", "Mentions légales", "Cookies"],
  },
  {
    title: "Support",
    links: ["Centre d'aide", "Contact", "Statut", "FAQ"],
  },
  {
    title: "Communauté",
    links: ["Blog", "Discord", "Partenaires", "Carrières"],
  },
]

const SOCIALS = [Globe, MessageCircle, Send, Share2]

export function Footer() {
  return (
    <footer className="relative overflow-hidden border-t border-primary/20">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent" />
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="grid gap-10 lg:grid-cols-[1.4fr_repeat(4,1fr)]">
          <div className="max-w-xs">
            <Link href="/" className="flex items-center gap-2.5">
              <span className="flex size-9 items-center justify-center rounded-xl bg-primary/15 text-primary glow-blue">
                <ScalesIcon className="size-5" />
              </span>
              <span className="font-heading text-lg font-bold">
                Lajistis<span className="text-primary"> AI</span>
              </span>
            </Link>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              Dwa ou, nan men ou. L&apos;intelligence juridique haïtienne au
              service de millions de citoyens.
            </p>
            <div className="mt-5 flex gap-2">
              {SOCIALS.map((Icon, i) => (
                <a
                  key={i}
                  href="#"
                  className="flex size-9 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary"
                  aria-label="Réseau social"
                >
                  <Icon className="size-4" />
                </a>
              ))}
            </div>
          </div>

          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h4 className="font-heading text-sm font-semibold text-foreground">
                {col.title}
              </h4>
              <ul className="mt-4 flex flex-col gap-2.5">
                {col.links.map((l) => (
                  <li key={l}>
                    <a
                      href="#"
                      className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {l}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-center gap-4 border-t border-border pt-8">
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            Fait avec <Heart className="size-4 fill-haiti-red text-haiti-red" />{" "}
            pour Haïti
            <span aria-hidden="true">🇭🇹</span>
          </p>
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} Lajistis AI. Tous droits réservés.
          </p>
        </div>
      </div>
      <div className="haiti-line h-1 w-full opacity-70" />
    </footer>
  )
}

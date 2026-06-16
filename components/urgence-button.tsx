import { Siren } from "lucide-react"

export function UrgenceButton() {
  return (
    <button
      type="button"
      className="group fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full bg-destructive px-4 py-3 text-sm font-semibold text-destructive-foreground shadow-lg animate-pulse-glow transition-transform hover:scale-105"
      aria-label="Urgence juridique"
    >
      <Siren className="size-5" />
      <span className="hidden sm:inline">Urgence Juridique</span>
    </button>
  )
}

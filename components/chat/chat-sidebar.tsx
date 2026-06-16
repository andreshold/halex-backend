"use client"

import Link from "next/link"
import {
  Search,
  Plus,
  Gavel,
  Shield,
  Briefcase,
  Users,
  MessageSquare,
  Settings,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { ScalesIcon } from "@/components/scales-icon"

const CATEGORIES = [
  { label: "Droit Civil", icon: Gavel, color: "text-primary" },
  { label: "Droit Pénal", icon: Shield, color: "text-haiti-red" },
  { label: "Travail", icon: Briefcase, color: "text-gold" },
  { label: "Famille", icon: Users, color: "text-primary" },
]

const HISTORY = [
  "Procédure de divorce en Haïti",
  "Droits du locataire",
  "Contrat de travail rompu",
  "Héritage et succession",
  "Plainte pour diffamation",
]

export function ChatSidebar({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  return (
    <>
      {open && (
        <button
          type="button"
          aria-label="Fermer le menu"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-background/70 backdrop-blur-sm lg:hidden"
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-sidebar-border bg-sidebar transition-transform duration-300 lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        {/* logo */}
        <div className="flex items-center justify-between gap-2 px-4 py-4">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="relative flex size-9 items-center justify-center rounded-xl bg-primary/15 text-primary glow-blue">
              <ScalesIcon className="size-5" />
              <span className="absolute -bottom-0.5 -right-0.5 size-3 rounded-full border-2 border-sidebar bg-green-500" />
            </span>
            <span className="font-heading text-base font-bold">
              Lajistis<span className="text-primary"> AI</span>
            </span>
          </Link>
          <button
            type="button"
            onClick={onClose}
            className="flex size-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-sidebar-accent lg:hidden"
            aria-label="Fermer"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* new question */}
        <div className="px-3">
          <button
            type="button"
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition-transform hover:scale-[1.02] glow-blue"
          >
            <Plus className="size-4" />
            Nouvelle Question
          </button>
        </div>

        {/* search */}
        <div className="px-3 py-3">
          <div className="flex items-center gap-2 rounded-lg border border-sidebar-border bg-background/50 px-3 py-2">
            <Search className="size-4 text-muted-foreground" />
            <input
              placeholder="Rechercher..."
              className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 pb-4">
          {/* categories */}
          <p className="px-2 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Catégories
          </p>
          <div className="flex flex-col gap-0.5">
            {CATEGORIES.map((c) => (
              <button
                key={c.label}
                type="button"
                className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-foreground/80 transition-colors hover:bg-sidebar-accent"
              >
                <c.icon className={cn("size-4", c.color)} />
                {c.label}
              </button>
            ))}
          </div>

          {/* history */}
          <p className="px-2 pb-2 pt-5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Conversations
          </p>
          <div className="flex flex-col gap-0.5">
            {HISTORY.map((h, i) => (
              <button
                key={h}
                type="button"
                className={cn(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground",
                  i === 0 && "bg-sidebar-accent text-foreground",
                )}
              >
                <MessageSquare className="size-4 shrink-0 opacity-70" />
                <span className="truncate">{h}</span>
              </button>
            ))}
          </div>
        </div>

        {/* profile */}
        <div className="border-t border-sidebar-border p-3">
          <button
            type="button"
            className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition-colors hover:bg-sidebar-accent"
          >
            <span className="flex size-9 items-center justify-center rounded-full bg-gradient-to-br from-primary to-gold text-sm font-bold text-background">
              JC
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-foreground">
                Jean Citoyen
              </span>
              <span className="block text-xs text-muted-foreground">
                Plan Citoyen
              </span>
            </span>
            <Settings className="size-4 text-muted-foreground" />
          </button>
        </div>
      </aside>
    </>
  )
}

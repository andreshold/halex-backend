"use client"

import { useState } from "react"
import { Mic, ArrowUp } from "lucide-react"
import { cn } from "@/lib/utils"

export function ChatInput({ onSend }: { onSend: (text: string) => void }) {
  const [value, setValue] = useState("")
  const [recording, setRecording] = useState(false)

  const submit = () => {
    const text = value.trim()
    if (!text) return
    onSend(text)
    setValue("")
  }

  return (
    <div className="border-t border-border bg-background/70 px-4 py-4 backdrop-blur-xl sm:px-6">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2 rounded-2xl border border-border bg-secondary/40 p-2 shadow-[inset_0_1px_3px_rgba(0,0,0,0.4)] transition-all focus-within:border-primary/50 focus-within:glow-blue">
          <button
            type="button"
            onClick={() => setRecording((v) => !v)}
            className={cn(
              "flex size-10 shrink-0 items-center justify-center rounded-xl transition-colors",
              recording
                ? "bg-destructive text-destructive-foreground animate-pulse-glow"
                : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )}
            aria-label="Entrée vocale"
          >
            <Mic className="size-5" />
          </button>

          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                submit()
              }
            }}
            rows={1}
            placeholder="Décrivez votre situation juridique..."
            className="max-h-40 flex-1 resize-none self-center bg-transparent py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />

          <button
            type="button"
            onClick={submit}
            disabled={!value.trim()}
            className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-transform hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40 enabled:glow-blue"
            aria-label="Envoyer"
          >
            <ArrowUp className="size-5" />
          </button>
        </div>
        <p className="mt-2.5 text-center text-xs text-muted-foreground">
          Lajistis AI fournit des informations juridiques, pas de conseil légal
          professionnel.
        </p>
      </div>
    </div>
  )
}

"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Menu, ArrowLeft, Sparkles } from "lucide-react"
import { ChatSidebar } from "@/components/chat/chat-sidebar"
import { ChatInput } from "@/components/chat/chat-input"
import {
  AiMessage,
  UserMessage,
  TypingIndicator,
  type ChatMessage,
} from "@/components/chat/message"
import { ScalesIcon } from "@/components/scales-icon"

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "ai",
  content:
    "Bonjou! Mwen se Lajistis AI, asistan jiridik ou. Posez-moi vos questions sur le droit haïtien — droit civil, pénal, du travail ou familial — et je vous répondrai avec les articles de loi exacts.",
  sources: [{ article: "Préambule", code: "Constitution 1987" }],
  confidence: 96,
}

const SUGGESTIONS = [
  "Quels sont mes droits en cas de licenciement ?",
  "Comment se déroule une procédure de divorce ?",
  "Que faire si mon propriétaire m'expulse ?",
  "Quels sont mes droits lors d'une garde à vue ?",
]

const SAMPLE_ANSWER: Omit<ChatMessage, "id" | "role"> = {
  content:
    "En droit haïtien, plusieurs protections s'appliquent à votre situation. Le contrat ne peut être rompu sans motif légitime, et un préavis ainsi qu'une indemnité peuvent vous être dus. Voici les références applicables à votre cas.",
  sources: [
    { article: "Art. 45", code: "Code du Travail" },
    { article: "Art. 1134", code: "Code Civil" },
  ],
  confidence: 88,
}

export default function ChatPage() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME])
  const [typing, setTyping] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const hasUser = messages.some((m) => m.role === "user")

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    })
  }, [messages, typing])

  const send = (text: string) => {
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
    }
    setMessages((m) => [...m, userMsg])
    setTyping(true)
    setTimeout(() => {
      setTyping(false)
      setMessages((m) => [
        ...m,
        { id: `a-${Date.now()}`, role: "ai", ...SAMPLE_ANSWER },
      ])
    }, 1600)
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      <ChatSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* top bar */}
        <header className="flex items-center justify-between gap-3 border-b border-border bg-background/70 px-4 py-3 backdrop-blur-xl">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="flex size-9 items-center justify-center rounded-lg border border-border text-foreground lg:hidden"
              aria-label="Ouvrir le menu"
            >
              <Menu className="size-5" />
            </button>
            <div>
              <h1 className="font-heading text-sm font-semibold">
                Assistant Juridique
              </h1>
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className="size-1.5 rounded-full bg-green-500" />
                En ligne
              </p>
            </div>
          </div>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" />
            Accueil
          </Link>
        </header>

        {/* messages */}
        <div
          ref={scrollRef}
          className="relative flex-1 overflow-y-auto"
        >
          <div className="pointer-events-none absolute inset-0 grid-pattern opacity-30" />
          {/* coat of arms watermark */}
          <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-[0.025]">
            <ScalesIcon className="size-[420px] text-primary" />
          </div>

          <div className="relative mx-auto flex max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6">
            {messages.map((m) =>
              m.role === "ai" ? (
                <AiMessage key={m.id} message={m} />
              ) : (
                <UserMessage key={m.id} content={m.content} />
              ),
            )}
            {typing && <TypingIndicator />}

            {!hasUser && !typing && (
              <div className="mt-2">
                <p className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  <Sparkles className="size-3.5 text-gold" />
                  Questions suggérées
                </p>
                <div className="grid gap-2.5 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => send(s)}
                      className="gradient-border rounded-xl glass px-4 py-3 text-left text-sm text-foreground/90 transition-all hover:-translate-y-0.5"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        <ChatInput onSend={send} />
      </div>
    </div>
  )
}

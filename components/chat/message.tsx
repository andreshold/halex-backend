"use client"

import { Copy, Share2, ThumbsUp, ThumbsDown, FileText } from "lucide-react"
import { cn } from "@/lib/utils"
import { ScalesIcon } from "@/components/scales-icon"
import { JusticeMeter } from "@/components/chat/justice-meter"
import { useLanguage } from "@/lib/language-context"

export type Source = { article: string; code: string }

export type ChatMessage = {
  id: string
  role: "ai" | "user"
  content: string
  sources?: Source[]
  confidence?: number
}

export function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-2xl rounded-br-md bg-gradient-to-br from-primary to-[#1d4ed8] px-4 py-3 text-sm leading-relaxed text-primary-foreground shadow-lg">
        {content}
      </div>
    </div>
  )
}

export function AiMessage({ message }: { message: ChatMessage }) {
  const { t } = useLanguage()
  const confidence = message.confidence ?? 92
  return (
    <div className="flex gap-3">
      <span className="mt-1 flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary glow-blue">
        <ScalesIcon className="size-5" />
      </span>
      <div className="flex max-w-[85%] flex-col gap-3">
        <div className="rounded-2xl rounded-tl-md glass px-4 py-3.5">
          <div className="mb-1.5 flex items-center gap-2">
            <span className="font-heading text-sm font-semibold text-foreground">
              Lajistis AI
            </span>
            <span className="rounded-full bg-green-500/15 px-2 py-0.5 text-[10px] font-medium text-green-400">
              {t.message.highConfidence}
            </span>
          </div>
          <p className="text-sm leading-relaxed text-foreground/90">
            {message.content}
          </p>

          {message.sources && message.sources.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {message.sources.map((s) => (
                <span
                  key={`${s.article}-${s.code}`}
                  className="inline-flex items-center gap-1.5 rounded-full border border-gold/30 bg-gold/10 px-2.5 py-1 font-mono text-xs text-gold"
                >
                  <FileText className="size-3" />
                  {s.article} — {s.code}
                </span>
              ))}
            </div>
          )}

          {/* confidence bar */}
          <div className="mt-3 flex items-center gap-3">
            <JusticeMeter score={confidence} />
            <div className="flex-1">
              <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>{t.message.lajistisScore}</span>
                <span className="font-mono">{confidence}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-green-500 to-primary"
                  style={{ width: `${confidence}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* actions */}
        <div className="flex items-center gap-1">
          <Action icon={Copy} label={t.message.copy} />
          <Action icon={Share2} label={t.message.share} />
          <Action icon={ThumbsUp} label={t.message.useful} />
          <Action icon={ThumbsDown} label={t.message.notUseful} />
        </div>
      </div>
    </div>
  )
}

function Action({
  icon: Icon,
  label,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
}) {
  return (
    <button
      type="button"
      className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      aria-label={label}
      title={label}
    >
      <Icon className="size-4" />
    </button>
  )
}

export function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <span className="mt-1 flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary glow-blue">
        <ScalesIcon className="size-5" />
      </span>
      <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-md glass px-4 py-4">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="size-2 animate-bounce rounded-full bg-primary"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  )
}

export function MessageSkeleton() {
  return (
    <div className="flex gap-3">
      <span className="mt-1 size-9 shrink-0 animate-pulse rounded-full bg-secondary" />
      <div className="flex w-full max-w-[85%] flex-col gap-2 rounded-2xl glass p-4">
        <span className="h-3 w-1/3 animate-pulse rounded bg-secondary" />
        <span className="h-3 w-full animate-pulse rounded bg-secondary" />
        <span className="h-3 w-4/5 animate-pulse rounded bg-secondary" />
        <span className={cn("h-3 w-2/3 animate-pulse rounded bg-secondary")} />
      </div>
    </div>
  )
}

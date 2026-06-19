"use client"

import { useEffect, useState } from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"
import { ScalesIcon } from "@/components/scales-icon"
import { useLanguage } from "@/lib/language-context"

type Mode = "in" | "up"

export function AuthModal({
  open,
  mode,
  onClose,
  onModeChange,
}: {
  open: boolean
  mode: Mode
  onClose: () => void
  onModeChange: (m: Mode) => void
}) {
  const { t } = useLanguage()
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    document.addEventListener("keydown", onKey)
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.style.overflow = ""
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button
        type="button"
        aria-label={t.authModal.closeLabel}
        onClick={onClose}
        className="absolute inset-0 bg-background/80 backdrop-blur-md animate-fade-up"
      />
      <div className="relative w-full max-w-md animate-fade-up overflow-hidden rounded-3xl glass-strong p-7">
        {/* watermark */}
        <div className="pointer-events-none absolute -right-8 -top-8 opacity-[0.06]">
          <ScalesIcon className="size-48 text-primary" />
        </div>
        <div className="haiti-line absolute inset-x-0 top-0 h-1 opacity-60" />

        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 flex size-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          aria-label="Fermer la fenêtre"
        >
          <X className="size-5" />
        </button>

        <div className="relative flex items-center gap-2.5">
          <span className="flex size-10 items-center justify-center rounded-xl bg-primary/15 text-primary glow-blue">
            <ScalesIcon className="size-5" />
          </span>
          <span className="font-heading text-lg font-bold">
            Lajistis<span className="text-primary"> AI</span>
          </span>
        </div>

        <h2 className="relative mt-6 font-heading text-2xl font-bold">
          {mode === "up" ? t.authModal.createAccount : t.authModal.welcomeBack}
        </h2>
        <p className="relative mt-1 text-sm text-muted-foreground">
          {mode === "up" ? t.authModal.join : t.authModal.access}
        </p>

        {/* tabs */}
        <div className="relative mt-6 grid grid-cols-2 gap-1 rounded-xl border border-border bg-secondary/50 p-1">
          <button
            type="button"
            onClick={() => onModeChange("up")}
            className={cn(
              "rounded-lg py-2 text-sm font-medium transition-colors",
              mode === "up" ? "bg-primary text-primary-foreground" : "text-muted-foreground",
            )}
          >
            {t.authModal.signUpTab}
          </button>
          <button
            type="button"
            onClick={() => onModeChange("in")}
            className={cn(
              "rounded-lg py-2 text-sm font-medium transition-colors",
              mode === "in" ? "bg-primary text-primary-foreground" : "text-muted-foreground",
            )}
          >
            {t.authModal.signInTab}
          </button>
        </div>

        <form
          className="relative mt-6 flex flex-col gap-4"
          onSubmit={(e) => e.preventDefault()}
        >
          <FloatingField label={t.authModal.emailLabel} type="email" />
          <FloatingField label={t.authModal.passwordLabel} type="password" />

          <button
            type="submit"
            className="mt-2 rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground transition-transform hover:scale-[1.02] glow-blue"
          >
            {mode === "up" ? t.authModal.createAccountCta : t.authModal.signInCta}
          </button>
        </form>

        <div className="relative my-5 flex items-center gap-3">
          <span className="h-px flex-1 bg-border" />
          <span className="text-xs text-muted-foreground">{t.authModal.or}</span>
          <span className="h-px flex-1 bg-border" />
        </div>

        <button
          type="button"
          className="relative flex w-full items-center justify-center gap-3 rounded-xl border border-border bg-secondary/40 py-3 text-sm font-medium transition-colors hover:bg-secondary"
        >
          <GoogleIcon />
          {t.authModal.continueWithGoogle}
        </button>
      </div>
    </div>
  )
}

function FloatingField({ label, type }: { label: string; type: string }) {
  const [value, setValue] = useState("")
  return (
    <div className="group relative">
      <input
        type={type}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        id={label}
        className="peer w-full rounded-xl border border-input bg-background/60 px-4 pb-2 pt-5 text-sm text-foreground shadow-[inset_0_1px_2px_rgba(0,0,0,0.4)] outline-none transition-colors focus:border-primary/60 focus:glow-blue"
        placeholder=" "
      />
      <label
        htmlFor={label}
        className="pointer-events-none absolute left-4 top-3.5 text-sm text-muted-foreground transition-all peer-focus:top-1.5 peer-focus:text-xs peer-focus:text-primary peer-[:not(:placeholder-shown)]:top-1.5 peer-[:not(:placeholder-shown)]:text-xs"
      >
        {label}
      </label>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1Z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.99.66-2.26 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z"
      />
    </svg>
  )
}

import { cn } from "@/lib/utils"

export function ScalesIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("size-6", className)}
      aria-hidden="true"
    >
      <path d="M12 3v18" />
      <path d="M7 21h10" />
      <path d="M5 6h14" />
      <path d="M8 6 4.5 13a3.5 3.5 0 0 0 7 0L8 6Z" />
      <path d="M16 6l-3.5 7a3.5 3.5 0 0 0 7 0L16 6Z" />
      <circle cx="12" cy="4" r="1.4" fill="currentColor" stroke="none" />
    </svg>
  )
}

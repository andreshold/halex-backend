import { cn } from "@/lib/utils"

export function JusticeMeter({
  score,
  className,
}: {
  score: number
  className?: string
}) {
  const radius = 16
  const circ = 2 * Math.PI * radius
  const offset = circ - (score / 100) * circ
  const color =
    score >= 80 ? "#22c55e" : score >= 55 ? "#f59e0b" : "#dc2626"

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)}>
      <svg viewBox="0 0 40 40" className="size-11 -rotate-90">
        <circle cx="20" cy="20" r={radius} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="3.5" />
        <circle
          cx="20"
          cy="20"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 1s ease" }}
        />
      </svg>
      <span className="absolute font-mono text-[10px] font-bold text-foreground">
        {score}
      </span>
    </div>
  )
}

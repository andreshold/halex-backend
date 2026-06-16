const ITEMS = [
  "Claude AI",
  "LangChain",
  "Constitution Haïtienne 1987",
  "Code Civil",
  "Code Pénal",
  "Code du Travail",
  "RAG Juridique",
]

export function TechStack() {
  const loop = [...ITEMS, ...ITEMS]
  return (
    <section className="relative border-y border-border py-10">
      <p className="mb-6 text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Propulsé par
      </p>
      <div className="relative overflow-hidden [mask-image:linear-gradient(90deg,transparent,#000_12%,#000_88%,transparent)]">
        <div className="flex w-max animate-marquee items-center gap-4">
          {loop.map((item, i) => (
            <span
              key={`${item}-${i}`}
              className="inline-flex shrink-0 items-center gap-2 rounded-full glass px-5 py-2.5 text-sm font-medium text-foreground/90"
            >
              <span className="size-1.5 rounded-full bg-gold" />
              {item}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

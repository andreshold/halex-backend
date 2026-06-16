"use client"

import { useState } from "react"
import { Navbar } from "@/components/navbar"
import { Particles } from "@/components/particles"
import { Hero } from "@/components/hero"
import { Features } from "@/components/features"
import { Documents } from "@/components/documents"
import { Pricing } from "@/components/pricing"
import { TechStack } from "@/components/tech-stack"
import { Footer } from "@/components/footer"
import { AuthModal } from "@/components/auth-modal"
import { UrgenceButton } from "@/components/urgence-button"

export default function Page() {
  const [authOpen, setAuthOpen] = useState(false)
  const [authMode, setAuthMode] = useState<"in" | "up">("up")

  const openAuth = (mode: "in" | "up") => {
    setAuthMode(mode)
    setAuthOpen(true)
  }

  return (
    <main className="relative min-h-screen overflow-x-hidden">
      {/* fixed star field across the whole page */}
      <div className="pointer-events-none fixed inset-0 z-0">
        <Particles className="size-full" />
      </div>

      <div className="relative z-10">
        <Navbar onAuth={openAuth} />
        <Hero onAuth={openAuth} />
        <Features />
        <Documents />
        <Pricing onAuth={openAuth} />
        <TechStack />
        <Footer />
      </div>

      <UrgenceButton />
      <AuthModal
        open={authOpen}
        mode={authMode}
        onClose={() => setAuthOpen(false)}
        onModeChange={setAuthMode}
      />
    </main>
  )
}

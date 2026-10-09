"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { setCachedUser } from "@/lib/auth";
import { fetchMe } from "@/lib/api";

export default function Landing() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    (async () => {
      const { data } = await supabase.auth.getSession();
      if (data.session?.access_token) {
        try {
          const me = await fetchMe();
          setCachedUser(me.name);
          router.replace(me.is_teacher ? "/school/dashboard" : me.grade_level ? "/app" : "/onboarding");
        } catch {
          router.replace("/login");
        }
        return;
      }
      setChecking(false);
    })();
  }, [router]);

  // Force light mode on landing page (no dark mode here)
  useEffect(() => {
    document.documentElement.classList.remove("dark");
  }, []);

  useEffect(() => {
    if (checking) return;

    // Scroll reveal
    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("vis");
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -30px 0px" }
    );

    document.querySelectorAll(".reveal").forEach((el) => revealObserver.observe(el));

    // Nav border on scroll
    const nav = document.getElementById("nav");
    const onScroll = () => {
      nav?.classList.toggle("scrolled", window.scrollY > 20);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
      anchor.addEventListener("click", (e) => {
        const targetId = anchor.getAttribute("href");
        if (targetId && targetId.length > 1) {
          const targetElement = document.querySelector(targetId);
          if (targetElement) {
            e.preventDefault();
            targetElement.scrollIntoView({ behavior: "smooth" });
          }
        }
      });
    });

    // Header CTA visibility for mobile and tablet
    const headerCta = document.querySelector(".nav-btn-wrap");
    const heroSection = document.querySelector(".hero");
    if (headerCta && heroSection) {
      const mobileTabletQuery = window.matchMedia("(max-width: 900px)");
      const updateHeaderCta = () => {
        const pastHero = heroSection.getBoundingClientRect().bottom <= 0;
        const shouldShowCta = !mobileTabletQuery.matches || pastHero;
        headerCta.classList.toggle("visible", shouldShowCta);
        nav?.classList.toggle(
          "cta-visible",
          shouldShowCta && mobileTabletQuery.matches
        );
      };

      window.addEventListener("scroll", updateHeaderCta, { passive: true });
      window.addEventListener("resize", updateHeaderCta);
      updateHeaderCta();
    }

    return () => {
      revealObserver.disconnect();
      window.removeEventListener("scroll", onScroll);
    };
  }, [checking]);

  if (checking) {
    return (
      <main className="onboarding flex min-h-screen items-center justify-center bg-paper">
        <p className="font-onb-ui text-sm text-ink-soft">Loading…</p>
      </main>
    );
  }

  return (
    <>
      {/* Google Fonts: DM Sans */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link
        rel="preconnect"
        href="https://fonts.gstatic.com"
        crossOrigin="anonymous"
      />
      <link
        href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap"
        rel="stylesheet"
      />

      <style dangerouslySetInnerHTML={{ __html: landingCSS }} />

      <div dangerouslySetInnerHTML={{ __html: landingHTML }} />
    </>
  );
}

const landingCSS = `
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
html {
  scroll-behavior: smooth;
}
body {
  font-family: 'DM Sans', system-ui, sans-serif !important;
  background: #fff;
  color: #3c3c3c;
  line-height: 1.6;
  overflow-x: hidden;
}
h1, h2, h3, h4 {
  font-family: 'DM Sans', system-ui, sans-serif !important;
  font-weight: 700;
}
a {
  color: inherit;
  text-decoration: none;
}
ul {
  list-style: none;
}

/* ── NAV ── */
.nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: #fff;
  border-bottom: 1px solid transparent;
  height: 64px;
  transition: border-color 0.3s;
}
.nav.scrolled {
  border-bottom: 1px solid #d5d5d5;
}
.nav-inner {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 32px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.nav-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 1.1rem;
  color: #3c3c3c;
}
.nav-logo svg {
  height: 32px;
  width: auto;
  display: block;
}
.nav-links {
  display: flex;
  align-items: center;
  gap: 24px;
}
.nav-links a {
  font-size: 14px;
  font-weight: 500;
  color: #666;
  transition: color 0.2s;
}
.nav-links a:hover {
  color: #3c3c3c;
}

/* 3D Button system */
.btn-3d {
  position: relative;
  border: none;
  background: transparent;
  padding: 0;
  cursor: pointer;
  outline-offset: 4px;
  transition: filter 0.25s;
  user-select: none;
  touch-action: manipulation;
  display: inline-block;
  font-family: inherit;
}
.btn-3d .bs {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.2);
  will-change: transform;
  transform: translateY(3px);
  transition: transform 0.6s cubic-bezier(0.3, 0.7, 0.4, 1);
}
.btn-3d .be {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border-radius: 12px;
  background: linear-gradient(to left, hsl(0 0% 0% / 0.15) 0%, hsl(0 0% 0% / 0.25) 8%, hsl(0 0% 0% / 0.25) 92%, hsl(0 0% 0% / 0.15) 100%);
}
.btn-3d .bf {
  display: block;
  position: relative;
  padding: 12px 27px;
  border-radius: 12px;
  font-size: 1.1rem;
  font-weight: 700;
  color: #fff;
  background: #3b6e5e;
  will-change: transform;
  transform: translateY(-4px);
  transition: transform 0.6s cubic-bezier(0.3, 0.7, 0.4, 1);
}
.btn-3d:hover {
  filter: brightness(110%);
}
.btn-3d:hover .bf {
  transform: translateY(-6px);
  transition: transform 0.25s cubic-bezier(0.3, 0.7, 0.4, 1.5);
}
.btn-3d:hover .bs {
  transform: translateY(4px);
  transition: transform 0.25s cubic-bezier(0.3, 0.7, 0.4, 1.5);
}
.btn-3d:active .bf {
  transform: translateY(-2px);
  transition: transform 34ms;
}
.btn-3d:active .bs {
  transform: translateY(1px);
  transition: transform 34ms;
}

/* White variant */
.btn-3d-w .bs {
  background: rgba(0, 0, 0, 0.15);
}
.btn-3d-w .be {
  background: linear-gradient(to left, #b8b8b8 0%, #c8c8c8 8%, #c8c8c8 92%, #b8b8b8 100%);
}
.btn-3d-w .bf {
  background: #fff;
  color: #3b6e5e;
  border: 1.5px solid #d5d5d5;
}

/* Nav button smaller */
.nav-btn .bf {
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.nav-btn .bs {
  background: rgba(0, 0, 0, 0.12);
  transform: translateY(1.5px);
}
.nav-btn .be {
  background: linear-gradient(to left, hsl(0 0% 0% / 0.08) 0%, hsl(0 0% 0% / 0.12) 8%, hsl(0 0% 0% / 0.12) 92%, hsl(0 0% 0% / 0.08) 100%);
}
.nav-btn .bf {
  transform: translateY(-2px);
}
.nav-btn:hover .bf {
  transform: translateY(-3px);
}
.nav-btn:hover .bs {
  transform: translateY(2px);
}
.nav-btn:active .bf {
  transform: translateY(-1px);
}
.nav-btn:active .bs {
  transform: translateY(0.5px);
}

/* ── HERO ── */
.hero {
  padding: 120px 32px 60px;
  max-width: 1100px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 64px;
  align-items: center;
  min-height: 80vh;
}
.hero-spacer {
  width: 100%;
  max-width: 320px;
  aspect-ratio: 1/1;
  margin: 0 auto;
}
.hero-content {
  text-align: left;
}
.hero h1 {
  font-size: clamp(2.2rem, 4.5vw, 3.2rem);
  font-weight: 700;
  line-height: 1.1;
  color: #3c3c3c;
  margin-bottom: 20px;
  letter-spacing: -0.02em;
}
.hero-sub {
  font-size: 18px;
  color: #666;
  line-height: 1.6;
  margin-bottom: 36px;
  max-width: 420px;
}
.hero-btns {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 400px;
  margin-bottom: 32px;
}
.hero-social {
  display: flex;
  align-items: center;
  gap: 10px;
}
.hero-avatars {
  display: flex;
}
.hero-av {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid #fff;
  margin-left: -8px;
  display: inline-block;
}
.hero-av:first-child {
  margin-left: 0;
}
.hero-av:nth-child(1) { background: #3B656E; }
.hero-av:nth-child(2) { background: #3B6E5E; }
.hero-av:nth-child(3) { background: #3B6E44; }
.hero-av:nth-child(4) { background: #E7EAE4; }
.hero-social span {
  font-size: 14px;
  color: #666;
}
.hero-social strong {
  color: #3c3c3c;
}

/* ── SUBJECTS ── */
.subjects {
  padding: 40px 32px 60px;
  max-width: 1100px;
  margin: 0 auto;
  border-top: 1px solid #e5e5e5;
}
.subjects-row {
  display: flex;
  justify-content: center;
  gap: 24px;
  flex-wrap: wrap;
}
.subject {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight:500;
  color: #666;
  transition: color 0.2s;
  cursor: default;
}
.subject:hover {
  color: #3c3c3c;
}
.subject-icon {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}
.subject-icon.green { background: #3b6e5e; }
.subject-icon.blue { background: #7ca8c8; }
.subject-icon.purple { background: #b8b0d8; }
.subject-icon.pink { background: #e8a0b4; }
.subject-icon.orange { background: #e8985c; }

/* ── FEATURES ── */
.features {
  padding: 80px 32px;
  max-width: 1100px;
  margin: 0 auto;
}
.feat {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 64px;
  align-items: center;
  margin-bottom: 80px;
}
.feat.rev .feat-vis {
  order: -1;
}
.feat h2 {
  font-size: clamp(1.8rem, 3.5vw, 2.6rem);
  font-weight: 700;
  line-height: 1.12;
  color: #3c3c3c;
  margin-bottom: 16px;
  letter-spacing: -0.015em;
}
.feat p {
  font-size: 17px;
  color: #666;
  line-height: 1.65;
  max-width: 420px;
}
.feat-vis {
  display: flex;
  justify-content: center;
}
.geo-card {
  width: 100%;
  max-width: 400px;
  aspect-ratio: 4/3;
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gc-green { background: linear-gradient(135deg, #e8f0ec, #d4e8dc); }
.gc-green .circles { position: relative; width: 180px; height: 180px; }
.gc-green .c1 { width: 100px; height: 100px; background: #3b6e5e; border-radius: 50%; position: absolute; top: 8px; left: 16px; opacity: 0.85; }
.gc-green .c2 { width: 72px; height: 72px; background: #f0d060; border-radius: 50%; position: absolute; bottom: 8px; right: 8px; opacity: 0.8; }
.gc-green .c3 { width: 48px; height: 48px; background: #e8a0b4; border-radius: 12px; position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%) rotate(12deg); opacity: 0.65; }

.gc-blue { background: linear-gradient(135deg, #ecf4f8, #c4dfe8); }
.gc-blue .blocks { display: grid; grid-template-columns: repeat(4,1fr); gap: 6px; padding: 16px; }
.gc-blue .block { width: 40px; height: 40px; border-radius: 8px; }
.gc-blue .block:nth-child(odd) { background: #3c3c3c; opacity: 0.7; }
.gc-blue .block:nth-child(even) { background: #7ca8c8; opacity: 0.6; }
.gc-blue .block:nth-child(3n) { background: #3b6e5e; opacity: 0.65; border-radius: 50%; }

.gc-pink { background: linear-gradient(135deg, #fdf0f4, #f4dce4); }
.gc-pink .lines { position: relative; width: 200px; height: 160px; }
.gc-pink .line { position: absolute; height: 3px; border-radius: 2px; }
.gc-pink .l1 { width: 120px; background: #e8a0b4; top: 24px; left: 16px; }
.gc-pink .l2 { width: 88px; background: #b8b0d8; top: 56px; left: 48px; }
.gc-pink .l3 { width: 140px; background: #3b6e5e; top: 88px; left: 8px; }
.gc-pink .dot { width: 14px; height: 14px; border-radius: 50%; position: absolute; right: 0; }
.gc-pink .d1 { background: #e8a0b4; top: 18px; right: 8px; }
.gc-pink .d2 { background: #b8b0d8; top: 50px; right: 16px; }
.gc-pink .d3 { background: #3b6e5e; top: 82px; right: 0; }

.gc-purple { background: linear-gradient(135deg, #f0eef8, #dcd8f0); }
.gc-purple .streak { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.gc-purple .num { font-size: 3.5rem; font-weight: 700; color: #3c3c3c; line-height: 1; }
.gc-purple .label { font-size: 13px; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }
.gc-purple .dots { display: flex; gap: 5px; }
.gc-purple .dot { width: 12px; height: 12px; border-radius: 50%; background: #b8b0d8; opacity: 0.35; }
.gc-purple .dot.on { background: #3b6e5e; opacity: 1; }
.gc-purple .trophy { width: 40px; height: 40px; background: #f0d060; border-radius: 50% 50% 8px 8px; margin-top: 4px; }

/* ── CTA ── */
.cta {
  margin: 0 auto;
  max-width: 1040px;
  background: #3b6e5e;
  border-radius: 24px;
  padding: 64px 48px;
  text-align: center;
  position: relative;
  overflow: hidden;
}
.cta::before {
  content: '';
  position: absolute;
  width: 200px;
  height: 200px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 50%;
  top: -60px;
  right: -40px;
}
.cta h2 {
  font-size: clamp(1.8rem, 3.5vw, 2.6rem);
  font-weight: 700;
  color: #fff;
  margin-bottom: 14px;
  position: relative;
}
.cta p {
  font-size: 17px;
  color: rgba(255, 255, 255, 0.82);
  margin-bottom: 32px;
  max-width: 480px;
  margin-left: auto;
  margin-right: auto;
  position: relative;
}

/* ── FOOTER ── */
.footer {
  background: #faf8f3;
  padding: 48px 32px 24px;
  margin-top: 80px;
  border-top: 1px solid #e5e5e5;
}
.footer-inner {
  max-width: 1100px;
  margin: 0 auto;
}
.footer-top {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr;
  gap: 40px;
  padding-bottom: 32px;
  border-bottom: 1px solid #e5e5e5;
}
.footer-brand svg {
  height: 32px;
  width: auto;
  margin-bottom: 10px;
}
.footer-brand p {
  font-size: 14px;
  color: #666;
  line-height: 1.6;
  max-width: 280px;
}
.footer-col h4 {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #3c3c3c;
  margin-bottom: 12px;
}
.footer-col a {
  display: block;
  font-size: 14px;
  color: #666;
  padding: 3px 0;
  transition: color 0.2s;
}
.footer-col a:hover {
  color: #3b6e5e;
}
.footer-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 24px;
}
.footer-copy {
  font-size: 13px;
  color: #999;
}
.footer-socials {
  display: flex;
  gap: 12px;
}
.footer-soc {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #666;
  transition: all 0.2s;
  cursor: pointer;
}
.footer-soc:hover {
  background: #3b6e5e;
  color: #fff;
}

/* ── REVEAL ── */
.reveal {
  opacity: 0;
  transform: translateY(24px);
  transition: opacity 0.6s ease, transform 0.6s ease;
}
.reveal.vis {
  opacity: 1;
  transform: translateY(0);
}

/* ── RESPONSIVE ── */
@media (max-width: 900px) {
  .hero {
    grid-template-columns: 1fr;
    text-align: center;
    padding-top: 100px;
    gap: 40px;
  }
  .hero-content {
    max-width: 100%;
    margin: 0 auto;
    text-align: center;
  }
  .hero-sub {
    margin: 0 auto;
  }
  .hero-btns {
    margin: 0 auto 32px;
  }
  .hero-social {
    justify-content: center;
  }
  .hero-spacer {
    order: -1;
    max-width: 260px;
  }
  .feat {
    grid-template-columns: 1fr;
    gap: 40px;
  }
  .feat.rev .feat-vis {
    order: 0;
  }
  .feat h2, .feat p {
    text-align: center;
    max-width: 100%;
  }
  .footer-top {
    grid-template-columns: 1fr 1fr;
    gap: 32px;
  }
  .nav-btn-wrap {
    display: none;
  }
  .nav-btn-wrap.visible {
    display: flex;
    align-items: center;
    animation: headerCtaEnter 0.35s cubic-bezier(0.3, 0.7, 0.4, 1) both;
  }
  @keyframes headerCtaEnter {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
}
@media (max-width: 640px) {
  .nav-inner {
    justify-content: center;
    gap: 16px;
  }
  .nav.cta-visible .nav-inner {
    justify-content: space-between;
  }
  .nav-logo {
    margin: 0;
  }
  .nav-links a:not(.nav-btn-wrap) {
    display: none;
  }
  .hero {
    padding-top: 90px;
    padding-bottom: 40px;
    gap: 32px;
  }
  .hero h1 {
    font-size: 1.75rem;
    line-height: 1.15;
  }
  .hero-sub {
    font-size: 16px;
    line-height: 1.5;
    margin-bottom: 28px;
  }
  .hero-btns {
    gap: 16px;
  }
  .hero-social {
    margin-top: 24px;
  }
  .hero-av {
    width: 28px;
    height: 28px;
  }
  .hero-social span {
    font-size: 13px;
  }
  .subjects-row {
    flex-wrap: nowrap;
    overflow-x: auto;
    justify-content: flex-start;
    gap: 10px;
    padding-bottom: 8px;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  .subjects-row::-webkit-scrollbar {
    display: none;
  }
  .subject {
    flex-shrink: 0;
    padding: 8px 14px;
    font-size: 13px;
  }
  .subject-icon {
    width: 22px;
    height: 22px;
    font-size: 11px;
  }
  .feat {
    padding: 48px 0;
    margin-bottom: 48px;
  }
  .geo-card {
    max-width: 260px;
  }
  .cta {
    padding: 40px 20px;
    margin: 0 16px;
    border-radius: 20px;
  }
  .cta h2 {
    font-size: 1.6rem;
  }
  .cta p {
    font-size: 15px;
  }
  .footer-top {
    grid-template-columns: 1fr;
    gap: 28px;
  }
  .footer-col {
    padding: 8px 0;
  }
  .footer-bottom {
    flex-direction: column;
    gap: 16px;
  }
  .features {
    padding: 48px 20px;
  }
  .subjects {
    padding: 32px 20px 48px;
  }
}
@media (max-width: 380px) {
  .hero h1 {
    font-size: 1.6rem;
  }
  .hero-sub {
    font-size: 15px;
  }
  .btn-3d .bf {
    padding: 14px 20px;
    font-size: 1rem;
  }
  .cta {
    padding: 32px 16px;
  }
  .cta h2 {
    font-size: 1.4rem;
  }
}

/* ── DARK MODE ── */
.dark body { background: #0f2d1a; color: #faf8f3; }
.dark .nav { background: #0f2d1a; }
.dark .nav.scrolled { border-bottom-color: #2a5e3d; }
.dark .nav-logo { color: #faf8f3; }
.dark .nav-links a { color: #6b9a82; }
.dark .nav-links a:hover { color: #faf8f3; }
.dark .hero h1 { color: #faf8f3; }
.dark .hero-sub { color: #b8d4c4; }
.dark .hero-social span { color: #b8d4c4; }
.dark .hero-social strong { color: #faf8f3; }
.dark .hero-av { border-color: #0f2d1a; }
.dark .subjects { border-top-color: #2a5e3d; }
.dark .subject { color: #6b9a82; }
.dark .subject:hover { color: #faf8f3; }
.dark .feat h2 { color: #faf8f3; }
.dark .feat p { color: #b8d4c4; }
.dark .footer { background: #163d24; border-top-color: #2a5e3d; }
.dark .footer-top { border-bottom-color: #2a5e3d; }
.dark .footer-brand p { color: #6b9a82; }
.dark .footer-col h4 { color: #faf8f3; }
.dark .footer-col a { color: #6b9a82; }
.dark .footer-copy { color: #4a7a62; }
.dark .footer-soc { background: #1e4a32; color: #6b9a82; }
.dark .footer-soc:hover { background: #3b6e5e; color: #faf8f3; }
.dark .btn-3d-w .bf { background: #163d24; border-color: #2a5e3d; color: #3b6e5e; }
.dark .gc-green { background: linear-gradient(135deg, #1a3a28, #163d24); }
.dark .gc-blue { background: linear-gradient(135deg, #163d24, #1a4a2d); }
.dark .gc-pink { background: linear-gradient(135deg, #1a4a2d, #163d24); }
.dark .gc-purple { background: linear-gradient(135deg, #163d24, #1a4a2d); }
.dark .gc-purple .num { color: #faf8f3; }
.dark .gc-purple .label { color: #6b9a82; }
.dark .gc-blue .block:nth-child(odd) { background: #faf8f3; }
`;

const pixieLogoSVG = `<svg viewBox="0 0 781.53 285.07" height="32" role="img" aria-label="Pixie logo">
  <path fill="#14462b" d="M282.4,232c0,11.25,0,21.7,0,32.16a41,41,0,0,1-.67,8.94c-1.58,6.8-8.3,11.85-15.46,12.07A15.65,15.65,0,0,1,251,274.35a22.09,22.09,0,0,1-1.26-7.35q0-62.49,0-125a16.65,16.65,0,0,1,4.47-11.84c8.14-8.77,21.09-6.48,25.72,4.55.5,1.19.86,2.44,1.5,4.32,14.08-13,30.43-17.2,48.71-13.18,14.44,3.18,25.82,11.3,34.62,23,18.24,24.34,15.73,58.13-5.85,80C337.79,250.31,309.21,251.71,282.4,232Zm61.12-46.2c0-17.86-13-32-29.48-32.09-17.51-.09-32,14.5-32.05,32.23,0,17.4,13.82,31.51,30.84,31.39C330,217.19,343.52,203.34,343.52,185.77Z"/>
  <path fill="#14462b" d="M698.09,195.17c-10.83,0-21.66.14-32.48-.08-3.81-.08-4.09,1.11-3,4.3,5.36,14.94,21.19,22.31,38.2,17.63,4.88-1.34,9.2-3.81,13.51-6.35A15.34,15.34,0,0,1,735.65,217c2.45,4.92.75,9.12-2.65,12.77-7.93,8.5-18.12,12.74-29.25,15.11-32.51,6.9-63.84-10.89-72.23-41.6-6.49-23.76-1.58-45,16.61-62.24,17-16.06,37-20.55,59.19-13.53s38.33,30.42,37.82,53.59c-.19,8.67-4.43,13.54-13.07,13.8-11.31.35-22.65.09-34,.09Zm-10.2-23.12v.19c7.13,0,14.28-.14,21.41.06,3.45.1,3.86-1,2.82-4a24.24,24.24,0,0,0-24-16.65c-11.05.28-22.17,8.23-25,17.61-.76,2.56.34,2.83,2.34,2.83C673,172,680.42,172.05,687.89,172.05Z"/>
  <path fill="#14462b" d="M502.82,162.49c2-.06,2.65-1.86,3.72-3,8.46-9.42,16.82-18.93,25.32-28.31,5-5.47,11-8,18.44-5.8,9.85,2.95,13.41,13,6.78,20.76-9.72,11.41-20.06,22.28-30.14,33.39-4.4,4.85-4.28,5.85.27,10.31,10.46,10.26,20.08,21.31,29.55,32.47,5.44,6.42,5.61,13.08,1.19,18.14a15.94,15.94,0,0,1-20,3.15,27,27,0,0,1-7.1-6.24c-8.26-9.59-16.54-19.17-24.73-28.83-2.21-2.61-3.38-3.11-6,.1-7.95,9.62-16.45,18.8-24.83,28.07a44,44,0,0,1-6.94,6.44A15.31,15.31,0,0,1,448.66,241c-4.6-5-4.6-12.08.42-18.15,10.33-12.49,21.4-24.31,32.45-36.14,1-1.09,3-1.93,1.94-4.08C491.75,177.67,497.84,170.61,502.82,162.49Z"/>
  <path fill="#14462b" d="M394.72,184.82c0-13.81-.05-27.62,0-41.44,0-10.82,7-18.28,16.89-18.22,9.28,0,16.1,7.39,16.14,17.93q.15,42.43-.06,84.87c-.06,10.09-6.41,17.17-15.31,17.81-9.73.71-17.42-6.74-17.57-17.52-.2-14.47-.05-28.95-.05-43.43Z"/>
  <path fill="#14462b" d="M579.78,231.51c-.07-.64-.15-1.28-.23-1.92,1.88-1.55,1.13-3.7,1.13-5.59.05-22.22,0-44.45.06-66.67,0-8.67-.93-17.42,2-25.86v0l1-1.15c9-9.34,24.21-5.76,27.84,6.65a25,25,0,0,1,.92,6.9q.07,41.73,0,83.47c0,10.8-6.73,18.21-16.32,18.38-5.65.09-10.44-1.79-13.51-6.89l-.81-1.34-.62-1.23.71-.27-.79.08c-.19-.5-.38-1-.58-1.5C582.3,233.05,581.92,232.06,579.78,231.51Z"/>
  <path fill="#3b6e5e" d="M502.82,162.49c-5,8.12-11.07,15.18-19.35,20.13-9.85-9.21-18.31-19.72-27.64-29.41q-2.26-2.34-4.47-4.72c-5.91-6.4-7-12.49-3.25-18,3.92-5.71,12.79-7.92,19.83-4.76a17.08,17.08,0,0,1,5.38,3.55C483.46,140.09,493.51,151,502.82,162.49Z"/>
  <path fill="#14462b" d="M394.42,97.09a17.1,17.1,0,0,1,17.1-17.17c9.17,0,16.7,7.8,16.82,17.55a16.62,16.62,0,0,1-16.85,16.76A16.88,16.88,0,0,1,394.42,97.09Z"/>
  <path fill="#14462b" d="M613,97.7c0,9.22-7.49,16.43-17.14,16.39A16.94,16.94,0,0,1,595,80.22,17.42,17.42,0,0,1,613,97.7Z"/>
  <path fill="#14462b" d="M764.83,213.53a16.67,16.67,0,0,1,16.7,16.91c-.08,8.4-7.57,15.4-16.49,15.38a16.46,16.46,0,0,1-16.38-16.15A16,16,0,0,1,764.83,213.53Z"/>
  <path fill="#2c6749" d="M582.78,131.47c-3,8.44-2,17.19-2,25.86-.06,22.22,0,44.45-.06,66.67,0,1.89.75,4-1.13,5.59-.17-1.8-.49-3.6-.49-5.39q-.06-39.87,0-79.74C579,139.78,579.29,135.15,582.78,131.47Z"/>
  <path fill="#2c6749" d="M579.78,231.51c2.14.55,2.52,1.54.78,3.08A3,3,0,0,1,579.78,231.51Z"/>
  <path fill="#2c6749" d="M583.73,130.34l-1,1.15Z"/>
  <path fill="#2c6749" d="M581.14,236.09l.79-.08-.71.27Z"/>
  <path fill="#2c6749" d="M581.84,237.51l.81,1.34Z"/>
  <path fill="#3b6e5e" d="M197.57,182.66c-7.85-45.2-39.46-90.7-86-96.22-2.22-.26-5.25-.08-5.23-3.38,0-3.56,3.35-3.8,5.82-4.47,20-5.36,27.63-27.71,14.09-46.25-6.71-9.19-13.79-17.75-17.87-28.52-1.93-5.1-5-5-7.48-.11-5.41,10.7-13.35,19-22.83,26.32C64.58,40.44,61.78,71.31,85.84,78.29c2.44.7,5.83,1,5.6,4.67s-3.64,3.61-6.1,4.12c-11.27,2.36-22.16,5.79-31.6,12.53C12,129.35-3,171.19.48,220.63c2.25,32,21.71,49.93,51.33,58.44a155,155,0,0,0,49.57,5.77c15.83,1,32-1.56,47.88-6.29,28-8.34,45.32-26,49.4-55.82A129.05,129.05,0,0,0,197.57,182.66ZM58.66,221.92c-6.31,0-11.42-7.1-11.42-15.85s5.11-15.86,11.42-15.86,11.41,7.1,11.41,15.86S65,221.92,58.66,221.92Zm39-149.4c-14-.86-20.77-12.43-15.21-25.76,4.15-9.95,13.87-15.16,20.61-25.68C105.92,29,110,33.71,113.85,38.74c6.23,8.2,6.27,17.36,2,26.48C112.11,73.1,104.83,73,97.7,72.52Zm38.85,149.4c-6.31,0-11.42-7.1-11.42-15.85s5.11-15.86,11.42-15.86S148,197.31,148,206.07,142.85,221.92,136.55,221.92Z"/>
</svg>`;

const landingHTML = `
<nav class="nav" id="nav">
  <div class="nav-inner">
    <a href="/" class="nav-logo" aria-label="Pixie home">
      ${pixieLogoSVG}
    </a>
    <div class="nav-links">
      <a href="#features">Features</a>
      <a href="#how">How it works</a>
      <a href="/school/login">Teacher login</a>
      <span class="nav-btn-wrap">
        <button class="btn-3d nav-btn">
          <span class="bs"></span>
          <span class="be"></span>
          <span class="bf">Get Started</span>
        </button>
      </span>
    </div>
  </div>
</nav>

<section class="hero">
  <div class="hero-spacer" aria-hidden="true"></div>
  <div class="hero-content reveal">
    <h1>The study buddy who actually gets you</h1>
    <p class="hero-sub">Always there, always learning.</p>
    <div class="hero-btns">
      <a href="/login?mode=signup" class="btn-3d" style="text-decoration:none"><span class="bs"></span><span class="be"></span><span class="bf">Get Started</span></a>
      <a href="/login?mode=login" class="btn-3d btn-3d-w" style="text-decoration:none"><span class="bs"></span><span class="be"></span><span class="bf">I Already Have An Account</span></a>
    </div>
    <div class="hero-social">
      <div class="hero-avatars">
        <div class="hero-av"></div>
        <div class="hero-av"></div>
        <div class="hero-av"></div>
        <div class="hero-av"></div>
      </div>
      <span><strong>12,400+</strong> students learning right now</span>
    </div>
  </div>
</section>

<section class="subjects" id="how">
  <div class="subjects-row">
    <div class="subject"><div class="subject-icon green">∑</div>Math</div>
    <div class="subject"><div class="subject-icon blue">⚛</div>Physics</div>
    <div class="subject"><div class="subject-icon purple"><svg width="800px" height="800px" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="24" fill="white"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M8.95137 3C7.53466 3 7.00572 4.75542 8 5.57453V10.1716C8 10.4368 7.89464 10.6911 7.70711 10.8787L2.87868 15.7071C2.31607 16.2697 2 17.0328 2 17.8284V18C2 19.6569 3.34315 21 5 21H19C20.6569 21 22 19.6569 22 18V17.8284C22 17.0328 21.6839 16.2697 21.1213 15.7071L16.2929 10.8787C16.1054 10.6911 16 10.4368 16 10.1716V5.57453C16.9943 4.75542 16.4653 3 15.0486 3H8.95137ZM16.5858 14H7.41421L9.12132 12.2929C9.68393 11.7303 10 10.9672 10 10.1716V5.2847C10 5.18797 9.99045 5.0927 9.97203 5H14.028C14.0096 5.0927 14 5.18797 14 5.2847V10.1716C14 10.9672 14.3161 11.7303 14.8787 12.2929L16.5858 14Z" fill="#323232"/>
</svg></div>Chemistry</div>
    <div class="subject"><div class="subject-icon pink">Aa</div>English</div>
    <div class="subject"><div class="subject-icon orange">&lt;/&gt;</div>Computer Science</div>
  </div>
</section>

<div id="features" class="features">
  <div class="feat reveal">
    <div>
      <h2>learns how you learn</h2>
      <p>No two students think the same way. Pixie adapts to yours — and gets better at helping you over time.</p>
    </div>
    <div class="feat-vis"><div class="geo-card gc-green"><div class="circles"><div class="c1"></div><div class="c2"></div><div class="c3"></div></div></div></div>
  </div>
  <div class="feat rev reveal">
    <div>
      <h2>reaches out before you ask</h2>
      <p>Most tools wait for you to open them. Pixie notices when you're stuck and comes to you.</p>
    </div>
    <div class="feat-vis"><div class="geo-card gc-blue"><div class="blocks"><div class="block"></div><div class="block"></div><div class="block"></div><div class="block"></div><div class="block"></div><div class="block"></div><div class="block"></div><div class="block"></div><div class="block"></div><div class="block"></div><div class="block"></div><div class="block"></div></div></div></div>
  </div>
  <div class="feat reveal">
    <div>
      <h2>knows your material</h2>
      <p>Pixie learns from your actual textbooks and notes. Not generic answers — help that's specific to what you're studying.</p>
    </div>
    <div class="feat-vis"><div class="geo-card gc-pink"><div class="lines"><div class="line l1"></div><div class="dot d1"></div><div class="line l2"></div><div class="dot d2"></div><div class="line l3"></div><div class="dot d3"></div></div></div></div>
  </div>
  <div class="feat rev reveal">
    <div>
      <h2>Stay motivated all semester long</h2>
      <p>Streaks, milestones, and Pixie's encouragement keep you on track. She nudges you when you haven't checked in — never guilt-trip, always cheer.</p>
    </div>
    <div class="feat-vis"><div class="geo-card gc-purple"><div class="streak"><div class="num">14</div><div class="label">day streak</div><div class="dots"><div class="dot on"></div><div class="dot on"></div><div class="dot on"></div><div class="dot on"></div><div class="dot on"></div><div class="dot"></div><div class="dot"></div></div><div class="trophy"></div></div></div></div>
  </div>
</div>

<section class="cta reveal" id="cta">
  <h2>Ready to meet your pixie?</h2>
  <p>Always there, always learning.</p>
  <a href="/login?mode=signup" class="btn-3d" style="max-width:400px;margin:0 auto;text-decoration:none;display:inline-block"><span class="bs"></span><span class="be"></span><span class="bf" style="padding:14px 32px;font-size:1rem">Get Started — It's Free</span></a>
</section>

<footer class="footer">
  <div class="footer-inner">
    <div class="footer-top">
      <div class="footer-brand">
        ${pixieLogoSVG}
        <p>Your AI study partner who makes learning feel less like a chore and more like an Adventure.</p>
      </div>
      <div class="footer-col">
        <h4>Product</h4>
        <a href="#">Subjects</a>
        <a href="#">Pricing</a>
        <a href="#">Mobile App</a>
        <a href="#">For Schools</a>
      </div>
      <div class="footer-col">
        <h4>Company</h4>
        <a href="#">About</a>
        <a href="#">Blog</a>
        <a href="#">Careers</a>
        <a href="#">Press</a>
      </div>
      <div class="footer-col">
        <h4>Support</h4>
        <a href="#">Help Center</a>
        <a href="#">Contact</a>
        <a href="#">Privacy</a>
        <a href="#">Terms</a>
      </div>
    </div>
    <div class="footer-bottom">
      <span class="footer-copy">&copy; 2026 Pixie Learning · by masnoi</span>
      <div class="footer-socials">
        <div class="footer-soc">ig</div>
        <div class="footer-soc">tw</div>
        <div class="footer-soc">yt</div>
      </div>
    </div>
  </div>
</footer>
`;

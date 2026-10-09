"use client";

import { useEffect, useState } from "react";
import { avatarUrlForUserId } from "@/lib/avatar";

const CACHE_PREFIX = "pixie:sprouts-avatar:v2:";
const MAX_SVG_BYTES = 64 * 1024;
const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
type CachedAvatar = { dataUrl: string; backgroundColor: string | null };
const inFlight = new Map<string, Promise<CachedAvatar | null>>();

function isSafeHexColor(value: string | null): value is string {
  return Boolean(value && /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(value));
}

function backgroundColorFromSvg(svg: string): string | null {
  try {
    const document = new DOMParser().parseFromString(svg, "image/svg+xml");
    const root = document.documentElement;
    if (document.querySelector("parsererror") || root.namespaceURI !== SVG_NAMESPACE || root.localName !== "svg") return null;

    const viewBox = root.getAttribute("viewBox")?.trim().split(/[\s,]+/).map(Number);
    if (!viewBox || viewBox.length !== 4 || viewBox.some((part) => !Number.isFinite(part)) || viewBox[2] <= 0 || viewBox[3] <= 0) return null;

    const clippedGroup = Array.from(root.children).find((element) => element.localName === "g" && /^url\(#[^)]+\)$/.test(element.getAttribute("clip-path") ?? ""));
    if (!clippedGroup) return null;

    const backgroundRect = Array.from(clippedGroup.children).find((element) => {
      if (element.localName !== "rect") return false;
      const x = Number(element.getAttribute("x") ?? 0);
      const y = Number(element.getAttribute("y") ?? 0);
      const width = Number(element.getAttribute("width"));
      const height = Number(element.getAttribute("height"));
      return x === viewBox[0] && y === viewBox[1] && width === viewBox[2] && height === viewBox[3] && isSafeHexColor(element.getAttribute("fill"));
    });

    const fill = backgroundRect?.getAttribute("fill") ?? null;
    return isSafeHexColor(fill) ? fill : null;
  } catch {
    return null;
  }
}

function toDataUrl(svg: string): string {
  const bytes = new TextEncoder().encode(svg);
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return `data:image/svg+xml;base64,${btoa(binary)}`;
}

async function fetchAndCacheAvatar(userId: string, url: string): Promise<CachedAvatar | null> {
  const key = `${CACHE_PREFIX}${userId}`;
  try {
    const cached = localStorage.getItem(key);
    if (cached && cached.length <= MAX_SVG_BYTES * 2) {
      const parsed: unknown = JSON.parse(cached);
      if (parsed && typeof parsed === "object" && "dataUrl" in parsed && typeof parsed.dataUrl === "string" && parsed.dataUrl.startsWith("data:image/svg+xml;base64,") && parsed.dataUrl.length <= MAX_SVG_BYTES * 2) {
        const backgroundColor = "backgroundColor" in parsed && typeof parsed.backgroundColor === "string" && isSafeHexColor(parsed.backgroundColor) ? parsed.backgroundColor : null;
        return { dataUrl: parsed.dataUrl, backgroundColor };
      }
    }
  } catch {
    // Browser storage may be disabled or full; load the stable remote URL instead.
  }

  const pending = inFlight.get(key);
  if (pending) return pending;

  const request = (async () => {
    try {
      const response = await fetch(url, { mode: "cors", credentials: "omit" });
      if (!response.ok || !response.headers.get("content-type")?.toLowerCase().includes("image/svg+xml")) return null;
      const svg = await response.text();
      if (new Blob([svg]).size > MAX_SVG_BYTES || !/<svg(?:\s|>)/i.test(svg)) return null;

      const avatar = { dataUrl: toDataUrl(svg), backgroundColor: backgroundColorFromSvg(svg) };
      try {
        localStorage.setItem(key, JSON.stringify(avatar));
      } catch {
        // The avatar still displays for this visit if persistent storage is unavailable.
      }
      return avatar;
    } catch {
      return null;
    } finally {
      inFlight.delete(key);
    }
  })();
  inFlight.set(key, request);
  return request;
}

export default function UserAvatar({
  userId,
  alt = "",
  fallbackSrc,
  width,
  height,
  onBackgroundColor,
}: {
  userId: string | null | undefined;
  alt?: string;
  fallbackSrc?: string;
  width?: number;
  height?: number;
  onBackgroundColor?: (color: string | null) => void;
}) {
  const remoteUrl = avatarUrlForUserId(userId);
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setSrc(null);
    onBackgroundColor?.(null);
    if (!userId?.trim()) setSrc(remoteUrl);
    else void fetchAndCacheAvatar(userId.trim(), remoteUrl).then((avatar) => {
      if (active) {
        onBackgroundColor?.(avatar?.backgroundColor ?? null);
        setSrc(avatar?.dataUrl ?? remoteUrl);
      }
    });
    return () => { active = false; };
  }, [onBackgroundColor, remoteUrl, userId]);

  if (!src) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      onError={() => {
        if (src.startsWith("data:")) {
          try { if (userId?.trim()) localStorage.removeItem(`${CACHE_PREFIX}${userId.trim()}`); } catch { /* storage is optional */ }
          onBackgroundColor?.(null);
          setSrc(remoteUrl);
        } else {
          onBackgroundColor?.(null);
          setSrc(fallbackSrc ?? null);
        }
      }}
    />
  );
}

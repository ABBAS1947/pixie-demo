import { ReactNode } from "react";
import { useRouter } from "next/navigation";

interface NavItem {
  icon: ReactNode;
  alt: string;
  isActive?: boolean;
  href?: string;
}

interface BottomNavProps {
  items: NavItem[];
  className?: string;
}

const GAPS = [43, 28, 29, 43];

/**
 * Bottom navigation — 5 icons, center one active (pill shape).
 * Accepts React components for icons instead of file paths.
 * Each item can have an href to navigate to on click.
 */
export default function BottomNav({ items, className = "" }: BottomNavProps) {
  const router = useRouter();

  return (
    <div id="bottom-nav" className={`flex items-center justify-center w-full ${className}`}>
      {items.map((item, i) => {
        const isActive = item.isActive;
        const size = isActive
          ? { width: 112, height: 47 }
          : { width: 48, height: 48 };
        const radius = isActive ? "rounded-[23px]" : "rounded-full";
        const bg = isActive ? "var(--color-dark)" : "var(--color-orange)";

        return (
          <button
            key={i}
            className={`flex items-center justify-center shadow-elevated ${radius}`}
            style={{
              ...size,
              backgroundColor: bg,
              flexShrink: 0,
              marginRight: i < items.length - 1 ? GAPS[i] ?? 0 : 0,
            }}
            onClick={() => {
              if (item.href) {
                router.push(item.href);
              }
            }}
            aria-label={item.alt}
          >
            {item.icon}
          </button>
        );
      })}
    </div>
  );
}

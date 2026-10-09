interface CatchUpCardProps {
  detail: string;
  className?: string;
  onClick?: () => void;
}

/**
 * Catch Up card — dark background, orange heading, white detail.
 * 3D button test variant (subtle): layered shadow + edge + face.
 * Height: 152px (fixed from Figma), card radius 28px.
 */
export default function CatchUpCard({ detail, className = "", onClick }: CatchUpCardProps) {
  return (
    <button className={`btn-3d-card ${className}`} onClick={onClick} aria-label={`Catch up ${detail}`}>
      <span className="bs" aria-hidden="true" />
      <span className="be" aria-hidden="true" />
      <span className="bf">
        <span className="font-card-heading text-orange mb-1" style={{ fontWeight: 900, fontSize: 14 }}>Catch Up</span>
        <span className="font-body text-white">{detail}</span>
      </span>
    </button>
  );
}

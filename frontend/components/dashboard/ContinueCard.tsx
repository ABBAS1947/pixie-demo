interface ContinueCardProps {
  topic: string;
  className?: string;
  onClick?: () => void;
}

/**
 * Continue card — dark background, orange heading, white topic.
 * 3D button test variant (subtle): layered shadow + edge + face.
 * Height: 152px (fixed from Figma), card radius 28px.
 */
export default function ContinueCard({ topic, className = "", onClick }: ContinueCardProps) {
  return (
    <button className={`btn-3d-card ${className}`} onClick={onClick} aria-label={`Continue ${topic}`}>
      <span className="bs" aria-hidden="true" />
      <span className="be" aria-hidden="true" />
      <span className="bf">
        <span className="font-card-heading text-orange mb-1" style={{ fontWeight: 900, fontSize: 14 }}>Continue</span>
        <span className="font-body text-white">{topic}</span>
      </span>
    </button>
  );
}

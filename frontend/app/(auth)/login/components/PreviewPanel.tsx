import Image from "next/image";

export default function PreviewPanel() {
  return (
    <div style={{ display: "grid", width: "100%", placeItems: "center", padding: "32px" }}>
      <Image
        src="/icons/fox-logo.svg"
        width={651}
        height={666}
        alt="Pixie mascot"
        priority
        style={{ display: "block", width: "min(100%, 520px, 58vh)", height: "auto", maxHeight: "75dvh", objectFit: "contain" }}
      />
    </div>
  );
}

interface NoviceRankIconProps {
  color?: string;
  size?: number;
}

export default function NoviceRankIcon({ color = "currentColor", size = 24 }: NoviceRankIconProps) {
  return (
    <svg width={size} height={size} viewBox="220 113 360 367" fill="none">
      <path
        d="M250 120
       C240 120 232 128 232 140
       L232 265
       C232 276 238 286 247 292
       L400 384
       L553 292
       C562 286 568 276 568 265
       L568 140
       C568 128 560 120 550 120
       C546 120 542 121 538 124
       L400 207
       L262 124
       C258 121 254 120 250 120Z"
        fill={color}
      />
      <path
        d="M250 340
       C243 340 237 344 233 350
       C227 359 230 371 239 377
       L400 473
       L561 377
       C570 371 573 359 567 350
       C561 341 550 338 541 344
       L400 428
       L259 344
       C256 342 253 340 250 340Z"
        fill={color}
      />
    </svg>
  );
}

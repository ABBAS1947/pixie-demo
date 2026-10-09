import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ChatBubbleProps {
  role: string;
  content: string;
}

export default function ChatBubble({ role, content }: ChatBubbleProps) {
  if (role === "user") {
    return (
      <div className="flex w-full justify-end">
        <div className="inline-flex max-w-[min(82%,680px)] rounded-[13px] bg-[var(--color-dark)] px-4 py-2.5 sm:max-w-[76%]">
          <p className="break-words whitespace-pre-wrap font-body text-[var(--color-white)]" style={{ fontSize: 16, fontWeight: 550, lineHeight: 1.5, letterSpacing: "-0.005em" }}>
            {content}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="chat-markdown min-w-0 max-w-full font-body text-[var(--color-dark)]" style={{ fontSize: 16, fontWeight: 450, lineHeight: 1.62, letterSpacing: "-0.012em" }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
      <img src="/icons/PixieLogo(Silhouette)-06.svg" alt="" width={23} height={23} className="ml-0.5 opacity-75" />
    </div>
  );
}

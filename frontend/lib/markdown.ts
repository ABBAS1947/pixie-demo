// ProseMirror JSON -> markdown serializer for the pixie editor.
// Mirrors the backend's markdown storage. Supports the MVP block set:
// paragraphs, H1-H3, bullet/ordered lists, blockquote, code block, divider,
// and inline bold/italic/strike/code/link/underline/highlight.

interface MDNode {
  type: string;
  text?: string;
  content?: MDNode[];
  marks?: { type: string; attrs?: Record<string, unknown> }[];
  attrs?: Record<string, unknown>;
}

function serializeText(node: MDNode): string {
  if (node.type === "hardBreak") return "\n";
  let t = node.text ?? "";
  for (const m of node.marks ?? []) {
    const href = (m.attrs?.href as string) ?? "";
    switch (m.type) {
      case "code":
        t = `\`${t}\``;
        break;
      case "bold":
        t = `**${t}**`;
        break;
      case "italic":
        t = `*${t}*`;
        break;
      case "strike":
        t = `~~${t}~~`;
        break;
      case "underline":
        t = `<u>${t}</u>`;
        break;
      case "highlight":
        t = `==${t}==`;
        break;
      case "link":
        t = `[${t}](${href})`;
        break;
    }
  }
  return t;
}

function inlineText(node: MDNode): string {
  return (node.content ?? [])
    .map((c) => (c.type === "text" ? serializeText(c) : ""))
    .join("");
}

function blockToMarkdown(node: MDNode): string {
  switch (node.type) {
    case "paragraph":
      return inlineText(node);
    case "heading": {
      const level = (node.attrs?.level as number) ?? 1;
      return `${"#".repeat(level)} ${inlineText(node)}`;
    }
    case "blockquote":
      return (node.content ?? []).map((c) => `> ${blockToMarkdown(c)}`).join("\n");
    case "bulletList":
      return (node.content ?? []).map((li) => `- ${listItemText(li)}`).join("\n");
    case "orderedList":
      return (node.content ?? []).map((li, i) => `${i + 1}. ${listItemText(li)}`).join("\n");
    case "codeBlock": {
      const lang = (node.attrs?.language as string) ?? "";
      const code = (node.content ?? []).map((c) => c.text ?? "").join("");
      return `\`\`\`${lang}\n${code}\n\`\`\``;
    }
    case "horizontalRule":
      return "---";
    default:
      return inlineText(node);
  }
}

function listItemText(li: MDNode): string {
  return (li.content ?? [])
    .map((c) => blockToMarkdown(c))
    .join("\n")
    .split("\n")
    .join("\n  ");
}

export function serializeMarkdown(doc: MDNode): string {
  return (doc.content ?? []).map(blockToMarkdown).join("\n\n").trim() + "\n";
}

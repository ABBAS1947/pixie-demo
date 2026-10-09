"use client";

import { useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import CharacterCount from "@tiptap/extension-character-count";
import Highlight from "@tiptap/extension-highlight";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import Underline from "@tiptap/extension-underline";
import StarterKit from "@tiptap/starter-kit";
import { ArrowLeft, MoreHorizontal, Trash2 } from "lucide-react";
import { marked } from "marked";
import { serializeMarkdown } from "@/lib/markdown";
import type { Note } from "@/lib/types";

export type SaveStatus = "idle" | "saving" | "saved";

interface Props {
  note: Note;
  saveStatus: SaveStatus;
  onBack: () => void;
  onChange: (patch: Partial<{ title: string; content: string; tags: string }>) => void;
  onDelete: () => void;
}

function EditorIcon({ name }: { name: string }) {
  return <img src={`/icons/${name}.svg`} alt="" aria-hidden />;
}

function TagRow({ tags, onTagsChange }: { tags: string[]; onTagsChange: (tags: string[]) => void }) {
  const [value, setValue] = useState("");
  const addTag = () => {
    const tag = value.trim().replace(/^#/, "");
    if (tag && !tags.includes(tag)) onTagsChange([...tags, tag]);
    setValue("");
  };
  return <div className="notes-editor-tags">
    {tags.map((tag) => <button type="button" key={tag} onClick={() => onTagsChange(tags.filter((item) => item !== tag))}>{tag} <span>×</span></button>)}
    <input value={value} onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addTag(); } }} onBlur={addTag} placeholder="+ Add tag" />
  </div>;
}

export default function NoteEditorPane({ note, saveStatus, onBack, onChange, onDelete }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [editorMode, setEditorMode] = useState<"normal" | "math">("normal");
  const editor = useEditor({
    extensions: [StarterKit, Underline, Highlight.configure({ multicolor: false }), Link.configure({ openOnClick: false }), Placeholder.configure({ placeholder: "Start writing…" }), CharacterCount],
    content: (marked.parse(note.content ?? "") as string) || "<p></p>",
    onUpdate: ({ editor: next }) => onChange({ content: serializeMarkdown(next.getJSON()) }),
    editorProps: { attributes: { class: "notes-editor-body" } },
  });
  const wordCount = (note.content ?? "").trim() ? (note.content ?? "").trim().split(/\s+/).length : 0;
  if (!editor) return null;
  const formatTools = [
    { name: "bold", label: "Bold", active: editor.isActive("bold"), onClick: () => editor.chain().focus().toggleBold().run() },
    { name: "italic", label: "Italic", active: editor.isActive("italic"), onClick: () => editor.chain().focus().toggleItalic().run() },
    { name: "underline", label: "Underline", active: editor.isActive("underline"), onClick: () => editor.chain().focus().toggleUnderline().run() },
    { name: "list", label: "Bullet list", active: editor.isActive("bulletList"), onClick: () => editor.chain().focus().toggleBulletList().run() },
    { name: "highlighter", label: "Highlight", active: editor.isActive("highlight"), onClick: () => editor.chain().focus().toggleHighlight().run() },
  ];
  return <section className="notes-editor-workspace">
    <header className="notes-editor-header">
      <button type="button" className="notes-back-button" onClick={onBack}><ArrowLeft size={20} /><span>Notes</span></button>
      <div className="notes-editor-meta"><span className={`notes-save-state ${saveStatus}`}>{saveStatus === "saving" ? "Saving…" : saveStatus === "saved" ? "Saved" : ""}</span><div className="relative"><button type="button" className="notes-more-button" aria-label="Note actions" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}><MoreHorizontal size={21} /></button>{menuOpen && <div className="notes-editor-menu"><button type="button" onClick={onDelete}><Trash2 size={16} /> Delete note</button></div>}</div></div>
    </header>
    <div className="notes-editor-tools-row"><div className="notes-editor-toolbar" aria-label="Formatting tools">
      {formatTools.map((tool) => <button key={tool.name} type="button" title={tool.label} aria-label={tool.label} aria-pressed={tool.active} className={tool.active ? "is-active" : ""} onClick={tool.onClick}><EditorIcon name={tool.name} /></button>)}
      <span className="notes-toolbar-divider" aria-hidden="true" />
      <button type="button" title="Normal writing" aria-label="Normal writing" aria-pressed={editorMode === "normal"} className={editorMode === "normal" ? "is-active" : ""} onClick={() => setEditorMode("normal")}><EditorIcon name="edit" /></button>
      <button type="button" title="Math tools" aria-label="Math tools" aria-pressed={editorMode === "math"} className={editorMode === "math" ? "is-active" : ""} onClick={() => setEditorMode("math")}><EditorIcon name="calculator" /></button>
    </div></div>
    <article className="notes-editor-paper">
      <div className="notes-editor-title-row"><input value={note.title} onChange={(event) => onChange({ title: event.target.value })} placeholder="Untitled note" autoFocus /></div>
      <TagRow tags={note.tags} onTagsChange={(tags) => onChange({ tags: tags.join(",") })} />
      <div className="notes-editor-scroll"><EditorContent editor={editor} /></div>
      <footer><span>{wordCount} {wordCount === 1 ? "word" : "words"}</span></footer>
    </article>
  </section>;
}

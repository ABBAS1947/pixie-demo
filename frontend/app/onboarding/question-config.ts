// One short question per screen. Answers retain the existing backend contract.

export type QuestionType = "text" | "choice" | "chips" | "tone";

export interface QuestionConfig {
  id: string;
  type: QuestionType;
  question: string;
  /** Example answer, not an instruction. */
  placeholder?: string;
  /** Closed-set options for choice/chips. "Other" is special-cased. */
  options?: string[];
  /** Which Answers key this writes to. */
  answerKey: string;
  /** Human label for the summary screen — never a camelCase field name. */
  label: string;
}

export const QUESTIONS: QuestionConfig[] = [
  {
    id: "name",
    type: "text",
    question: "What should I call you?",
    placeholder: "Your name",
    answerKey: "name",
    label: "Name",
  },
  {
    id: "grade",
    type: "choice",
    question: "What grade are you in?",
    options: ["Middle School (6th-8th)", "High School (9th-12th)", "College / University", "Other"],
    answerKey: "grade",
    label: "Grade",
  },
  {
    id: "subjects",
    type: "chips",
    question: "What are you studying?",
    options: ["Math", "Physics", "Chemistry", "Biology", "English", "Computer Science", "History", "Other"],
    answerKey: "subjects",
    label: "Subjects",
  },
  {
    id: "goals",
    type: "chips",
    question: "What's your goal?",
    options: ["Exam prep", "Catching up", "Staying ahead", "Building fundamentals", "Just exploring"],
    answerKey: "goals",
    label: "Goals",
  },
  {
    id: "learningStyle",
    type: "choice",
    question: "How do you learn best?",
    options: ["Visual", "Reading & writing", "Hands-on", "Talk it through"],
    answerKey: "learningStyle",
    label: "Learning style",
  },
  {
    id: "tone",
    type: "tone",
    question: "How should Pixie sound?",
    answerKey: "tone",
    label: "Tone",
  },
];

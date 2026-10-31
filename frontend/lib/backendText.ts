import { useLocale, useMessages } from "next-intl";
import ENGLISH from "@/messages/en.json";

// The backend writes its sentences in English, because Muse Spark and the exports read them too.
// messages/*.json holds a template for each sentence, and this fills in the translated template.
// backend/tests/test_backend_text.py fails when the backend writes a sentence with no template.

type Section = { templates: Record<string, string>; words: Record<string, string>; inline: Record<string, string> };
type Template = { pattern: RegExp; names: string[]; target: string };

const ESCAPE = /[.*+?^${}()|[\]\\]/g;
// A new sentence starts after a period, at a capital: "3.0 eV. DFT gaps", but not "et al. 2018".
const SENTENCE = /(?<=[.)])\s+(?=[A-Z])/;

function compile(en: Section, target: Section): Template[] {
  return Object.entries(en.templates)
    .map(([key, text]) => {
      const names: string[] = [];
      const parts = text.split(/\{(\w+)\}/);
      const source = parts
        .map((part, i) => {
          if (i % 2 === 0) return part.replace(ESCAPE, "\\$&");
          names.push(part);
          return "(.+?)";
        })
        .join("");
      return { pattern: new RegExp(`^${source}$`), names, target: target.templates[key] ?? text, literal: text.length - names.join("").length };
    })
    .sort((a, b) => b.literal - a.literal);
}

export function makeBackendText(en: Section, target: Section): (text: string) => string {
  const templates = compile(en, target);
  const words = new Map(Object.entries(en.words).map(([key, word]) => [word, target.words[key] ?? word]));
  const inline = Object.entries(en.inline).map(([key, word]) => [new RegExp(`\\b${word}\\b`, "g"), target.inline[key] ?? word] as const);

  const value = (text: string) => {
    const word = words.get(text);
    if (word) return word;
    return inline.reduce((out, [pattern, replacement]) => out.replace(pattern, replacement), text);
  };

  const sentence = (text: string): string | null => {
    const word = words.get(text);
    if (word) return word;
    for (const template of templates) {
      const match = template.pattern.exec(text);
      if (match) {
        return template.names.reduce((out, name, i) => out.replace(`{${name}}`, () => value(match[i + 1])), template.target);
      }
    }
    return null;
  };

  // Split first: a placeholder would otherwise swallow the sentences after it. No template crosses
  // a sentence boundary. A sentence with no template stays in English rather than disappearing.
  return (text) =>
    text
      .split(SENTENCE)
      .map((part) => sentence(part) ?? part)
      .join(" ");
}

const cache = new Map<string, (text: string) => string>();

/** Translates a sentence from the backend into the UI language. */
export function useBackendText(): (text: string) => string {
  const locale = useLocale();
  const messages = useMessages() as unknown as { Backend?: Section };
  return (text) => {
    if (locale === "en" || !messages.Backend) return text;
    let translate = cache.get(locale);
    if (!translate) {
      translate = makeBackendText(ENGLISH.Backend, messages.Backend);
      cache.set(locale, translate);
    }
    return translate(text);
  };
}

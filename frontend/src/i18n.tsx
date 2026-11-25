import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import translations from "./translations.json";
export type Language = "fr" | "en" | "es" | "ar";
const languages: Language[] = ["fr", "en", "es", "ar"];
const messages: Record<string, Record<string, string>> = translations;
const Context = createContext({
  language: "fr" as Language,
  setLanguage: (_: Language) => {},
  t: (s: string) => s,
});
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() => {
    try {
      const stored = localStorage.getItem("sillage-language");
      return languages.includes(stored as Language)
        ? (stored as Language)
        : "fr";
    } catch {
      return "fr";
    }
  });
  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
    document.title =
      language === "fr"
        ? "Sillage — Recherche documentaire"
        : `Sillage — ${messages["Recherche documentaire"][language]}`;
    try {
      localStorage.setItem("sillage-language", language);
    } catch {
      /* Storage can be disabled. */
    }
  }, [language]);
  const t = (text: string): string => {
    if (language === "fr") return text;
    const progress = /^Découpage Qwen : (\d+\/\d+) caractères$/.exec(text);
    if (progress)
      return `${messages["Découpage Qwen"][language]}: ${progress[1]} ${messages["caractères"][language]}`;
    return messages[text]?.[language] ?? text;
  };
  return (
    <Context.Provider value={{ language, setLanguage, t }}>
      {children}
    </Context.Provider>
  );
}
export const useLanguage = () => useContext(Context);
export function LanguageSelector() {
  const { language, setLanguage } = useLanguage();
  return (
    <label className="language-selector">
      <span aria-hidden="true">🌐</span>
      <select
        aria-label="Langue / Language / Idioma / اللغة"
        value={language}
        onChange={(e) => setLanguage(e.target.value as Language)}
      >
        <option value="fr">Français</option>
        <option value="en">English</option>
        <option value="es">Español</option>
        <option value="ar">العربية</option>
      </select>
    </label>
  );
}

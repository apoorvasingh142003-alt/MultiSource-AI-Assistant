/**
 * Minimal i18n for English + Hebrew (RTL).
 * All new UI strings live here. Use t("key") for English or t("key", "he") for Hebrew.
 */

type Lang = "en" | "he";

const strings: Record<string, Record<Lang, string>> = {
  // General
  "app.title": { en: "Nexus AI", he: "Nexus AI" },
  "app.subtitle": { en: "Adaptive Multi-Domain Intelligence Agent", he: "סוכן בינה מותאם רב-תחומי" },

  // Tabs
  "tab.chat": { en: "Chat", he: "צ'אט" },
  "tab.workspace": { en: "Workspace", he: "סביבת עבודה" },
  "tab.demo": { en: "Demo", he: "דמו" },

  // Chat Sidebar
  "sidebar.new_chat": { en: "New Chat", he: "צ'אט חדש" },
  "sidebar.search": { en: "Search chats…", he: "חיפוש שיחות…" },
  "sidebar.today": { en: "Today", he: "היום" },
  "sidebar.yesterday": { en: "Yesterday", he: "אתמול" },
  "sidebar.last_7_days": { en: "Last 7 Days", he: "7 הימים האחרונים" },
  "sidebar.older": { en: "Older", he: "ישן יותר" },
  "sidebar.delete_confirm": { en: "Delete this chat?", he: "למחוק שיחה זו?" },

  // AI Settings Panel
  "settings.title": { en: "AI Settings", he: "הגדרות AI" },
  "settings.agent_role": { en: "Agent Role", he: "תפקיד סוכן" },
  "settings.custom_prompt": { en: "Custom System Prompt", he: "הנחיית מערכת מותאמת" },
  "settings.output_format": { en: "Output Format", he: "פורמט פלט" },
  "settings.chars_remaining": { en: "chars remaining", he: "תווים נותרו" },

  // Answer Panel
  "answer.title": { en: "Answer", he: "תשובה" },
  "answer.routed_to": { en: "Routed to", he: "מנותב אל" },
  "answer.confidence": { en: "confidence", he: "ביטחון" },
  "answer.supporting": { en: "Supporting evidence", he: "ראיות תומכות" },
  "answer.sources": { en: "Sources", he: "מקורות" },
  "answer.insufficient": { en: "Insufficient evidence — not answered", he: "ראיות לא מספקות — לא נענה" },
  "answer.general_knowledge": { en: "Answered from model knowledge — no indexed source contributed.", he: "נענה מידע כללי של המודל — אין מקור מאונדקס." },
  "answer.trace": { en: "View retrieval trace", he: "הצג מעקב אחזור" },
  "answer.explain": { en: "Explain This Answer", he: "הסבר תשובה זו" },
  "answer.read_aloud": { en: "Read Aloud", he: "הקרא בקול" },
  "answer.copy": { en: "Copy", he: "העתק" },
  "answer.export": { en: "Export", he: "ייצוא" },
  "answer.save_to_workspace": { en: "Save to Workspace", he: "שמור לסביבת עבודה" },

  // Verification
  "verify.verified": { en: "Citations verified", he: "ציטוטים אומתו" },
  "verify.unverified": { en: "Citations unverified", he: "ציטוטים לא אומתו" },
  "verify.contradictions": { en: "Contradictions detected", he: "סתירות זוהו" },

  // Read Aloud
  "tts.play": { en: "Play", he: "נגן" },
  "tts.pause": { en: "Pause", he: "השהה" },
  "tts.resume": { en: "Resume", he: "המשך" },
  "tts.stop": { en: "Stop", he: "עצור" },
  "tts.speed": { en: "Speed", he: "מהירות" },
  "tts.voice": { en: "Voice", he: "קול" },

  // Table
  "table.export_csv": { en: "Export CSV", he: "ייצוא CSV" },
  "table.copy_table": { en: "Copy Table", he: "העתק טבלה" },
  "table.sort_asc": { en: "Sort ascending", he: "מיין עולה" },
  "table.sort_desc": { en: "Sort descending", he: "מיין יורד" },

  // Explainability
  "explain.title": { en: "How This Answer Was Produced", he: "כיצד הופקה תשובה זו" },
  "explain.routing": { en: "Routing", he: "ניתוב" },
  "explain.retrieval": { en: "Retrieval", he: "אחזור" },
  "explain.generation": { en: "Generation", he: "הפקה" },
  "explain.verification": { en: "Verification", he: "אימות" },
  "explain.source_contribution": { en: "Source Contribution", he: "תרומת מקורות" },
  "explain.trust_details": { en: "Trust Details", he: "פרטי אמינות" },

  // Workspace
  "workspace.title": { en: "Workspaces", he: "סביבות עבודה" },
  "workspace.new": { en: "New Workspace", he: "סביבת עבודה חדשה" },
  "workspace.artifacts": { en: "Artifacts", he: "ממצאים" },
  "workspace.generate": { en: "Generate New Artifact", he: "הפק ממצא חדש" },
  "workspace.memory": { en: "Memory", he: "זיכרון" },
  "workspace.workflows": { en: "Workflows", he: "תהליכי עבודה" },

  // Common actions
  "action.ask": { en: "Ask", he: "שאל" },
  "action.clear": { en: "Clear", he: "נקה" },
  "action.cancel": { en: "Cancel", he: "בטל" },
  "action.save": { en: "Save", he: "שמור" },
  "action.delete": { en: "Delete", he: "מחק" },
  "action.rename": { en: "Rename", he: "שנה שם" },
  "action.close": { en: "Close", he: "סגור" },
  "action.working": { en: "Working…", he: "עובד…" },
};

/**
 * Translate a key to a localized string.
 * Falls back to English if the key or language is missing.
 */
export function t(key: string, lang: Lang = "en"): string {
  const entry = strings[key];
  if (!entry) return key;
  return entry[lang] || entry.en || key;
}

/**
 * Detect the preferred language from the browser or return "en".
 */
export function detectLang(): Lang {
  if (typeof window === "undefined") return "en";
  const nav = navigator.language || "";
  return nav.startsWith("he") ? "he" : "en";
}

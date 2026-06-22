"use client";
import React from "react";
import { Button, Icons, cn } from "./ui";

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

function stripCitations(text: string): string {
  // Remove [eN] citation markers and markdown syntax before speaking.
  return text
    .replace(/\[e\d+\]/g, "")
    .replace(/[*_~`#>|]/g, "")
    .replace(/\n{2,}/g, ". ")
    .replace(/\n/g, " ")
    .trim();
}

// Detect Hebrew so we can offer matching voices (English otherwise).
function detectLang(text: string): "he" | "en" {
  return /[֐-׿]/.test(text) ? "he" : "en";
}

export default function ReadAloud({ text }: { text: string }) {
  const [speaking, setSpeaking] = React.useState(false);
  const [paused, setPaused] = React.useState(false);
  const [speed, setSpeed] = React.useState(1);
  const [voices, setVoices] = React.useState<SpeechSynthesisVoice[]>([]);
  const [voiceIdx, setVoiceIdx] = React.useState(0);
  const [spoken, setSpoken] = React.useState("");          // current sentence being read
  const utteranceRef = React.useRef<SpeechSynthesisUtterance | null>(null);

  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const lang = detectLang(text);

  React.useEffect(() => {
    if (!supported) return;
    const loadVoices = () => {
      const v = speechSynthesis.getVoices();
      if (v.length > 0) setVoices(v);
    };
    loadVoices();
    speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () => {
      speechSynthesis.removeEventListener("voiceschanged", loadVoices);
      speechSynthesis.cancel();
    };
  }, [supported]);

  // Voices whose language matches the answer language (fallback: all voices).
  const langVoices = React.useMemo(() => {
    const filtered = voices.filter((v) => v.lang?.toLowerCase().startsWith(lang));
    return filtered.length > 0 ? filtered : voices;
  }, [voices, lang]);

  const cleaned = React.useMemo(() => stripCitations(text), [text]);

  const play = () => {
    if (!supported) return;
    speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(cleaned);
    utt.rate = speed;
    if (langVoices[voiceIdx]) utt.voice = langVoices[voiceIdx];
    // Highlight the sentence currently being spoken via boundary events.
    utt.onboundary = (ev) => {
      const idx = ev.charIndex ?? 0;
      const start = Math.max(
        cleaned.lastIndexOf(".", idx - 1),
        cleaned.lastIndexOf("!", idx - 1),
        cleaned.lastIndexOf("?", idx - 1),
      ) + 1;
      let end = cleaned.length;
      for (const p of [".", "!", "?"]) {
        const e = cleaned.indexOf(p, idx);
        if (e !== -1 && e < end) end = e + 1;
      }
      setSpoken(cleaned.slice(start, end).trim());
    };
    utt.onend = () => { setSpeaking(false); setPaused(false); setSpoken(""); };
    utt.onerror = () => { setSpeaking(false); setPaused(false); setSpoken(""); };
    utteranceRef.current = utt;
    speechSynthesis.speak(utt);
    setSpeaking(true);
    setPaused(false);
  };

  const pause = () => { speechSynthesis.pause(); setPaused(true); };
  const resume = () => { speechSynthesis.resume(); setPaused(false); };
  const stop = () => { speechSynthesis.cancel(); setSpeaking(false); setPaused(false); setSpoken(""); };

  // Unsupported browser — show a disabled button with an explanatory tooltip (spec 4.1.4).
  if (!supported) {
    return (
      <Button variant="ghost" size="sm" disabled title="Text-to-speech is not supported in this browser.">
        <Icons.play className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Read Aloud</span>
      </Button>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {!speaking ? (
          <Button variant="ghost" size="sm" onClick={play} title="Read aloud">
            <Icons.play className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Read Aloud</span>
          </Button>
        ) : (
          <>
            {paused ? (
              <Button variant="ghost" size="sm" onClick={resume} title="Resume">
                <Icons.play className="h-3.5 w-3.5" />
              </Button>
            ) : (
              <Button variant="ghost" size="sm" onClick={pause} title="Pause">
                <svg viewBox="0 0 24 24" fill="currentColor" className="h-3.5 w-3.5">
                  <rect x="6" y="5" width="4" height="14" rx="1" />
                  <rect x="14" y="5" width="4" height="14" rx="1" />
                </svg>
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={stop} title="Stop">
              <Icons.x className="h-3.5 w-3.5" />
            </Button>
            <select
              value={speed}
              onChange={(e) => setSpeed(parseFloat(e.target.value))}
              className="h-7 rounded-md border border-slate-200 bg-white px-1.5 text-[11px] text-slate-600"
              title="Speed"
            >
              {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
            </select>
          </>
        )}

        {langVoices.length > 1 && (
          <select
            value={voiceIdx}
            onChange={(e) => setVoiceIdx(parseInt(e.target.value, 10))}
            className="h-7 max-w-[140px] rounded-md border border-slate-200 bg-white px-1.5 text-[11px] text-slate-600"
            title="Voice"
          >
            {langVoices.map((v, i) => <option key={v.name} value={i}>{v.name}</option>)}
          </select>
        )}
      </div>

      {speaking && spoken && (
        <p className="max-w-md rounded-md bg-indigo-50 px-2 py-1 text-[11px] italic leading-snug text-indigo-600 ring-1 ring-inset ring-indigo-100"
          dir={lang === "he" ? "rtl" : "ltr"}>
          🔊 {spoken}
        </p>
      )}
    </div>
  );
}

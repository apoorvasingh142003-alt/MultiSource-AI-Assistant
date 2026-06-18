"use client";
import React from "react";
import { Button, Icons, cn } from "./ui";

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

function stripCitations(text: string): string {
  // Remove [eN] citation markers and markdown syntax
  return text
    .replace(/\[e\d+\]/g, "")
    .replace(/[*_~`#>|]/g, "")
    .replace(/\n{2,}/g, ". ")
    .replace(/\n/g, " ")
    .trim();
}

export default function ReadAloud({ text }: { text: string }) {
  const [speaking, setSpeaking] = React.useState(false);
  const [paused, setPaused] = React.useState(false);
  const [speed, setSpeed] = React.useState(1);
  const [voices, setVoices] = React.useState<SpeechSynthesisVoice[]>([]);
  const [voiceIdx, setVoiceIdx] = React.useState(0);
  const utteranceRef = React.useRef<SpeechSynthesisUtterance | null>(null);

  // Check TTS support
  const supported =
    typeof window !== "undefined" && "speechSynthesis" in window;

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

  const play = () => {
    if (!supported) return;
    speechSynthesis.cancel();

    const cleaned = stripCitations(text);
    const utt = new SpeechSynthesisUtterance(cleaned);
    utt.rate = speed;
    if (voices[voiceIdx]) utt.voice = voices[voiceIdx];
    utt.onend = () => {
      setSpeaking(false);
      setPaused(false);
    };
    utt.onerror = () => {
      setSpeaking(false);
      setPaused(false);
    };
    utteranceRef.current = utt;
    speechSynthesis.speak(utt);
    setSpeaking(true);
    setPaused(false);
  };

  const pause = () => {
    speechSynthesis.pause();
    setPaused(true);
  };

  const resume = () => {
    speechSynthesis.resume();
    setPaused(false);
  };

  const stop = () => {
    speechSynthesis.cancel();
    setSpeaking(false);
    setPaused(false);
  };

  if (!supported) return null;

  return (
    <div className="flex items-center gap-1.5">
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
              <svg
                viewBox="0 0 24 24"
                fill="currentColor"
                className="h-3.5 w-3.5"
              >
                <rect x="6" y="5" width="4" height="14" rx="1" />
                <rect x="14" y="5" width="4" height="14" rx="1" />
              </svg>
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={stop} title="Stop">
            <Icons.x className="h-3.5 w-3.5" />
          </Button>

          {/* Speed control */}
          <select
            value={speed}
            onChange={(e) => setSpeed(parseFloat(e.target.value))}
            className="h-7 rounded-md border border-slate-200 bg-white px-1.5 text-[11px] text-slate-600"
            title="Speed"
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  );
}

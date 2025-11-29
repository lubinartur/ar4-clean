import { useEffect, useState } from "react";

export type OutputDensity = "short" | "balanced" | "deep";
export type ResponseTone = "bro" | "strict" | "neutral";
export type InterfaceLanguage = "auto" | "en" | "ru";

export interface CoreSettings {
  operatorName: string;
  interfaceLanguage: InterfaceLanguage;
  neuralPersonality: "short_sharp" | "balanced" | "verbose";
  outputDensity: OutputDensity;
  responseTone: ResponseTone;
  temperature: number;
  stickySidebar: boolean;
  activeModel: string;
  streaming: boolean;
  chunkProfile: "speed" | "balanced" | "deep";
  autoLabelSessions: boolean;
}

const STORAGE_KEY = "air4-core-settings-v1";

const DEFAULT_SETTINGS: CoreSettings = {
  operatorName: "ARCH",
  interfaceLanguage: "auto",
  neuralPersonality: "balanced",
  outputDensity: "balanced",
  responseTone: "bro",
  temperature: 0.5,
  stickySidebar: true,
  activeModel: "mistral-7b-local",
  streaming: true,
  chunkProfile: "balanced",
  autoLabelSessions: true,
};

export function useSettings() {
  const [settings, setSettings] = useState<CoreSettings>(DEFAULT_SETTINGS);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      setSettings({ ...DEFAULT_SETTINGS, ...parsed });
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      // ignore
    }
  }, [settings]);

  return { settings, setSettings };
}

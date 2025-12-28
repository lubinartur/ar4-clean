
import React, { useState, useEffect } from "react";
import { useSettings } from "../hooks/useSettings";
import { useAir4 } from "../contexts/Air4Context";
import { AVAILABLE_MODELS } from "../services/air4Service";
import { ChevronDown, Check, Sliders, Cpu, User, Database, FileText, ShieldAlert } from "lucide-react";
import type { IngestMode, SessionConfig } from "../types";

type ModelName = (typeof AVAILABLE_MODELS)[number];

interface SettingsProps {
  activeSessionId: string | null;
}

const SettingsPage: React.FC<SettingsProps> = ({ activeSessionId }) => {
  const { settings, setSettings } = useSettings();
  const air4 = useAir4();
  
  // Session Config state
  const [sessionConfig, setSessionConfig] = useState<SessionConfig>({});
  
  // Ollama models state
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState<boolean>(true);
  const [modelsError, setModelsError] = useState<string | null>(null);

  // Bridge to backend session / ingest behaviour
  const [autoTitle, setAutoTitle] = useState<boolean>(air4.getAutoTitle());
  const [ingestMode, setIngestMode] = useState<IngestMode>(air4.getIngestMode());

  // Fetch Ollama models on mount
  const fetchOllamaModels = async () => {
    setModelsLoading(true);
    setModelsError(null);
    try {
      const apiBaseUrl = (import.meta as any).env?.VITE_API_BASE_URL 
        ? (import.meta as any).env.VITE_API_BASE_URL.replace(/\/$/, '')
        : 'http://127.0.0.1:8000';
      
      const response = await fetch(`${apiBaseUrl}/models/ollama`);
      if (!response.ok) {
        throw new Error(`Failed to fetch models: ${response.status}`);
      }
      const data = await response.json();
      const models = Array.isArray(data.models) ? data.models : [];
      setOllamaModels(models);
    } catch (error) {
      console.error('[Settings] Failed to fetch Ollama models:', error);
      setModelsError(error instanceof Error ? error.message : 'Unknown error');
      setOllamaModels([]);
    } finally {
      setModelsLoading(false);
    }
  };

  useEffect(() => {
    fetchOllamaModels();
  }, []);

  // Load session config when activeSessionId changes
  useEffect(() => {
    if (activeSessionId) {
      const config = air4.getSessionConfig(activeSessionId);
      if (config) {
        setSessionConfig(config);
      } else {
        // Initialize with defaults from global settings
        setSessionConfig({
          model: air4.getActiveModel?.() || "auto",
          tone: settings.responseTone,
          density: settings.outputDensity,
          uiLang: settings.interfaceLanguage,
          streaming: settings.streaming,
        });
      }
    } else {
      setSessionConfig({});
    }
  }, [activeSessionId, air4, settings]);


  // --- Handlers wired to CoreSettings + air4 service where нужно ---

  const handleOperatorChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSettings((prev) => ({ ...prev, operatorName: val }));
  };

  const handleLanguageChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value as "auto" | "en" | "ru";
    setSettings((prev) => ({ ...prev, interfaceLanguage: val }));
  };

  const handlePersonalityChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value as "short_sharp" | "balanced" | "verbose";
    setSettings((prev) => ({ ...prev, neuralPersonality: val }));
  };

  const handleOutputDensityChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value as "short" | "balanced" | "deep";
    setSettings((prev) => ({ ...prev, outputDensity: val }));
  };

  const handleToneChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value as "bro" | "strict" | "neutral";
    setSettings((prev) => ({ ...prev, responseTone: val }));
  };

  const handleTemperatureChange = (val: number) => {
    setSettings((prev) => ({ ...prev, temperature: val }));
  };

  const handleStickySidebarToggle = () => {
    setSettings((prev) => ({ ...prev, stickySidebar: !prev.stickySidebar }));
  };

  const handleModelSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const model = e.target.value;
    console.log("[MODEL SELECT]", model);
    air4.setActiveModel(model as any);
    // setSettings только для UI синхронизации
    setSettings((prev) => ({ ...prev, activeModel: model as any }));
  };

  const handleStreamingToggle = () => {
    setSettings((prev) => ({ ...prev, streaming: !prev.streaming }));
  };

  const toggleAutoTitle = () => {
    const newVal = !autoTitle;
    setAutoTitle(newVal);
    air4.setAutoTitle(newVal);
  };

  const handleClearSessions = () => {
    if (
      confirm(
        "Are you sure you want to clear all chat history?\n\nThis action cannot be undone."
      )
    ) {
      air4.deleteAllSessions();
    }
  };

  const mapChunkProfileToIngest = (profile: "speed" | "balanced" | "deep"): IngestMode => {
    switch (profile) {
      case "speed":
        return "fast";
      case "deep":
        return "high-precision";
      default:
        return "smart";
    }
  };

  const handleChunkProfileChange = (profile: "speed" | "balanced" | "deep") => {
    setSettings((prev) => ({ ...prev, chunkProfile: profile }));
    const mode = mapChunkProfileToIngest(profile);
    setIngestMode(mode);
    air4.setIngestMode(mode);
  };

  const rerunSetup = () => {
    if (
      confirm(
        "Reset local configuration and run onboarding again?\n\nThis will clear all local settings and restart the setup process."
      )
    ) {
      // Удаляем все ключи из localStorage содержащие "air4" (case-insensitive)
      const keysToRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.toLowerCase().includes('air4')) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach(key => localStorage.removeItem(key));
      
      // Hard reload на корень
      window.location.href = '/';
      window.location.reload();
    }
  };

  const handleReset = () => {
    if (
      confirm(
        "FACTORY RESET WARNING\n\nThis will wipe all local data and return you to the setup screen. Continue?"
      )
    ) {
      air4.resetSystem();
    }
  };

  // Pretty labels
  const toneLabel = (t: "bro" | "strict" | "neutral") => {
    if (t === "bro") return "Bro mode";
    if (t === "strict") return "Strict";
    return "Neutral";
  };

  const densityLabel = (d: "short" | "balanced" | "deep") => {
    if (d === "short") return "Short";
    if (d === "balanced") return "Balanced";
    return "Deep";
  };

  const modelLabel = (m: string) => m;

  return (
    <div className="h-full flex flex-col relative text-slate-300 p-8">
      {/* Header */}
      <header className="mb-8 z-10 flex-shrink-0 animate-fade-in-up">
        <h2 className="text-2xl font-bold text-white tracking-tight mb-2 flex items-center gap-3">
          <Sliders className="w-6 h-6 text-air-500" />
          System Configuration
        </h2>
        <p className="text-sm text-slate-400 max-w-2xl leading-relaxed">
          Configure local core identity, neural engine parameters, memory retention policies, and ingestion protocols.
        </p>
      </header>

      {/* Content Grid */}
      <div className="flex-1 overflow-y-auto custom-scrollbar -mr-4 pr-4 pb-4">
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {/* 1. IDENTITY MATRIX */}
          <Card
            title="Identity Matrix"
            subtitle="System addressable name, language and personality."
            icon={User}
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FieldGroup label="Operator Designation">
                <TextInput
                  value={settings.operatorName}
                  onChange={handleOperatorChange}
                  placeholder="Enter Name"
                />
              </FieldGroup>

              <FieldGroup label="Interface Language">
                <Select value={settings.interfaceLanguage} onChange={handleLanguageChange}>
                  <option value="auto">Auto Detect</option>
                  <option value="en">English (US)</option>
                  <option value="ru">Russian (RU)</option>
                </Select>
              </FieldGroup>
            </div>

            <FieldGroup label="Neural Personality">
              <Select
                value={settings.neuralPersonality}
                onChange={handlePersonalityChange}
              >
                <option value="short_sharp">Short &amp; Sharp</option>
                <option value="balanced">Balanced (Standard)</option>
                <option value="verbose">Verbose / Deep</option>
              </Select>
            </FieldGroup>
          </Card>

          {/* 2. SESSION PRESETS */}
          <Card
            title="Session Presets"
            subtitle="Output density, tone and UX behaviour."
            icon={Sliders}
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FieldGroup label="Output Density">
                <Select
                  value={settings.outputDensity}
                  onChange={handleOutputDensityChange}
                >
                  <option value="short">Short</option>
                  <option value="balanced">Balanced</option>
                  <option value="deep">Deep</option>
                </Select>
              </FieldGroup>

              <FieldGroup label="Response Tone">
                <Select value={settings.responseTone} onChange={handleToneChange}>
                  <option value="bro">Bro mode</option>
                  <option value="strict">Strict</option>
                  <option value="neutral">Neutral</option>
                </Select>
              </FieldGroup>
            </div>

            <div className="p-4 bg-white/5 rounded-xl border border-white/5 mb-3 group hover:border-white/10 transition-colors">
              <div className="flex justify-between items-center mb-3">
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider group-hover:text-slate-400 transition-colors">
                  Temperature
                </label>
                <span className="text-xs font-mono text-air-400 font-bold">
                  {settings.temperature.toFixed(1)}
                </span>
              </div>
              <div className="relative h-2 bg-slate-800/50 rounded-full w-full">
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.1}
                  value={settings.temperature}
                  onChange={(e) =>
                    handleTemperatureChange(parseFloat(e.target.value))
                  }
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                />
                <div
                  className="absolute top-0 left-0 h-full bg-air-500 rounded-full transition-all duration-150"
                  style={{ width: `${settings.temperature * 100}%` }}
                ></div>
                <div
                  className="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-white rounded-full shadow-lg pointer-events-none transition-all duration-150"
                  style={{
                    left: `${settings.temperature * 100}%`,
                    transform: "translate(-50%, -50%)",
                  }}
                ></div>
              </div>
              <p className="text-[10px] text-slate-600 mt-2">
                Controls randomness of responses (0.0 - 1.0)
              </p>
            </div>

            <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5 hover:border-white/10 transition-colors">
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                Sticky Sidebar
              </span>
              <Checkbox
                checked={settings.stickySidebar}
                onChange={handleStickySidebarToggle}
              />
            </div>
          </Card>

          {/* 3. NEURAL ENGINE */}
          <Card
            title="Neural Engine"
            subtitle="Active model and streaming behaviour."
            icon={Cpu}
          >
            <FieldGroup label="Active Model Weight">
              <Select 
                value={air4.getActiveModel?.() || "auto"} 
                onChange={handleModelSelect}
              >
                {modelsLoading ? (
                  <option value="auto">Loading models...</option>
                ) : modelsError || ollamaModels.length === 0 ? (
                  <option value="auto">Ollama unavailable</option>
                ) : (
                  <>
                    <option value="auto">auto (router)</option>
                    {ollamaModels.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </>
                )}
              </Select>
              <p className="text-[10px] text-slate-500 mt-2">
                Effective model: {(() => {
                  const model = air4.getActiveModel?.() || "auto";
                  return model === "auto" ? "auto (router)" : model;
                })()} (global)
              </p>
            </FieldGroup>

            <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5 hover:border-white/10 transition-colors">
              <div>
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                  Real-Time Token Streaming
                </span>
                <span
                  className={`text-xs font-bold block ${
                    settings.streaming ? "text-emerald-400" : "text-slate-400"
                  }`}
                >
                  {settings.streaming ? "Enabled" : "Disabled"}
                </span>
              </div>
              <Checkbox checked={settings.streaming} onChange={handleStreamingToggle} />
            </div>
          </Card>

          {/* 3.5. SESSION CONFIG */}
          {activeSessionId && (
            <Card
              title="Session Configuration"
              subtitle="Override settings for current session. Changes apply immediately."
              icon={Sliders}
            >
              <p className="text-xs text-slate-400 mb-4">
                Active session: {activeSessionId || 'none'}
              </p>
              <FieldGroup label="Model Override">
                <Select 
                  value={sessionConfig.model || ""} 
                  onChange={(e) => {
                    const newConfig = { ...sessionConfig };
                    if (e.target.value) {
                      newConfig.model = e.target.value;
                    } else {
                      delete newConfig.model;
                    }
                    setSessionConfig(newConfig);
                    air4.setSessionConfig(activeSessionId, newConfig);
                  }}
                >
                  <option value="">Use Global ({(() => {
                    const model = air4.getActiveModel?.() || "auto";
                    return model === "auto" ? "auto (router)" : model;
                  })()})</option>
                  {modelsLoading ? (
                    <option value="">Loading models...</option>
                  ) : modelsError || ollamaModels.length === 0 ? (
                    <option value="">Ollama unavailable</option>
                  ) : (
                    <>
                      <option value="auto">auto (router)</option>
                      {ollamaModels.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </>
                  )}
                </Select>
                <p className="text-[10px] text-slate-500 mt-2">
                  Effective model: {(() => {
                    const sessionModel = sessionConfig.model;
                    const globalModel = air4.getActiveModel?.() || "auto";
                    const effective = sessionModel || globalModel;
                    const display = effective === "auto" ? "auto (router)" : effective;
                    return sessionModel 
                      ? `${display} (session override)` 
                      : `${display} (global)`;
                  })()}
                </p>
              </FieldGroup>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FieldGroup label="Tone Override">
                  <Select 
                    value={sessionConfig.tone || ""} 
                    onChange={(e) => {
                      const newConfig = { ...sessionConfig };
                      if (e.target.value) {
                        newConfig.tone = e.target.value;
                      } else {
                        delete newConfig.tone;
                      }
                      setSessionConfig(newConfig);
                      air4.setSessionConfig(activeSessionId, newConfig);
                    }}
                  >
                    <option value="">Use Global ({toneLabel(settings.responseTone)})</option>
                    <option value="bro">Bro mode</option>
                    <option value="strict">Strict</option>
                    <option value="neutral">Neutral</option>
                  </Select>
                </FieldGroup>

                <FieldGroup label="Density Override">
                  <Select 
                    value={sessionConfig.density || ""} 
                    onChange={(e) => {
                      const newConfig = { ...sessionConfig };
                      if (e.target.value) {
                        newConfig.density = e.target.value;
                      } else {
                        delete newConfig.density;
                      }
                      setSessionConfig(newConfig);
                      air4.setSessionConfig(activeSessionId, newConfig);
                    }}
                  >
                    <option value="">Use Global ({densityLabel(settings.outputDensity)})</option>
                    <option value="short">Short</option>
                    <option value="balanced">Balanced</option>
                    <option value="deep">Deep</option>
                  </Select>
                </FieldGroup>
              </div>

              <FieldGroup label="Language Override">
                <Select 
                  value={sessionConfig.uiLang || ""} 
                  onChange={(e) => {
                    const newConfig = { ...sessionConfig };
                    if (e.target.value) {
                      newConfig.uiLang = e.target.value;
                    } else {
                      delete newConfig.uiLang;
                    }
                    setSessionConfig(newConfig);
                    air4.setSessionConfig(activeSessionId, newConfig);
                  }}
                >
                  <option value="">Use Global ({settings.interfaceLanguage})</option>
                  <option value="auto">Auto Detect</option>
                  <option value="en">English (US)</option>
                  <option value="ru">Russian (RU)</option>
                </Select>
              </FieldGroup>

              <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5 hover:border-white/10 transition-colors">
                <div>
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                    Streaming Override
                  </span>
                  <span
                    className={`text-xs font-bold block ${
                      (sessionConfig.streaming !== undefined ? sessionConfig.streaming : settings.streaming) 
                        ? "text-emerald-400" 
                        : "text-slate-400"
                    }`}
                  >
                    {(sessionConfig.streaming !== undefined ? sessionConfig.streaming : settings.streaming) 
                      ? "Enabled" 
                      : "Disabled"}
                  </span>
                </div>
                <Checkbox 
                  checked={sessionConfig.streaming !== undefined ? sessionConfig.streaming : settings.streaming} 
                  onChange={() => {
                    const newConfig = { 
                      ...sessionConfig, 
                      streaming: sessionConfig.streaming !== undefined ? !sessionConfig.streaming : !settings.streaming 
                    };
                    setSessionConfig(newConfig);
                    air4.setSessionConfig(activeSessionId, newConfig);
                  }} 
                />
              </div>
            </Card>
          )}

          {/* 4. MEMORY & CONTEXT */}
          <Card
            title="Memory & Context"
            subtitle="Session titles and history management."
            icon={Database}
          >
            <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5 hover:border-white/10 transition-colors mb-4">
              <div>
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                  Auto-Label Sessions
                </span>
                <span
                  className={`text-xs font-bold block ${
                    autoTitle ? "text-emerald-400" : "text-slate-400"
                  }`}
                >
                  {autoTitle ? "Enabled" : "Disabled"}
                </span>
              </div>
              <Checkbox checked={autoTitle} onChange={toggleAutoTitle} />
            </div>

            <div className="p-4 bg-white/5 rounded-xl border border-white/5 hover;border-white/10 transition-colors flex items-center justify-between">
              <div>
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                  Prune Chat Logs
                </span>
                <p className="text-[10px] text-slate-600 max-w-[200px] leading-tight">
                  Remove local chat history from device. Vector memory persists.
                </p>
              </div>
              <button
                onClick={handleClearSessions}
                className="px-4 py-2 bg-transparent hover:bg-air-500/10 border border-slate-700 hover:border-air-500 text-slate-400 hover:text-air-500 rounded-lg text-[10px] font-bold tracking-widest uppercase transition-all"
              >
                Execute
              </button>
            </div>
          </Card>

          {/* 5. INGESTION PROTOCOLS */}
          <div className="xl:col-span-1">
            <Card
              title="Ingestion Protocols"
              subtitle="Chunking depth profiles."
              icon={FileText}
            >
              <div className="p-4 bg-white/5 rounded-xl border border-white/5 hover:border-white/10 transition-colors">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-3">
                  Chunking Strategy
                </span>
                <p className="text-[10px] text-slate-500 mb-4 leading-relaxed">
                  Defines how documents are split into chunks. Deeper strategies improve recall at the cost of processing time.
                </p>

                <div className="grid grid-cols-3 gap-2">
                  <IngestButton
                    label="Speed"
                    active={settings.chunkProfile === "speed"}
                    onClick={() => handleChunkProfileChange("speed")}
                  />
                  <IngestButton
                    label="Balanced"
                    active={settings.chunkProfile === "balanced"}
                    onClick={() => handleChunkProfileChange("balanced")}
                  />
                  <IngestButton
                    label="Deep"
                    active={settings.chunkProfile === "deep"}
                    onClick={() => handleChunkProfileChange("deep")}
                  />
                </div>
              </div>
            </Card>
          </div>

          {/* 6. DANGER ZONE */}
          <div className="xl:col-span-1">
            <div className="h-full p-6 rounded-2xl glass-card bg-red-500/5 border-red-500/20 hover:border-red-500/40 transition-colors">
              <div className="flex items-center gap-2 mb-2">
                <ShieldAlert className="w-4 h-4 text-red-500" />
                <h3 className="text-[10px] font-bold text-red-500 uppercase tracking-[0.2em]">
                  Danger Zone
                </h3>
              </div>
              <p className="text-xs text-red-200/50 mb-6">Irreversible local actions.</p>

              <div className="p-4 bg-black/20 rounded-xl border border-red-500/10 flex flex-col md:flex-row items-center justify-between gap-4">
                <div>
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                    System Factory Reset
                  </span>
                  <p className="text-[10px] text-slate-500 max-w-xs leading-tight">
                    Clears settings, logs &amp; UI state. Does not wipe Vector DB.
                  </p>
                </div>
                <button
                  onClick={handleReset}
                  className="px-5 py-3 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 hover:border-red-500 text-red-400 hover:text-red-200 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all whitespace-nowrap"
                >
                  Initiate Purge
                </button>
              </div>
            </div>
          </div>

          {/* 7. SETUP */}
          <div className="xl:col-span-2">
            <Card
              title="Setup"
              subtitle="Reset local configuration and run onboarding again."
              icon={Sliders}
            >
              <div className="p-4 bg-white/5 rounded-xl border border-white/5 hover:border-white/10 transition-colors flex flex-col md:flex-row items-center justify-between gap-4">
                <div>
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                    Re-run setup
                  </span>
                  <p className="text-[10px] text-slate-500 max-w-xs leading-tight">
                    Clear all local configuration and restart onboarding.
                  </p>
                </div>
                <button
                  onClick={rerunSetup}
                  className="px-5 py-3 bg-air-500/10 hover:bg-air-500/20 border border-air-500/30 hover:border-air-500 text-air-400 hover:text-air-200 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all whitespace-nowrap"
                >
                  Re-run setup
                </button>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
};

// --- Sub-Components ---

const Card = ({ title, subtitle, icon: Icon, children }: any) => (
  <div className="glass-card p-6 rounded-2xl animate-fade-in-up">
    <div className="flex items-start gap-3 mb-6">
      <div className="p-2 rounded-lg bg-air-500/10 text-air-500">
        {Icon && <Icon className="w-5 h-5" />}
      </div>
      <div>
        <h3 className="text-sm font-bold text-white tracking-wide uppercase">
          {title}
        </h3>
        <p className="text-xs text-slate-500">{subtitle}</p>
      </div>
    </div>
    <div className="space-y-4">{children}</div>
  </div>
);

const FieldGroup = ({ label, children }: any) => (
  <div className="p-4 bg-white/5 rounded-xl border border-white/5 hover:border-white/10 transition-colors">
    <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
      {label}
    </label>
    {children}
  </div>
);

const TextInput = ({ value, onChange, placeholder }: any) => (
  <input
    type="text"
    value={value}
    onChange={onChange}
    placeholder={placeholder}
    className="glass-input w-full rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-air-500/50 transition-colors placeholder-slate-600"
  />
);

const Select = ({ value, onChange, children }: any) => (
  <div className="relative group">
    <select
      value={value}
      onChange={onChange}
      className="glass-input w-full appearance-none rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-air-500/50 transition-colors cursor-pointer"
    >
      {children}
    </select>
    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 group-hover:text-air-400 transition-colors pointer-events-none" />
  </div>
);

const Checkbox = ({ checked, onChange }: any) => (
  <button
    onClick={onChange}
    className={`w-5 h-5 rounded border flex items-center justify-center transition-all shadow-sm ${
      checked
        ? "bg-air-500 border-air-500 text-white shadow-air-500/30"
        : "bg-transparent border-slate-600 hover:border-air-500 hover:bg-white/5"
    }`}
  >
    {checked && <Check className="w-3.5 h-3.5" />}
  </button>
);

const IngestButton = ({ label, active, onClick }: any) => (
  <button
    onClick={onClick}
    className={`px-4 py-3 rounded-xl border text-[10px] font-bold uppercase tracking-wider transition-all duration-300 ${
      active
        ? "bg-air-500/10 border-air-500 text-air-400 shadow-[0_0_15px_rgba(249,115,22,0.15)] scale-[1.02]"
        : "bg-white/5 border-transparent text-slate-500 hover:bg-white/10 hover:text-slate-300"
    }`}
  >
    {label}
  </button>
);

export default SettingsPage;

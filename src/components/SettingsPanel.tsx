import React from 'react';
import { X, HardDrive, Workflow, Download } from 'lucide-react';
import { motion } from 'motion/react';
import { EXPORT_FORMAT_OPTIONS, KEEP_HISTORY_OPTIONS } from '../constants';
import { GenerationConfig } from '../types';

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  generationConfig: GenerationConfig;
  onGenerationConfigChange: (config: GenerationConfig) => void;
}

export function SettingsPanel({ open, onClose, generationConfig, onGenerationConfigChange }: SettingsPanelProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      <motion.aside
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 26, stiffness: 300 }}
        className="relative w-full max-w-sm h-full bg-surface-container border-l border-outline-variant/20 overflow-y-auto no-scrollbar"
      >
        <div className="sticky top-0 bg-surface-container z-10 flex items-center justify-between px-6 py-5 border-b border-outline-variant/15">
          <div>
            <h2 className="font-headline text-lg font-bold uppercase tracking-tight text-on-surface">Advanced Settings</h2>
            <p className="text-[10px] uppercase tracking-widest text-outline mt-1">Workflow And Output Preferences</p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center text-outline hover:text-on-surface transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-6 space-y-8">
          <section className="space-y-4">
            <h3 className="font-label text-[10px] uppercase tracking-widest text-outline flex items-center gap-2">
              <Download size={12} /> Affects Generated Output
            </h3>
            <div className="space-y-3">
              <SettingRow label="Export Format" helper="Applied to export payload and mock output packaging.">
                <select
                  value={generationConfig.exportFormat}
                  onChange={(event) => onGenerationConfigChange({ ...generationConfig, exportFormat: event.target.value as GenerationConfig['exportFormat'] })}
                  className="bg-surface-container-lowest border-none text-xs font-body p-2 rounded text-on-surface"
                >
                  {EXPORT_FORMAT_OPTIONS.map((format) => (
                    <option key={format}>{format}</option>
                  ))}
                </select>
              </SettingRow>
            </div>
          </section>

          <section className="space-y-4">
            <h3 className="font-label text-[10px] uppercase tracking-widest text-outline flex items-center gap-2">
              <Workflow size={12} /> Workflow And Storage Preferences
            </h3>
            <div className="space-y-3">
              <SettingRow label="Keep History" helper="Controls how long this browser keeps local history records.">
                <select
                  value={generationConfig.keepHistory}
                  onChange={(event) => onGenerationConfigChange({ ...generationConfig, keepHistory: event.target.value as GenerationConfig['keepHistory'] })}
                  className="bg-surface-container-lowest border-none text-xs font-body p-2 rounded text-on-surface"
                >
                  {KEEP_HISTORY_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option === 'forever' ? 'Forever' : option === '30-days' ? '30 Days' : '7 Days'}
                    </option>
                  ))}
                </select>
              </SettingRow>
              <SettingRow label="Auto-Export On Complete" helper="Automatically opens the export when generation finishes.">
                <ToggleSwitch
                  on={generationConfig.autoExportOnComplete}
                  onToggle={() => onGenerationConfigChange({ ...generationConfig, autoExportOnComplete: !generationConfig.autoExportOnComplete })}
                />
              </SettingRow>
            </div>
          </section>

          <section className="bg-surface-container-low rounded-xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-primary">
              <HardDrive size={14} />
              <p className="text-[10px] uppercase tracking-widest font-bold">Browser-Local Product Version</p>
            </div>
            <p className="text-sm leading-relaxed text-on-surface-variant">
              This public version keeps workflow preferences and history on the current browser/device. The structure is ready to swap to backend persistence later without changing the core workspace UX.
            </p>
          </section>
        </div>
      </motion.aside>
    </div>
  );
}

function SettingRow({ label, helper, children }: { label: string; helper: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface-container-low rounded-lg px-4 py-4 space-y-3">
      <div className="space-y-1">
        <span className="text-xs text-on-surface">{label}</span>
        <p className="text-[10px] text-outline leading-relaxed">{helper}</p>
      </div>
      <div>{children}</div>
    </div>
  );
}

function ToggleSwitch({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`w-10 h-5 rounded-full relative transition-colors ${on ? 'bg-primary' : 'bg-surface-container-highest'}`}
    >
      <div
        className={`absolute top-0.5 w-4 h-4 rounded-full transition-all ${on ? 'left-5 bg-on-primary' : 'left-0.5 bg-outline'}`}
      />
    </button>
  );
}

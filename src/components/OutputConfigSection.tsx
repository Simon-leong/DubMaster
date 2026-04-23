/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { Settings2 } from 'lucide-react';

interface OutputConfigSectionProps {
  outputClasses: string[];
  setOutputClasses: (c: string[]) => void;
  duration: number;
  setDuration: (d: number) => void;
}

export function OutputConfigSection({
  outputClasses,
  setOutputClasses,
  duration,
  setDuration,
}: OutputConfigSectionProps) {
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.00s`;
  };

  const toggleClass = (cls: string) => {
    if (outputClasses.includes(cls)) {
      // Don't allow deselecting the last one
      if (outputClasses.length > 1) {
        setOutputClasses(outputClasses.filter((c) => c !== cls));
      }
    } else {
      setOutputClasses([...outputClasses, cls]);
    }
  };

  return (
    <div className="bg-surface-container-lowest p-6 rounded-xl flex flex-col gap-6">
      <h2 className="font-label text-xs font-bold uppercase tracking-widest text-on-surface-variant flex items-center gap-2">
        <Settings2 size={14} /> Output Configuration
      </h2>

      <div className="flex flex-col gap-3">
        <label className="font-label text-[10px] uppercase tracking-widest text-outline">Output Class (multi-select)</label>
        <div className="grid grid-cols-2 gap-2">
          {['Sound Effects', 'Speech', 'Background Music', 'Song'].map((cls) => (
            <button
              key={cls}
              onClick={() => toggleClass(cls)}
              className={`${outputClasses.includes(cls) ? 'bg-primary text-on-primary' : 'bg-surface-container-highest text-on-surface hover:bg-surface-container-high'} text-[11px] font-bold py-3 rounded uppercase tracking-tighter transition-colors`}
            >
              {cls}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex justify-between items-end">
          <label className="font-label text-[10px] uppercase tracking-widest text-outline">Target Duration</label>
          <span className="text-primary font-mono text-xs">{formatDuration(duration)}</span>
        </div>
        <div className="h-1 bg-surface-container-highest w-full relative cursor-pointer group">
          <input
            type="range"
            min="1"
            max="30"
            value={duration}
            onChange={(e) => setDuration(parseInt(e.target.value))}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
          />
          <div
            className="absolute top-0 left-0 h-full bg-gradient-to-r from-primary to-inverse-primary transition-all duration-75"
            style={{ width: `${(duration / 30) * 100}%` }}
          ></div>
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-on-surface rounded-full shadow-lg transition-all duration-75"
            style={{ left: `calc(${(duration / 30) * 100}% - 6px)` }}
          ></div>
        </div>
      </div>
    </div>
  );
}

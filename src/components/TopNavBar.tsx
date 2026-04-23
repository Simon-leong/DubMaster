/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { AnimatePresence } from 'motion/react';
import { Home, Settings } from 'lucide-react';
import { GenerationConfig, View } from '../types';
import { SettingsPanel } from './SettingsPanel';

interface TopNavBarProps {
  currentView: View;
  setView: (v: View) => void;
  generationConfig: GenerationConfig;
  onGenerationConfigChange: (config: GenerationConfig) => void;
}

export function TopNavBar({ currentView, setView, generationConfig, onGenerationConfigChange }: TopNavBarProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <>
      <nav className="flex justify-between items-center w-full px-12 h-20 bg-background sticky top-0 z-50 border-b border-outline-variant/10">
        <div className="flex items-center gap-8">
          <span className="text-xl font-black tracking-tighter text-on-surface font-headline uppercase cursor-pointer" onClick={() => setView('home')}>
            DubMaster
          </span>
          <div className="hidden md:flex items-center gap-6">
            <button
              onClick={() => setView('home')}
              className={`text-sm tracking-wider transition-colors duration-200 flex items-center gap-2 ${currentView === 'home' ? 'text-primary border-b-2 border-primary pb-1' : 'text-outline hover:text-on-surface'}`}
            >
              <Home size={14} /> Home
            </button>
            <button
              onClick={() => setView('workspace')}
              className={`text-sm tracking-wider transition-colors duration-200 ${currentView === 'workspace' ? 'text-primary border-b-2 border-primary pb-1' : 'text-outline hover:text-on-surface'}`}
            >
              Workspace
            </button>
            <button
              onClick={() => setView('history')}
              className={`text-sm tracking-wider transition-colors duration-200 ${currentView === 'history' ? 'text-primary border-b-2 border-primary pb-1' : 'text-outline hover:text-on-surface'}`}
            >
              History
            </button>
          </div>
        </div>
        <div className="flex items-center justify-end min-w-[72px]">
          <button
            onClick={() => setSettingsOpen(true)}
            className={`transition-all duration-200 active:scale-95 ${settingsOpen ? 'text-primary' : 'text-outline hover:text-on-surface'}`}
          >
            <Settings size={20} />
          </button>
        </div>
      </nav>

      <AnimatePresence>
        {settingsOpen && (
          <SettingsPanel
            open={settingsOpen}
            onClose={() => setSettingsOpen(false)}
            generationConfig={generationConfig}
            onGenerationConfigChange={onGenerationConfigChange}
          />
        )}
      </AnimatePresence>
    </>
  );
}

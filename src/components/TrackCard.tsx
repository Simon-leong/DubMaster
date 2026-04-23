/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { Play, Pause, Download, Share2, MoreHorizontal } from 'lucide-react';
import { motion } from 'motion/react';

interface TrackCardProps {
  id: string;
  title: string;
  type: string;
  duration: string;
  active?: boolean;
  playing?: boolean;
  onSelect: () => void;
  onTogglePlay: () => void;
}

export const TrackCard: React.FC<TrackCardProps> = ({ 
  id,
  title, 
  type, 
  duration, 
  active = false, 
  playing = false, 
  onSelect, 
  onTogglePlay 
}) => {
  return (
    <div 
      onClick={onSelect}
      className={`group p-4 rounded-xl border transition-all cursor-pointer ${active ? 'bg-surface-container-high border-primary shadow-lg shadow-primary/5' : 'bg-surface-container-low border-outline-variant/10 hover:bg-surface-container hover:border-outline-variant/30'}`}
    >
      <div className="flex items-center gap-4 mb-4">
        <button 
          onClick={(e) => { e.stopPropagation(); onTogglePlay(); }}
          className={`w-10 h-10 rounded-full flex items-center justify-center active:scale-95 transition-all ${playing ? 'bg-primary text-on-primary' : 'bg-surface-container-highest text-on-surface'}`}
        >
          {playing ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}
        </button>
        <div className="flex-grow h-12 bg-surface-container-lowest relative overflow-hidden flex items-center px-1">
          <div className="flex items-end gap-[2px] h-8 w-full opacity-40">
            {[12, 16, 24, 32, 28, 20, 24, 12, 8, 14, 20, 16, 10, 12, 8, 15, 22, 18, 25, 30, 14, 10, 18, 24, 20, 16, 12, 8].map((h, i) => (
              <motion.div 
                key={i} 
                className={`flex-grow rounded-t-sm ${playing ? 'bg-primary' : 'bg-outline'}`}
                animate={playing ? { height: [`${h/2}px`, `${h}px`, `${h/2}px`] } : { height: `${h/2}px` }}
                transition={{ duration: 1, repeat: Infinity, delay: i * 0.05 }}
              />
            ))}
          </div>
          {playing && (
            <motion.div 
              className="absolute top-0 left-0 h-full w-1 bg-primary z-10 shadow-[0_0_10px_rgba(var(--primary),0.5)]"
              animate={{ left: ['0%', '100%'] }}
              transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
            />
          )}
        </div>
      </div>
      <div className="flex justify-between items-end">
        <div>
          <h3 className="font-headline font-bold text-sm uppercase tracking-tight text-on-surface">{title}</h3>
          <p className="font-label text-[10px] text-outline uppercase tracking-widest">{type} // {duration}</p>
        </div>
        <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <button className="p-2 text-outline hover:text-primary transition-colors"><Download size={14} /></button>
          <button className="p-2 text-outline hover:text-primary transition-colors"><Share2 size={14} /></button>
          <button className="p-2 text-outline hover:text-primary transition-colors"><MoreHorizontal size={14} /></button>
        </div>
      </div>
    </div>
  );
}

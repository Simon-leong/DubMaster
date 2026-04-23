/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Archive, CalendarClock, Download, HardDrive, Play, Trash2, Waves } from 'lucide-react';
import { AppNotice, Artifact } from '../types';
import { getPreviewUrl } from '../services/api';

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Unknown';
  }

  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

interface HistoryViewProps {
  artifacts: Artifact[];
  onOpenWorkspace: () => void;
  onDeleteItem: (id: string) => void;
  onClearAll: () => void;
  onExport: (id: string) => Promise<{ url: string }>;
  onNotify: (tone: AppNotice['tone'], title: string, message: string) => void;
  focusedArtifactId?: string | null;
  onFocusHandled?: () => void;
}

export function HistoryView({
  artifacts,
  onOpenWorkspace,
  onDeleteItem,
  onClearAll,
  onExport,
  onNotify,
  focusedArtifactId,
  onFocusHandled,
}: HistoryViewProps) {
  const [selectedTrack, setSelectedTrack] = useState(artifacts[0]?.id || '');
  const [isExporting, setIsExporting] = useState(false);
  const [isConfirmingClearAll, setIsConfirmingClearAll] = useState(false);
  const [highlightedTrack, setHighlightedTrack] = useState('');
  const itemRefs = useRef<Record<string, HTMLElement | null>>({});

  useEffect(() => {
    if (artifacts.length === 0) {
      setSelectedTrack('');
      setIsConfirmingClearAll(false);
      return;
    }

    if (!artifacts.some((artifact) => artifact.id === selectedTrack)) {
      setSelectedTrack(artifacts[0].id);
    }
  }, [artifacts, selectedTrack]);

  useEffect(() => {
    if (!focusedArtifactId || !artifacts.some((artifact) => artifact.id === focusedArtifactId)) {
      return;
    }

    setSelectedTrack(focusedArtifactId);
    setHighlightedTrack(focusedArtifactId);

    const frameId = window.requestAnimationFrame(() => {
      itemRefs.current[focusedArtifactId]?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    });

    const timeoutId = window.setTimeout(() => {
      setHighlightedTrack((current) => (current === focusedArtifactId ? '' : current));
    }, 2600);

    onFocusHandled?.();

    return () => {
      window.cancelAnimationFrame(frameId);
      window.clearTimeout(timeoutId);
    };
  }, [artifacts, focusedArtifactId, onFocusHandled]);

  const selectedArtifact = useMemo(() => {
    return artifacts.find((artifact) => artifact.id === selectedTrack) || null;
  }, [artifacts, selectedTrack]);

  const handleExport = async () => {
    if (!selectedTrack) {
      onNotify('warning', 'No artifact selected', 'Select a history item before exporting.');
      return;
    }

    setIsExporting(true);
    try {
      const response = await onExport(selectedTrack);
      const a = document.createElement('a');
      a.href = response.url;
      a.download = '';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (error) {
      console.error('History export failed:', error);
      onNotify('warning', 'Export unavailable', 'DubMaster could not export this artifact just yet.');
    } finally {
      setIsExporting(false);
    }
  };

  const handleDeleteSelected = () => {
    if (!selectedTrack) {
      return;
    }

    onDeleteItem(selectedTrack);
  };

  const handleClearAll = () => {
    if (artifacts.length === 0) {
      return;
    }

    if (!isConfirmingClearAll) {
      setIsConfirmingClearAll(true);
      onNotify('warning', 'Confirm clear all', 'Click "Confirm Clear All" once more to remove every locally saved artifact from this browser.');
      return;
    }

    onClearAll();
    setIsConfirmingClearAll(false);
  };

  return (
    <div className="p-8 md:p-12 max-w-[1600px] mx-auto w-full space-y-12">
      <header className="flex flex-col lg:flex-row justify-between items-start lg:items-end gap-6 border-l-4 border-primary pl-6">
        <div>
          <h1 className="text-4xl md:text-5xl font-headline font-extrabold tracking-tight text-on-surface uppercase">History</h1>
          <p className="text-on-surface-variant font-label text-sm tracking-widest uppercase">
            Local Archive // {artifacts.length} Saved Items
          </p>
        </div>
        <div className="flex flex-wrap gap-4">
          <button
            onClick={onOpenWorkspace}
            className="bg-surface-container-high text-on-surface px-6 py-3 rounded font-bold uppercase tracking-widest text-xs hover:bg-surface-container transition-all"
          >
            Back To Workspace
          </button>
          <button
            onClick={handleDeleteSelected}
            disabled={!selectedTrack}
            className={`bg-surface-container-high text-on-surface px-6 py-3 rounded font-bold uppercase tracking-widest text-xs transition-all flex items-center gap-2 ${selectedTrack ? 'hover:bg-surface-container' : 'opacity-50 cursor-not-allowed'}`}
          >
            <Trash2 size={14} /> Delete Selected
          </button>
          <button
            onClick={handleClearAll}
            disabled={artifacts.length === 0}
            className={`bg-surface-container-high text-on-surface px-6 py-3 rounded font-bold uppercase tracking-widest text-xs transition-all ${artifacts.length > 0 ? 'hover:bg-surface-container' : 'opacity-50 cursor-not-allowed'}`}
          >
            {isConfirmingClearAll ? 'Confirm Clear All' : 'Clear All'}
          </button>
          <button
            onClick={handleExport}
            disabled={isExporting || !selectedTrack}
            className={`bg-primary text-on-primary px-8 py-3 rounded font-bold uppercase tracking-widest text-xs transition-all flex items-center gap-2 ${isExporting || !selectedTrack ? 'opacity-50 cursor-not-allowed' : 'hover:bg-primary-container'}`}
          >
            <Download size={16} /> {isExporting ? 'Exporting...' : 'Export Selected'}
          </button>
        </div>
      </header>

      <div className="bg-surface-container rounded-2xl p-5 border border-outline-variant/10 flex items-start gap-4">
        <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
          <HardDrive size={18} />
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-primary mb-2">Local Storage Note</p>
          <p className="text-sm leading-relaxed text-on-surface-variant">
            History is stored only on this browser and device using local storage. It is not tied to an account and will not sync across browsers or machines in this version.
          </p>
        </div>
      </div>

      {artifacts.length === 0 ? (
        <div className="bg-surface-container-lowest border border-outline-variant/10 rounded-3xl p-12 text-center space-y-5">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-surface-container flex items-center justify-center text-primary">
            <Archive size={28} />
          </div>
          <div className="space-y-3">
            <h2 className="text-2xl font-headline font-bold uppercase tracking-tight text-on-surface">No Local History Yet</h2>
            <p className="max-w-2xl mx-auto text-sm leading-relaxed text-on-surface-variant">
              Completed generations will appear here automatically and remain available when you revisit later on the same browser and device.
            </p>
          </div>
          <button
            onClick={onOpenWorkspace}
            className="bg-primary text-on-primary px-8 py-4 rounded-lg font-bold uppercase tracking-widest text-xs hover:bg-primary-container transition-all"
          >
            Start A New Generation
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <section className="lg:col-span-4 space-y-6">
            <div className="bg-surface-container p-6 rounded-xl space-y-4">
              <h2 className="font-label text-xs font-bold uppercase tracking-widest text-outline flex items-center gap-2">
                <Archive size={14} /> Archive Summary
              </h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-surface-container-lowest rounded-lg p-4">
                  <p className="text-[10px] uppercase tracking-widest text-outline mb-2">Saved</p>
                  <p className="text-2xl font-headline font-bold text-on-surface">{artifacts.length}</p>
                </div>
                <div className="bg-surface-container-lowest rounded-lg p-4">
                  <p className="text-[10px] uppercase tracking-widest text-outline mb-2">Newest</p>
                  <p className="text-xs font-mono text-on-surface">{formatTimestamp(artifacts[0].createdAt)}</p>
                </div>
              </div>
            </div>

            <div className="space-y-3 overflow-y-auto max-h-[620px] pr-2 no-scrollbar">
              {artifacts.map((artifact) => (
                <article
                  key={artifact.id}
                  ref={(element) => {
                    itemRefs.current[artifact.id] = element;
                  }}
                  onClick={() => setSelectedTrack(artifact.id)}
                  className={`w-full text-left p-4 rounded-xl border transition-all cursor-pointer ${selectedTrack === artifact.id ? 'bg-surface-container-high border-primary shadow-lg shadow-primary/5' : 'bg-surface-container-low border-outline-variant/10 hover:bg-surface-container hover:border-outline-variant/30'} ${highlightedTrack === artifact.id ? 'ring-2 ring-primary/50 shadow-[0_0_40px_rgba(185,156,255,0.22)]' : ''}`}
                >
                  <div className="flex justify-between gap-4">
                    <div className="flex gap-3">
                      <div className="w-10 h-10 bg-surface-container-highest rounded flex items-center justify-center text-primary">
                        <Waves size={18} />
                      </div>
                      <div className="space-y-1">
                        <h3 className="text-sm font-bold text-on-surface uppercase tracking-tight">{artifact.title}</h3>
                        <p className="text-[10px] text-outline uppercase tracking-widest">{artifact.type} // {artifact.duration}</p>
                        <p className="text-[10px] text-outline">{formatTimestamp(artifact.createdAt)}</p>
                        {highlightedTrack === artifact.id && (
                          <p className="text-[10px] uppercase tracking-widest text-primary font-bold">Newly Generated</p>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        onDeleteItem(artifact.id);
                      }}
                      className="text-outline hover:text-primary transition-colors h-fit"
                      aria-label={`Delete ${artifact.title}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="lg:col-span-8 space-y-6">
            <div className="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-8 shadow-2xl">
              <div className="flex flex-col md:flex-row justify-between gap-6 border-b border-outline-variant/10 pb-6 mb-8">
                <div>
                  <h2 className="font-headline text-3xl font-bold uppercase tracking-tight text-on-surface">
                    {selectedArtifact?.title || 'No Artifact Selected'}
                  </h2>
                  <p className="font-label text-xs text-outline uppercase tracking-widest mt-2">
                    {selectedArtifact ? `${selectedArtifact.type} // ${selectedArtifact.duration}` : 'Select an artifact to inspect'}
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-3 min-w-[260px]">
                  <div className="bg-surface-container-low rounded-lg p-4">
                    <p className="text-[10px] uppercase tracking-widest text-outline mb-1">Created</p>
                    <p className="font-mono text-xs text-on-surface">{selectedArtifact ? formatTimestamp(selectedArtifact.createdAt) : '-'}</p>
                  </div>
                  <div className="bg-surface-container-low rounded-lg p-4">
                    <p className="text-[10px] uppercase tracking-widest text-outline mb-1">Source</p>
                    <p className="font-mono text-xs text-on-surface uppercase">{selectedArtifact?.sourceType || '-'}</p>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div className="xl:col-span-2 bg-background/40 rounded-xl p-6 border border-outline-variant/10">
                  <div className="flex justify-between items-center mb-6">
                    <h3 className="font-label text-xs font-bold uppercase tracking-widest text-outline flex items-center gap-2">
                      <Play size={14} /> Preview
                    </h3>
                    <span className="text-[10px] bg-surface-container-highest px-2 py-1 rounded text-on-surface uppercase font-bold">
                      {selectedArtifact?.runtimeMode === 'live' ? 'Live Result' : 'Preview'}
                    </span>
                  </div>
                  {selectedArtifact && selectedArtifact.runtimeMode === 'live' ? (
                    <div className="space-y-4">
                      <video
                        key={`video-${selectedArtifact.id}`}
                        src={getPreviewUrl(selectedArtifact.id)}
                        controls
                        className="w-full rounded-lg bg-black"
                        style={{ maxHeight: '280px' }}
                        onError={(e) => {
                          // If video fails (audio-only wav), hide video and show audio
                          const target = e.currentTarget;
                          target.style.display = 'none';
                          const audioEl = target.nextElementSibling as HTMLAudioElement | null;
                          if (audioEl) audioEl.style.display = 'block';
                        }}
                      />
                      <audio
                        key={`audio-${selectedArtifact.id}`}
                        src={getPreviewUrl(selectedArtifact.id)}
                        controls
                        className="w-full"
                        style={{ display: 'none' }}
                      />
                    </div>
                  ) : (
                    <div className="h-56 w-full flex items-center justify-center text-outline">
                      <p className="text-sm uppercase tracking-widest">No preview available</p>
                    </div>
                  )}
                </div>

                <div className="space-y-4">
                  <div className="bg-surface-container-low rounded-xl p-5">
                    <h3 className="font-label text-xs font-bold uppercase tracking-widest text-outline flex items-center gap-2">
                      <CalendarClock size={14} /> Metadata
                    </h3>
                    <div className="mt-4 space-y-3 text-sm">
                      <div className="flex justify-between gap-4">
                        <span className="text-outline uppercase text-[10px] tracking-widest">Prompt</span>
                        <span className="text-on-surface text-right max-w-[60%] line-clamp-3">{selectedArtifact?.prompt || '-'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-outline uppercase text-[10px] tracking-widest">Output</span>
                        <span className="text-on-surface">{selectedArtifact?.previewMetadata?.outputClass || '-'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-outline uppercase text-[10px] tracking-widest">Quality Mode</span>
                        <span className="text-on-surface uppercase">{selectedArtifact?.generationConfig.qualityMode || '-'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-outline uppercase text-[10px] tracking-widest">Style</span>
                        <span className="text-on-surface">{selectedArtifact?.previewMetadata?.acousticStyle || '-'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-outline uppercase text-[10px] tracking-widest">Model</span>
                        <span className="text-on-surface">{selectedArtifact?.previewMetadata?.languageModel || '-'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-outline uppercase text-[10px] tracking-widest">Render</span>
                        <span className="text-on-surface text-right">{selectedArtifact ? `${selectedArtifact.generationConfig.outputSampleRate} / ${selectedArtifact.generationConfig.bitDepth}` : '-'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-outline uppercase text-[10px] tracking-widest">Channels</span>
                        <span className="text-on-surface">{selectedArtifact?.generationConfig.channels || '-'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-outline uppercase text-[10px] tracking-widest">Mode</span>
                        <span className={`uppercase ${selectedArtifact?.runtimeMode === 'demo' ? 'text-secondary-fixed-dim' : 'text-on-surface'}`}>
                          {selectedArtifact?.runtimeMode || '-'}
                        </span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-outline uppercase text-[10px] tracking-widest">Source File</span>
                        <span className="text-on-surface text-right">
                          {selectedArtifact?.inputSnapshot.videoFileName || selectedArtifact?.inputSnapshot.imageFileName || '-'}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="bg-surface-container-low rounded-xl p-5">
                    <h3 className="font-label text-xs font-bold uppercase tracking-widest text-outline">Export Info</h3>
                    <div className="mt-4 space-y-3 text-sm text-on-surface-variant">
                      <p>Format: {selectedArtifact?.exportInfo?.format || selectedArtifact?.generationConfig.exportFormat || 'WAV'}</p>
                      <p>Last export: {selectedArtifact?.exportInfo?.lastExportedAt ? formatTimestamp(selectedArtifact.exportInfo.lastExportedAt) : 'Not exported yet'}</p>
                      <p>Saved locally for this browser version of DubMaster.</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

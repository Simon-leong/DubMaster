/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { motion } from 'motion/react';
import { CheckCircle2, RefreshCw, Hourglass, Cpu } from 'lucide-react';
import { ActiveGeneration } from '../types';

interface ProcessingViewProps {
  activeGeneration: ActiveGeneration | null;
}

function getProgress(status: ActiveGeneration['status'] | undefined, stage?: ActiveGeneration['stage']) {
  if (status === 'completed') return 100;
  if (status === 'failed') return 100;
  if (!stage) {
    return status === 'pending' ? 8 : status === 'processing' ? 50 : 5;
  }
  switch (stage) {
    case 'uploading': return 5;
    case 'planning': return 20;
    case 'assigning': return 40;
    case 'synthesizing': return 65;
    case 'mixing': return 88;
    case 'done': return 100;
    default: return 10;
  }
}

function getStatusLabel(status: ActiveGeneration['status'] | undefined, stage?: ActiveGeneration['stage']) {
  if (status === 'completed') return 'Completed';
  if (status === 'failed') return 'Failed';
  if (!stage) {
    return status === 'pending' ? 'Queueing' : 'Processing';
  }
  switch (stage) {
    case 'uploading': return 'Preparing Inputs';
    case 'planning': return 'Stage 1 — Planning';
    case 'assigning': return 'Stage 2 — Expert Routing';
    case 'synthesizing': return 'Stage 3 — Synthesis';
    case 'mixing': return 'Mixing';
    case 'done': return 'Completed';
    default: return 'Processing';
  }
}

function getStageIndex(stage?: ActiveGeneration['stage']): number {
  switch (stage) {
    case 'planning': return 1;
    case 'assigning': return 2;
    case 'synthesizing': return 3;
    case 'mixing': return 3;
    case 'done': return 4;
    default: return 0;
  }
}

export function ProcessingView({ activeGeneration }: ProcessingViewProps) {
  const status = activeGeneration?.status;
  const stage = activeGeneration?.stage;
  const stageIdx = getStageIndex(stage);
  const progress = getProgress(status, stage);
  const statusLabel = getStatusLabel(status, stage);
  const isPending = status === 'pending' || stageIdx < 1;
  const isProcessing = status === 'processing' && stageIdx >= 1 && stageIdx < 4;
  const isCompleted = status === 'completed' || stageIdx >= 4;
  const promptPreview = activeGeneration?.payload.prompt?.trim() || 'No prompt supplied';
  const config = activeGeneration?.payload.config;
  const inputSource = activeGeneration?.payload.videoFileName
    ? `Video: ${activeGeneration.payload.videoFileName}`
    : activeGeneration?.payload.imageFileName
      ? `Image: ${activeGeneration.payload.imageFileName}`
      : 'Prompt only';
  const runtimeModeLabel = activeGeneration?.runtimeMode === 'demo' ? 'Demo Preview' : 'Live Backend';
  const statusMessage = activeGeneration?.statusMessage || 'Preparing DubMaster generation pipeline.';

  return (
    <div className="p-8 md:p-12 max-w-7xl mx-auto w-full space-y-12">
      <header className="mb-12">
        <h1 className="font-headline font-bold text-4xl tracking-tight text-on-surface uppercase mb-2">Processing</h1>
        <div className="flex items-center gap-4">
          <div className="h-1 w-24 bg-surface-container-highest rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-primary to-inverse-primary"
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
            />
          </div>
          <span className="font-label text-xs uppercase tracking-widest text-primary">
            {statusLabel} // {progress}% Complete
          </span>
        </div>
        <div className="mt-4 inline-flex items-center gap-3 rounded-full border border-outline-variant/15 bg-surface-container px-4 py-2">
          <span className={`w-2 h-2 rounded-full ${activeGeneration?.runtimeMode === 'demo' ? 'bg-secondary-fixed-dim' : 'bg-primary'}`}></span>
          <span className="text-[10px] uppercase tracking-widest text-on-surface">{runtimeModeLabel}</span>
        </div>
        <p className="mt-4 max-w-3xl text-sm text-on-surface-variant">{statusMessage}</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-8 space-y-8">
          <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {(() => {
              const s1Active = stage === 'planning';
              const s1Done = stageIdx > 1;
              const s2Active = stage === 'assigning';
              const s2Done = stageIdx > 2;
              const s3Active = stage === 'synthesizing' || stage === 'mixing';
              const s3Done = stageIdx >= 4;
              return (
                <>
                  <div className={`bg-surface-container p-6 rounded-lg border-l-2 ${s1Active ? 'border-primary' : s1Done ? 'border-primary/20' : 'border-outline-variant/40'}`}>
                    {s1Active && <div className="absolute top-0 right-0 p-2"><div className="w-2 h-2 rounded-full bg-primary animate-ping"></div></div>}
                    <div className="flex justify-between items-start mb-4">
                      {s1Active ? <RefreshCw size={20} className="text-primary animate-spin" /> : s1Done ? <CheckCircle2 size={20} className="text-primary fill-primary/20" /> : <Hourglass size={20} className="text-outline" />}
                      <span className={`font-label text-[10px] uppercase tracking-wider ${s1Active ? 'text-primary' : 'text-outline'}`}>{s1Active ? 'Active' : 'Stage 01'}</span>
                    </div>
                    <h3 className="font-headline font-bold text-sm uppercase text-on-surface mb-2">Planning</h3>
                    <p className="font-body text-xs text-on-surface-variant leading-relaxed">LLM analyzes multimodal inputs and identifies audio events with timing.</p>
                    {s1Active && (
                      <div className="mt-4 h-[2px] w-full bg-surface-container-highest">
                        <motion.div className="h-full bg-primary" animate={{ width: ['0%', '70%'] }} transition={{ duration: 2, repeat: Infinity, repeatType: 'reverse' }} />
                      </div>
                    )}
                  </div>

                  <div className={`p-6 rounded-lg border-l-2 shadow-2xl relative overflow-hidden ${s2Active ? 'bg-surface-container-high border-primary' : s2Done ? 'bg-surface-container border-primary/20' : 'bg-surface-container-lowest border-outline-variant/40'}`}>
                    {s2Active && <div className="absolute top-0 right-0 p-2"><div className="w-2 h-2 rounded-full bg-primary animate-ping"></div></div>}
                    <div className="flex justify-between items-start mb-4">
                      {s2Active ? <RefreshCw size={20} className="text-primary animate-spin" /> : s2Done ? <CheckCircle2 size={20} className="text-primary fill-primary/20" /> : <Hourglass size={20} className="text-outline" />}
                      <span className={`font-label text-[10px] uppercase tracking-wider ${s2Active ? 'text-primary' : 'text-outline'}`}>{s2Active ? 'Active' : 'Stage 02'}</span>
                    </div>
                    <h3 className="font-headline font-bold text-sm uppercase text-on-surface mb-2">Expert Routing</h3>
                    <p className="font-body text-xs text-on-surface-variant leading-relaxed">Domain experts (SFX, Speech, Music, Song) select models and prepare inputs.</p>
                    <div className="mt-4 h-[2px] w-full bg-surface-container-highest">
                      <motion.div
                        className="h-full bg-primary"
                        animate={s2Active ? { width: ['0%', '60%'] } : { width: s2Done ? '100%' : '0%' }}
                        transition={s2Active ? { duration: 1.5, repeat: Infinity, repeatType: 'reverse' } : { duration: 0.4 }}
                      />
                    </div>
                  </div>

                  <div className={`p-6 rounded-lg border-l-2 ${s3Active ? 'bg-surface-container-high border-primary' : s3Done ? 'bg-surface-container border-primary/20' : 'bg-surface-container-lowest border-outline-variant opacity-60'}`}>
                    {s3Active && <div className="absolute top-0 right-0 p-2"><div className="w-2 h-2 rounded-full bg-primary animate-ping"></div></div>}
                    <div className="flex justify-between items-start mb-4">
                      {s3Active ? <RefreshCw size={20} className="text-primary animate-spin" /> : s3Done ? <CheckCircle2 size={20} className="text-primary fill-primary/20" /> : <Hourglass size={20} className="text-outline" />}
                      <span className={`font-label text-[10px] uppercase tracking-wider ${s3Active ? 'text-primary' : s3Done ? 'text-primary' : 'text-outline'}`}>{s3Active ? 'Active' : 'Stage 03'}</span>
                    </div>
                    <h3 className={`font-headline font-bold text-sm uppercase mb-2 ${s3Active || s3Done ? 'text-on-surface' : 'text-on-surface-variant'}`}>Synthesis & Mix</h3>
                    <p className={`font-body text-xs leading-relaxed ${s3Active || s3Done ? 'text-on-surface-variant' : 'text-outline'}`}>Tree-of-Thought audio generation, evaluation, and final mix.</p>
                    {s3Active && (
                      <div className="mt-4 h-[2px] w-full bg-surface-container-highest">
                        <motion.div className="h-full bg-primary" animate={{ width: ['0%', '50%'] }} transition={{ duration: 2, repeat: Infinity, repeatType: 'reverse' }} />
                      </div>
                    )}
                  </div>
                </>
              );
            })()}
          </section>

          <section className="bg-surface-container-low rounded-xl p-8 aspect-video flex flex-col justify-center relative group overflow-hidden">
            <div className="absolute inset-0 opacity-10 pointer-events-none bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')]"></div>
            <div className="flex items-end justify-between gap-1 h-32 px-4">
              {[12, 16, 24, 32, 28, 20, 24, 12, 8, 14, 20, 16, 10, 12, 8, 15, 22, 18, 25, 30, 14, 10, 18, 24, 20, 16, 12, 8].map((h, i) => (
                <motion.div
                  key={i}
                  className={`w-1 rounded-t-sm ${i < 10 ? 'bg-primary' : 'bg-secondary-fixed-dim'}`}
                  animate={{ height: [`${h * 2}px`, `${h * 3}px`, `${h * 2}px`] }}
                  transition={{ duration: 1 + Math.random(), repeat: Infinity }}
                />
              ))}
            </div>
            <div className="mt-12 flex justify-between items-center border-t border-outline-variant/20 pt-6">
              <div className="flex gap-8">
                <div>
                  <span className="block font-label text-[10px] uppercase text-outline tracking-widest mb-1">Current Frequency</span>
                  <span className="font-mono text-sm text-on-surface">{isPending ? 'Standby' : isCompleted ? 'Stable' : config?.outputSampleRate || '48 kHz'}</span>
                </div>
                <div>
                  <span className="block font-label text-[10px] uppercase text-outline tracking-widest mb-1">Refinement</span>
                  <span className="font-mono text-sm text-on-surface">
                    {isPending ? 'Queued' : config?.qualityMode === 'fast' ? 'Low' : config?.qualityMode === 'high-quality' ? 'High' : 'Balanced'}
                  </span>
                </div>
              </div>
              <div className="bg-surface-container-highest border border-outline-variant/15 text-on-surface px-4 py-2 rounded text-xs font-bold uppercase tracking-widest">
                {activeGeneration?.id || 'Awaiting Job'}
              </div>
            </div>
          </section>
        </div>

        <aside className="lg:col-span-4 space-y-6">
          <div className="bg-surface-container p-6 rounded-lg">
            <h2 className="font-headline font-bold text-xs uppercase tracking-widest text-on-surface mb-6 border-b border-outline-variant/20 pb-2">Job Configuration</h2>
            <dl className="space-y-4">
              <div className="flex justify-between gap-4">
                <dt className="font-label text-[10px] text-outline uppercase">Input Source</dt>
                <dd className="font-body text-xs text-on-surface font-medium text-right">{inputSource}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="font-label text-[10px] text-outline uppercase">Execution Mode</dt>
                <dd className="font-body text-xs text-on-surface font-medium text-right">{runtimeModeLabel}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="font-label text-[10px] text-outline uppercase">Render Format</dt>
                <dd className="font-body text-xs text-on-surface font-medium text-right">
                  {config ? `${config.outputSampleRate} / ${config.bitDepth}` : '48 kHz / 24-bit'}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="font-label text-[10px] text-outline uppercase">Target Model</dt>
                <dd className="font-body text-xs text-on-surface font-medium text-right">{activeGeneration?.payload.languageModel || 'Kimi-K2.5'}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="font-label text-[10px] text-outline uppercase">Output Profile</dt>
                <dd className="font-body text-xs text-on-surface font-medium text-right">
                  {activeGeneration ? `${activeGeneration.payload.outputClass} / ${config?.channels || 'Stereo'} / ${config?.exportFormat || 'WAV'}` : 'WAV'}
                </dd>
              </div>
            </dl>
          </div>

          <div className="bg-surface-container-lowest rounded-lg p-6 border border-outline-variant/10 h-80 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-headline font-bold text-xs uppercase tracking-widest text-primary">System Logs</h2>
              <span className="w-2 h-2 rounded-full bg-tertiary"></span>
            </div>
            <div className="flex-grow overflow-y-auto font-mono text-[10px] space-y-2 text-on-surface-variant leading-relaxed no-scrollbar">
              <p><span className="text-outline">[LIVE]</span> JOB {activeGeneration?.id || 'PENDING'} REGISTERED.</p>
              <p><span className="text-outline">[LIVE]</span> PROMPT PROFILE: {promptPreview.slice(0, 48).toUpperCase()}{promptPreview.length > 48 ? '...' : ''}</p>
              <p><span className="text-outline">[LIVE]</span> OUTPUT CLASS: {(activeGeneration?.payload.outputClass || 'Unknown').toUpperCase()}.</p>
              <p className="text-primary"><span className="text-outline">[LIVE]</span> CURRENT STATUS: {(status || 'pending').toUpperCase()}.</p>
              <p><span className="text-outline">[LIVE]</span> QUALITY MODE: {(config?.qualityMode || 'balanced').toUpperCase()}.</p>
              <p><span className="text-outline">[LIVE]</span> ACOUSTIC STYLE: {(activeGeneration?.payload.acousticStyle || 'Default').toUpperCase()}.</p>
              <p><span className="text-outline">[LIVE]</span> TARGET DURATION: {activeGeneration?.payload.duration || 0}S.</p>
              <p><span className="text-outline">[LIVE]</span> LANGUAGE MODEL: {(activeGeneration?.payload.languageModel || 'Default').toUpperCase()}.</p>
              <p><span className="text-outline">[LIVE]</span> OUTPUT SAMPLE RATE: {(config?.outputSampleRate || '48 kHz').toUpperCase()}.</p>
              <p><span className="text-outline">[LIVE]</span> BIT DEPTH / CHANNELS: {(config?.bitDepth || '24 bit').toUpperCase()} / {(config?.channels || 'Stereo').toUpperCase()}.</p>
              <p><span className="text-outline">[LIVE]</span> VISUAL CONDITIONING: {(activeGeneration?.payload.videoRef || activeGeneration?.payload.imageRef) ? 'ATTACHED' : 'NONE'}.</p>
              <p className={activeGeneration?.runtimeMode === 'demo' ? 'text-secondary-fixed-dim' : ''}><span className="text-outline">[LIVE]</span> EXECUTION MODE: {runtimeModeLabel.toUpperCase()}.</p>
              <p className={isProcessing ? 'animate-pulse' : ''}><span className="text-outline">[LIVE]</span> PIPELINE HEARTBEAT ACTIVE.</p>
              <div className="pt-2 border-t border-outline-variant/10 mt-2">
                <div className="flex items-center gap-2">
                  <span className="w-1 h-3 bg-primary animate-bounce"></span>
                  <span className="text-primary italic">{isCompleted ? 'Artifact ready in History.' : statusMessage}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-surface-container-high p-4 rounded-lg flex items-center gap-4">
            <div className="w-10 h-10 rounded bg-primary/10 flex items-center justify-center">
              <Cpu size={20} className="text-primary" />
            </div>
            <div className="flex-grow">
              <span className="block font-label text-[10px] uppercase text-outline">Resource Load</span>
              <div className="flex items-center gap-2">
                <span className="font-headline font-bold text-lg">{progress}%</span>
                <div className="h-1 flex-grow bg-surface-container-highest rounded-full overflow-hidden">
                  <div className="h-full bg-tertiary" style={{ width: `${progress}%` }}></div>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

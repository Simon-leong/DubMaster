/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { PlusCircle, Waves, Music2, Download } from 'lucide-react';
import { Artifact, GenerationConfig, GenerationDraft } from '../types';
import { UploadSection } from './UploadSection';
import { OutputConfigSection } from './OutputConfigSection';
import { JobSummarySection } from './JobSummarySection';

interface WorkspaceProps {
  onGenerate: (request: GenerationDraft) => Promise<void>;
  artifacts: Artifact[];
  onNewGeneration: () => void;
  onViewHistory: () => void;
  generationConfig: GenerationConfig;
  onGenerationConfigChange: (config: GenerationConfig) => void;
}

export function Workspace({
  onGenerate,
  artifacts,
  onNewGeneration,
  onViewHistory,
  generationConfig,
  onGenerationConfigChange,
}: WorkspaceProps) {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [referenceAudioFile, setReferenceAudioFile] = useState<File | null>(null);
  const [speechTargetText, setSpeechTargetText] = useState("");
  const [prompt, setPrompt] = useState("");
  const [outputClasses, setOutputClasses] = useState<string[]>(["Sound Effects"]);
  const [duration, setDuration] = useState(12);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const speechSelected = outputClasses.includes("Speech");

  const handleGenerateClick = async () => {
    setIsSubmitting(true);
    try {
      const request: GenerationDraft = {
        prompt,
        outputClass: outputClasses.join(','),
        languageModel: '',
        acousticStyle: '',
        duration,
        videoFile,
        imageFile,
        referenceAudioFile: speechSelected ? referenceAudioFile : null,
        speechTargetText: speechSelected ? speechTargetText : '',
        config: generationConfig,
        requestedAt: new Date().toISOString(),
      };

      await onGenerate(request);
    } catch (error) {
      console.error('Workspace submission failed:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-8 md:p-12 max-w-[1600px] mx-auto w-full space-y-12">
      <header className="flex flex-col gap-2 border-l-4 border-primary pl-6">
        <h1 className="text-4xl md:text-5xl font-headline font-extrabold tracking-tight text-on-surface uppercase">Workspace</h1>
        <p className="text-on-surface-variant font-label text-sm tracking-widest uppercase">Multi-Agent Audio Generation Pipeline</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left: Source + Config */}
        <section className="lg:col-span-8 flex flex-col gap-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <UploadSection
              videoFile={videoFile}
              setVideoFile={setVideoFile}
              imageFile={imageFile}
              setImageFile={setImageFile}
              prompt={prompt}
              setPrompt={setPrompt}
              showReferenceAudio={speechSelected}
              referenceAudioFile={referenceAudioFile}
              setReferenceAudioFile={setReferenceAudioFile}
              speechTargetText={speechTargetText}
              setSpeechTargetText={setSpeechTargetText}
            />
            <OutputConfigSection
              outputClasses={outputClasses}
              setOutputClasses={setOutputClasses}
              duration={duration}
              setDuration={setDuration}
            />
          </div>
        </section>

        {/* Right: Summary + Generate */}
        <section className="lg:col-span-4 flex flex-col gap-6">
          <JobSummarySection
            prompt={prompt}
            videoFile={videoFile}
            imageFile={imageFile}
            outputClass={outputClasses.join(', ')}
            onGenerate={handleGenerateClick}
            isProcessing={isSubmitting}
          />
        </section>
      </div>

      {/* Recent Artifacts */}
      <section className="flex flex-col gap-6 mt-4">
        <div className="flex justify-between items-end border-b border-outline-variant/20 pb-4">
          <h2 className="font-headline text-xl font-bold text-on-surface uppercase tracking-tight">Recent Artifacts</h2>
          <button onClick={onViewHistory} className="text-[10px] uppercase font-bold text-primary tracking-widest hover:underline">View All History</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {artifacts.length === 0 && (
            <div className="md:col-span-2 lg:col-span-3 bg-surface-container-low rounded-xl border border-outline-variant/10 p-8 text-center space-y-3">
              <p className="text-sm font-bold uppercase tracking-widest text-on-surface">No Local History Yet</p>
              <p className="text-sm text-on-surface-variant max-w-2xl mx-auto">
                Completed generations will appear here and stay on this browser/device using local storage.
              </p>
            </div>
          )}

          {artifacts.map((art) => (
            <div key={art.id} className="bg-surface-container-low group hover:bg-surface-container-high p-4 rounded-lg flex flex-col gap-4 transition-all border border-transparent hover:border-outline-variant/20">
              <div className="flex justify-between items-start">
                <div className="flex gap-3">
                  <div className="w-10 h-10 bg-surface-container-highest rounded flex items-center justify-center text-primary">
                    {art.type === 'Song' ? <Music2 size={20} className="text-tertiary" /> : <Waves size={20} />}
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-on-surface uppercase tracking-tighter">{art.title}</h3>
                    <p className="text-[9px] text-outline uppercase">{art.type} // {art.duration}</p>
                    <p className="text-[10px] text-outline">{new Date(art.createdAt).toLocaleString()}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {art.runtimeMode === 'demo' && (
                    <span className="text-[9px] uppercase tracking-widest text-tertiary font-bold">Demo</span>
                  )}
                  <button className="text-outline hover:text-primary transition-colors">
                  <Download size={16} />
                  </button>
                </div>
              </div>
              <div className="h-12 w-full flex items-end gap-[1px]">
                {art.heights.length > 0 ? (
                  art.heights.map((h, i) => (
                    <div key={i} className="flex-grow bg-primary/40 rounded-t-sm" style={{ height: `${h * 4}px` }}></div>
                  ))
                ) : (
                  <div className="w-full h-[1px] bg-outline-variant/30 relative mb-4">
                    <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[60%] h-[3px] bg-tertiary"></div>
                  </div>
                )}
              </div>
            </div>
          ))}

          <div
            onClick={onNewGeneration}
            className="border-2 border-dashed border-outline-variant/20 rounded-lg flex flex-col items-center justify-center p-8 text-outline gap-2 cursor-pointer hover:bg-surface-container-low transition-colors"
          >
            <PlusCircle size={24} />
            <span className="text-[10px] uppercase font-bold tracking-widest">New Generation</span>
          </div>
        </div>
      </section>
    </div>
  );
}

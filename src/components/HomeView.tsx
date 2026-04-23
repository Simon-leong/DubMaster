/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useRef, useState } from 'react';
import { ArrowRight, Clapperboard, Image as ImageIcon, Mic2, Music4, Sparkles, Play, Pause, Clock, Volume2 } from 'lucide-react';

interface HomeViewProps {
  onStartCreating: () => void;
  onOpenHistory: () => void;
}

const demos = [
  {
    title: 'Atmosphere Demo',
    description: 'Ambient soundscape generation — environmental layers, atmospheric pads, and natural textures driven by multimodal input.',
    outputType: 'Atmosphere',
    icon: ImageIcon,
    source: 'Video + Text Prompt',
    video: '/demos/atmosphere.mp4',
    color: 'bg-tertiary-container text-on-tertiary-container',
  },
  {
    title: 'Sound Effects Demo',
    description: 'Precisely timed foley and sound effects synchronized to video events — impacts, movements, and environmental cues.',
    outputType: 'Sound Effects',
    icon: Clapperboard,
    source: 'Video Upload',
    video: '/demos/sound_effect.mp4',
    color: 'bg-primary-container text-on-primary-container',
  },
  {
    title: 'Speech Demo',
    description: 'Expressive speech synthesis with natural prosody, controlled pacing, and studio-quality clarity from text input.',
    outputType: 'Speech',
    icon: Mic2,
    source: 'Text Prompt',
    video: '/demos/speech.mp4',
    color: 'bg-secondary-container text-on-secondary-container',
  },
  {
    title: 'Music Demo',
    description: 'AI-composed musical score — ambient pads, melodic lines, and rhythmic beds tailored to scene context and mood.',
    outputType: 'Background Music',
    icon: Music4,
    source: 'Image + Text Prompt',
    video: '/demos/music.mp4',
    color: 'bg-primary-container text-on-primary-container',
  },
];

const pipelineSteps = [
  { step: '01', title: 'Upload or Describe', detail: 'Provide a video, image, or text prompt as your source material.' },
  { step: '02', title: 'Configure Output', detail: 'Select audio category (SFX / Speech / Background Music / Song) and target duration.' },
  { step: '03', title: 'AI Planning', detail: 'The LLM decomposes your input into a structured audio event plan.' },
  { step: '04', title: 'Synthesize & Mix', detail: 'Domain experts generate each event via Tree-of-Thought refinement, then mix.' },
];

function DemoCard({ demo, Icon }: { demo: typeof demos[number]; Icon: typeof demos[number]['icon'] }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      v.play();
      setPlaying(true);
    } else {
      v.pause();
      setPlaying(false);
    }
  };

  return (
    <article className="bg-white rounded-2xl border border-outline-variant/20 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      <div className="relative bg-black aspect-video">
        <video
          ref={videoRef}
          src={demo.video}
          className="w-full h-full object-contain"
          onEnded={() => setPlaying(false)}
          playsInline
        />
        <div className="absolute top-4 left-4 flex items-center gap-2">
          <div className={`w-7 h-7 rounded-lg ${demo.color} flex items-center justify-center`}>
            <Icon size={14} />
          </div>
          <span className="text-[10px] uppercase tracking-widest font-bold text-white/80 drop-shadow">{demo.outputType}</span>
        </div>
      </div>

      <div className="p-6 space-y-4">
        <div className="space-y-2">
          <h3 className="text-lg font-headline font-bold tracking-tight text-on-surface">{demo.title}</h3>
          <p className="text-sm leading-relaxed text-on-surface-variant">{demo.description}</p>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4 text-[10px] uppercase tracking-widest text-outline">
            <span className="flex items-center gap-1"><Volume2 size={10} /> {demo.source}</span>
          </div>
          <button
            onClick={togglePlay}
            className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary cursor-pointer hover:shadow-md hover:shadow-primary/25 transition-all"
          >
            {playing ? <Pause size={14} /> : <Play size={14} className="ml-0.5" />}
          </button>
        </div>
      </div>
    </article>
  );
}

export function HomeView({ onStartCreating, onOpenHistory }: HomeViewProps) {
  const showcaseRef = useRef<HTMLElement | null>(null);

  return (
    <div className="p-8 md:p-12 max-w-[1600px] mx-auto w-full space-y-20">
      {/* Hero */}
      <section className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-stretch">
        <div className="xl:col-span-7 bg-white border border-outline-variant/30 rounded-3xl p-8 md:p-12 shadow-lg relative overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(103,80,164,0.08),transparent_40%),radial-gradient(circle_at_bottom_left,rgba(125,82,96,0.06),transparent_35%)] pointer-events-none"></div>
          <div className="relative space-y-8">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary-container text-on-primary-container text-[10px] font-bold uppercase tracking-widest">
              <Sparkles size={12} /> AI Audio Generation Studio
            </div>
            <div className="space-y-5 max-w-3xl">
              <h1 className="text-5xl md:text-7xl font-headline font-extrabold uppercase tracking-tight text-on-surface leading-none">
                Shape sound from video, images, and text.
              </h1>
              <p className="text-base md:text-lg leading-relaxed text-on-surface-variant max-w-2xl">
                DubMaster is a multi-agent AI studio that generates speech, music, sound effects, and
                atmospheric layers. Upload a video, drop in an image, or write a prompt to build polished
                audio in one workspace.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-4">
              <button
                onClick={onStartCreating}
                className="bg-primary text-on-primary px-8 py-4 rounded-xl font-bold uppercase tracking-widest text-xs hover:shadow-lg hover:shadow-primary/20 transition-all flex items-center justify-center gap-2"
              >
                Start Creating <ArrowRight size={16} />
              </button>
              <button
                onClick={() => showcaseRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                className="bg-surface-container-high text-on-surface px-8 py-4 rounded-xl font-bold uppercase tracking-widest text-xs hover:bg-surface-container-highest transition-all"
              >
                View Demos
              </button>
            </div>
          </div>
        </div>

        <div className="xl:col-span-5 grid grid-cols-1 gap-6">
          <div className="bg-white rounded-2xl p-6 border border-outline-variant/20 shadow-sm">
            <p className="text-[10px] uppercase tracking-widest text-outline font-bold mb-4">How It Works</p>
            <div className="space-y-3">
              {pipelineSteps.map((s) => (
                <div key={s.step} className="flex gap-4 items-start bg-surface-container-low rounded-xl px-4 py-3.5">
                  <span className="text-primary font-mono text-xs font-bold mt-0.5">{s.step}</span>
                  <div>
                    <p className="text-sm font-semibold text-on-surface">{s.title}</p>
                    <p className="text-xs text-on-surface-variant mt-0.5 leading-relaxed">{s.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 border border-outline-variant/20 shadow-sm">
            <p className="text-[10px] uppercase tracking-widest text-outline font-bold mb-3">Quick Start</p>
            <p className="text-sm leading-relaxed text-on-surface-variant">
              No account required. Open the workspace, configure your generation,
              and export the result. All history stays on this browser.
            </p>
            <button
              onClick={onOpenHistory}
              className="mt-4 text-[10px] uppercase tracking-widest font-bold text-primary hover:underline"
            >
              Open Local History
            </button>
          </div>
        </div>
      </section>

      {/* Demo Showcase */}
      <section ref={showcaseRef} className="space-y-8">
        <div className="border-b border-outline-variant/30 pb-4">
          <h2 className="font-headline text-2xl md:text-3xl font-bold uppercase tracking-tight text-on-surface">
            Featured Demos
          </h2>
          <p className="text-sm text-on-surface-variant mt-2">
            Sample outputs generated by DubMaster from different input types and output categories.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {demos.map((demo) => {
            const Icon = demo.icon;

            return (
              <DemoCard key={demo.title} demo={demo} Icon={Icon} />
            );
          })}
        </div>

        {/* CTA */}
        <div className="flex justify-center pt-4">
          <button
            onClick={onStartCreating}
            className="bg-primary-container text-on-primary-container px-10 py-4 rounded-xl font-bold uppercase tracking-widest text-xs hover:shadow-lg hover:shadow-primary/15 transition-all flex items-center gap-2"
          >
            Try It Yourself <ArrowRight size={16} />
          </button>
        </div>
      </section>
    </div>
  );
}

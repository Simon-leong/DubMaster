/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { BookOpenText, Cable, PlaySquare, ServerCog } from 'lucide-react';

const architectureItems = [
  ['Access Model', 'The public website version does not require login, registration, account profiles, or authentication to create audio.'],
  ['Frontend', 'Vite + React + TypeScript application in src/ with componentized home, workspace, processing, history, and docs views.'],
  ['Backend', 'FastAPI service in backend/app/ that handles uploads, generation creation, polling, history reads, detail reads, and export.'],
  ['History Storage', 'History is currently stored with a browser-local storage service abstraction, so it persists on one device now and can be replaced by backend persistence later.'],
  ['Generation Engine', 'Current generation behavior is intentionally mock/in-memory so the product flow stays testable while the real algorithm agent layer is built.'],
  ['API Wiring', 'The frontend uses VITE_API_BASE_URL to call the local backend for upload, generation, polling, and export.'],
] as const;

const runSteps = [
  'Open one terminal in DubMaster/ and run npm run dev:backend',
  'Open a second terminal in DubMaster/ and run npm run dev:frontend',
  'Visit http://localhost:3000 in the browser',
  'Generate, inspect history, and export a WAV to verify the full stack flow',
];

const endpointItems = [
  'POST /upload/video',
  'POST /upload/image',
  'POST /generations',
  'GET /generations',
  'GET /generations/{id}',
  'GET /generations/{id}/status',
  'POST /generations/{id}/export',
];

export function DocsView() {
  return (
    <div className="p-8 md:p-12 max-w-[1600px] mx-auto w-full space-y-12">
      <header className="flex flex-col gap-2 border-l-4 border-primary pl-6">
        <h1 className="text-4xl md:text-5xl font-headline font-extrabold tracking-tight text-on-surface uppercase">Docs</h1>
        <p className="text-on-surface-variant font-label text-sm tracking-widest uppercase">
          Project Notes // Local Runtime Guide // API Reference
        </p>
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-8">
        <section className="xl:col-span-7 space-y-6">
          <div className="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-8 shadow-2xl">
            <div className="flex items-center gap-3 mb-6">
              <BookOpenText size={20} className="text-primary" />
              <h2 className="font-headline text-2xl font-bold text-on-surface">System Architecture</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {architectureItems.map(([title, description]) => (
                <div key={title} className="bg-surface-container-low rounded-xl p-5 border border-outline-variant/10">
                  <h3 className="font-label text-xs font-bold uppercase tracking-widest text-primary mb-3">{title}</h3>
                  <p className="text-sm leading-relaxed text-on-surface-variant">{description}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-8 shadow-2xl">
            <div className="flex items-center gap-3 mb-6">
              <PlaySquare size={20} className="text-primary" />
              <h2 className="font-headline text-2xl font-bold text-on-surface">Local Run Checklist</h2>
            </div>
            <ol className="space-y-4">
              {runSteps.map((step, index) => (
                <li key={step} className="flex gap-4 items-start">
                  <span className="w-8 h-8 rounded-full bg-primary/15 text-primary flex items-center justify-center font-bold text-sm">{index + 1}</span>
                  <p className="text-sm leading-relaxed text-on-surface-variant pt-1">{step}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <aside className="xl:col-span-5 space-y-6">
          <div className="bg-surface-container p-6 rounded-xl space-y-5">
            <div className="flex items-center gap-3">
              <Cable size={18} className="text-primary" />
              <h2 className="font-headline text-lg font-bold text-on-surface">API Surface</h2>
            </div>
            <div className="space-y-3">
              {endpointItems.map((endpoint) => (
                <div key={endpoint} className="bg-surface-container-lowest rounded-lg px-4 py-3 font-mono text-xs text-on-surface border border-outline-variant/10">
                  {endpoint}
                </div>
              ))}
            </div>
          </div>

          <div className="bg-surface-container p-6 rounded-xl space-y-5">
            <div className="flex items-center gap-3">
              <ServerCog size={18} className="text-primary" />
              <h2 className="font-headline text-lg font-bold text-on-surface">Current Status</h2>
            </div>
            <div className="space-y-4 text-sm text-on-surface-variant leading-relaxed">
              <p>The full local product loop is now runnable: upload, create generation, poll, save to history, inspect details, and export.</p>
              <p>History is persisted locally on the same browser/device rather than in an account or cloud profile for this version.</p>
              <p>The backend generation logic is still a clear mock service by design, which keeps the UI reliable while the paper-inspired multi-agent pipeline is implemented incrementally.</p>
              <p>The next safe expansion point is replacing the in-memory generation service and local history storage with a real orchestration layer and backend persistence while preserving the current UI contract.</p>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

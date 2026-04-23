/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  ActiveGeneration,
  AppNotice,
  Artifact,
  GenerationConfig,
  GenerationDraft,
  GenerationPayload,
  View,
} from './types';
import { TopNavBar } from './components/TopNavBar';
import { Footer } from './components/Footer';
import { Workspace } from './components/Workspace';
import { ProcessingView } from './components/ProcessingView';
import { HistoryView } from './components/HistoryView';
import { HomeView } from './components/HomeView';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AppNoticeBanner } from './components/AppNoticeBanner';
import {
  createGeneration,
  exportGeneration,
  pollGenerationStatus,
  uploadAudio,
  uploadImage,
  uploadVideo,
} from './services/api';
import {
  addHistoryItem,
  clearHistory,
  createHistoryItem,
  deleteHistoryItem,
  loadHistory,
  updateHistoryExportInfo,
} from './services/historyService';
import { loadGenerationSettings, saveGenerationSettings } from './services/settingsService';

function describeError(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === 'string' && error) {
    return error;
  }
  return 'Unknown error';
}

const NOTICE_TIMEOUT_MS = 15000;

export default function App() {
  const [view, setView] = useState<View>('home');
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [workspaceVersion, setWorkspaceVersion] = useState(0);
  const [activeGeneration, setActiveGeneration] = useState<ActiveGeneration | null>(null);
  const [generationConfig, setGenerationConfig] = useState<GenerationConfig>(() => loadGenerationSettings());
  const [notice, setNotice] = useState<AppNotice | null>(null);
  const [historyFocusId, setHistoryFocusId] = useState<string | null>(null);

  useEffect(() => {
    try {
      setArtifacts(loadHistory(generationConfig.keepHistory));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    saveGenerationSettings(generationConfig);
    setArtifacts(loadHistory(generationConfig.keepHistory));
  }, [generationConfig]);

  useEffect(() => {
    if (!notice) {
      return undefined;
    }

    const timeoutId = window.setTimeout(() => {
      setNotice((currentNotice) => (currentNotice?.id === notice.id ? null : currentNotice));
    }, NOTICE_TIMEOUT_MS);

    return () => window.clearTimeout(timeoutId);
  }, [notice]);

  const pushNotice = (tone: AppNotice['tone'], title: string, message: string) => {
    setNotice({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      tone,
      title,
      message,
    });
  };

  const handleGenerationConfigChange = (nextConfig: GenerationConfig) => {
    setGenerationConfig(nextConfig);
  };

  const buildPayloadFromDraft = (draft: GenerationDraft): GenerationPayload => ({
    prompt: draft.prompt,
    outputClass: draft.outputClass,
    languageModel: draft.languageModel,
    acousticStyle: draft.acousticStyle,
    duration: draft.duration,
    videoFileName: draft.videoFile?.name,
    imageFileName: draft.imageFile?.name,
    speechTargetText: draft.speechTargetText,
    requestedAt: draft.requestedAt,
    config: draft.config,
  });

  const persistCompletedArtifact = async (
    resultId: string,
    artifact: Artifact,
    payload: GenerationPayload,
    runtimeMode: ActiveGeneration['runtimeMode'],
  ) => {
    const savedHistory = addHistoryItem(
      runtimeMode === 'demo' ? artifact : createHistoryItem(artifact, payload, payload.config),
      payload.config.keepHistory,
    );

    setArtifacts(savedHistory);
    setActiveGeneration({
      id: resultId,
      status: 'completed',
      payload,
      runtimeMode,
      statusMessage: runtimeMode === 'demo' ? 'Demo result created locally.' : 'Generation complete.',
    });
    setHistoryFocusId(resultId);
    setView('history');

    if (payload.config.autoExportOnComplete) {
      try {
        pushNotice('info', 'Auto-export started', 'Preparing your latest result for download.');
        const exportResponse = await handleExport(resultId);
        const a = document.createElement('a');
        a.href = exportResponse.url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch (autoExportError) {
        console.error('Auto export failed:', autoExportError);
        pushNotice('warning', 'Export delayed', 'The result was created, but automatic export could not be opened right away.');
      }
    }
  };

  const runLiveGeneration = async (payload: GenerationPayload) => {
    pushNotice('info', 'Submitting generation job', 'Sending your current DubMaster configuration to the live backend.');
    const response = await createGeneration(payload);
    setActiveGeneration({
      id: response.id,
      status: response.status,
      payload,
      runtimeMode: 'live',
      statusMessage: 'Backend connected. Running live generation.',
    });

    return pollGenerationStatus(response.id, (update) => {
      const stageMessages: Record<string, string> = {
        uploading: 'Preparing source inputs...',
        planning: 'Stage 1: Analyzing inputs and creating audio event plan...',
        assigning: 'Stage 2: Routing events to domain experts (SFX, Speech, Music, Song)...',
        synthesizing: 'Stage 3: Generating audio with Tree-of-Thought refinement...',
        mixing: 'Compositing and mixing audio tracks...',
        done: 'Generation complete.',
      };
      const stageMsg = update.stage ? stageMessages[update.stage] || update.stageDetail || '' : '';
      const detailMsg = update.stageDetail || stageMsg;

      setActiveGeneration({
        id: update.id,
        status: update.status,
        payload,
        runtimeMode: 'live',
        stage: update.stage,
        stageDetail: update.stageDetail,
        statusMessage: detailMsg || (update.status === 'processing'
          ? 'Live generation in progress.'
          : update.status === 'completed'
            ? 'Finalizing backend result.'
            : 'Waiting for backend worker.'),
      });
    });
  };

  const handleGenerate = async (draft: GenerationDraft) => {
    if (!draft.prompt.trim() && !draft.videoFile && !draft.imageFile) {
      pushNotice('warning', 'Add an input to begin', 'Upload a video or image, or enter a text prompt before starting a generation.');
      setView('workspace');
      return;
    }

    const speechSelected = draft.outputClass.split(',').map((c) => c.trim()).includes('Speech');
    if (speechSelected && !draft.referenceAudioFile) {
      pushNotice('warning', 'Reference voice required', 'Speech output requires a reference audio clip for voice cloning. Upload a short WAV/MP3 sample.');
      setView('workspace');
      return;
    }
    if (speechSelected && !(draft.speechTargetText || '').trim()) {
      pushNotice('warning', 'Target utterance required', 'Enter the exact sentence you want the cloned voice to speak in the "What to Say" box.');
      setView('workspace');
      return;
    }

    let payload = buildPayloadFromDraft(draft);

    setView('processing');
    setActiveGeneration({
      id: 'preparing-inputs',
      status: 'pending',
      payload,
      runtimeMode: 'live',
      statusMessage: 'Preparing source inputs for generation.',
    });

    try {
      if (draft.videoFile) {
        pushNotice('info', 'Uploading source video', 'Preparing visual timing and atmosphere cues for generation.');
        const videoUpload = await uploadVideo(draft.videoFile);
        payload = { ...payload, videoRef: videoUpload.ref };
      }

      if (draft.imageFile) {
        pushNotice('info', 'Uploading source image', 'Preparing visual scene cues for generation.');
        const imageUpload = await uploadImage(draft.imageFile);
        payload = { ...payload, imageRef: imageUpload.ref };
      }

      if (draft.referenceAudioFile) {
        pushNotice('info', 'Uploading reference voice', 'Preparing voice cloning reference.');
        const audioUpload = await uploadAudio(draft.referenceAudioFile);
        payload = { ...payload, referenceAudioRef: audioUpload.ref };
      }

      const result = await runLiveGeneration(payload);

      if (result.status === 'completed' && result.artifact) {
        await persistCompletedArtifact(result.id, result.artifact, payload, 'live');
        pushNotice('success', 'Audio generated and saved to History', 'Your latest artifact is now selected in History and ready to inspect.');
        return;
      }

      if (result.status === 'failed') {
        const detail = result.stageDetail || 'Backend reported the generation failed without a detail message.';
        pushNotice('error', 'Generation failed', detail);
      } else {
        pushNotice('error', 'Generation did not complete', `Backend returned status "${result.status}" without a completed artifact.`);
      }
      setActiveGeneration(null);
      setView('workspace');
    } catch (error) {
      console.error('Generation flow failed:', error);
      pushNotice('error', 'Generation failed', describeError(error));
      setActiveGeneration(null);
      setView('workspace');
    }
  };

  const handleNewGeneration = () => {
    setWorkspaceVersion((current) => current + 1);
    setActiveGeneration(null);
    setHistoryFocusId(null);
    setView('workspace');
  };

  const handleDeleteHistoryItem = (id: string) => {
    setArtifacts(deleteHistoryItem(id, generationConfig.keepHistory));
    pushNotice('info', 'History updated', 'The selected artifact was removed from local history on this browser.');
  };

  const handleClearHistory = () => {
    setArtifacts(clearHistory());
    pushNotice('info', 'Local history cleared', 'All locally saved DubMaster artifacts were removed from this browser.');
  };

  const handleExport = async (id: string) => {
    const artifact = artifacts.find((item) => item.id === id);
    const exportConfig = artifact?.generationConfig || generationConfig;

    try {
      const response = await exportGeneration(id, exportConfig);
      setArtifacts(updateHistoryExportInfo(id, {
        url: response.url,
        lastExportedAt: new Date().toISOString(),
        format: exportConfig.exportFormat,
      }, generationConfig.keepHistory));
      return response;
    } catch (error) {
      console.error('Export request failed:', error);
      pushNotice('error', 'Export failed', describeError(error));
      throw error;
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-primary font-headline text-xl animate-pulse uppercase tracking-widest">Initializing Synthesis Engine...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-on-surface font-body selection:bg-primary/30 flex flex-col">
      <TopNavBar
        currentView={view}
        setView={setView}
        generationConfig={generationConfig}
        onGenerationConfigChange={handleGenerationConfigChange}
      />

      {notice && (
        <AppNoticeBanner
          notice={notice}
          onDismiss={() => setNotice(null)}
        />
      )}

      <ErrorBoundary>
        <main className="flex-grow flex flex-col">
          <AnimatePresence mode="wait">
            {view === 'home' && (
              <motion.div
                key="home"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.3 }}
                className="flex-grow flex flex-col"
              >
                <HomeView
                  onStartCreating={() => setView('workspace')}
                  onOpenHistory={() => {
                    setHistoryFocusId(null);
                    setView('history');
                  }}
                />
              </motion.div>
            )}
            {view === 'workspace' && (
              <motion.div
                key={`workspace-${workspaceVersion}`}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.3 }}
                className="flex-grow flex flex-col"
              >
                <Workspace
                  onGenerate={handleGenerate}
                  artifacts={artifacts}
                  onNewGeneration={handleNewGeneration}
                  onViewHistory={() => {
                    setHistoryFocusId(null);
                    setView('history');
                  }}
                  generationConfig={generationConfig}
                  onGenerationConfigChange={handleGenerationConfigChange}
                />
              </motion.div>
            )}
            {view === 'processing' && (
              <motion.div
                key="processing"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 1.05 }}
                transition={{ duration: 0.3 }}
                className="flex-grow flex flex-col"
              >
                <ProcessingView activeGeneration={activeGeneration} />
              </motion.div>
            )}
            {view === 'history' && (
              <motion.div
                key="history"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.3 }}
                className="flex-grow flex flex-col"
              >
                <HistoryView
                  artifacts={artifacts}
                  onOpenWorkspace={() => setView('workspace')}
                  onDeleteItem={handleDeleteHistoryItem}
                  onClearAll={handleClearHistory}
                  onExport={handleExport}
                  onNotify={pushNotice}
                  focusedArtifactId={historyFocusId}
                  onFocusHandled={() => setHistoryFocusId(null)}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </main>
      </ErrorBoundary>

      <Footer />
    </div>
  );
}

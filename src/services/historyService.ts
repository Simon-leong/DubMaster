import {
  Artifact,
  ExportInfo,
  GenerationPayload,
  GenerationConfig,
  KeepHistoryPolicy,
  SourceType,
} from '../types';

const HISTORY_STORAGE_KEY = 'dubmaster.history.v1';

function isBrowser() {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function sortNewestFirst(items: Artifact[]) {
  return [...items].sort((left, right) => {
    return new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime();
  });
}

function getHistoryCutoff(policy: KeepHistoryPolicy): number | null {
  const now = Date.now();

  switch (policy) {
    case '7-days':
      return now - 7 * 24 * 60 * 60 * 1000;
    case '30-days':
      return now - 30 * 24 * 60 * 60 * 1000;
    case 'forever':
    default:
      return null;
  }
}

function applyHistoryPolicy(items: Artifact[], policy: KeepHistoryPolicy) {
  const cutoff = getHistoryCutoff(policy);
  if (cutoff === null) {
    return items;
  }

  return items.filter((item) => new Date(item.createdAt).getTime() >= cutoff);
}

function getSourceType(payload: GenerationPayload): SourceType {
  if ((payload.videoRef || payload.videoFileName) && (payload.imageRef || payload.imageFileName)) {
    return 'video+image';
  }
  if (payload.videoRef || payload.videoFileName) {
    return 'video';
  }
  if (payload.imageRef || payload.imageFileName) {
    return 'image';
  }
  return 'text';
}

function normalizeArtifact(item: Partial<Artifact>): Artifact | null {
  if (!item.id || !item.title || !item.type || !item.duration || !Array.isArray(item.heights)) {
    return null;
  }

  const requestedAt = item.inputSnapshot?.requestedAt || item.createdAt || new Date(0).toISOString();

  return {
    id: item.id,
    title: item.title,
    type: item.type,
    duration: item.duration,
    heights: item.heights,
    createdAt: item.createdAt || new Date(0).toISOString(),
    prompt: item.prompt || '',
    sourceType: item.sourceType || 'text',
    previewMetadata: {
      barCount: item.previewMetadata?.barCount ?? item.heights.length,
      hasWaveform: item.previewMetadata?.hasWaveform ?? item.heights.length > 0,
      outputClass: item.previewMetadata?.outputClass || item.type,
      languageModel: item.previewMetadata?.languageModel || 'Unknown',
      acousticStyle: item.previewMetadata?.acousticStyle || 'Unknown',
      hasVisualConditioning: item.previewMetadata?.hasVisualConditioning ?? false,
      qualityMode: item.previewMetadata?.qualityMode || 'balanced',
    },
    generationConfig: item.generationConfig || {
      qualityMode: item.previewMetadata?.qualityMode || 'balanced',
      outputSampleRate: '48 kHz',
      bitDepth: '24 bit',
      channels: 'Stereo',
      exportFormat: item.exportInfo?.format || 'WAV',
      keepHistory: 'forever',
      autoExportOnComplete: false,
    },
    runtimeMode: item.runtimeMode || 'live',
    inputSnapshot: {
      videoFileName: item.inputSnapshot?.videoFileName,
      imageFileName: item.inputSnapshot?.imageFileName,
      requestedAt,
    },
    exportInfo: item.exportInfo,
  };
}

function persist(items: Artifact[], keepHistory: KeepHistoryPolicy) {
  if (!isBrowser()) {
    return items;
  }

  const sorted = sortNewestFirst(applyHistoryPolicy(items, keepHistory));
  window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(sorted));
  return sorted;
}

export function loadHistory(keepHistory: KeepHistoryPolicy): Artifact[] {
  if (!isBrowser()) {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }

    const items = sortNewestFirst(applyHistoryPolicy(
      parsed
        .map((item) => normalizeArtifact(item))
        .filter((item): item is Artifact => item !== null),
      keepHistory,
    ));
    return persist(items, keepHistory);
  } catch (error) {
    console.error('Failed to parse local history:', error);
    return [];
  }
}

export function addHistoryItem(item: Artifact, keepHistory: KeepHistoryPolicy): Artifact[] {
  const items = loadHistory(keepHistory).filter((existing) => existing.id !== item.id);
  items.unshift(item);
  return persist(items, keepHistory);
}

export function deleteHistoryItem(id: string, keepHistory: KeepHistoryPolicy): Artifact[] {
  return persist(loadHistory(keepHistory).filter((item) => item.id !== id), keepHistory);
}

export function clearHistory(): Artifact[] {
  if (isBrowser()) {
    window.localStorage.removeItem(HISTORY_STORAGE_KEY);
  }
  return [];
}

export function updateHistoryExportInfo(id: string, exportInfo: ExportInfo, keepHistory: KeepHistoryPolicy): Artifact[] {
  const items = loadHistory(keepHistory).map((item) => {
    if (item.id !== id) {
      return item;
    }

    return {
      ...item,
      exportInfo: {
        ...item.exportInfo,
        ...exportInfo,
      },
    };
  });

  return persist(items, keepHistory);
}

export function createHistoryItem(
  artifact: Pick<Artifact, 'id' | 'title' | 'type' | 'duration' | 'heights'>,
  payload: GenerationPayload,
  config: GenerationConfig,
): Artifact {
  const requestedAt = payload.requestedAt || new Date().toISOString();

  return {
    id: artifact.id,
    title: artifact.title,
    type: artifact.type,
    duration: artifact.duration,
    heights: artifact.heights,
    createdAt: requestedAt,
    prompt: payload.prompt,
    sourceType: getSourceType(payload),
    previewMetadata: {
      barCount: artifact.heights.length,
      hasWaveform: artifact.heights.length > 0,
      outputClass: payload.outputClass,
      languageModel: payload.languageModel,
      acousticStyle: payload.acousticStyle,
      hasVisualConditioning: Boolean(payload.videoRef || payload.imageRef),
      qualityMode: config.qualityMode,
    },
    generationConfig: { ...config },
    runtimeMode: 'live',
    inputSnapshot: {
      videoFileName: payload.videoFileName,
      imageFileName: payload.imageFileName,
      requestedAt,
    },
  };
}

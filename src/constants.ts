/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  Artifact,
  BitDepth,
  ChannelMode,
  ExportFormat,
  GenerationConfig,
  KeepHistoryPolicy,
  OutputSampleRate,
  QualityMode,
} from './types';

export const QUALITY_MODE_OPTIONS: QualityMode[] = ['fast', 'balanced', 'high-quality'];
export const OUTPUT_SAMPLE_RATE_OPTIONS: OutputSampleRate[] = ['44.1 kHz', '48 kHz', '96 kHz'];
export const BIT_DEPTH_OPTIONS: BitDepth[] = ['16 bit', '24 bit', '32 bit'];
export const CHANNEL_OPTIONS: ChannelMode[] = ['Mono', 'Stereo', '5.1 Surround'];
export const EXPORT_FORMAT_OPTIONS: ExportFormat[] = ['WAV', 'FLAC', 'MP3'];
export const KEEP_HISTORY_OPTIONS: KeepHistoryPolicy[] = ['forever', '30-days', '7-days'];

export const DEFAULT_GENERATION_CONFIG: GenerationConfig = {
  qualityMode: 'balanced',
  outputSampleRate: '48 kHz',
  bitDepth: '24 bit',
  channels: 'Stereo',
  exportFormat: 'WAV',
  keepHistory: 'forever',
  autoExportOnComplete: false,
};

export const MOCK_ARTIFACTS: Artifact[] = [
  {
    id: '1',
    title: 'Cybernetic Whirr_v1',
    type: 'SFX',
    duration: '00:04.2s',
    heights: [4, 8, 10, 6, 12, 4, 9, 7, 5, 8, 11, 6, 4, 7, 10, 5, 3, 6, 9, 4],
    createdAt: new Date(0).toISOString(),
    prompt: 'Legacy mock artifact',
    sourceType: 'text',
    previewMetadata: {
      barCount: 20,
      hasWaveform: true,
      outputClass: 'Sound Effects',
      languageModel: 'Unknown',
      acousticStyle: 'Unknown',
      hasVisualConditioning: false,
      qualityMode: 'balanced',
    },
    generationConfig: DEFAULT_GENERATION_CONFIG,
    runtimeMode: 'live',
    inputSnapshot: {
      requestedAt: new Date(0).toISOString(),
    },
  },
  {
    id: '2',
    title: 'Ambient Void_Deep',
    type: 'Song',
    duration: '01:30.0s',
    heights: [],
    createdAt: new Date(0).toISOString(),
    prompt: 'Legacy mock artifact',
    sourceType: 'text',
    previewMetadata: {
      barCount: 0,
      hasWaveform: false,
      outputClass: 'Song',
      languageModel: 'Unknown',
      acousticStyle: 'Unknown',
      hasVisualConditioning: false,
      qualityMode: 'balanced',
    },
    generationConfig: DEFAULT_GENERATION_CONFIG,
    runtimeMode: 'live',
    inputSnapshot: {
      requestedAt: new Date(0).toISOString(),
    },
  },
];

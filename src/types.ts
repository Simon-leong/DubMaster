/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export type View = 'home' | 'workspace' | 'processing' | 'history';

export type SourceType = 'video' | 'image' | 'video+image' | 'text';
export type QualityMode = 'fast' | 'balanced' | 'high-quality';
export type OutputSampleRate = '44.1 kHz' | '48 kHz' | '96 kHz';
export type BitDepth = '16 bit' | '24 bit' | '32 bit';
export type ChannelMode = 'Mono' | 'Stereo' | '5.1 Surround';
export type ExportFormat = 'WAV' | 'FLAC' | 'MP3';
export type KeepHistoryPolicy = 'forever' | '30-days' | '7-days';
export type RuntimeMode = 'live' | 'demo';
export type NoticeTone = 'info' | 'success' | 'warning' | 'error';

export interface GenerationConfig {
  qualityMode: QualityMode;
  outputSampleRate: OutputSampleRate;
  bitDepth: BitDepth;
  channels: ChannelMode;
  exportFormat: ExportFormat;
  keepHistory: KeepHistoryPolicy;
  autoExportOnComplete: boolean;
}

export interface PreviewMetadata {
  barCount: number;
  hasWaveform: boolean;
  outputClass: string;
  languageModel: string;
  acousticStyle: string;
  hasVisualConditioning: boolean;
  qualityMode: QualityMode;
}

export interface InputSnapshot {
  videoFileName?: string;
  imageFileName?: string;
  requestedAt: string;
}

export interface ExportInfo {
  url?: string;
  lastExportedAt?: string;
  format?: ExportFormat;
}

export interface Artifact {
  id: string;
  title: string;
  type: string;
  duration: string;
  heights: number[];
  createdAt: string;
  prompt: string;
  sourceType: SourceType;
  previewMetadata: PreviewMetadata;
  generationConfig: GenerationConfig;
  runtimeMode: RuntimeMode;
  inputSnapshot: InputSnapshot;
  exportInfo?: ExportInfo;
}

export interface GenerationDraft {
  prompt: string;
  outputClass: string;
  languageModel: string;
  acousticStyle: string;
  duration: number;
  videoFile: File | null;
  imageFile: File | null;
  referenceAudioFile?: File | null;
  speechTargetText?: string;
  config: GenerationConfig;
  requestedAt: string;
}

export interface GenerationPayload {
  prompt: string;
  outputClass: string;
  languageModel: string;
  acousticStyle: string;
  duration: number;
  videoRef?: string;
  imageRef?: string;
  referenceAudioRef?: string;
  speechTargetText?: string;
  videoFileName?: string;
  imageFileName?: string;
  requestedAt: string;
  config: GenerationConfig;
}

export interface GenerationResponse {
  id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  artifact?: Artifact;
  stage?: 'uploading' | 'planning' | 'assigning' | 'synthesizing' | 'mixing' | 'done';
  stageDetail?: string;
}

export interface ActiveGeneration {
  id: string;
  status: GenerationResponse['status'];
  payload: GenerationPayload;
  runtimeMode: RuntimeMode;
  statusMessage?: string;
  stage?: GenerationResponse['stage'];
  stageDetail?: string;
}

export interface AppNotice {
  id: string;
  tone: NoticeTone;
  title: string;
  message: string;
}

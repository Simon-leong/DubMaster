/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Artifact, GenerationConfig, GenerationPayload, GenerationResponse } from '../types';

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : import.meta.env.DEV
      ? 'http://localhost:8000'
      : ''
).replace(/\/$/, '');
const DEFAULT_POLL_INTERVAL_MS = 3000;
const DEFAULT_POLL_TIMEOUT_MS = 600000;

export class ApiError extends Error {
  status?: number;
  path: string;

  constructor(message: string, path: string, status?: number, options?: ErrorOptions) {
    super(message, options);
    this.name = 'ApiError';
    this.path = path;
    this.status = status;
  }
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init?.headers || {}),
      },
    });
  } catch (error) {
    throw new ApiError('Unable to reach the DubMaster backend.', path, undefined, {
      cause: error instanceof Error ? error : undefined,
    });
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;

    try {
      const errorData = await response.json();
      if (typeof errorData?.detail === 'string') {
        message = errorData.detail;
      }
    } catch {
      // Fall back to the default error message when the response is not JSON.
    }

    throw new ApiError(message, path, response.status);
  }

  return response.json() as Promise<T>;
}

/**
 * Uploads a video file to the backend.
 */
export async function uploadVideo(file: File): Promise<{ ref: string }> {
  const formData = new FormData();
  formData.append('file', file);

  return apiRequest<{ ref: string }>('/upload/video', {
    method: 'POST',
    body: formData,
  });
}

/**
 * Uploads an image file to the backend.
 */
export async function uploadImage(file: File): Promise<{ ref: string }> {
  const formData = new FormData();
  formData.append('file', file);

  return apiRequest<{ ref: string }>('/upload/image', {
    method: 'POST',
    body: formData,
  });
}

/**
 * Uploads a reference audio file for voice cloning (CosyVoice).
 */
export async function uploadAudio(file: File): Promise<{ ref: string }> {
  const formData = new FormData();
  formData.append('file', file);

  return apiRequest<{ ref: string }>('/upload/audio', {
    method: 'POST',
    body: formData,
  });
}

/**
 * Initiates a new audio generation job.
 */
export async function createGeneration(payload: GenerationPayload): Promise<GenerationResponse> {
  return apiRequest<GenerationResponse>('/generations', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
}

/**
 * Fetches the list of all generations/artifacts.
 */
export async function getGenerations(): Promise<Artifact[]> {
  return apiRequest<Artifact[]>('/generations');
}

/**
 * Fetches a specific generation by ID.
 */
export async function getGenerationById(id: string): Promise<GenerationResponse> {
  return apiRequest<GenerationResponse>(`/generations/${id}`);
}

/**
 * Exports a generation (e.g., triggers a download or returns a URL).
 */
export async function exportGeneration(id: string, config: Pick<GenerationConfig, 'exportFormat' | 'outputSampleRate' | 'bitDepth' | 'channels'>): Promise<{ url: string }> {
  const params = new URLSearchParams({
    format: config.exportFormat,
    sample_rate: config.outputSampleRate,
    bit_depth: config.bitDepth,
    channels: config.channels,
  });

  return apiRequest<{ url: string }>(`/generations/${id}/export?${params.toString()}`, {
    method: 'POST',
  });
}

/**
 * Returns the preview URL for in-browser playback of a completed generation.
 */
export function getPreviewUrl(id: string): string {
  return `${API_BASE_URL}/generations/${id}/preview`;
}

/**
 * Polls for the status of a generation job.
 */
export async function pollGenerationStatus(
  id: string,
  onStatusUpdate?: (response: GenerationResponse) => void,
): Promise<GenerationResponse> {
  const startedAt = Date.now();

  while (Date.now() - startedAt < DEFAULT_POLL_TIMEOUT_MS) {
    const result = await apiRequest<GenerationResponse>(`/generations/${id}/status`);
    onStatusUpdate?.(result);

    if (result.status === 'completed' || result.status === 'failed') {
      return result;
    }

    await new Promise((resolve) => setTimeout(resolve, DEFAULT_POLL_INTERVAL_MS));
  }

  throw new Error(`Generation ${id} did not complete within ${DEFAULT_POLL_TIMEOUT_MS / 1000} seconds.`);
}

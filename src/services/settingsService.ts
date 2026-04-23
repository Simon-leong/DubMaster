import { DEFAULT_GENERATION_CONFIG } from '../constants';
import { GenerationConfig } from '../types';

const SETTINGS_STORAGE_KEY = 'dubmaster.settings.v1';

function isBrowser() {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

export function loadGenerationSettings(): GenerationConfig {
  if (!isBrowser()) {
    return DEFAULT_GENERATION_CONFIG;
  }

  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) {
      return DEFAULT_GENERATION_CONFIG;
    }

    return {
      ...DEFAULT_GENERATION_CONFIG,
      ...JSON.parse(raw),
    };
  } catch (error) {
    console.error('Failed to load DubMaster settings:', error);
    return DEFAULT_GENERATION_CONFIG;
  }
}

export function saveGenerationSettings(settings: GenerationConfig): GenerationConfig {
  if (isBrowser()) {
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  }

  return settings;
}

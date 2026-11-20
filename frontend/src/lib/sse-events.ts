import type { AskResult } from '@/api/types'

export interface SseStatus {
  type: 'status'
  step?: string
}

export interface SseData extends AskResult {
  type: 'data'
}

export interface SseToken {
  type: 'token'
  text?: string
}

export interface SseDone extends AskResult {
  type: 'done'
}

export interface SseError {
  type: 'error'
  message?: string
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

export function isSseStatus(v: unknown): v is SseStatus {
  return isRecord(v) && v.type === 'status'
}

export function isSseData(v: unknown): v is SseData {
  return isRecord(v) && v.type === 'data'
}

export function isSseToken(v: unknown): v is SseToken {
  return isRecord(v) && v.type === 'token'
}

export function isSseDone(v: unknown): v is SseDone {
  return isRecord(v) && v.type === 'done'
}

export function isSseError(v: unknown): v is SseError {
  return isRecord(v) && v.type === 'error'
}
